"""Read-only candidate routing plan. Never saves a native PCB."""
from pathlib import Path
import hashlib
import json
import sys
import math
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'cad'))
import complete_v2_routes as router
import pcbnew as k
from audit_v2_routing_engineering import TraceGraph, uid, mm
REMOVED=[]
BOARDS=[]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def desc(b, item):
    if isinstance(item, k.PAD):
        return {'kind':'pad', 'uuid':uid(item), 'ref':item.GetParentFootprint().GetReference(), 'pin':item.GetNumber(), 'at':mm(item.GetPosition())}
    if isinstance(item, k.PCB_VIA):
        return {'kind':'via', 'uuid':uid(item), 'at':mm(item.GetPosition()), 'drill_mm':k.ToMM(item.GetDrill())}
    return {'kind':'track', 'uuid':uid(item), 'start':mm(item.GetStart()), 'end':mm(item.GetEnd()), 'width_mm':k.ToMM(item.GetWidth()), 'layer':b.GetLayerName(item.GetLayer()), 'length_mm':k.ToMM(item.GetLength())}
def pad(b, ref, pin):
    return next(p for f in b.GetFootprints() if f.GetReference()==ref for p in f.Pads() if p.GetNumber()==pin)
def components_after_cut(graph, net, cut):
    ids={a for a,t in graph.items.items() if t.GetNetname()==net} - set(cut)
    out=[]
    while ids:
        at=next(iter(ids)); q=[at]; found={at}
        while q:
            node=q.pop()
            for nb in graph.edges[node]:
                if nb in ids and nb not in found: found.add(nb);q.append(nb)
        ids-=found
        pads=[desc(graph.board,graph.items[n]) for n in found if isinstance(graph.items[n],k.PAD)]
        if pads:out.append({'pads':pads,'track_count':sum(isinstance(graph.items[n],k.PCB_TRACK) for n in found),'retained_UUIDs':sorted(found)})
    return out
def candidate(b, net, start, end, width, label, starts=(0,), ends=(0,), logic=False):
    before={uid(t) for t in b.GetTracks()}
    try:
        info=router.route(b,net,start,end,width,starts,ends,logic=logic)
        info.update({'label':label,'candidate_not_native_DRC_proof':True,'items':[desc(b,t) for t in b.GetTracks() if uid(t) not in before]})
        info['segment_total_length_mm']=sum(t.get('length_mm',0) for t in info['items'])
    except Exception as e:info={'label':label,'failed':repr(e),'start':start,'end':end,'width_mm':width}
    return info

def point_segment(p,a,z):
    dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy
    q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
    return math.dist(p,(a[0]+q*dx,a[1]+q*dy))
