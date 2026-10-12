"""Apply explicitly generated POWER geometry proposals, refill, and prove scope.

Only straight segment geometry and three reviewed generic GND via positions
may change. Failed full DRC or immutable-payload proof restores original
PCB and project bytes. No schematic/model/footprint edits are performed.
"""
from pathlib import Path
import argparse, hashlib, json, math, subprocess, sys
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from sync_v2_native_metadata import parse

ROOT=Path(__file__).resolve().parents[2]
A=ROOT/'audit/routing_geometry_2026_10_12'
P=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb'
PRO=P.with_suffix('.kicad_pro')
KEEP=[]
MOVE={
    'abef7171-4628-40af-a869-996e360c8c00':([75,13],[74.5,13]),
    '5c0dd5da-919d-4027-8d11-ff23c080cdf0':([25.5,7.5],[27,7.5]),
    'e2cd119a-835f-4b3b-9f81-32b4b88cae54':([1.55,37],[1.5,37.5]),
}
def sha(data):return hashlib.sha256(data).hexdigest()
def uid(t):return str(t.m_Uuid.AsString())
def xy(p):return [round(k.ToMM(p.x),6),round(k.ToMM(p.y),6)]
def vec(p):return k.VECTOR2I(int(round(p[0]*1e6)),int(round(p[1]*1e6)))
def static(tree):
    def strip(node):
        if not isinstance(node,list):return node
        if node and node[0] in ['segment','arc','filled_polygon','fill_segments']:return None
        if node and node[0]=='via':
            u=next(n[1].strip('"') for n in node if isinstance(n,list) and n and n[0]=='uuid')
            return [strip(n) for n in node if not(isinstance(n,list) and n and n[0]=='at' and u in MOVE)]
        return [x for n in node if (x:=strip(n)) is not None]
    # SaveBoard may re-order independent objects; retain every token in them.
    result=strip(tree)
    return [result[0]]+sorted(result[1:],key=lambda n:json.dumps(n,separators=(',',':')))
def metrics(board):
    tracks=[t for t in board.GetTracks() if not isinstance(t,k.PCB_VIA)]
    vias=[t for t in board.GetTracks() if isinstance(t,k.PCB_VIA)]
    bad=[]
    for t in tracks:
        a,z=t.GetStart(),t.GetEnd();dx,dy=abs(z.x-a.x),abs(z.y-a.y)
        # One-nanometre source quantisation (KiCad FromMM legacy truncation).
        if not(dx<=1 or dy<=1 or abs(dx-dy)<=1):bad.append(uid(t))
    return {'segments':len(tracks),'total_segment_length_mm':sum(k.ToMM(t.GetLength()) for t in tracks),'vias':len(vias),'GND_vias':sum(t.GetNetname()=='GND' for t in vias),'non_0_45_90_UUIDs':bad}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--proposal',default=str(A/'POWER_proposals.json'));ap.add_argument('--move-ground',action='store_true');ap.add_argument('--round',default='1');args=ap.parse_args()
    proposal=json.loads(Path(args.proposal).read_text(encoding='utf-8'));original=P.read_bytes();pro=PRO.read_bytes();beforetree=static(parse(original.decode('utf-8')))
    assert proposal['source_sha256']==sha(original),'Source changed since dry-run'
    board=k.LoadBoard(str(P));KEEP.append(board);before=metrics(board)
    allitems={uid(t):t for t in board.GetTracks()};moves=[];changes=[]
    try:
        if args.move_ground:
            for u,(old,new) in MOVE.items():
                t=allitems[u];assert isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND'
                assert math.dist(xy(t.GetPosition()),old)<1e-6
                t.SetPosition(vec(new));moves.append({'uuid':u,'before_mm':old,'after_mm':new,'diameter_F_Cu_mm':k.ToMM(t.GetWidth(k.F_Cu)),'drill_mm':k.ToMM(t.GetDrill())})
        nets={n.GetNetname():n for n in board.GetNetInfo().NetsByNetcode().values()}
        for c in proposal['proposals']:
            old=[allitems[u] for u in c['old_UUIDs']]
            assert all(t.GetNetname()==c['net'] and board.GetLayerName(t.GetLayer())==c['layer'] and abs(k.ToMM(t.GetWidth())-c['width_mm'])<1e-6 for t in old)
            layer=old[0].GetLayer();width=old[0].GetWidth();locked=old[0].IsLocked()
            for t in old:board.Remove(t);KEEP.append(t)
            newids=[]
            for a,z in zip(c['after_path_mm'],c['after_path_mm'][1:]):
                t=k.PCB_TRACK(board);t.SetStart(vec(a));t.SetEnd(vec(z));t.SetLayer(layer);t.SetWidth(width);t.SetNet(nets[c['net']]);t.SetLocked(locked);board.Add(t);newids.append(uid(t))
            changes.append(dict(c,new_UUIDs=newids))
        k.SaveBoard(str(P),board)
        # Restore project settings before the DRC if KiCad ever wrote them.
        if PRO.read_bytes()!=pro:PRO.write_bytes(pro)
        report=A/('POWER_strict_drc_round'+args.round+'.json')
        cmd=['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--all-track-errors','--severity-all','--schematic-parity','--format','json','--refill-zones','--save-board','-o',str(report),str(P)]
        run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        (A/('POWER_drc_console_round'+args.round+'.txt')).write_text(run.stdout,encoding='utf-8')
        if PRO.read_bytes()!=pro:PRO.write_bytes(pro)
        drc=json.loads(report.read_text(encoding='utf-8'))
        counts={q:len(drc.get(q,[])) for q in ['violations','unconnected_items','schematic_parity','ignored_checks']}
        if run.returncode!=0 or any(counts.values()):raise AssertionError('Native DRC rejected '+json.dumps(counts))
        afterbytes=P.read_bytes();immutable=static(parse(afterbytes.decode('utf-8')))
        if immutable!=beforetree:
            (A/('POWER_immutable_before_round'+args.round+'.json')).write_text(json.dumps(beforetree),encoding='utf-8')
            (A/('POWER_immutable_after_round'+args.round+'.json')).write_text(json.dumps(immutable),encoding='utf-8')
            raise AssertionError('Non-track, non-GND-via immutable PCB payload differs')
        final=k.LoadBoard(str(P));KEEP.append(final);after=metrics(final);assert not after['non_0_45_90_UUIDs']
        proof={'status':'BOARD_ROUND_ACCEPTED_STRICT_DRC_ZERO','before_sha256':sha(original),'after_sha256':sha(afterbytes),'before':before,'after':after,'changes':changes,'ground_moves':moves,'DRC':{'path':str(report.relative_to(ROOT)).replace('\\','/'),'sha256':sha(report.read_bytes()),'counts':counts},'immutable_scope':{'unchanged_payload_except_segments_GND_via_at_and_zone_fill':True,'footprints_fields_3D_pads_nets_drawings_keepouts_settings_unchanged':True,'kicad_pro_bytes_unchanged':PRO.read_bytes()==pro,'kicad_pro_sha256':sha(pro)},'manufacturing_or_EMI_physical_tests_performed':False}
    except BaseException as exc:
        P.write_bytes(original);PRO.write_bytes(pro)
        proof={'status':'REJECTED_RESTORED_SOURCE_BYTES','error':repr(exc),'source_sha256':sha(original),'proposals':len(proposal['proposals'])}
        (A/('POWER_round'+args.round+'_result.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise
    (A/('POWER_round'+args.round+'_result.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':proof['status'],'before':before,'after':after,'DRC':counts,'ground_moves':len(moves),'sha256':proof['after_sha256']}),flush=True)
if __name__=='__main__':main()
