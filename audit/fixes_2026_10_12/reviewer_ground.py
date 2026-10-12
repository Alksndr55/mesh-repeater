"""Reuse unchanged independent audit geometry extractor, run afresh without writes."""
from pathlib import Path
import hashlib,json,runpy,sys
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew
configure_headless()
module=ROOT/'audit/independent_2026_10_12/routing_native.py'
api=runpy.run_path(str(module),run_name='independent_frozen_geometry_helpers')
path=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
before=hashlib.sha256(path.read_bytes()).hexdigest()
held,record=api['load']('LOGIC',path)
out={'input_sha256':before,'method':'Independent auditor frozen read-only copper union/connected-islands algorithm, freshly evaluated after fixes. Native same-layer GND fills/tracks/pads/vias + only plated barrels bridge layers; no SaveBoard/no refill.','extractor_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),'physical_ground_components':record['GND_physical_components'],'component_count':len(record['GND_physical_components']),'unconnected_connectivity':record['unconnected'],'native_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==before}
assert out['component_count']==1 and out['native_unchanged']
(OUT/'reviewer_ground.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,ensure_ascii=False))
