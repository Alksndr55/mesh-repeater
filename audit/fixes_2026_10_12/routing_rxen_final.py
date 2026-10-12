from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless();import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(P));held=[]
net=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='/RADIO_RXEN')
for t in list(b.GetTracks()):
 if t.GetNetname()=='/RADIO_RXEN':b.Remove(t);held.append(t)
def path(pts,layer):
 for a,z in zip(pts,pts[1:]):
  t=k.PCB_TRACK(b);t.SetStart(r.vec(a));t.SetEnd(r.vec(z));t.SetWidth(k.FromMM(.2));t.SetLayer(layer);t.SetNet(net);t.SetLocked(True);b.Add(t)
path([[10.38,15.96],[9.34,15.96],[4,21.3]],k.B_Cu)
v=k.PCB_VIA(b);v.SetPosition(r.vec([4,21.3]));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(net);v.SetLocked(True);b.Add(v)
path([[4,21.3],[3.8,21.5],[3.8,39]],k.F_Cu)
q=r.route(b,'/RADIO_RXEN',(3.8,39),(56,21),.2,(0,),(0,),True)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P),b)
(OUT/'routing_rxen_final.json').write_text(json.dumps(q,indent=2),encoding='utf8')
