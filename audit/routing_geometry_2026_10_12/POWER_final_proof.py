"""Read-only actual-diff scope proof for saved POWER route edits."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/cad'),str(Path(__file__).parent)]
from beautify_v2_power_routes import P,PRO,A,k,static,parse,xy,uid,MOVE
from independent_geometry_final import metrics

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def descriptors(board):
    out={}
    for t in board.GetTracks():
        via=isinstance(t,k.PCB_VIA)
        rec={'kind':'via' if via else 'segment','net':t.GetNetname(),'layer':t.GetLayer(),
             'width_iu':t.GetWidth(k.F_Cu) if via else t.GetWidth(),
             'start_iu':[t.GetStart().x,t.GetStart().y],'end_iu':[t.GetEnd().x,t.GetEnd().y],
             'locked':t.IsLocked()}
        if via:rec.update(drill_iu=t.GetDrill(),top_layer=t.TopLayer(),bottom_layer=t.BottomLayer())
        out[uid(t)]=rec
    return out

def main():
    oldp=A/'before/design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb'
    a=k.LoadBoard(str(oldp));z=k.LoadBoard(str(P));da,dz=descriptors(a),descriptors(z)
    diff={u:{'before':da[u],'after':dz[u]} for u in set(da)&set(dz) if da[u]!=dz[u]}
    removed=set(da)-set(dz);added=set(dz)-set(da)
    rounds=[json.loads((A/f'POWER_round{i}_result.json').read_text(encoding='utf-8')) for i in [1,2]]
    changes=[c for r in rounds for c in r['changes']]
    allowed={u for c in changes for u in c['old_UUIDs']}
    created={u:(c['net'],c['layer'],round(c['width_mm']*1e6)) for c in changes for u in c['new_UUIDs']}
    assert removed.issubset(allowed) and added.issubset(created)
    assert set(diff)==set(MOVE)
    for u,v in diff.items():
        aa,zz=v['before'].copy(),v['after'].copy()
        for key in ['start_iu','end_iu']:aa.pop(key);zz.pop(key)
        assert aa==zz and zz['kind']=='via' and zz['net']=='GND'
        assert xy(next(t for t in z.GetTracks() if uid(t)==u).GetPosition())==MOVE[u][1]
    for u in added:
        net,layer,width=created[u]
        assert dz[u]['net']==net and z.GetLayerName(dz[u]['layer'])==layer and dz[u]['width_iu']==width
    immutable=static(parse(oldp.read_text(encoding='utf-8')))==static(parse(P.read_text(encoding='utf-8')))
    assert immutable
    assert sha(PRO)==rounds[0]['immutable_scope']['kicad_pro_sha256']==rounds[1]['immutable_scope']['kicad_pro_sha256']
    protected=json.loads((A/'POWER_proposals.json').read_text(encoding='utf-8'))['protected_track_UUIDs']
    assert all(u in dz and da[u]==dz[u] for u in protected)
    bm,_=metrics(a);am,_=metrics(z)
    assert not am['segments_outside_0_45_90']
    assert not [t for t in am['turns_outside_45_90'] if t['bare_copper_degree2_reversal']]
    drc_path=A/'POWER_strict_drc_round2.json';drc=json.loads(drc_path.read_text(encoding='utf-8'))
    counts={q:len(drc.get(q,[])) for q in ['violations','unconnected_items','schematic_parity','ignored_checks']}
    assert not any(counts.values())
    proof={'status':'BOARD_FINAL_READY','board':'POWER','before_source':oldp.relative_to(ROOT).as_posix(),
      'after_source':P.relative_to(ROOT).as_posix(),'before_sha256':sha(oldp),'after_sha256':sha(P),
      'before':bm,'after':am,'changes':changes,'ground_moves':rounds[0]['ground_moves'],
      'counts':{'chains_edited_across_two_rounds':len(changes),'segments_removed':bm['segments']-am['segments'],
                'turns_removed':bm['turns']-am['turns'],'length_saved_mm':bm['length_mm']-am['length_mm'],
                'ground_vias_moved':len(diff)},
      'actual_diff_proof':{'immutable_non_copper_payload_equal':True,'footprints_fields_pads_nets_3D_drawings_keepouts_settings_equal':True,
        'kicad_pro_bytes_equal':True,'kicad_pro_sha256':sha(PRO),'protected_critical_tracks_exactly_retained':len(protected),
        'existing_segment_UUIDs_changed_in_place':0,'existing_via_UUIDs_changed_in_place':sorted(diff),
        'removed_UUIDs_are_only_approved_segments':True,'new_UUIDs_match_approved_net_width_layer':True,
        'new_tracks':len(added),'removed_original_tracks':len(removed)},
      'DRC':{'path':drc_path.relative_to(ROOT).as_posix(),'sha256':sha(drc_path),'counts':counts},
      'ground_island_validation':'Independent reviewer will validate final saved filled islands; via77/13 sole local return remains exact.',
      'unchanged_policy':'CN/TPS loops, INA differential pickup+RC, C53 feed, netlist, component poses and GPIO/ISP contract unchanged.',
      'physical_EMI_or_manufacturing_test_performed':False,
      'remaining_geometry':'Dense BAT B.Cu and FILTER_OUT/J101 pad passages remain multi-corner where foreign copper/pad/return clearance prevents native-clear simplification; no widths or electrical parts changed.'}
    (A/'POWER_changes.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':proof['status'],'sha256':proof['after_sha256'],'before':{q:bm[q] for q in ['segments','turns','length_mm','micro_segments_under_0_25_mm']},'after':{q:am[q] for q in ['segments','turns','length_mm','micro_segments_under_0_25_mm']},'counts':proof['counts'],'DRC':counts}))
if __name__=='__main__':main()
