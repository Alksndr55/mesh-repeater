from pathlib import Path
import sys,json,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless()
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';CLI='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe';held=[];pruned=[]
for it in range(8):
 report=OUT/('routing_native_drc5.json' if it==0 else 'routing_native_final_drc.json');d=json.load(open(report,encoding='utf8'))
 if not d['violations']:break
 if any(v['type']!='track_dangling' or any('GPS_TX_MCU' not in i['description'] for i in v['items']) for v in d['violations']):raise RuntimeError(d['violations'])
 b=k.LoadBoard(str(P));lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
 for v in d['violations']:
  for i in v['items']:
   t=lookup[i['uuid']];b.Remove(t);held.append(t);pruned.append(i)
 k.SaveBoard(str(P),b)
 subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','--refill-zones','--save-board','-o',str(OUT/'routing_native_final_drc.json'),str(P)],check=True)
(OUT/'routing_pruned_twigs.json').write_text(json.dumps(pruned,indent=2),encoding='utf8')
