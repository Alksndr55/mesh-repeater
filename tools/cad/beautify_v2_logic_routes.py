"""Conservative LOGIC-only octilinear shortcuts and reviewed free GND stitches.

No footprint, pin, net, field, 3D model, power star branch or RF geometry edits.
Native copper contacts and keepouts bracket every proposed local shortcut.
Finally refill, strict saved-board DRC and non-routing S-expression invariance.
"""
from pathlib import Path
import collections, hashlib, json, math, subprocess
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from sync_v2_native_metadata import parse, first_difference

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'audit/routing_geometry_2026_10_12'
PCB = ROOT / 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
PRO = PCB.with_suffix('.kicad_pro')
CLI = 'C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
PROTECTED = {'GND', 'SYS_3V3', 'FILTER_OUT', 'RADIO_3V3', 'ANT_RF', 'ANT_SMA'}
U6_LOOP_IDS = {'4b25abcd-a663-4a52-b97d-9870c2df6f17', '9d19b25c-92ad-4bf8-8434-8eb319fc2db3',
               '9a572254-8c8f-409a-8312-3b628d194a43', '75d4b218-ad30-4005-954d-00562a80e552',
               '7ac1cb1d-4ebf-4110-b0e1-361ef6be3c41', '5cc4a7ae-b41f-4b6a-be77-ee512f9bc4d8',
               '5e825d43-b9e4-4082-935e-f10ddd59f788'}
HELD = []

def sha(data): return hashlib.sha256(data).hexdigest()
def uid(o): return o.m_Uuid.AsString()
def xy(p): return tuple(round(k.ToMM(v), 6) for v in (p.x, p.y))
def vec(p): return k.VECTOR2I(round(p[0]*1000000), round(p[1]*1000000))
def width(o): return k.ToMM(o.GetWidth(k.F_Cu) if isinstance(o, k.PCB_VIA) else o.GetWidth())
def protected(o): return o.GetNetname().lstrip('/') in PROTECTED

def polygon(o, layer, clearance=0):
    if isinstance(o, k.PAD): return o.GetEffectivePolygon(layer)
    p = k.SHAPE_POLY_SET()
    o.TransformShapeToPolygon(p, layer, k.FromMM(clearance), 1000, k.ERROR_OUTSIDE)
    return p

def all_objects(b):
    return list(b.GetTracks()) + [p for f in b.GetFootprints() for p in f.Pads()]

def cache(b):
    result = []
    for o in all_objects(b):
        for layer in (k.F_Cu, k.B_Cu):
            if not o.IsOnLayer(layer): continue
            bb = o.GetBoundingBox()
            bounds = [k.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())]
            result.append((o, layer, polygon(o, layer), bounds))
    return result

def segment(b, a, z, w, net, layer):
    t = k.PCB_TRACK(b); HELD.append(t)
    t.SetStart(vec(a)); t.SetEnd(vec(z)); t.SetWidth(k.FromMM(w))
    t.SetLayer(layer); t.SetNet(net)
    return t

def candidate_clear(b, points, w, net, layer, obstacles):
    for a, z in zip(points, points[1:]):
        t = segment(b, a, z, w, net, layer)
        inflated = polygon(t, layer, .2)
        margin = w / 2 + .201
        box = [min(a[0],z[0])-margin, min(a[1],z[1])-margin,
               max(a[0],z[0])+margin, max(a[1],z[1])+margin]
        for o, ly, p, bb in obstacles:
            if ly != layer or o.GetNetCode() == net.GetNetCode(): continue
            if box[2]<bb[0] or box[0]>bb[2] or box[3]<bb[1] or box[1]>bb[3]: continue
            if inflated.Collide(p, 0): return False
        actual = polygon(t, layer)
        for zone in b.Zones():
            if zone.GetIsRuleArea() and zone.IsOnLayer(layer) and (
                zone.GetDoNotAllowTracks() or zone.GetZoneName() == 'RF_GROUND_GUARD'):
                if actual.Collide(zone.Outline(), 0): return False
    return True

