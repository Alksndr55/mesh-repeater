"""Read-only stitch geometry inventory; never saves native boards."""
from pathlib import Path
import sys, math, json, hashlib, collections
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
def xy(v):return (round(k.ToMM(v.x),6),round(k.ToMM(v.y),6))
def uid(o):return o.m_Uuid.AsString()
def pointseg(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];l=dx*dx+dy*dy
 f=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l)) if l else 0
 return math.dist(p,(a[0]+f*dx,a[1]+f*dy))
def analyze(name):
 path=ROOT/f'design/MeshRepeater2_{name}/MeshRepeater2_{name}.kicad_pcb'
 b=k.LoadBoard(str(path));tracks=list(b.GetTracks());pads=[(f.GetReference(),p) for f in b.GetFootprints() for p in f.Pads()]
 vias=[t for t in tracks if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND']
 rows=[]
 for v in vias:
  pos=xy(v.GetPosition());rad=k.ToMM(v.GetWidth(k.F_Cu))/2
  gtracks=[];ng=[]
  for t in tracks:
   if isinstance(t,k.PCB_VIA):continue
   d=pointseg(pos,xy(t.GetStart()),xy(t.GetEnd()))-k.ToMM(t.GetWidth())/2-rad
   if t.GetNetname()=='GND' and d<=0.00001:gtracks.append({'uuid':uid(t),'layer':k.LayerName(t.GetLayer()),'start':xy(t.GetStart()),'end':xy(t.GetEnd()),'width':k.ToMM(t.GetWidth())})
   if t.GetNetname()!='GND':ng.append((d,t.GetNetname(),k.LayerName(t.GetLayer()),uid(t)))
  nearpads=sorted((math.dist(pos,xy(p.GetPosition())),r,p.GetNumber(),p.GetNetname()) for r,p in pads)[:5]
  islands=[]
  for z in b.Zones():
   if z.GetNetname()!='GND' or z.GetIsRuleArea():continue
   layer=z.GetLayer();poly=k.SHAPE_POLY_SET(z.GetFilledPolysList(layer));poly.Unfracture()
   for i in range(poly.OutlineCount()):
    q=k.SHAPE_POLY_SET();q.AddOutline(poly.COutline(i))
    for h in range(poly.HoleCount(i)):q.AddHole(poly.CHole(i,h),0)
    if q.Contains(v.GetPosition()):islands.append({'zone':z.GetZoneName(),'layer':k.LayerName(layer),'outline':i})
  rows.append({'uuid':uid(v),'at_mm':pos,'diameter_mm':2*rad,'drill_mm':k.ToMM(v.GetDrill()),'ground_tracks':gtracks,'nearest_non_ground_tracks':[{'edge_clearance_mm':round(d,4),'net':n,'layer':l,'uuid':u} for d,n,l,u in sorted(ng)[:5]],'nearest_pads':[{'center_distance_mm':round(d,4),'ref':r,'pad':p,'net':n} for d,r,p,n in nearpads],'filled_islands':islands})
 groups={axis:[{'coord':val,'count':len(ids),'uuids':ids} for val,ids in sorted(collections.defaultdict(list).items())] for axis in []}
 for axis,idx in [('X',0),('Y',1)]:
  d=collections.defaultdict(list)
  for r in rows:d[round(r['at_mm'][idx],3)].append(r['uuid'])
  groups[axis]=[{'coord':val,'count':len(ids),'uuids':ids} for val,ids in sorted(d.items()) if len(ids)>1]
 return {'board':name,'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'ground_via_count':len(rows),'ground_track_attached_count':sum(bool(r['ground_tracks']) for r in rows),'rows':rows,'aligned_groups':groups}
out={'method':'Read-only pcbnew native inventory; explicit via width layer, filled zones unfractured. Pad proximity is advisory, not clearance qualification.','boards':[analyze('Power'),analyze('Logic')]}
p=Path(__file__).with_suffix('.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
for b in out['boards']:
 print(b['board'],b['ground_via_count'],b['ground_track_attached_count'])
 for r in b['rows']:
  print(r['uuid'][:8],r['at_mm'],'track' if r['ground_tracks'] else 'free','islands',','.join(x['zone']+':'+str(x['outline']) for x in r['filled_islands']),'near',r['nearest_pads'][:2],'signal',r['nearest_non_ground_tracks'][:1])
