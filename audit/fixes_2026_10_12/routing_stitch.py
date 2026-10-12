from pathlib import Path
import sys,json,math,subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless();import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(P));held=[];added=[]
# Prune the remaining one-ended GPS twig.
for t in list(b.GetTracks()):
 if str(t.m_Uuid.AsString())=='6ecb9dc0-19e5-40de-8250-af59a7207dda':b.Remove(t);held.append(t)
gnd=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='GND')
pads=[p for f in b.GetFootprints() for p in f.Pads()]
def ground():
 out={l:k.SHAPE_POLY_SET() for l in [k.F_Cu,k.B_Cu]}
 for z in b.Zones():
  if not z.GetIsRuleArea() and z.GetNetname()=='GND':
   for l in out:
    if z.HasFilledPolysForLayer(l):out[l].BooleanAdd(z.GetFilledPolysList(l))
 return out
polygons={}
for p in pads:
 for l in [k.F_Cu,k.B_Cu]:
  if p.IsOnLayer(l):polygons[(id(p),l)]=p.GetEffectivePolygon(l)
def pd(pt,a,z):
 d=(z[0]-a[0],z[1]-a[1]);den=d[0]*d[0]+d[1]*d[1];q=max(0,min(1,((pt[0]-a[0])*d[0]+(pt[1]-a[1])*d[1])/den)) if den else 0
 return math.dist(pt,(a[0]+q*d[0],a[1]+q*d[1]))
def free(at):
 p=r.vec(at)
 if not(.8<at[0]<89.2 and .8<at[1]<59.2):return False
 for t in b.GetTracks():
  if isinstance(t,k.PCB_VIA):
   if math.dist(at,r.xy(t.GetPosition()))<(.3+k.ToMM(t.GetDrill())/2+.25)-.000001:return False
  if t.GetNetname()!='GND':
   w=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth())
   if pd(at,r.xy(t.GetStart()),r.xy(t.GetEnd())) < .3+w/2+.20001:return False
 for pad in pads:
  if pad.GetDrillSize().x>0:
   rr=max(r.xy(pad.GetDrillSize()))/2+.3+.25
   if math.dist(at,r.xy(pad.GetPosition()))<rr-.000001:return False
  if pad.GetNetname()=='GND':continue
  for l in [k.F_Cu,k.B_Cu]:
   poly=polygons.get((id(pad),l))
   if poly is not None and (poly.Contains(p) or k.ToMM(poly.Distance(p)) < .50001):return False
 return True
def add(at,reason):
 v=k.PCB_VIA(b);v.SetPosition(r.vec(at));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(gnd);v.SetLocked(True);v.SetFrontTentingMode(k.TENTING_MODE_TENTED);v.SetBackTentingMode(k.TENTING_MODE_TENTED);b.Add(v);added.append({'at':at,'reason':reason,'uuid':str(v.m_Uuid.AsString())})
def nearest(at):return min((math.dist(at,r.xy(t.GetPosition())) for t in b.GetTracks() if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND'),default=999)
critical={'Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)','/RADIO_RST','Net-(M2-SCK)','/RADIO_DIO1','GPS_TX_MCU'}
for v in [t for t in b.GetTracks() if isinstance(t,k.PCB_VIA) and t.GetNetname() in critical]:
 at=r.xy(v.GetPosition())
 if nearest(at)<=1.2:continue
 g=ground();choices=[]
 for rad in [.85,1.0,1.15,1.3,1.45,1.6,1.8,2.0]:
  for i in range(24):
   q=(round(at[0]+rad*math.cos(i*math.pi/12),2),round(at[1]+rad*math.sin(i*math.pi/12),2));p=r.vec(q)
   if not free(q) or not any(x.Contains(p) for x in g.values()):continue
   choices.append((rad,q))
  if choices:break
 if choices:
  add(choices[0][1],'near '+v.GetNetname()+' via '+str(at));k.ZONE_FILLER(b).Fill(b.Zones())
# Stitch remaining large reference islands, seeded only from actual GND on one side.
for it in range(3):
 g=ground();probes=[]
 for t in b.GetTracks():
  if isinstance(t,k.PCB_VIA) or t.GetNetname() not in critical:continue
  other=k.B_Cu if t.GetLayer()==k.F_Cu else k.F_Cu;a,z=r.xy(t.GetStart()),r.xy(t.GetEnd());length=math.dist(a,z)
  for n in range(1,max(2,math.ceil(length/2))):
   ratio=n/max(2,math.ceil(length/2));at=(a[0]+ratio*(z[0]-a[0]),a[1]+ratio*(z[1]-a[1]))
   if not g[other].Contains(r.vec(at)):probes.append((at,other,t.GetNetname()))
 count=0
 for at,other,net in probes:
  if nearest(at)<1.3:continue
  options=[]
  for rad in [.9,1.2,1.5,1.8,2.1,2.4]:
   for i in range(16):
    q=(round(at[0]+rad*math.cos(i*math.pi/8),2),round(at[1]+rad*math.sin(i*math.pi/8),2));p=r.vec(q)
    if not free(q) or not any(x.Contains(p) for x in g.values()):continue
    # Prefer seeding the previously removed opposite-layer polygon.
    options.append((g[other].Contains(p),rad,q))
   if options:break
  if options:
   options.sort();add(options[0][2],'reference stitch '+net+' near '+str(at));count+=1
   if count>=12:break
 if not count:break
 k.ZONE_FILLER(b).Fill(b.Zones())
k.SaveBoard(str(P),b)
(OUT/'routing_ground_stitches.json').write_text(json.dumps({'added':added,'diameter_mm':.6,'drill_mm':.3,'tented_both':True,'method':'via clearance checked to tracks/pads/holes; each new barrel seeded from a real filled GND polygon on at least one side, then refill; native DRC and copper union required'},indent=2),encoding='utf8')
print('Added GND vias',len(added),flush=True)
