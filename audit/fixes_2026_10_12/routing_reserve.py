from pathlib import Path
import sys,json,math,subprocess
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
import complete_v2_routes as r
sys.path.insert(0,str(ROOT/'tools'))
from plan_v2_routing_corrections import manual,desc
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
OUT=Path(__file__).parent
b=k.LoadBoard(str(OUT/'routing_before.kicad_pcb'));held=[];added=[];removed=[]
base=json.load(open(ROOT/'audit/independent_2026_10_12/routing_native.json',encoding='utf8'))['boards']['BASELINE']
nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
cut=['Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)','/RADIO_RST','/RADIO_RXEN']
def rm(t,why):
 removed.append(dict(desc(b,t),net=t.GetNetname(),why=why));b.Remove(t);held.append(t)
for t in list(b.GetTracks()):
 if t.GetNetname() in cut:rm(t,'R1/R2 complete reroute')
def tr(net,a,z,layer,w=.2):
 t=k.PCB_TRACK(b);t.SetStart(r.vec(a));t.SetEnd(r.vec(z));t.SetWidth(k.FromMM(w));t.SetLayer(k.F_Cu if layer=='F.Cu' else k.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t);added.append(t);return t
def via(net,at):
 t=k.PCB_VIA(b);t.SetPosition(r.vec(at));t.SetWidth(k.FromMM(.6));t.SetDrill(k.FromMM(.3));t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t);added.append(t);return t
def path(net,pts,layer):
 return [tr(net,a,z,layer) for a,z in zip(pts,pts[1:])]
path('Net-(M2-MOSI)',[[30.9125,23.58],[31.0125,23.58],[33,21.5925],[33,16.1],[34.9,16.1],[35.6,16.8],[35.6,17.7],[38.4,17.7]],'F.Cu');via('Net-(M2-MOSI)',[38.4,17.7]);path('Net-(M2-MOSI)',[[38.4,17.7],[42,17.7]],'B.Cu');via('Net-(M2-MOSI)',[42,17.7]);path('Net-(M2-MOSI)',[[42,17.7],[53.3,17.7],[56,15]],'F.Cu')
for d in base['items'].values():
 if d['net']=='Net-(M1-P0.02_{slash}_MISO)' and d['kind']=='track':tr(d['net'],d['start'],d['end'],d['layer'],d['width_mm'])
 if d['net']=='Net-(M1-P0.02_{slash}_MISO)' and d['kind']=='via':via(d['net'],d['at'])
# Reserve SPI corridor and remove only tracks/vias that actually conflict.
conflicts=set()
for t in added:
 d=desc(b,t)
 if isinstance(t,k.PCB_VIA):
  for layer in ['F.Cu','B.Cu']:
   conflicts.update(x['uuid'] for x in manual(b,t.GetNetname(),'via',[dict(start=d['at'],end=d['at'],layer=layer)],.6)['nonmatching_track_conflicts_for_local_rework'])
 else:conflicts.update(x['uuid'] for x in manual(b,t.GetNetname(),'SPI',[d],d['width_mm'])['nonmatching_track_conflicts_for_local_rework'])
lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
protected={'/ANT_RF','/ANT_SMA','/RADIO_3V3','SYS_3V3','Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)'}
for u in conflicts:
 t=lookup[u]
 if t.GetNetname() in protected:
  print('PROTECTED conflict',t.GetNetname(),desc(b,t),flush=True);continue
 rm(t,'free compact SPI corridor')
k.SaveBoard(str(OUT/'routing_candidate2.kicad_pcb'),b)
(OUT/'routing_changes2.json').write_text(json.dumps({'removed':removed,'added':[dict(desc(b,t),net=t.GetNetname()) for t in added]},indent=2),encoding='utf8')
print('Reserved baseline SPI; conflicts removed',len(conflicts),flush=True)