def segment_gap(a,z,c,d):
    def cross(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if cross(a,z,c)*cross(a,z,d)<0 and cross(c,d,a)*cross(c,d,z)<0:return 0
    return min(point_segment(a,c,d),point_segment(z,c,d),point_segment(c,a,z),point_segment(d,a,z))
def manual(b,net,label,segments,width=.8):
    hits={}
    for seg in segments:
        layer=k.F_Cu if seg['layer']=='F.Cu' else k.B_Cu
        a,z=seg['start'],seg['end']
        for t in b.GetTracks():
            if not t.IsOnLayer(layer) or t.GetNetname()==net:continue
            tw=k.ToMM(t.GetWidth(layer) if isinstance(t,k.PCB_VIA) else t.GetWidth())
            gap=segment_gap(a,z,mm(t.GetStart()),mm(t.GetEnd()))-(width+tw)/2
            if gap<.225:
                hit=desc(b,t);hit.update({'net':t.GetNetname(),'approx_edge_gap_mm':gap});hits[uid(t)]=hit
    return {'label':label,'net':net,'width_mm':width,'segments':segments,'segment_total_length_mm':sum(math.dist(s['start'],s['end']) for s in segments),'candidate_not_native_DRC_proof':True,'nonmatching_track_conflicts_for_local_rework':list(hits.values()),'pad_clearance_not_proved_by_this_plan':True}

def main():
    audit=json.loads((ROOT/'audit/v2_routing_engineering.json').read_text(encoding='utf-8'))
    files={name:ROOT/'design'/('MeshRepeater2_'+name.title())/('MeshRepeater2_'+name.title()+'.kicad_pcb') for name in ['POWER','LOGIC']}
    hashes={str(p.relative_to(ROOT)):sha(p) for p in files.values()}
    result={'source_sha256':hashes,'native_boards_saved':False,'status':'candidate coordinates; final native DRC and graph audit required'}
    b=k.LoadBoard(str(files['LOGIC']));BOARDS.append(b);g=TraceGraph(b)
    old=audit['boards']['LOGIC'];common=old['MCU_modem_common_SYS_feed']['track_UUIDs']
    # Keep M1->C21->C22 local bulk links; remove only C22->FB1 old tie.
    fbextra=['eb7d2d32-8a09-47f7-9d77-5b31c103ed5a','82a80147-dbc9-45db-94df-65eb53d638a5']
    cut=set(common+fbextra)
    common_vias=old['paths']['J11_to_MCU']['via_UUIDs']
    # Keep the local MCU via: its remaining M1/cap links form the final destination.
    removable_vias=[v for v in common_vias if not any(n not in cut and isinstance(g.items[n],k.PCB_TRACK) for n in g.edges[v])]
    result['SYS']={'common_trunk_remove':[desc(b,g.items[n]) for n in common], 'FB1_old_bulk_tie_remove':[desc(b,g.items[n]) for n in fbextra], 'vias_remove_if_only_cut_neighbors':[desc(b,g.items[n]) for n in removable_vias], 'retained_load_components_after_cut':components_after_cut(g,'SYS_3V3',cut | set(removable_vias))}
    for n in cut | set(removable_vias):b.Remove(g.items[n]);REMOVED.append(g.items[n])
    # Two direct positive-feed branches; each starts on the switched J11 pin.
    start=mm(pad(b,'J11','2').GetPosition())
    def segs(points,layer):return [{'start':a,'end':z,'layer':layer} for a,z in zip(points,points[1:])]
    result['SYS']['candidate_routes']=[
        manual(b,'SYS_3V3','J11_to_MCU_bulk',segs([start,[80.94,30.6],[37.6,30.6],[29.05,22.05],[29.05,13.35]],'B.Cu')+segs([[29.05,13.35],[29.05,12.25]],'F.Cu')),
        manual(b,'SYS_3V3','J11_to_FB1_input',segs([start,[82.04,29.5],[43.8,29.5],[32.65,18.35],[32.65,15.65]],'B.Cu')+segs([[32.65,15.65],[32.65,14.45]],'F.Cu'))]
    result['SYS']['new_vias']=[{'at':[29.05,13.35],'drill_mm':.3,'diameter_mm':.6,'net':'SYS_3V3'},{'at':[32.65,15.65],'drill_mm':.3,'diameter_mm':.6,'net':'SYS_3V3'}]
    result['SYS']['rejected_unassisted_Astar']={'MCU_length_mm':164.855,'FB1_length_mm':169.294,'reason':'Existing signal routing forces excessive detour; reserve direct power corridor and rework only conflicting signal portions.'}
    # Connector-only leaf of the old positive BAT rail. Keep all original cap/control taps.
    b=k.LoadBoard(str(files['POWER']));BOARDS.append(b);g=TraceGraph(b)
    tail=['01c84e0c-0cd3-41d7-a1e4-81448b894bb4','fac57d8d-431b-457b-9a81-6389088ab900','1275f693-e8b8-4794-8aaf-7e969a94f28b','8bd9141c-b57a-44f2-a24a-eafe783ba1eb','eb27aea4-d952-4b3c-80cc-61ffa1c1329a']
    present=[n for n in tail if n in g.items]
    retained=components_after_cut(g,'BAT',present)
    leaf=next(c for c in retained if len(c['pads'])==1 and c['pads'][0]['ref']=='J101' and c['pads'][0]['pin']=='9')
    leaf_items=[n for n in leaf['retained_UUIDs'] if not isinstance(g.items[n],k.PAD)]
    result['BATsense']={'distinct_path_without_main_tracks_exists':audit['boards']['POWER'].get('battery_sense_route_excluding_selected_main_tracks'), 'connector_leaf_remove':[desc(b,g.items[n]) for n in present+leaf_items], 'retained_components_after_cut':retained, 'warning':'Retain C13/C17/R15 and all BAT functional taps; sense path must leave the J8 positive pad separately and have no second contact with main BAT copper.'}
    for n in present:b.Remove(g.items[n]);REMOVED.append(g.items[n])
    result['BATsense']['candidate_route']=manual(b,'BAT','J8_battery_pad_to_cable_9',segs([[22.75,9.3],[22.75,7.35],[24.3,5.8],[74.18,5.8],[75.58,7.2],[75.58,9.7],[74.31,10.97]],'F.Cu'),.25)
    result['BATsense']['candidate_route']['same_net_main_copper_separation_requires_native_geometry_check']=True
    result['RF']=old['RF_to_F_GND_zone_gap_samples']
    result['input_files_unchanged_at_end']=all(sha(ROOT/p)==digest for p,digest in hashes.items())
    out=ROOT/'audit/v2_routing_correction_plan.json';out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'file':str(out),'SYS_routes':[{'label':r['label'],'length':r.get('segment_total_length_mm'),'failed':r.get('failed')} for r in result['SYS']['candidate_routes']],'BATsense_route':result['BATsense']['candidate_route'].get('failed','candidate computed'),'unchanged':result['input_files_unchanged_at_end']},indent=2))
if __name__=='__main__':main()
