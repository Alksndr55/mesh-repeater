"""Controlled negative DRC experiment on a disposable copy, never native CAD."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
native=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(native); b=k.LoadBoard(str(native)); net=next(p.GetNetCode() for f in b.GetFootprints() if f.GetReference()=='M1' for p in f.Pads() if p.GetNumber()=='21')
probe_dir=OUT/'reviewer_rf_negative'
probe_dir.mkdir(exist_ok=True)
probe=probe_dir/'reviewer_RF_negative_probe.kicad_pcb'
for ext in ('.kicad_pro','.kicad_dru'):
 source=native.with_suffix(ext); assert source.is_file(),source
 shutil.copyfile(source,probe.with_suffix(ext))
table=native.parent/'fp-lib-table'
assert table.is_file()
(probe_dir/'fp-lib-table').write_text(table.read_text(encoding='utf-8').replace('${KIPRJMOD}',native.parent.as_posix()),encoding='utf-8')
t=k.PCB_TRACK(b); t.SetNetCode(net);t.SetLayer(k.B_Cu);t.SetWidth(k.FromMM(.25));t.SetStart(k.VECTOR2I(k.FromMM(37.4),k.FromMM(8.6)));t.SetEnd(k.VECTOR2I(k.FromMM(49.2),k.FromMM(8.6)));b.Add(t);track_uuid=str(t.m_Uuid.AsString());k.SaveBoard(str(probe),b)
cli=Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe');drc=OUT/'reviewer_RF_negative_drc.json'
run=subprocess.run([str(cli),'pcb','drc','--format','json','--severity-all','--all-track-errors','-o',str(drc),str(probe)],capture_output=True,text=True)
data=json.loads(drc.read_text(encoding='utf-8'))
matches=[v for v in data.get('violations',[]) if v.get('type') in {'items_not_allowed','disallowed_items'} and 'RF opposite layer permits GND and RF only' in v.get('description','') and any(item.get('uuid')==track_uuid for item in v.get('items',[]))]
record={'native_input_sha256':before,'native_unchanged':sha(native)==before,'probe_not_deliverable':True,'probe_file':str(probe.relative_to(ROOT)),'added_track_uuid':track_uuid,'controlled_geometry':{'netcode':net,'start':[37.4,8.6],'end':[49.2,8.6],'width_mm':.25,'layer':'B.Cu'},'rule_input_sha256':sha(native.with_suffix('.kicad_dru')),'pro_input_sha256':sha(native.with_suffix('.kicad_pro')),'library_context':'Original fp-lib-table copied with KIPRJMOD rebased to unchanged native library; avoids unrelated relocated-library warnings.','DRC_exit_code':run.returncode,'disallowed_items_for_controlled_segment':matches,'all_violation_types':[v.get('type') for v in data.get('violations',[])],'stdout':run.stdout,'stderr':run.stderr,'status':'PASS' if matches and sha(native)==before else 'FAIL'}
(OUT/'reviewer_RF_negative.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record,ensure_ascii=False));assert record['status']=='PASS'
