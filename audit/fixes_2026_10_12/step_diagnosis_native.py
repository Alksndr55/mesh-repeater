"""Read-only inspection of saved copper contours around KiCad STEP warnings."""
from pathlib import Path
import hashlib,json,sys,math
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
path=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
before=hashlib.sha256(path.read_bytes()).hexdigest()
b=k.LoadBoard(str(path))
targets=[(36.241763,11.878018,36.390318,11.960842),(32.721615,11.520504,32.922606,11.635013)]
def pts(c):return [[k.ToMM(c.CPoint(i).x),k.ToMM(c.CPoint(i).y)] for i in range(c.PointCount())]
def detail(c):
 p=pts(c);xs=[a[0] for a in p];ys=[a[1] for a in p]
 return {'points':p,'bbox_mm':[min(xs),min(ys),max(xs),max(ys)],'area_mm2':abs(c.Area())/1e12,'closed':c.IsClosed()}
rows=[];counts={};nearby=[];clipped=[]
for z in b.Zones():
 if z.GetIsRuleArea():continue
 for layer in (k.F_Cu,k.B_Cu):
  if not z.HasFilledPolysForLayer(layer):continue
  p=k.SHAPE_POLY_SET(z.GetFilledPolysList(layer));p.Unfracture();p.Simplify()
  name=k.LayerName(layer)+':'+z.GetNetname()+':'+z.GetZoneName()
  counts[name]={'outlines':p.OutlineCount(),'holes':sum(p.HoleCount(i) for i in range(p.OutlineCount())),'global_self_intersection_check':'Not used for manufacturing verdict: saved fill uses weakly-simple contour/hole link encoding; local Boolean-clipped planar areas checked separately.'}
  if layer==k.F_Cu:
   for tid,t in enumerate(targets):
    r=k.SHAPE_POLY_SET();c=k.SHAPE_LINE_CHAIN()
    for x,y in [(t[0]-.01,t[1]-.01),(t[2]+.01,t[1]-.01),(t[2]+.01,t[3]+.01),(t[0]-.01,t[3]+.01)]:c.Append(k.VECTOR2I(k.FromMM(x),k.FromMM(y)))
    c.SetClosed(True);r.AddOutline(c)
    q=k.SHAPE_POLY_SET(p);q.BooleanIntersection(r);q.Unfracture()
    regions=[{'outline':detail(q.Outline(i)),'holes':[detail(q.Hole(i,j)) for j in range(q.HoleCount(i))]} for i in range(q.OutlineCount())]
    clipped.append({'target_index':tid,'layer':k.LayerName(layer),'net':z.GetNetname(),'zone':z.GetZoneName(),'zone_uuid':str(z.m_Uuid.AsString()),'clip_margin_mm':.01,'polygon_self_intersecting':q.IsSelfIntersecting(),'regions':regions,'filled_area_mm2':q.Area()/1e12})
  for i in range(p.OutlineCount()):
   cs=[('outline',None,p.Outline(i))]+[('hole',j,p.Hole(i,j)) for j in range(p.HoleCount(i))]
   for kind,j,c in cs:
    r=detail(c);bb=r['bbox_mm']
    for tid,t in enumerate(targets):
     if bb[0]<=t[2]+.01 and bb[2]>=t[0]-.01 and bb[1]<=t[3]+.01 and bb[3]>=t[1]-.01:
      close=max(abs(v-w) for v,w in zip(bb,t))<.05
      if close or r['area_mm2']<.05:
       rows.append({'zone_uuid':z.m_Uuid.AsString(),'net':z.GetNetname(),'layer':k.LayerName(layer),'outline_index':i,'hole_index':j,'kind':kind,'target_index':tid,'bbox_matches_warning':close,**r})
for f in b.GetFootprints():
 for p in f.Pads():
  x,y=k.ToMM(p.GetPosition().x),k.ToMM(p.GetPosition().y)
  if any(math.dist((x,y),((t[0]+t[2])/2,(t[1]+t[3])/2))<2 for t in targets):
   nearby.append({'ref':f.GetReference(),'pin':p.GetNumber(),'net':p.GetNetname(),'at_mm':[x,y],'size_mm':[k.ToMM(p.GetSize().x),k.ToMM(p.GetSize().y)],'layer':k.LayerName(f.GetLayer())})
result={'input':str(path.relative_to(ROOT)),'sha256':before,'native_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==before,'targets_mm':targets,'zone_counts':counts,'matching_native_contours':rows,'nearby_pads':nearby,'clipped_native_filled_area_at_warning_boxes':clipped}
assert result['native_unchanged']
(Path(__file__).parent/'step_diagnosis_native.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='matching_native_contours'},ensure_ascii=False));print(json.dumps([{k:v for k,v in r.items() if k!='points'} for r in rows],ensure_ascii=False))
