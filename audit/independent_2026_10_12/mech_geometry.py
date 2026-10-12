import FreeCAD as App, Part, json, hashlib, math
from pathlib import Path
root=Path.cwd(); out=root/'audit/independent_2026_10_12'; r={}
def bbox(s):
 b=s.BoundBox; return [round(v,7) for v in (b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax)]
def info(s):
 return {'bbox':bbox(s),'solids':len(s.Solids)}
for board in ['Power','Logic','Shield']:
 p=root/f'output/{board.upper()}/MeshRepeater2_{board}.step'
 s=Part.Shape();s.read(str(p));rr={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),**info(s),'solids':[info(x) for x in s.Solids]};r[board]=rr
 print(board, info(s))
p=root/'docs/mechanics/MeshRepeater2_assembly.FCStd'; doc=App.openDocument(str(p)); r['assembly']={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'objects':{o.Label:info(o.Shape) for o in doc.Objects if hasattr(o,'Shape')}}
boards={x:doc.getObject(x+'_native_PCB_export').Shape for x in ['POWER','SHIELD','LOGIC']}
r['pairwise']={};
for a,b in [('POWER','SHIELD'),('LOGIC','SHIELD')]:
 ba=boards[a].BoundBox; bb=boards[b].BoundBox; r['pairwise'][a+'-'+b]={'envelope_vertical_gap':max(bb.ZMin-ba.ZMax,ba.ZMin-bb.ZMax), 'disjoint_vertical_envelopes':max(bb.ZMin-ba.ZMax,ba.ZMin-bb.ZMax)>0}
 print(a,b,r['pairwise'][a+'-'+b])
r['models']={}
for p in (root/'design/MeshRepeater2_Logic/3dmodels').glob('*.step'):
 if any(x in p.name for x in ['DS1022','DS1013','SW_TE','JST_','XH_','NiceNano','SMA','DS1027']):
  s=Part.Shape();s.read(str(p));r['models'][p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),**info(s),'solids':[info(x) for x in s.Solids]};print(p.name,info(s))
(out/'mechanics.geometry.json').write_text(json.dumps(r,indent=2),encoding='utf8')


