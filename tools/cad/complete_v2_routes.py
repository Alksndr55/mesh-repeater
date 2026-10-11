"""Complete only missing connections using 45/90-degree paths; native DRC gates.

The accepted CN/TPS/RF geometry stays locked. This is a candidate router, never
a substitute for checking the finally saved native board.
"""
from pathlib import Path
import argparse, heapq, json, math, subprocess, time
import numpy as np
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
STEP=.1;NX=901;NY=601;CLEAR=.225
def xy(p):return k.ToMM(p.x),k.ToMM(p.y)
def vec(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def route(b,net,start,end,width,starts=(0,),ends=(0,),logic=False,source_points=None,target_points=None):
 blocked=np.zeros((2,NY,NX),dtype=bool);vb=np.zeros((NY,NX),dtype=bool)
 def bounds(box):
  x0=max(0,int(math.floor(box[0]/STEP)));x1=min(NX,int(math.ceil(box[2]/STEP))+1);y0=max(0,int(math.floor(box[1]/STEP)));y1=min(NY,int(math.ceil(box[3]/STEP))+1);return x0,x1,y0,y1
 def rect(arr,box,margin):
  x0,x1,y0,y1=bounds((box[0]-margin,box[1]-margin,box[2]+margin,box[3]+margin))
  if x1>x0 and y1>y0:arr[y0:y1,x0:x1]=True
 def capsule(arr,a,z,r):
  x0,x1,y0,y1=bounds((min(a[0],z[0])-r,min(a[1],z[1])-r,max(a[0],z[0])+r,max(a[1],z[1])+r))
  if x1<=x0 or y1<=y0:return
  yy,xx=np.mgrid[y0:y1,x0:x1]*STEP;dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy;q=np.clip(((xx-a[0])*dx+(yy-a[1])*dy)/den,0,1) if den else 0
  arr[y0:y1,x0:x1] |= (xx-a[0]-q*dx)**2+(yy-a[1]-q*dy)**2 <= r*r
 for f in b.GetFootprints():
  for pd in f.Pads():
   box=pd.GetBoundingBox();bb=tuple(k.ToMM(v) for v in (box.GetLeft(),box.GetTop(),box.GetRight(),box.GetBottom()));npth=pd.GetAttribute()==k.PAD_ATTRIB_NPTH
   size=xy(pd.GetSize());round_pad=pd.GetShape() in (k.PAD_SHAPE_CIRCLE,k.PAD_SHAPE_OVAL) and abs(size[0]-size[1])<.001
   def pad_block(arr,margin):
    if round_pad:capsule(arr,xy(pd.GetPosition()),xy(pd.GetPosition()),size[0]/2+margin)
    else:rect(arr,bb,margin)
   pad_block(vb,.31 if pd.GetNetname()==net else .3+CLEAR)
   if pd.GetNetname()==net and not npth:continue
   for layer,idx in [(k.F_Cu,0),(k.B_Cu,1)]:
    if pd.IsOnLayer(layer) or npth:pad_block(blocked[idx],width/2+CLEAR)
 for t in b.GetTracks():
  if t.GetNetname()==net:continue
  a,z=xy(t.GetStart()),xy(t.GetEnd());r=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth())/2
  for layer,idx in [(k.F_Cu,0),(k.B_Cu,1)]:
   if t.IsOnLayer(layer):capsule(blocked[idx],a,z,r+width/2+CLEAR)
  capsule(vb,a,z,r+.3+CLEAR)
 for arr in [blocked[0],blocked[1],vb]:
  if logic:rect(arr,(12,30.5,24,45.5),.31)
  edge=.3+(.3 if arr is vb else width/2);n=math.ceil(edge/STEP);arr[:n,:]=True;arr[:,:n]=True;arr[-n:,:]=True;arr[:,-n:]=True
 # Rounded coordinates remain within existing copper. There are no arbitrary
 # angled centre-to-grid stubs: every new segment belongs to the octilinear grid.
 s=(round(start[0]/STEP),round(start[1]/STEP));z=(round(end[0]/STEP),round(end[1]/STEP))
 def ident(x,y,l):return (l*NY+y)*NX+x
 def coords(n):return n%NX,(n//NX)%NY,n//(NX*NY)
 source_points=source_points or [(start,l) for l in starts];target_points=target_points or [(end,l) for l in ends]
 def ids(points):
  out=set()
  for at,l in points:
   x,y=round(at[0]/STEP),round(at[1]/STEP)
   if 0<=x<NX and 0<=y<NY and not blocked[l,y,x]:out.add(ident(x,y,l))
  return out
 goals=ids(target_points);sources=ids(source_points)
 if not sources or not goals:raise RuntimeError(('blocked endpoints',net,start,end,starts,ends))
 size=2*NX*NY;dist=np.full(size,np.inf);prev=np.full(size,-1,dtype=np.int32);q=[]
 gx=[coords(n)[0] for n in goals];gy=[coords(n)[1] for n in goals];gx0,gx1,gy0,gy1=min(gx),max(gx),min(gy),max(gy)
 def heur(x,y):
  dx=max(gx0-x,x-gx1,0);dy=max(gy0-y,y-gy1,0);return max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)
 for n in sources:
  dist[n]=0;cx,cy,cl=coords(n);heapq.heappush(q,(heur(cx,cy),0,n))
 visited=0;target=None
 while q:
  _,cost,n=heapq.heappop(q)
  if cost>dist[n]+1e-7:continue
  if n in goals:target=n;break
  visited+=1;x,y,l=coords(n)
  for dx,dy in [(1,0),(0,1),(-1,0),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
   xx,yy=x+dx,y+dy
   if not(0<=xx<NX and 0<=yy<NY) or blocked[l,yy,xx]:continue
   if dx and dy and (blocked[l,y,xx] or blocked[l,yy,x]):continue
   m=ident(xx,yy,l);nc=cost+math.hypot(dx,dy)*(1 if l==0 else 1.20)
   if nc+1e-7<dist[m]:dist[m]=nc;prev[m]=n;heapq.heappush(q,(nc+heur(xx,yy),nc,m))
  if not vb[y,x] and not blocked[1-l,y,x]:
   m=ident(x,y,1-l);nc=cost+90
   if nc+1e-7<dist[m]:dist[m]=nc;prev[m]=n;heapq.heappush(q,(nc+heur(x,y),nc,m))
  if visited>1100000:raise RuntimeError(('search exhausted',net))
 if target is None:raise RuntimeError(('no route',net,start,end,visited))
 path=[];n=target
 while n!=-1:path.append(coords(n));n=int(prev[n])
 path.reverse();segments=[];vias=[];points=[(path[0][0]*STEP,path[0][1]*STEP)];layer=path[0][2];last=None
 for a,c in zip(path,path[1:]):
  if a[2]!=c[2]:
   at=(a[0]*STEP,a[1]*STEP);points.append(at);segments.append((layer,points));vias.append(at);points=[at];layer=c[2];last=None
  else:
   direction=(c[0]-a[0],c[1]-a[1])
   if last is not None and direction!=last:points.append((a[0]*STEP,a[1]*STEP))
   last=direction
 points.append((path[-1][0]*STEP,path[-1][1]*STEP));segments.append((layer,points));ni=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()==net)
 count=0
 for layer,pts in segments:
  for a,z in zip(pts,pts[1:]):
   if math.dist(a,z)<1e-7:continue
   t=k.PCB_TRACK(b);t.SetStart(vec(a));t.SetEnd(vec(z));t.SetLayer(k.F_Cu if layer==0 else k.B_Cu);t.SetWidth(k.FromMM(width));t.SetNet(ni);t.SetLocked(True);b.Add(t);count+=1
 for at in vias:
  v=k.PCB_VIA(b);v.SetPosition(vec(at));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(ni);v.SetLocked(True);b.Add(v)
 print(net,'visited',visited,'segments',count,'vias',len(vias),flush=True)
 return {'net':net,'width_mm':width,'start':start,'end':end,'segments':count,'vias':vias,'visited':visited}