def chains(b, split_width=True):
    tracks = [t for t in b.GetTracks() if not isinstance(t, k.PCB_VIA)]
    adjacency = collections.defaultdict(list)
    for t in tracks:
        for p in (xy(t.GetStart()), xy(t.GetEnd())):
            adjacency[(t.GetNetCode(), t.GetLayer(), p)].append(t)
    anchors = {(o.GetNetCode(),ly,xy(o.GetPosition())) for o in all_objects(b)
               if isinstance(o,(k.PAD,k.PCB_VIA)) for ly in (k.F_Cu,k.B_Cu) if o.IsOnLayer(ly)}
    def terminal(key):
        ts = adjacency[key]
        return len(ts) != 2 or key in anchors or (split_width and len({t.GetWidth() for t in ts}) != 1)
    seen = set(); result = []
    for initial in tracks:
        if uid(initial) in seen: continue
        ends = [(initial.GetNetCode(),initial.GetLayer(),xy(initial.GetStart())),
                (initial.GetNetCode(),initial.GetLayer(),xy(initial.GetEnd()))]
        at = next((p for p in ends if terminal(p)),ends[0]); points=[at[2]]; group=[]; t=initial
        while uid(t) not in seen:
            seen.add(uid(t)); group.append(t)
            z=xy(t.GetEnd()) if xy(t.GetStart()) == at[2] else xy(t.GetStart()); points.append(z)
            nxt=(t.GetNetCode(),t.GetLayer(),z)
            if terminal(nxt): break
            other=next(o for o in adjacency[nxt] if uid(o)!=uid(t))
            if uid(other) in seen: break
            at=nxt; t=other
        result.append((group,points))
    return result

def alternatives(a,z):
    dx=z[0]-a[0]; dy=z[1]-a[1]; ax=abs(dx); ay=abs(dy); sx=1 if dx>=0 else -1; sy=1 if dy>=0 else -1
    if min(ax,ay,abs(ax-ay)) < .00001: return [[a,z]]
    mids=[]
    if ax>=ay: mids.extend([(z[0]-sx*ay,a[1]),(a[0]+sx*ay,z[1])])
    else: mids.extend([(a[0],z[1]-sy*ax),(z[0],a[1]+sy*ax)])
    mids.extend([(a[0],z[1]),(z[0],a[1])])
    return [[a,tuple(round(v,6) for v in m),z] for m in mids]

def contact_preserved(b, old, points, net, layer, w):
    oldids={uid(t) for t in old}; original=k.SHAPE_POLY_SET(); replacement=k.SHAPE_POLY_SET()
    for t in old: original.BooleanAdd(polygon(t,layer))
    for a,z in zip(points,points[1:]): replacement.BooleanAdd(polygon(segment(b,a,z,w,net,layer),layer))
    contacts=[]
    for o in all_objects(b):
        if uid(o) in oldids or o.GetNetCode()!=net.GetNetCode() or not o.IsOnLayer(layer): continue
        p=polygon(o,layer)
        if original.Collide(p,0):
            contacts.append(uid(o))
            if not replacement.Collide(p,0): return False,contacts
    return True,contacts

