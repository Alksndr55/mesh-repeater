import FreeCAD,Part,json,math
from pathlib import Path
root=Path.cwd();r={}
def bbox(s):
 b=s.BoundBox;return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
d=FreeCAD.openDocument(str(root/'docs/mechanics/MeshRepeater2_assembly.FCStd'));s=d.getObject('SHIELD_native_PCB_export').Shape
r['shield_solids']=[{'bbox':bbox(o),'volume':o.Volume,'faces':len(o.Faces)} for o in s.Solids]
r['all_assembly_bbox']=bbox(Part.makeCompound([o.Shape for o in d.Objects if hasattr(o,'Shape')]))
r['hardware_clearance']=[]
for name,z,length in [('POWER',1.52,18),('LOGIC',22.04,15)]:
 s=d.getObject(name+'_native_PCB_export').Shape
 for n,(x,y) in enumerate([(3.5,-3.5),(86.5,-3.5),(3.5,-56.5),(86.5,-56.5)]):
  h=Part.makeCylinder(5.5/math.sqrt(3),length,FreeCAD.Vector(x,y,z)); nearest=[]
  for si,solid in enumerate(s.Solids):
   b=solid.BoundBox
   if name=='POWER' and b.ZMax<=1.67:continue
   if name=='LOGIC' and b.ZMin>=37.39:continue
   hb=h.BoundBox;sep=max(hb.XMin-b.XMax,b.XMin-hb.XMax,hb.YMin-b.YMax,b.YMin-hb.YMax,0)
   if sep<2:nearest.append({'distance':h.distToShape(solid)[0],'solid':si,'bbox':bbox(solid)})
  r['hardware_clearance'].append({'board':name,'corner':n+1,'nearest':min(nearest,key=lambda a:a['distance']) if nearest else None,'lower_bound_if_none':2})
  print(name,n+1,r['hardware_clearance'][-1])
(root/'audit/independent_2026_10_12/mechanics.fit.json').write_text(json.dumps(r,indent=2),encoding='utf8')
