"""Advisory orthogonal stitching moves, read only. Fresh refill+DRC required."""
from pathlib import Path
import json,sys,math,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
D=json.loads((Path(__file__).with_name('GND_before_analysis.json')).read_text(encoding='utf8'))
def xy(v):return k.ToMM(v.x),k.ToMM(v.y)
def vec(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def uid(o):return o.m_Uuid.AsString()
def pointseg(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];l=dx*dx+dy*dy
 f=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l)) if l else 0
 return math.dist(p,(a[0]+f*dx,a[1]+f*dy))
out={'method':{'purpose':'Advisory moves of generic main-plane stitch; no native writes. Vias touching GND tracks, local islands, RF_CPWs or <=1.8 mm from any pad are protected. Already regular main grid and POWER screen fence retained.','step_mm':0.5,'max_move_mm':1.6,'prefer_edge_clearance_mm':0.5,'min_edge_clearance_mm':0.4,'same_filled_F_B_islands_required':True,'sample_disk_radius_mm':0.3,'caveat':'Candidates require simultaneous collision resolution, refill, full DRC and native GND-continuity analysis after changed routes.'},'boards':[]}
for B in D['boards']:
 path=ROOT/B['path'];sha=hashlib.sha256(path.read_bytes()).hexdigest()
 assert sha==B['sha256'],f'{B["board"]} changed before advisory run'
 b=k.LoadBoard(str(path));polys={};tracks=[];vias=[];obstacles=[]
 for z in b.Zones():
  if z.GetNetname()!='GND' or z.GetIsRuleArea():continue
  poly=k.SHAPE_POLY_SET(z.GetFilledPolysList(z.GetLayer()));poly.Unfracture()
  for i in range(poly.OutlineCount()):
   q=k.SHAPE_POLY_SET();q.AddOutline(poly.COutline(i))
   for h in range(poly.HoleCount(i)):q.AddHole(poly.CHole(i,h),0)
   polys[z.GetZoneName(),i]=q
 for t in b.GetTracks():
  if isinstance(t,k.PCB_VIA):vias.append((uid(t),xy(t.GetPosition()),k.ToMM(t.GetWidth(k.F_Cu))/2))
  elif t.GetNetname()!='GND':tracks.append((xy(t.GetStart()),xy(t.GetEnd()),k.ToMM(t.GetWidth())/2))
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.GetNetname()=='GND' and p.GetAttribute()!=k.PAD_ATTRIB_NPTH:continue
   box=p.GetBoundingBox();obstacles.append((k.ToMM(box.GetLeft()),k.ToMM(box.GetTop()),k.ToMM(box.GetRight()),k.ToMM(box.GetBottom())))
 main={('GND_TOP',3),('GND_REFERENCE',2)} if B['board']=='Power' else {('GND_TOP',17),('GND_REFERENCE',10)}
 protected=[];candidates=[];blocked=[];crowded_regular=[]
 for r in B['rows']:
  pos=tuple(r['at_mm']);tags={(g['zone'],g['outline']) for g in r['filled_islands']};reason=[]
  if r['ground_tracks']:reason.append('GND track copper contact')
  if not main<=tags:reason.append('not both main GND filled islands')
  if any(g['zone'].startswith('RF_') for g in r['filled_islands']):reason.append('RF CPW return')
  if min(p['center_distance_mm'] for p in r['nearest_pads'])<=1.8:reason.append('local pad/decoupling vicinity')
  # Screen-fence geometry is already regular. Only move its severely pinched
  # members parallel to the existing row/column; never towards switch nets.
  initial=r['nearest_non_ground_tracks'][0]['edge_clearance_mm']
  on3=all(abs((v-1.5)/3-round((v-1.5)/3))<1e-6 for v in pos)
  fence=B['board']=='Power' and (pos[0] in (7,83) or pos[1] in (13,56))
  if on3 or fence:
   reason.append('already regular 3 mm main grid or 2 mm POWER screen fence')
   if initial<.4 and not any(g['zone'].startswith('RF_') for g in r['filled_islands']):crowded_regular.append({'uuid':r['uuid'],'at_mm':pos,'edge_clearance_mm':initial,'advice':'Keep this row/column; remove route staircase around it or shift entire affected fence row only after its own clearance/continuity proof.'})
  if reason:
   protected.append({'uuid':r['uuid'],'at_mm':pos,'reasons':reason});continue
  offgrid=any(abs(v*2-round(v*2))>1e-4 for v in pos)
  if initial>=.4 and not offgrid:continue
  possibilities=[]
  for dx in range(-3,4):
   for dy in range(-3,4):
    if dx and dy:continue
    q=(round((pos[0]+dx*.5)*2)/2,round((pos[1]+dy*.5)*2)/2)
    dist=math.dist(pos,q)
    if dist<1e-5 or dist>1.6 or not (1.0<=q[0]<=89.0 and 1.0<=q[1]<=59.0):continue
    # Preserve the screen fence's X/Y line, not only global coarse grid.
    if B['board']=='Power' and pos[0] in (7,83) and q[0]!=pos[0]:continue
    if B['board']=='Power' and pos[1] in (13,56) and q[1]!=pos[1]:continue
    rad=r['diameter_mm']/2
    if any(u!=r['uuid'] and math.dist(q,p)<rad+rr+.2-1e-6 for u,p,rr in vias):continue
    if any(x1-rad-.25<=q[0]<=x2+rad+.25 and y1-rad-.25<=q[1]<=y2+rad+.25 for x1,y1,x2,y2 in obstacles):continue
    clearance=min(pointseg(q,a,z)-rr-rad for a,z,rr in tracks)
    if clearance<.4 or (initial<.4 and clearance<initial+.08):continue
    samples=[q]+[(q[0]+rad*math.cos(n*math.pi/8),q[1]+rad*math.sin(n*math.pi/8)) for n in range(16)]
    if not all(polys[tag].Contains(vec(s)) for tag in main for s in samples):continue
    # Maximise corridor width then minimise displacement; favor existing 3-mm
    # grid when equally unobstructed. Exact sample is conservative on fills.
    on3=all(abs((v-1.5)/3-round((v-1.5)/3))<1e-6 for v in q)
    score=(on3,-dist,min(clearance,.7)) if initial>=.4 else (on3,min(clearance,.7),-dist)
    possibilities.append((score,{'at_mm':q,'move_mm':round(dist,4),'edge_clearance_mm':round(clearance,4),'on_3mm_grid':on3}))
  if possibilities:
   alternatives=[q for score,q in sorted(possibilities,key=lambda a:a[0],reverse=True)[:4]]
   candidates.append({'uuid':r['uuid'],'from_mm':pos,'old_edge_clearance_mm':initial,'recommended':alternatives[0],'alternatives':alternatives})
  else:blocked.append({'uuid':r['uuid'],'at_mm':pos,'old_edge_clearance_mm':initial,'reason':'No conservative orthogonal 0.5 mm target preserving filled islands and >=0.35 mm corridor; reroute locally before moving.'})
 # Reserve targets in UUID order so simultaneous moves cannot stack vias.
 selected=[]
 for row in candidates:
  alternatives=[q for q in row['alternatives'] if all(math.dist(q['at_mm'],r['recommended']['at_mm'])>=.8-1e-6 for r in selected)]
  if alternatives:row['recommended']=alternatives[0];row['alternatives']=alternatives;selected.append(row)
  else:blocked.append({'uuid':row['uuid'],'at_mm':row['from_mm'],'old_edge_clearance_mm':row['old_edge_clearance_mm'],'reason':'Target conflicts with another selected move; manual coordinated row needed.'})
 out['boards'].append({'board':B['board'],'sha256':sha,'protected':protected,'candidates':selected,'blocked':blocked,'crowded_already_regular':crowded_regular})
p=Path(__file__).with_suffix('.json');p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
for b in out['boards']:
 print(b['board'],'protected',len(b['protected']),'moves',len(b['candidates']),'blocked',len(b['blocked']))
 for r in b['candidates']:print(r['uuid'],r['from_mm'],'->',r['recommended'])