def item_layers(desc):
 if 'PTH' in desc or 'Перех.' in desc:return (0,1)
 return (1,) if 'B.Cu' in desc else (0,)
def component_points(b,item):
 """Use all existing copper endpoints of the reported connected component."""
 net=item.GetNetCode();nodes=[t for t in b.GetTracks() if t.GetNetCode()==net]+[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode()==net]
 def pts(t):return [xy(t.GetPosition())] if isinstance(t,k.PAD) else [xy(t.GetStart()),xy(t.GetEnd())]
 def adjacent(a,c):
  common=[l for l in [k.F_Cu,k.B_Cu] if a.IsOnLayer(l) and c.IsOnLayer(l)]
  if not common:return False
  if isinstance(a,k.PAD):
   return any(a.HitTest(vec(p),0) for p in pts(c))
  if isinstance(c,k.PAD):return adjacent(c,a)
  def pd(p,aa,zz):
   dx,dy=zz[0]-aa[0],zz[1]-aa[1];den=dx*dx+dy*dy;q=max(0,min(1,((p[0]-aa[0])*dx+(p[1]-aa[1])*dy)/den)) if den else 0
   return math.dist(p,(aa[0]+q*dx,aa[1]+q*dy))
  aa,az=pts(a);ca,cz=pts(c)
  return min(pd(aa,ca,cz),pd(az,ca,cz),pd(ca,aa,az),pd(cz,aa,az))<.001
 reached={str(item.m_Uuid.AsString())};queue=[item]
 while queue:
  at=queue.pop()
  for node in nodes:
   uid=str(node.m_Uuid.AsString())
   if uid not in reached and adjacent(at,node):reached.add(uid);queue.append(node)
 out=[]
 for node in nodes:
  if str(node.m_Uuid.AsString()) not in reached:continue
  for p in pts(node):
   for layer,idx in [(k.F_Cu,0),(k.B_Cu,1)]:
    if node.IsOnLayer(layer):out.append((p,idx))
 return out
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',choices=['POWER','LOGIC'],required=True);ap.add_argument('--rounds',type=int,default=3);args=ap.parse_args();name='MeshRepeater2_'+args.board.title();pcb=ROOT/'design'/name/(name+'.kicad_pcb');audit=ROOT/'audit'/('routing_'+args.board.lower());audit.mkdir(exist_ok=True)
 cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe';routes=[];fail=[]
 for iteration in range(args.rounds):
  report=audit/f'drc_{iteration}.json';subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--schematic-parity','-o',str(report),str(pcb)],check=True,stdout=subprocess.PIPE)
  drc=json.loads(report.read_text(encoding='utf-8'));missing=drc['unconnected_items'];print('round',iteration,'unconnected',len(missing),flush=True)
  if not missing:break
  b=k.LoadBoard(str(pcb));lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for pd in f.Pads():lookup[str(pd.m_Uuid.AsString())]=pd
  for pair in missing:
   a,z=pair['items']
   if a['uuid'] not in lookup or z['uuid'] not in lookup:continue # ground zone islands: handled by fence check.
   net=lookup[a['uuid']].GetNetname();assert net==lookup[z['uuid']].GetNetname(),pair
   if net=='GND':width=.5
   elif args.board=='LOGIC' and net=='BAT':width=.25 # ADC cable sense, not a load feed.
   elif any(n in net for n in ['SOLAR','BAT','FILTER_OUT','FILTER_MID','SYS_3V3']):width=.8 if net!='BAT_ADC' else .2
   else:width=.25
   start=tuple(a['pos'][i] for i in ('x','y'));end=tuple(z['pos'][i] for i in ('x','y'))
   sp=component_points(b,lookup[a['uuid']]);tp=component_points(b,lookup[z['uuid']])
   try:routes.append(route(b,net,start,end,width,item_layers(a['description']),item_layers(z['description']),args.board=='LOGIC',sp,tp))
   except RuntimeError as ex:
    # Sense/LED branches and narrow existing load land entries may need .4mm.
    # Bulk connector-to-C53/C4 feeds are checked separately in the final audit.
    if width==.8:
     try:routes.append(route(b,net,start,end,.4,item_layers(a['description']),item_layers(z['description']),args.board=='LOGIC',sp,tp));continue
     except RuntimeError as ex2:ex=ex2
    fail.append(str(ex));print('candidate failure',str(ex),flush=True)
  k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(pcb),b)
  if not routes:break
 (audit/'route_log.json').write_text(json.dumps({'routes':routes,'candidate_failures':fail},indent=2),encoding='utf-8')
if __name__=='__main__':main()
