"""Read-only FreeCAD/OCC validity of the existing full LOGIC STEP export."""
from pathlib import Path
import hashlib,json,time
import FreeCAD as App
import Part
ROOT=Path(__file__).resolve().parents[2]
path=ROOT/'output/LOGIC/MeshRepeater2_Logic.step'
digest=hashlib.sha256(path.read_bytes()).hexdigest();started=time.monotonic()
s=Part.Shape();s.read(str(path))
valid=s.isValid()
invalid=[i for i,x in enumerate(s.Solids) if not x.isValid()]
bb=s.BoundBox
result={'input':str(path.relative_to(ROOT)),'sha256':digest,'FreeCAD_version':App.Version(),'method':'Part.Shape.read of the exact full STEP; OCC BRep validity of compound and every exported solid. This checks delivered shapes, not fidelity of skipped source contours.','valid_compound':valid,'exported_solid_count':len(s.Solids),'invalid_solid_indices':invalid,'bbox_mm':[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax],'source_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==digest,'elapsed_seconds':time.monotonic()-started}
assert result['source_unchanged']
(Path(__file__).parent/'step_diagnosis_brep.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
