"""Independent, read-only extraction from saved KiCad 10 PCBs; never SaveBoard."""
from pathlib import Path
import pcbnew as k
import json, math, hashlib, heapq
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
def mm(p): return [round(k.ToMM(p.x),6),round(k.ToMM(p.y),6)]
def uid(o): return str(o.m_Uuid.AsString())
def chain(c): return [mm(c.CPoint(i)) for i in range(c.PointCount())]
def polys(p): return [{'shell':chain(p.COutline(i)), 'holes':[chain(p.CHole(i,j)) for j in range(p.HoleCount(i))]} for i in range(p.OutlineCount())]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def optional_mm(x):return None if x is None else k.ToMM(x)
def description(b,o):
    base={'uuid':uid(o),'net':o.GetNetname(),'net_code':o.GetNetCode()}
    if isinstance(o,k.PAD):
        base.update(kind='pad',ref=o.GetParentFootprint().GetReference(),pin=o.GetNumber(),at=mm(o.GetPosition()),size=mm(o.GetSize()),drill=mm(o.GetDrillSize()),shape=int(o.GetShape()),angle=o.GetOrientationDegrees(),layers=[b.GetLayerName(l) for l in [k.F_Cu,k.B_Cu] if o.IsOnLayer(l)],connection=int(o.GetLocalZoneConnection()),thermal_gap_mm=optional_mm(o.GetLocalThermalGapOverride()),thermal_spoke_mm=optional_mm(o.GetLocalThermalSpokeWidthOverride()))
    elif isinstance(o,k.PCB_VIA): base.update(kind='via',at=mm(o.GetPosition()),drill_mm=k.ToMM(o.GetDrill()),diameter_mm=k.ToMM(o.GetWidth(k.F_Cu)),layers=[b.GetLayerName(l) for l in [k.F_Cu,k.B_Cu] if o.IsOnLayer(l)])
    else: base.update(kind='track',start=mm(o.GetStart()),end=mm(o.GetEnd()),length_mm=k.ToMM(o.GetLength()),width_mm=k.ToMM(o.GetWidth()),layer=b.GetLayerName(o.GetLayer()))
    return base
