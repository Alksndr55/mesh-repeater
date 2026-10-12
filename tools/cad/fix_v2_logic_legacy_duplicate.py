"""Remove only the independently identified inherited MCU_RESET duplicate."""
from finish_v2_markings import ROOT,k
from sync_v2_native_metadata import parse
from fix_v2_power_final_tracks import tracks,without_tracks,sha
import json,subprocess
KEEP=[]
def main():
 pcb=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
 out=ROOT/'audit/ina219_and_vertical_2026_10_12/final_track_patch';out.mkdir(parents=True,exist_ok=True)
 initial=pcb.read_bytes();tree=parse(initial.decode('utf8'));original=tracks(tree)
 keeper='1e5d9fbc-082f-4639-bfed-8ac84e6480a1';removed='53096325-e1f2-42fc-a163-5be4e0247dd1'
 assert keeper in original and removed in original
 geometry=lambda node:[q for q in node if not(isinstance(q,list)and q and q[0]=='uuid')]
 assert geometry(original[keeper])==geometry(original[removed]),'Segments must be exact duplicates'
 project=pcb.with_suffix('.kicad_pro');project_initial=project.read_bytes()
 (out/'before_logic.kicad_pcb').write_bytes(initial)
 b=k.LoadBoard(str(pcb));KEEP.append(b)
 t=next(t for t in b.GetTracks()if t.m_Uuid.AsString()==removed)
 assert t.GetNetname().endswith('MCU_RESET') and t.GetLayer()==k.B_Cu and t.GetWidth()==250000
 assert sorted([(t.GetStart().x,t.GetStart().y),(t.GetEnd().x,t.GetEnd().y)])==[(34200000,37700000),(34300000,37700000)]
 b.Remove(t)
 try:
  assert pcb.read_bytes()==initial,'Concurrent native mutation'
  k.SaveBoard(str(pcb),b)
  if project.read_bytes()!=project_initial:project.write_bytes(project_initial)
  final=pcb.read_bytes();after=parse(final.decode('utf8'))
  expected={id:node for id,node in original.items()if id!=removed}
  assert tracks(after)==expected,'Unexpected track mutation'
  assert without_tracks(after)==without_tracks(tree),'Unexpected non-track mutation'
  drcpath=out/'LOGIC_strict_drc.json'
  run=subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--schematic-parity','-o',str(drcpath),str(pcb)],capture_output=True,text=True,encoding='utf8',errors='replace')
  (out/'logic_drc_console.txt').write_text(run.stdout+run.stderr,encoding='utf8')
  drc=json.loads(drcpath.read_text(encoding='utf8'));counts={name:len(drc.get(name,[]))for name in ['violations','unconnected_items','schematic_parity']}
  assert run.returncode==0 and not any(counts.values()),('Strict DRC failed',run.returncode,counts)
  proof={'status':'ONLY_INHERITED_EXACT_LOGIC_DUPLICATE_REMOVED','source_pcb_sha256':sha(initial),'final_pcb_sha256':sha(final),'retained_uuid':keeper,'removed_uuid':removed,'retained_segment':original[keeper],'same_exact_copper_union':True,'all_other_track_attributes_and_uuid_preserved':True,'all_non_segment_native_tokens_exactly_unchanged':True,'strict_drc':counts,'drc_exit_code':run.returncode,'saved_no_refill':True}
  (out/'logic_proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(proof),flush=True)
 except BaseException:
  pcb.write_bytes(initial);project.write_bytes(project_initial);raise
if __name__=='__main__':main()
