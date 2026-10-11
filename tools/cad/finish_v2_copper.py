"""Join ground planes and remove obsolete partition stubs, with native DRC proof.

Only documented same-net vias/stubs are changed. No component, functional value,
switching-loop, RF centre conductor or schematic connection is changed.
"""
import argparse,json,math,subprocess
from complete_v2_routes import ROOT,k,xy,vec
REMOVED=[] # KiCad10 SWIG transfers ownership on Remove; retain proxies until exit.

def distance(p,a,z):
 dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy
 q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
 return math.dist(p,(a[0]+q*dx,a[1]+q*dy))

def octilinear(a,z):
 dx,dy=z[0]-a[0],z[1]-a[1];d=min(abs(dx),abs(dy))
 mid=(a[0]+math.copysign(d,dx),a[1]+math.copysign(d,dy))
 return [a,mid,z]

def stub(b,a,z,template):
 for s,e in zip(octilinear(a,z),octilinear(a,z)[1:]):
  if math.dist(s,e)<.000001:continue
  t=k.PCB_TRACK(b);t.SetStart(vec(s));t.SetEnd(vec(e));t.SetWidth(template.GetWidth());t.SetLayer(template.GetLayer());t.SetNetCode(template.GetNetCode());t.SetLocked(True);b.Add(t)

def merge(b,remove_uid,keep_uid,log):
 lookup={t.m_Uuid.AsString():t for t in b.GetTracks()};old=lookup.get(remove_uid);keep=lookup.get(keep_uid)
 if not old or not keep:return
 assert isinstance(old,k.PCB_VIA) and isinstance(keep,k.PCB_VIA) and old.GetNetCode()==keep.GetNetCode()
 a,z=xy(old.GetPosition()),xy(keep.GetPosition())
 for t in list(b.GetTracks()):
  if isinstance(t,k.PCB_VIA) or t.GetNetCode()!=keep.GetNetCode():continue
  for getter,setter in [(t.GetStart,t.SetStart),(t.GetEnd,t.SetEnd)]:
   p=xy(getter())
   if math.dist(p,a)<.001:
    # Retain the original long straight segment and connect its endpoint with
    # 45/90-degree copper inside the existing same-net annulus.
    stub(b,p,z,t)
 b.Remove(old);REMOVED.append(old);log.append({'merge_via':remove_uid,'into':keep_uid,'from':a,'to':z})

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',choices=['POWER','LOGIC'],required=True);args=ap.parse_args()
 name='MeshRepeater2_'+args.board.title();p=ROOT/'design'/name/(name+'.kicad_pcb');b=k.LoadBoard(str(p));log=[]
 if args.board=='POWER':merge(b,'dd6d4656-c629-44e1-b265-fa781221f4e2','ebf29eaf-75d8-46da-bd72-c6912a6a87b3',log)
 else:merge(b,'9c20da56-2b5f-462b-9e59-7da748997a39','f1eee42c-b03e-4e95-93bb-0dca448083b3',log)
 # Add a short octilinear centre connection for the rounded DONE endpoint.
 if args.board=='POWER':
  lookup={t.m_Uuid.AsString():t for t in b.GetTracks()}
  t=lookup.get('bb5add23-f403-4d34-aa9b-0a1a88fe151d');v=lookup.get('4f6b6e21-4905-4d59-843c-63a1086fb1bd')
  if t and v:stub(b,xy(t.GetStart()),xy(v.GetPosition()),t)
 # Obsolete one-layer vias from former inter-board connector tails.
 remove={'POWER':['ed6bb76c-d039-4f43-9983-5e4c614df924','438cac47-4214-4b5c-813a-02d7b941062c'],
 'LOGIC':['1f0ac6aa-518c-4937-b13b-35748375cc9f','68193309-2371-4034-98c4-9d684c6137a4','d2342433-364c-4645-a428-61f5b829812f','f1291161-18af-4880-977b-e9e2a7893bf7','bedfa249-5daa-4ef6-be22-a3ec6a10e5c3']}[args.board]
 for t in list(b.GetTracks()):
  if t.m_Uuid.AsString() in remove:
   log.append({'removed_partition_stub':t.m_Uuid.AsString(),'net':t.GetNetname(),'position':xy(t.GetStart())});b.Remove(t);REMOVED.append(t)
 k.ZONE_FILLER(b).Fill(b.Zones())
 ground=next(p.GetNet() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND')
 zones={l:[z.GetFilledPolysList(l) for z in b.Zones() if z.GetNetname()=='GND' and z.IsOnLayer(l) and not z.GetIsRuleArea()] for l in (k.F_Cu,k.B_Cu)}
 pads=[p for f in b.GetFootprints() for p in f.Pads()];tracks=list(b.GetTracks())
 def safe(at):
  if args.board=='LOGIC' and 11.4<at[0]<24.6 and 29.9<at[1]<46.1:return False
  if any(z.GetIsRuleArea() and z.Outline().Contains(vec(at)) for z in b.Zones()):return False
  for layer in (k.F_Cu,k.B_Cu):
   if not any(z.Contains(vec(at)) for z in zones[layer]):return False
  for p in pads:
   if p.GetNetname()=='GND' and p.GetAttribute()!=k.PAD_ATTRIB_NPTH:
    if p.GetAttribute()==k.PAD_ATTRIB_PTH and math.dist(at,xy(p.GetPosition()))<max(xy(p.GetDrillSize()))/2+.15+.3:return False
    continue
   box=p.GetBoundingBox();margin=.525
   if k.ToMM(box.GetLeft())-margin<=at[0]<=k.ToMM(box.GetRight())+margin and k.ToMM(box.GetTop())-margin<=at[1]<=k.ToMM(box.GetBottom())+margin:return False
  for t in tracks:
   if isinstance(t,k.PCB_VIA) and math.dist(at,xy(t.GetPosition()))<k.ToMM(t.GetDrill())/2+.15+.3:return False
   if t.GetNetname()=='GND':
    if not isinstance(t,k.PCB_VIA) and distance(at,xy(t.GetStart()),xy(t.GetEnd()))<.45:return False
    continue
   w=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth())
   if distance(at,xy(t.GetStart()),xy(t.GetEnd()))<w/2+.3+.225:return False
  return True
 candidates=[]
 # A regular fence and 3mm interior grid join retained polygon islands.
 for x in [1.5+3*i for i in range(30)]:
  candidates.extend([(x,1.5),(x,58.5)])
 for y in [4.5+3*i for i in range(18)]:candidates.extend([(1.5,y),(88.5,y)])
 for y in [4.5+3*i for i in range(18)]:
  for x in [4.5+3*i for i in range(28)]:candidates.append((x,y))
 count=0
 for at in candidates:
  if not safe(at):continue
  v=k.PCB_VIA(b);v.SetPosition(vec(at));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(ground);v.SetLocked(True);b.Add(v);tracks.append(v);count+=1
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(p),b)
 audit=ROOT/'audit'/('routing_'+args.board.lower());audit.mkdir(exist_ok=True)
 (audit/'copper_finish.json').write_text(json.dumps({'changes':log,'ground_stitches_added':count,'pitch_mm':3,'diameter_mm':.6,'drill_mm':.3},indent=2),encoding='utf-8')
 subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--schematic-parity','-o',str(audit/'drc_copper.json'),str(p)],check=True)
 print(args.board,'stitches',count)
if __name__=='__main__':main()