def load(name,path):
    b=k.LoadBoard(str(path)); conn=b.GetConnectivity(); model_path=path.parent/'model.json'
    model=json.loads(model_path.read_text(encoding='utf8')) if model_path.exists() else None
    logicmap={}
    fps={f.GetReference():f for f in b.GetFootprints()}
    if model:
        for part in model['parts']:
            for p in fps[part['ref']].Pads():
                logical=part['nets'].get(p.GetNumber())
                if logical is not None: logicmap[p.GetNetCode()]=logical
    allitems={uid(o):o for o in b.GetTracks()}
    for f in fps.values():
        for p in f.Pads(): allitems[uid(p)]=p
    desc={u:description(b,o) for u,o in allitems.items()}
    for d in desc.values():d['logical_net']=logicmap.get(d['net_code'],d['net'])
    edges=defaultdict(set)
    for u,o in allitems.items():
        for nb in list(conn.GetConnectedPads(o))+list(conn.GetConnectedTracks(o)):
            v=uid(nb)
            if v in allitems and o.GetNetCode()==nb.GetNetCode():edges[u].add(v);edges[v].add(u)
    zones=[]
    for z in b.Zones():
        zd={'uuid':uid(z),'name':z.GetZoneName(),'net':z.GetNetname(),'logical_net':logicmap.get(z.GetNetCode(),z.GetNetname()),'rule_area':z.GetIsRuleArea(),'layers':[b.GetLayerName(l) for l in [k.F_Cu,k.B_Cu] if z.IsOnLayer(l)],'outline':polys(z.Outline())}
        if not z.GetIsRuleArea():
            zd.update(min_thickness_mm=k.ToMM(z.GetMinThickness()),clearance_mm=k.ToMM(z.GetLocalClearance()),thermal_gap_mm=k.ToMM(z.GetThermalReliefGap()),thermal_spoke_mm=k.ToMM(z.GetThermalReliefSpokeWidth()),connection=int(z.GetPadConnection()),fills={b.GetLayerName(l):polys(z.GetFilledPolysList(l)) for l in [k.F_Cu,k.B_Cu] if z.HasFilledPolysForLayer(l)})
        zones.append(zd)
    # Build real same-layer copper union from fills AND GND tracks/pads/vias.
    ground={}; layers=[k.F_Cu,k.B_Cu] if b.GetCopperLayerCount()>1 else [k.F_Cu]
    for l in layers:
        cu=k.SHAPE_POLY_SET()
        for z in b.Zones():
            if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.HasFilledPolysForLayer(l):cu.BooleanAdd(z.GetFilledPolysList(l))
        for o in allitems.values():
            if o.GetNetname()!='GND' or not o.IsOnLayer(l): continue
            if isinstance(o,k.PAD):cu.BooleanAdd(o.GetEffectivePolygon(l))
            else:
                s=k.SHAPE_POLY_SET();o.TransformShapeToPolygon(s,l,0,1000,k.ERROR_OUTSIDE);cu.BooleanAdd(s)
        ground[l]=cu
    result={'name':name,'path':str(path.relative_to(ROOT)),'sha256':sha(path),'unconnected':conn.GetUnconnectedCount(False),'copper_layers':b.GetCopperLayerCount(),'thickness_mm':k.ToMM(b.GetDesignSettings().GetBoardThickness()),'items':desc,'edges':{u:sorted(v) for u,v in edges.items()},'zones':zones,'GND_full_copper':{b.GetLayerName(l):polys(p) for l,p in ground.items()},'footprints':{r:{'at':mm(f.GetPosition()),'angle':f.GetOrientationDegrees(),'value':f.GetValue(),'footprint':str(f.GetFPID().GetLibItemName())} for r,f in fps.items()}}
    # Separate native copper outline islands, connected across plated through items.
    islands={}
    for l,cu in ground.items():
        for n in range(cu.OutlineCount()):
            ps=k.SHAPE_POLY_SET();ps.AddOutline(cu.COutline(n))
            for h in range(cu.HoleCount(n)): ps.AddHole(cu.CHole(n,h),0)
            islands[(l,n)]=ps
    gedge=defaultdict(set)
    touch={}
    for u,o in allitems.items():
        if o.GetNetname()!='GND':continue
        touched=[]
        for key,ps in islands.items():
            if o.IsOnLayer(key[0]) and ps.Contains(o.GetPosition()):touched.append(key)
        # A drilled PAD / through VIA contributes conductive barrel; SMD does not.
        if isinstance(o,k.PCB_VIA) or isinstance(o,k.PAD) and o.GetDrillSize().x>0:
            for a in touched:
                for c in touched:gedge[a].add(c)
        touch[u]=touched
    remain=set(islands); components=[]; key_to_component={}
    while remain:
        first=next(iter(remain));seen={first};q=[first]
        while q:
            at=q.pop()
            for nb in gedge[at]:
                if nb not in seen:seen.add(nb);q.append(nb)
        remain-=seen;idx=len(components)
        for key in seen:key_to_component[key]=idx
        components.append({'islands':[{'layer':b.GetLayerName(l),'index':n,'area_mm2':islands[(l,n)].Area()/1e12} for l,n in sorted(seen)]})
    result['GND_physical_components']=components
    result['GND_item_components']={u:sorted({key_to_component[t] for t in ts}) for u,ts in touch.items()}
    # Independently sample opposite-layer reference at 0.05 mm along EACH signal track.
    refs=[]
    for u,o in allitems.items():
        if not isinstance(o,k.PCB_TRACK) or isinstance(o,k.PCB_VIA) or o.GetNetname()=='GND':continue
        l=k.B_Cu if o.GetLayer()==k.F_Cu else k.F_Cu
        if l not in ground:continue
        a,e=o.GetStart(),o.GetEnd();count=max(1,math.ceil(k.ToMM(o.GetLength())/.05));missing=[];edge_dist=[]
        for i in range(count+1):
            p=k.VECTOR2I(round(a.x+(e.x-a.x)*i/count),round(a.y+(e.y-a.y)*i/count))
            if not ground[l].Contains(p):missing.append(i)
            else:edge_dist.append(k.ToMM(ground[l].Distance(p)))
        spans=[]
        for i in missing:
            if spans and i==spans[-1][1]+1:spans[-1][1]=i
            else:spans.append([i,i])
        spans=[{'length_mm':(j-i)/count*k.ToMM(o.GetLength()),'start':[k.ToMM(a.x+(e.x-a.x)*i/count),k.ToMM(a.y+(e.y-a.y)*i/count)],'end':[k.ToMM(a.x+(e.x-a.x)*j/count),k.ToMM(a.y+(e.y-a.y)*j/count)]} for i,j in spans]
        refs.append({'uuid':u,'logical_net':desc[u]['logical_net'],'reference_layer':b.GetLayerName(l),'length_mm':k.ToMM(o.GetLength()),'sample_count':count+1,'uncovered_fraction':len(missing)/(count+1),'missing_spans':spans})
    result['opposite_ground_samples']=refs
    return b,result
def main():
    paths={'POWER':ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb','LOGIC':ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb','SHIELD':ROOT/'design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pcb','BASELINE':ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pcb'}
    hashes={str(p.relative_to(ROOT)):sha(p) for p in paths.values()};results={};held=[]
    for name,p in paths.items():
        print('Reading '+name,flush=True);b,r=load(name,p);held.append(b);results[name]=r
        print(name+' items='+str(len(r['items']))+' GND components='+str(len(r['GND_physical_components'])),flush=True)
    result={'method':'saved native KiCad 10 pcbnew; filled copper union + actual tracks, pads, vias; plated through items connect per-layer ground outline components; no fill, SaveBoard, DRC or CAD mutation','input_hashes':hashes,'inputs_unchanged':all(sha(ROOT/p)==h for p,h in hashes.items()),'boards':results}
    destination=OUT/'routing_native.json';destination.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(destination,flush=True)
if __name__=='__main__':main()
