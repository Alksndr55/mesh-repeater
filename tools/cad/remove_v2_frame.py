"""Explicit independently reviewed removal of mechanical SH1 only."""
from pathlib import Path
import json
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'design/MeshRepeater2_Power';m=json.loads((p/'model.json').read_text(encoding='utf-8'))
m['parts']=[v for v in m['parts'] if v['ref']!='SH1']
m['board']['shield']['frame_decision']='removed_after_independent_geometry_review';m['board']['shield']['frame_fitted']=False;m['board']['shield']['lid']=False
m['removed_original_mechanical_parts']={'SH1':'90x60 mounting hardware courtyard conflicts. Smaller frame would require component/routing changes and custom fabrication; continuous middle foil retained. EMI equivalence requires measurement.'}
(p/'model.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
b=k.LoadBoard(str(p/'MeshRepeater2_Power.kicad_pcb'))
for f in list(b.GetFootprints()):
 if f.GetReference()=='SH1':b.Remove(f)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(p/'MeshRepeater2_Power.kicad_pcb'),b)
print('Removed only SH1; functional circuit and all tracks preserved.')
