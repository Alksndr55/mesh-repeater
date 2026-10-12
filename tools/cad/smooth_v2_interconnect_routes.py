"""Shorten only new interconnect routes, preserving45/90geometry and nativeDRC."""
from pathlib import Path
import collections, hashlib, json, math, shutil, subprocess
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
A=ROOT/'audit/ina219_vertical_interconnect_2026_10_12'
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
KEEP=[]
def uid(t):return str(t.m_Uuid.AsString())
def xy(p):return k.ToMM(p.x),k.ToMM(p.y)
def v(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def aligned(a,z):
 dx,dy=abs(z[0]-a[0]),abs(z[1]-a[1]);return dx<1e-5 or dy<1e-5 or abs(dx-dy)<1e-5
def options(a,z):
 if aligned(a,z):yield[a,z]
 yield[a,(a[0],z[1]),z];yield[a,(z[0],a[1]),z]
 dx,dy=z[0]-a[0],z[1]-a[1];m=min(abs(dx),abs(dy));sx=1 if dx>=0 else-1;sy=1 if dy>=0 else-1
 yield[a,(a[0]+sx*m,a[1]+sy*m),z]
 yield[a,(z[0]-sx*m,z[1]-sy*m),z]
def main():
 b=k.LoadBoard(str(P));old=k.LoadBoard(str(A/'MeshRepeater2_Logic_before.kicad_pcb'));KEEP.extend([b,old]);oldids={uid(t)for t in old.GetTracks()}
 snapshot=A/'logic_before_route_smoothing.kicad_pcb';shutil.copy2(P,snapshot)
 changes=[]
 nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
 for net in ['FILTER_OUT','SYS_3V3','MODE','BAT','SDA','SCL']:
  tracks=[t for t in b.GetTracks()if t.GetNetname()==net and uid(t)not in oldids and not isinstance(t,k.PCB_VIA)]
  foreign=[]
  for t in b.GetTracks():
   if t.GetNetname()!=net:
    for layer in [k.F_Cu,k.B_Cu]:
     if t.IsOnLayer(layer):foreign.append((layer,t.GetEffectiveShape(layer)))
  for f in b.GetFootprints():
   for p in f.Pads():
    if p.GetNetname()!=net:
     for layer in [k.F_Cu,k.B_Cu]:
      if p.IsOnLayer(layer):foreign.append((layer,p.GetEffectiveShape(layer)))
  shaped=[]
  for layer,s in foreign:
   bb=s.BBox();shaped.append((layer,[k.ToMM(c)for c in [bb.GetX(),bb.GetY(),bb.GetRight(),bb.GetBottom()]],s))
  def clear(a,z,layer,width):
   margin=.55+width/2
   if any(not(margin<=p[0]<=90-margin and margin<=p[1]<=60-margin)for p in [a,z]):return False
   t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(z));t.SetLayer(layer);t.SetWidth(k.FromMM(width));s=t.GetEffectiveShape(layer)
   x0,y0,x1,y1=min(a[0],z[0])-width/2-.225,min(a[1],z[1])-width/2-.225,max(a[0],z[0])+width/2+.225,max(a[1],z[1])+width/2+.225
   for area in [(12,30.5,24,45.5),(31,.5,45,12)]:
    if x0<area[2]and x1>area[0]and y0<area[3]and y1>area[1]:return False
   for other_layer,box,other in shaped:
    if other_layer==layer and x0<=box[2]and x1>=box[0]and y0<=box[3]and y1>=box[1]and s.Collide(other,k.FromMM(.21)):return False
   return True
  groups=collections.defaultdict(list)
  for t in tracks:groups[(t.GetLayer(),t.GetWidth())].append(t)
  for (layer,width_i),ts in groups.items():
   width=k.ToMM(width_i);graph=collections.defaultdict(list);at={}
   for t in ts:
    a,z=xy(t.GetStart()),xy(t.GetEnd());graph[a].append((z,t));graph[z].append((a,t));at[uid(t)]=t
   anchors={p for p,edges in graph.items()if len(edges)!=2}
   # Pads, vias and retained copper are fixed anchors even at degree-two nodes.
   samepads=[p for f in b.GetFootprints()for p in f.Pads()if p.GetNetname()==net and p.IsOnLayer(layer)]
   samevias=[t for t in b.GetTracks()if isinstance(t,k.PCB_VIA)and t.GetNetname()==net]
   for p in graph:
    if any(pd.HitTest(v(p),0)for pd in samepads)or any(math.dist(p,xy(t.GetPosition()))<.31 for t in samevias):anchors.add(p)
   visited=set()
   for start in list(anchors):
    for target,first in graph[start]:
     if uid(first)in visited:continue
     pts=[start,target];chain=[first];visited.add(uid(first));prior=start;here=target
     while here not in anchors:
      following=[(p,t)for p,t in graph[here]if p!=prior]
      if len(following)!=1:break
      nxt,t=following[0]
      if uid(t)in visited:break
      chain.append(t);visited.add(uid(t));pts.append(nxt);prior,here=here,nxt
     if len(chain)<3:continue
     n=len(pts);cost=[float('inf')]*n;choice=[None]*n;cost[-1]=0
     for i in range(n-2,-1,-1):
      for j in range(i+1,n):
       for candidate in options(pts[i],pts[j]):
        candidate=[p for ix,p in enumerate(candidate)if ix==0 or math.dist(p,candidate[ix-1])>1e-7]
        if not all(aligned(a,z)and clear(a,z,layer,width)for a,z in zip(candidate,candidate[1:])):continue
        score=sum(math.dist(a,z)for a,z in zip(candidate,candidate[1:]))+.4*(len(candidate)-1)+cost[j]
        if score<cost[i]-1e-6:cost[i]=score;choice[i]=(j,candidate)
     if choice[0]is None:continue
     out=[pts[0]];index=0
     while index<n-1:
      index,path=choice[index];out.extend(path[1:])
     original_length=sum(math.dist(a,z)for a,z in zip(pts,pts[1:]));new_length=sum(math.dist(a,z)for a,z in zip(out,out[1:]))
     if len(out)-1>=len(chain)or new_length>original_length+.001:continue
     for t in chain:b.Remove(t);KEEP.append(t)
     for a,z in zip(out,out[1:]):
      t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(z));t.SetLayer(layer);t.SetWidth(width_i);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t)
     changes.append({'net':net,'layer':k.LayerName(layer),'width_mm':width,'before_segments':len(chain),'after_segments':len(out)-1,'before_length_mm':original_length,'after_length_mm':new_length,'path_mm':out})
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P),b)
 report=A/'logic_smoothed_drc.json';subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--refill-zones','--save-board','-o',str(report),str(P)],check=True,stdout=subprocess.PIPE)
 d=json.loads(report.read_text(encoding='utf-8'));counts={n:len(d.get(n,[]))for n in ['violations','unconnected_items','schematic_parity']}
 if any(counts.values()):
  shutil.copy2(snapshot,P);status='REVERTED_NATIVE_DRC_REJECTED'
 else:status='ACCEPTED_NATIVE_DRC_CLEAN'
 proof={'status':status,'changes':changes,'DRC_counts':counts,'native_sha256':hashlib.sha256(P.read_bytes()).hexdigest()}
 (A/'logic_route_smoothing.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':status,'chains':len(changes),'segment_reduction':sum(c['before_segments']-c['after_segments']for c in changes),'DRC':counts}),flush=True)
if __name__=='__main__':main()