def smooth(b, phase):
    changes=[]
    print('Smoothing '+phase,flush=True)
    for group,points in chains(b):
        if len(group)<3 or protected(group[0]): continue
        layer=group[0].GetLayer(); net=group[0].GetNet(); w=width(group[0])
        obstacles=cache(b); prefix=[0]
        for a,z in zip(points,points[1:]): prefix.append(prefix[-1]+math.dist(a,z))
        best=[None]*len(points); best[0]=(0,0,[])
        for i in range(len(points)-1):
            if best[i] is None: continue
            for j in range(i+1,len(points)):
                options=[[points[i],points[j]]] if j==i+1 else alternatives(points[i],points[j])
                for pp in options:
                    cost=sum(math.dist(a,z) for a,z in zip(pp,pp[1:]))
                    if cost>prefix[j]-prefix[i]+.000003: continue
                    if j>i+1 and (len(pp)-1>=j-i or not candidate_clear(b,pp,w,net,layer,obstacles)): continue
                    score=(best[i][0]+len(pp)-1,best[i][1]+cost)
                    if best[j] is None or score<best[j][:2]: best[j]=(score[0],score[1],best[i][2]+pp[1:])
        if best[-1] is None or best[-1][0]>=len(group): continue
        revised=[points[0]]+best[-1][2]
        okay,contacts=contact_preserved(b,group,revised,net,layer,w)
        if not okay: continue
        records=[{'uuid':uid(t),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width_mm':width(t)} for t in group]
        locked=all(t.IsLocked() for t in group)
        for t in group: b.Remove(t); HELD.append(t)
        added=[]
        for a,z in zip(revised,revised[1:]):
            t=segment(b,a,z,w,net,layer); t.SetLocked(locked); b.Add(t); added.append(uid(t))
        changes.append({'phase':phase,'net':net.GetNetname(),'layer':b.GetLayerName(layer),'width_mm':w,
                        'before':records,'before_points':points,'after_points':revised,'added_uuids':added,
                        'contacts_preserved':contacts,'length_before_mm':prefix[-1],'length_after_mm':best[-1][1]})
    print('Accepted '+str(len(changes))+' local chains in '+phase,flush=True)
    return changes

def shorten_named_u6_loop(b):
    lookup={uid(t):t for t in b.GetTracks()}; assert U6_LOOP_IDS.issubset(lookup)
    old=[lookup[u] for u in sorted(U6_LOOP_IDS)]; assert all(t.GetNetname()=='SYS_3V3' and width(t)==.4 and t.GetLayer()==k.F_Cu for t in old)
    pp=[(43.1,35.5),(41.9,35.5),(41.5,35.9)];net=old[0].GetNet()
    assert candidate_clear(b,pp,.4,net,k.F_Cu,cache(b))
    okay,contacts=contact_preserved(b,old,pp,net,k.F_Cu,.4); assert okay and len(contacts)==4
    original_length=sum(k.ToMM(t.GetLength()) for t in old)
    records=[{'uuid':uid(t),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width_mm':width(t)} for t in old]
    for t in old: b.Remove(t); HELD.append(t)
    added=[]
    for a,z in zip(pp,pp[1:]):
        t=segment(b,a,z,.4,net,k.F_Cu);t.SetLocked(True);b.Add(t);added.append(uid(t))
    return {'phase':'named_U6_feed_only','net':'SYS_3V3','layer':'F.Cu','width_mm':.4,'before':records,
            'after_points':pp,'added_uuids':added,'contacts_preserved':contacts,
            'length_before_mm':original_length,'length_after_mm':sum(math.dist(a,z) for a,z in zip(pp,pp[1:])),
            'authorization':'Only the identified local seven-segment U6 feed; four actual external native copper contacts preserved; other MCU/FB1 star tracks immutable.'}

def move_ground(b):
    review=json.loads((OUT/'GND_before_candidates.json').read_text(encoding='utf8'))
    proposals=next(x for x in review['boards'] if x['board']=='Logic')['candidates']
    byid={uid(t):t for t in b.GetTracks()}; changes=[]; skipped=[]
    for proposal in proposals:
        via=byid[proposal['uuid']]; assert isinstance(via,k.PCB_VIA) and via.GetNetname()=='GND'
        old=xy(via.GetPosition()); choices=[proposal['recommended']]+proposal['alternatives']
        if old==(50.73,14.22): choices=[x for x in choices if x['at_mm']==[50.5,13.5]]+choices
        chosen=None
        for choice in choices:
            at=tuple(choice['at_mm']); via.SetPosition(vec(at)); clear=True
            for o in all_objects(b):
                if uid(o)==uid(via): continue
                if isinstance(o,k.PCB_VIA) and math.dist(at,xy(o.GetPosition()))<.8: clear=False; break
                if o.GetNetname()=='GND': continue
                margin=.4 if isinstance(o,k.PCB_TRACK) and not isinstance(o,k.PCB_VIA) else .2
                for ly in (k.F_Cu,k.B_Cu):
                    if o.IsOnLayer(ly) and polygon(via,ly,margin).Collide(polygon(o,ly),0): clear=False; break
                if not clear: break
            if clear:
                for z in b.Zones():
                    if z.GetIsRuleArea() and (z.GetDoNotAllowVias() or z.GetZoneName()=='RF_GROUND_GUARD'):
                        if any(z.IsOnLayer(ly) and polygon(via,ly).Collide(z.Outline(),0) for ly in (k.F_Cu,k.B_Cu)): clear=False; break
            if clear: chosen=at; break
        if chosen is None: via.SetPosition(vec(old)); skipped.append({'uuid':uid(via),'from':old,'reason':'new native geometry clearance'})
        else: changes.append({'uuid':uid(via),'from':old,'to':chosen,'diameter_mm':width(via),'drill_mm':k.ToMM(via.GetDrillValue()),'net':via.GetNetname()})
    return changes,skipped

def metrics(b):
    ts=[t for t in b.GetTracks() if not isinstance(t,k.PCB_VIA)]; vs=[t for t in b.GetTracks() if isinstance(t,k.PCB_VIA)]; gs=[v for v in vs if v.GetNetname()=='GND']
    turns=collinear=0
    for group,p in chains(b,False):
        for a,c,z in zip(p,p[1:],p[2:]):
            cross=(c[0]-a[0])*(z[1]-c[1])-(c[1]-a[1])*(z[0]-c[0])
            if abs(cross)>1e-7: turns+=1
            else: collinear+=1
    return {'tracks':len(ts),'vias':len(vs),'ground_vias':len(gs),'turns':turns,'collinear_joins':collinear,
            'length_mm':sum(k.ToMM(t.GetLength()) for t in ts),'segments_under_0_25_mm':sum(k.ToMM(t.GetLength())<.25 for t in ts),
            'bad_angle_count':sum(min(abs(xy(t.GetEnd())[0]-xy(t.GetStart())[0]),abs(xy(t.GetEnd())[1]-xy(t.GetStart())[1]),abs(abs(xy(t.GetEnd())[0]-xy(t.GetStart())[0])-abs(xy(t.GetEnd())[1]-xy(t.GetStart())[1])))>.00001 for t in ts),
            'ground_grid_0_5mm_aligned':sum(all(abs(x*2-round(x*2))<.00001 for x in xy(v.GetPosition())) for v in gs)}

def invariant(node):
    if not isinstance(node,list): return node
    if node and node[0] in ('segment','filled_polygon','filled_areas_thickness'): return None
    if node and node[0]=='via': return [invariant(x) for x in node if not(isinstance(x,list) and x and x[0]=='at')]
    return [p for x in node if (p:=invariant(x)) is not None]

def main():
    OUT.mkdir(parents=True,exist_ok=True); initial=PCB.read_bytes(); pro=PRO.read_bytes()
    b=k.LoadBoard(str(PCB)); HELD.append(b); before=metrics(b)
    immutable={uid(t):(xy(t.GetStart()),xy(t.GetEnd()),t.GetLayer(),width(t),t.GetNetname()) for t in b.GetTracks() if protected(t) and not isinstance(t,k.PCB_VIA) and uid(t) not in U6_LOOP_IDS}
    nonground_vias={uid(v):(xy(v.GetPosition()),width(v),v.GetDrillValue(),v.GetNetname()) for v in b.GetTracks() if isinstance(v,k.PCB_VIA) and v.GetNetname()!='GND'}
    changes=smooth(b,'initial'); moves,skipped=move_ground(b); changes+=smooth(b,'after_ground_alignment')
    u6=shorten_named_u6_loop(b);changes.append(u6);u6_new=set(u6['added_uuids'])
    report={'board':str(PCB.relative_to(ROOT)),'before_sha256':sha(initial),'metrics_before':before,'changes':changes,'ground_moves':moves,'ground_skipped':skipped}
    try:
        k.ZONE_FILLER(b).Fill(b.Zones()); k.SaveBoard(str(PCB),b)
        if PRO.read_bytes()!=pro: PRO.write_bytes(pro)
        difference=first_difference(invariant(parse(initial.decode('utf8'))),invariant(parse(PCB.read_text(encoding='utf8'))))
        if difference: raise AssertionError('Non-routing invariant: '+repr(difference))
        saved=k.LoadBoard(str(PCB)); HELD.append(saved)
        assert immutable=={uid(t):(xy(t.GetStart()),xy(t.GetEnd()),t.GetLayer(),width(t),t.GetNetname()) for t in saved.GetTracks() if protected(t) and not isinstance(t,k.PCB_VIA) and uid(t) not in u6_new}
        assert nonground_vias=={uid(v):(xy(v.GetPosition()),width(v),v.GetDrillValue(),v.GetNetname()) for v in saved.GetTracks() if isinstance(v,k.PCB_VIA) and v.GetNetname()!='GND'}
        drc=OUT/'LOGIC_strict_drc.json'
        cp=subprocess.run([CLI,'pcb','drc','--all-track-errors','--severity-all','--schematic-parity','--exit-code-violations','--format','json','-o',str(drc),str(PCB)],capture_output=True,text=True)
        report['drc_console']=cp.stdout+cp.stderr
        report['drc_exit_code']=cp.returncode
        data=json.loads(drc.read_text(encoding='utf8')); counts={key:len(data.get(key,[])) for key in ('violations','unconnected_items','schematic_parity','ignored_checks')}
        assert cp.returncode==0,('DRC exit code',cp.returncode)
        assert not any(counts.values()),counts
        assert PRO.read_bytes()==pro
        report.update(status='BOARD_FINAL_READY',final_sha256=sha(PCB.read_bytes()),metrics_after=metrics(saved),strict_drc_counts=counts,
                      proof={'nonrouting_s_expression_equal':True,'protected_RF_nonlocal_power_GND_tracks_unchanged':True,'named_U6_feed_four_external_contacts_preserved':True,'non_GND_vias_unchanged':True,'project_settings_bytes_unchanged':True,'footprints_fields_pinmap_models_keepouts_unchanged':True})
    except Exception as e:
        PCB.write_bytes(initial); PRO.write_bytes(pro); report.update(status='ROLLED_BACK',error=repr(e)); raise
    finally:
        (OUT/'LOGIC_changes.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({key:report[key] for key in ('status','final_sha256','metrics_before','metrics_after','strict_drc_counts')},indent=2),flush=True)

if __name__=='__main__': main()
