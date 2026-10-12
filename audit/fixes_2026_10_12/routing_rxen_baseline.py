from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless();import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(P));held=[]
base=json.load(open(ROOT/'audit/independent_2026_10_12/routing_native.json',encoding='utf8'))['boards']['BASELINE']
net=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='/RADIO_RXEN')
for t in list(b.GetTracks()):
 if t.GetNetname()=='/RADIO_RXEN':b.Remove(t);held.append(t)
for d in base['items'].values():
 if d['logical_net']!='RADIO_RXEN' or d['kind']=='pad':continue
 if d['kind']=='via':
  t=k.PCB_VIA(b);t.SetPosition(r.vec(d['at']));t.SetWidth(k.FromMM(d['diameter_mm']));t.SetDrill(k.FromMM(d['drill_mm']));t.SetLayerPair(k.F_Cu,k.B_Cu)
 else:
  t=k.PCB_TRACK(b);t.SetStart(r.vec(d['start']));t.SetEnd(r.vec(d['end']));t.SetWidth(k.FromMM(d['width_mm']));t.SetLayer(k.F_Cu if d['layer']=='F.Cu' else k.B_Cu)
 t.SetNet(net);t.SetLocked(True);b.Add(t)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(OUT/'routing_rxen_baseline.kicad_pcb'),b)
