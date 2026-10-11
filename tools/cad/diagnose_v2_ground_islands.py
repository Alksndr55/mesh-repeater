"""Read-only geometry diagnosis of each filled GND polygon, no SaveBoard."""
from pathlib import Path
import argparse,hashlib,json,math
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
def xy(p):return [k.ToMM(p.x),k.ToMM(p.y)]
def vec(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def bbox(pts):return [min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]
def distance(p,a,z):
 dx,dy=z[0]-a[0],z[1]-a[1];d=dx*dx+dy*dy;q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d)) if d else 0
 return math.dist(p,[a[0]+q*dx,a[1]+q*dy])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();p=a.pcb.resolve();out=a.out.resolve()
 assert p.is_relative_to(ROOT) and out.is_relative_to(ROOT)
 source_sha=hashlib.sha256(p.read_bytes()).hexdigest();b=k.LoadBoard(str(p));objects=[]
 for f in b.GetFootprints():
  for pad in f.Pads():
   if pad.GetNetname()!='GND' or pad.GetAttribute()==k.PAD_ATTRIB_NPTH:continue
   pos=xy(pad.GetPosition());sz=xy(pad.GetSize());samples=[pos]
   for n in range(16):
    t=n*math.pi/8;samples.append([pos[0]+(sz[0]/2-.025)*math.cos(t),pos[1]+(sz[1]/2-.025)*math.sin(t)])
   objects.append(dict(kind='pad',name=f.GetReference()+'.'+pad.GetNumber(),at=pos,layers=[l for l in (k.F_Cu,k.B_Cu) if pad.IsOnLayer(l)],samples=samples,r=max(sz)/2))
 for t in b.GetTracks():
  if t.GetNetname()!='GND':continue
  if isinstance(t,k.PCB_VIA):
   pos=xy(t.GetPosition());r=k.ToMM(t.GetWidth(k.F_Cu))/2;pts=[pos]
   for n in range(16):
    a=n*math.pi/8;pts.append([pos[0]+(r-.025)*math.cos(a),pos[1]+(r-.025)*math.sin(a)])
   objects.append(dict(kind='via',name=t.m_Uuid.AsString(),at=pos,layers=[k.F_Cu,k.B_Cu],samples=pts,r=r))
  else:
   s,e=xy(t.GetStart()),xy(t.GetEnd());N=max(1,math.ceil(math.dist(s,e)/.1));pts=[[s[0]+(e[0]-s[0])*n/N,s[1]+(e[1]-s[1])*n/N] for n in range(N+1)]
   objects.append(dict(kind='track',name=t.m_Uuid.AsString(),at=s,end=e,layers=[t.GetLayer()],samples=pts,r=k.ToMM(t.GetWidth())/2))
 rows=[];allpolys=[]
 for z in b.Zones():
  if z.GetNetname()!='GND' or z.GetIsRuleArea():continue
  layer=z.GetLayer();poly=k.SHAPE_POLY_SET(z.GetFilledPolysList(layer));poly.Unfracture();islands=[]
  for i in range(poly.OutlineCount()):
   chain=poly.COutline(i);pts=[xy(chain.CPoint(n)) for n in range(chain.PointCount())];box=bbox(pts);group=k.SHAPE_POLY_SET();group.AddOutline(chain)
   for h in range(poly.HoleCount(i)):group.AddHole(poly.CHole(i,h),0)
   contacts=[]
   for obj in objects:
    if layer not in obj['layers']:continue
    if any(group.Contains(vec(q)) for q in obj['samples']):contacts.append({n:obj[n] for n in ('kind','name','at')})
   area=abs(chain.Area())/1e12;cx,cy=(box[0]+box[2])/2,(box[1]+box[3])/2
   nearest=[]
   for obj in objects:
    if layer not in obj['layers']:continue
    gap=(distance([cx,cy],obj['at'],obj['end']) if 'end' in obj else math.dist([cx,cy],obj['at']))-obj['r']
    nearest.append((gap,obj))
   row=dict(index=i,area_mm2=area,bbox_mm=box,holes=poly.HoleCount(i),contacts=contacts,nearest_ground_objects=[dict(gap_from_box_center_mm=g,**{n:o[n] for n in ('kind','name','at')}) for g,o in sorted(nearest,key=lambda p:p[0])[:4]],vertices_mm=pts if area<2 else None)
   islands.append(row);allpolys.append((z.GetZoneName(),layer,row,group))
  rows.append(dict(name=z.GetZoneName(),uuid=z.m_Uuid.AsString(),layer=k.LayerName(layer),priority=z.GetAssignedPriority(),islands=islands))
 for zn,layer,row,poly in allpolys:
  row['touching_other_zone_islands']=[dict(zone=zn2,index=row2['index']) for zn2,l2,row2,p2 in allpolys if l2==layer and zn2!=zn and poly.Collide(p2,0)]
 result={'source_sha256':source_sha,'unchanged_source_after':hashlib.sha256(p.read_bytes()).hexdigest()==source_sha,'zones':rows,'contact_method':'filled per-outline geometry including its holes versus samples in actual GND pad/via copper and track centrelines; min=.1mm track sample,16point annulus samples; native polygon Collide at0clearance for adjacent same-layer zone contacts.'}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'sha':source_sha,'zones':[dict(name=z['name'],layer=z['layer'],islands=[dict(index=i['index'],area=i['area_mm2'],bbox=i['bbox_mm'],contacts=len(i['contacts'])) for i in z['islands']]) for z in rows]},ensure_ascii=True))
if __name__=='__main__':main()
