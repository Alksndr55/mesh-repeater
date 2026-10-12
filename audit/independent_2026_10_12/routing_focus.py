"""Native RF geometry and saved-snapshot signal route study, read only."""
from pathlib import Path
import pcbnew as k
import json,math,heapq
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
D=json.loads((OUT/'routing_native.json').read_text(encoding='utf8'))
def path(b,start,end):
    items=b['items'];edges=b['edges'];src=[u for u,o in items.items() if o['kind']=='pad' and [o['ref'],o['pin']]==list(start)];dst={u for u,o in items.items() if o['kind']=='pad' and [o['ref'],o['pin']]==list(end)}
    if not src or not dst:return None
    def weight(u):
        o=items[u]
        return o['length_mm'] if o['kind']=='track' else b['thickness_mm'] if o['kind']=='via' else 0
    q=[(0,u) for u in src];dist={u:0 for u in src};prev={};finish=None
    while q:
        cost,u=heapq.heappop(q)
        if cost!=dist[u]:continue
        if u in dst:finish=u;break
        for v in edges.get(u,[]):
            candidate=cost+(weight(u)+weight(v))/2
            if candidate<dist.get(v,math.inf):dist[v]=candidate;prev[v]=u;heapq.heappush(q,(candidate,v))
    if finish is None:return {'start':start,'end':end,'track_only_connected':False}
    nodes=[finish]
    while nodes[-1] in prev:nodes.append(prev[nodes[-1]])
    nodes.reverse();vias=[items[u] for u in nodes if items[u]['kind']=='via'];ts=[items[u] for u in nodes if items[u]['kind']=='track'];nearest=[]
    grounds=[x for x in items.values() if x['logical_net']=='GND' and (x['kind']=='via' or x['kind']=='pad' and x['drill'][0]>0)]
    for v in vias:
        g=min(grounds,key=lambda o:math.dist(o['at'],v['at']));nearest.append({'signal_via_at':v['at'],'nearest_ground_barrel_at':g['at'],'nearest_ground_barrel_center_mm':math.dist(g['at'],v['at']),'ground_item_uuid':g['uuid'],'ground_kind':g['kind'],'ground_ref':g.get('ref'),'ground_pin':g.get('pin')})
    endpoint_dist=math.dist(items[src[0]]['at'],items[finish]['at']);total=sum(t['length_mm'] for t in ts)
    sample={x['uuid']:x for x in b['opposite_ground_samples']}
    missing=sum(t['length_mm']*sample[t['uuid']]['uncovered_fraction'] for t in ts);worst=max((span | {'uuid':t['uuid'],'layer':t['layer'],'reference_layer':sample[t['uuid']]['reference_layer']} for t in ts for span in sample[t['uuid']]['missing_spans']),key=lambda x:x['length_mm'],default=None)
    return {'start':start,'end':end,'track_only_connected':True,'copper_segment_length_mm':total,'via_barrel_length_mm':len(vias)*b['thickness_mm'],'center_distance_mm':endpoint_dist,'detour_factor':total/endpoint_dist if endpoint_dist else 0,'via_count':len(vias),'nearest_return_barrels':nearest,'opposite_GND_uncovered_estimate_mm':missing,'worst_single_track_gap':worst,'route_items':[items[u] for u in nodes]}
def ground(b,l):
    cu=k.SHAPE_POLY_SET()
    for z in b.Zones():
        if not z.GetIsRuleArea() and z.GetNetname()=='GND' and z.HasFilledPolysForLayer(l):cu.BooleanAdd(z.GetFilledPolysList(l))
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname()=='GND' and p.IsOnLayer(l):cu.BooleanAdd(p.GetEffectivePolygon(l))
    for t in b.GetTracks():
        if t.GetNetname()=='GND' and t.IsOnLayer(l):
            poly=k.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,l,0,1000,k.ERROR_OUTSIDE);cu.BooleanAdd(poly)
    return cu
def agm(a,b):
    for _ in range(30):
        a,b=(a+b)/2,math.sqrt(a*b)
        if abs(a-b)<1e-15:return a
    return a
def ellip_ratio(x):
    def K(m):return math.pi/(2*agm(1,math.sqrt(1-m*m)))
    return K(x)/K(math.sqrt(1-x*x))
def cpwg(w,s,h=1.43,er=4.5,t=.035):
    # Ghione/Naldi backed CPW with first order thickness, as scikit-rf source.
    k1=w/(w+2*s);q1=ellip_ratio(k1);k3=math.tanh(math.pi*w/(4*h))/math.tanh(math.pi*(w+2*s)/(4*h));q3=ellip_ratio(k3)
    e=1+q3/(q1+q3)*(er-1);delta=1.25*t/math.pi*(1+math.log(4*math.pi*w/t));ke=k1+(1-k1*k1)*delta/(2*s);qe=ellip_ratio(ke)
    e=e-(.7*(e-1)*t/s)/(q1+.7*t/s)
    return {'Z0_ohm':377/(2*(qe+q3)*math.sqrt(e)),'epsilon_effective':e}
