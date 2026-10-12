"""Fresh FreeCAD measurements independent of the correction author's reports."""
from pathlib import Path
import hashlib, json, subprocess
import FreeCAD as App, Part
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'audit/fixes_2026_10_12'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def box(s):
 b=s.BoundBox
 return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
report={'reviewer':'fresh independent FreeCAD STEP read and Git baseline footprint comparison','date':'2026-10-12','switch_models':[],'footprints':[]}
for name in ('Power','Logic'):
 folder=ROOT/'design'/('MeshRepeater2_'+name)
 p=folder/'3dmodels/SW_TE_1825027_2_Side.step'
 shape=Part.read(str(p)); bb=box(shape)
 assert shape.isValid() and len(shape.Solids)>0
 assert abs((bb[3]-bb[0])-8.41)<1e-6
 report['switch_models'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'valid':True,'solids':len(shape.Solids),'bbox_mm':bb,'bracket_width_mm':bb[3]-bb[0]})
 for fp in (folder/'Meshcore.pretty').glob('SW_TE_1825027_2_Side*.kicad_mod'):
  rel=str(fp.relative_to(ROOT)).replace('\\','/')
  baseline=subprocess.run(['git','cat-file','blob','HEAD:'+rel],cwd=ROOT,check=True,capture_output=True).stdout
  assert baseline==fp.read_bytes(),rel
  report['footprints'].append({'path':rel,'unchanged_from_published_baseline':True,'sha256':sha(fp),'comparison':'Entire file byte-identical, covering pads, courtyard, Fab and model offset/rotation/scale.'})
assert report['switch_models'][0]['sha256']==report['switch_models'][1]['sha256']
mate=ROOT/'docs/mechanics/Connfly_DS1071_SCB01x4_Mated_Envelope.step'
shape=Part.read(str(mate)); bb=box(shape); dims=[bb[i+3]-bb[i] for i in range(3)]
assert shape.isValid() and all(abs(a-b)<1e-6 for a,b in zip(dims,[14.25,10.41,2.79]))
report['mate_model']={'path':str(mate.relative_to(ROOT)),'sha256':sha(mate),'valid':True,'bbox_mm':bb,'dimensions_mm':dims,'matches_manufacturer_maximum_housing_envelope':True,'measured_mating_depth':False,'mating_qualified':False}
report['M-02']='PASS_MODEL_ENVELOPE_AND_UNCHANGED_FOOTPRINTS'
report['source_dimensions_visual_check']='TE C-1825027 rev H sheet: bracket 8.41 mm, mounting centre pitch 7.01 mm, terminals 4.50 mm, terminal drill0.99 mm, bracket drill1.30 mm at y2.49 mm. Connfly DS1071 rev B: female 10.16×2.54×14.00 ±0.25 mm.'
(OUT/'reviewer_models.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'M-02':report['M-02'],'SW_width':report['switch_models'][0]['bracket_width_mm'],'footprints_unchanged':len(report['footprints']),'mate_dims':dims}))
