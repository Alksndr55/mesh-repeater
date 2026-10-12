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
path('Net-(M2-MOSI)',[[30.9125,23.58],[30.92,23.58],[33,21.5],[33,16.1],[33.3,15.8],[35.9,15.8]],'F.Cu');via('Net-(M2-MOSI)',[35.9,15.8]);path('Net-(M2-MOSI)',[[35.9,15.8],[45.2,15.8],[45.9,15.1],[49.7,15.1]],'B.Cu');via('Net-(M2-MOSI)',[49.7,15.1]);path('Net-(M2-MOSI)',[[49.7,15.1],[50,15.1],[51.4,16.5],[54,16.5],[54.6,15.9],[55.1,15.9],[56,15]],'F.Cu')
path('Net-(M1-P0.02_{slash}_MISO)',[[25.62,21.04],[26.08,21.5],[32.1,21.5]],'F.Cu');via('Net-(M1-P0.02_{slash}_MISO)',[32.1,21.5]);path('Net-(M1-P0.02_{slash}_MISO)',[[32.1,21.5],[32.55,21.95],[33.45,21.95]],'B.Cu');via('Net-(M1-P0.02_{slash}_MISO)',[33.45,21.95]);path('Net-(M1-P0.02_{slash}_MISO)',[[33.45,21.95],[35.4,20],[46.6,20],[47.05,19.55]],'F.Cu');via('Net-(M1-P0.02_{slash}_MISO)',[47.05,19.55]);path('Net-(M1-P0.02_{slash}_MISO)',[[47.05,19.55],[59.5,19.55]],'B.Cu');via('Net-(M1-P0.02_{slash}_MISO)',[59.5,19.55]);path('Net-(M1-P0.02_{slash}_MISO)',[[59.5,19.55],[60.25,18.8],[60.3125,18.8]],'F.Cu')
path('/RADIO_RST',[[25.62,33.74],[25.62,33.72],[30.3,38.4],[34.5,38.4],[34.7,38.2],[39.9,38.2],[46.7,31.4],[46.7,29.3]],'B.Cu');via('/RADIO_RST',[46.7,29.3]);path('/RADIO_RST',[[46.7,29.3],[49.1,26.9],[49.1,18],[43,18],[42,17],[40,17]],'F.Cu')
# Reserve SPI corridor and remove only tracks/vias that actually conflict.
conflicts=set()
for t in added:
 d=desc(b,t)
 if isinstance(t,k.PCB_VIA):
  for layer in ['F.Cu','B.Cu']:
   conflicts.update(x['uuid'] for x in manual(b,t.GetNetname(),'via',[dict(start=d['at'],end=d['at'],layer=layer)],.6)['nonmatching_track_conflicts_for_local_rework'])
 else:conflicts.update(x['uuid'] for x in manual(b,t.GetNetname(),'SPI',[d],d['width_mm'])['nonmatching_track_conflicts_for_local_rework'])
lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
protected={'/ANT_RF','/ANT_SMA','/RADIO_3V3','SYS_3V3','Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)','/RADIO_RST'}
for u in conflicts:
 t=lookup[u]
 if t.GetNetname() in protected:
  print('PROTECTED conflict',t.GetNetname(),desc(b,t),flush=True);continue
 rm(t,'free compact SPI corridor')
k.SaveBoard(str(OUT/'routing_candidate4.kicad_pcb'),b)
(OUT/'routing_changes4.json').write_text(json.dumps({'removed':removed,'added':[dict(desc(b,t),net=t.GetNetname()) for t in added]},indent=2),encoding='utf8')
print('Reserved baseline SPI; conflicts removed',len(conflicts),flush=True)