def rf(name):
    path=ROOT/D['boards'][name]['path'];b=k.LoadBoard(str(path));fcu=ground(b,k.F_Cu);bcu=ground(b,k.B_Cu);items=D['boards'][name]['items'];rfids={u for u,t in items.items() if t['logical_net'] in ['ANT_RF','ANT_SMA']};out=[]
    for t in b.GetTracks():
        if str(t.m_Uuid.AsString()) not in rfids or isinstance(t,k.PCB_VIA):continue
        a,z=t.GetStart(),t.GetEnd();dx,dy=z.x-a.x,z.y-a.y;norm=math.hypot(dx,dy);nx,ny=-dy/norm,dx/norm;wid=k.ToMM(t.GetWidth());samples=[]
        for f in [.2,.35,.5,.65,.8]:
            x,y=a.x+dx*f,a.y+dy*f;gaps=[]
            for sign in [-1,1]:
                gap=None
                for j in range(1,501):
                    d=wid/2+j*.01;p=k.VECTOR2I(round(x+nx*sign*k.FromMM(d)),round(y+ny*sign*k.FromMM(d)))
                    if fcu.Contains(p):gap=j*.01;break
                gaps.append(gap)
            samples.append({'at':[k.ToMM(x),k.ToMM(y)],'edge_gaps_left_right_mm':gaps,'B_GND_present':bcu.Contains(k.VECTOR2I(round(x),round(y)))})
        out.append({'uuid':str(t.m_Uuid.AsString()),'net':items[str(t.m_Uuid.AsString())]['logical_net'],'width_mm':wid,'length_mm':k.ToMM(t.GetLength()),'samples':samples})
    return out
def main():
    pairs={'MOSI':(('R24','2'),('M2','14')),'MISO':(('R26','2'),('M1','6')),'SCK':(('R23','2'),('M2','12')),'NSS':(('R25','2'),('M2','15')),'BUSY':(('M2','10'),('M1','7')),'DIO1':(('M2','6'),('M1','2')),'RESET':(('M1','1'),('M2','4')),'RXEN':(('M1','21'),('M2','11'))}
    result={'signal_paths':{n:{label:path(D['boards'][n],*pair) for label,pair in pairs.items()} for n in ['LOGIC','BASELINE']},'RF_cross_sections':{n:rf(n) for n in ['LOGIC','BASELINE']},'ideal_symmetric_grounded_CPW_estimates':{'method':'quasi-static Ghione/Naldi, scikit-rf source, h=1.43mm er=4.5 t=.035mm; infinite symmetric side grounds, solid backside, no mask, pad/bend/NT1 discontinuities; NOT measured or field-solved impedance','source':'https://scikit-rf.readthedocs.io/en/latest/_modules/skrf/media/cpw.html','values':[{'width_mm':w,'gap_mm':s,**cpwg(w,s)} for w in [.6,.8,1.3] for s in [.25,.6]]}}
    pwrpairs={'C1_Q1':(('C1','1'),('Q1','2')),'Q1_D1':(('Q1','3'),('D1','2')),'D1_D2':(('D1','1'),('D2','1')),'D2_C1ground':(('D2','2'),('C1','2')),'L1_R56':(('L1','2'),('R56','1')),'R1_U1BAT':(('R1','2'),('U1','14')),'L1_U1CSP':(('L1','2'),('U1','13')),'TPS_FB':(('U2','4'),('R13','2'))}
    result['POWER_local_paths']={n:{label:path(D['boards'][n],*pair) for label,pair in pwrpairs.items()} for n in ['POWER','BASELINE']}
    for n in ['POWER','LOGIC']:
        b=D['boards'][n];ps=[]
        for u,t in b['items'].items():
            if t['kind']=='pad' and t['ref'] in ['J101','J201'] and t['logical_net']=='GND':ps.append({'ref':t['ref'],'pin':t['pin'],'at':t['at'],'native_copper_components':b['GND_item_components'][u]})
        result[n+'_cable_ground_contacts']=ps
    (OUT/'routing_focus.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'SPI':{n:{label:{key:r[key] for key in ['copper_segment_length_mm','center_distance_mm','detour_factor','via_count','opposite_GND_uncovered_estimate_mm']} for label,r in v.items()} for n,v in result['signal_paths'].items()},'CPWG':result['ideal_symmetric_grounded_CPW_estimates'],'CN':{n:{label:{key:r.get(key) for key in ['copper_segment_length_mm','via_count']} for label,r in v.items()} for n,v in result['POWER_local_paths'].items()}},ensure_ascii=True,indent=2))
if __name__=='__main__':main()
