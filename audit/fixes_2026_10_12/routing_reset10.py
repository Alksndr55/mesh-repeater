from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless()
import routing_router as r
sys.path.insert(0,str(ROOT/'tools'));from plan_v2_routing_corrections import manual,desc
b=k.LoadBoard(str(OUT/'routing_candidate9.kicad_pcb'));held=[];removed=[];added=[]
nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
def rm(t,why):removed.append(dict(desc(b,t),net=t.GetNetname(),why=why));b.Remove(t);held.append(t)
for t in list(b.GetTracks()):
 if t.GetNetname()=='/RADIO_RST':rm(t,'short reset')
def tr(net,a,z,layer,w=.2):
 t=k.PCB_TRACK(b);t.SetStart(r.vec(a));t.SetEnd(r.vec(z));t.SetWidth(k.FromMM(w));t.SetLayer(k.F_Cu if layer=='F.Cu' else k.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t);added.append(t);return t
def via(net,at):
 t=k.PCB_VIA(b);t.SetPosition(r.vec(at));t.SetWidth(k.FromMM(.6));t.SetDrill(k.FromMM(.3));t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t);added.append(t);return t
def path(net,pts,layer):return [tr(net,a,z,layer) for a,z in zip(pts,pts[1:])]
path('/RADIO_RST',[[25.62,33.74],[28,33.74],[32.74,29],[37.5,29],[37.5,19.6]],'B.Cu');via('/RADIO_RST',[37.5,19.6]);path('/RADIO_RST',[[37.5,19.6],[37.5,18.3],[38.8,17],[40,17]],'F.Cu')
conflicts=set()
for t in added:
 d=desc(b,t)
 for l in (['F.Cu','B.Cu'] if isinstance(t,k.PCB_VIA) else [d['layer']]):
  seg=dict(start=d.get('start',d.get('at')),end=d.get('end',d.get('at')),layer=l)
  conflicts.update(x['uuid'] for x in manual(b,t.GetNetname(),'reset',[seg],.6 if isinstance(t,k.PCB_VIA) else .2)['nonmatching_track_conflicts_for_local_rework'])
lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
for u in conflicts:
 t=lookup[u];print('CONFLICT',t.GetNetname(),desc(b,t),flush=True)
 if t.GetNetname() in {'SYS_3V3','/ANT_RF','/ANT_SMA','Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)'}:continue
 rm(t,'reset bridge conflict')
k.SaveBoard(str(OUT/'routing_candidate10.kicad_pcb'),b)
(OUT/'routing_changes10.json').write_text(json.dumps({'removed':removed,'added':[dict(desc(b,t),net=t.GetNetname()) for t in added]},indent=2),encoding='utf8')
