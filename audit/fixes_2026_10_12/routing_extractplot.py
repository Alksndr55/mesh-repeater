from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless()
b=k.LoadBoard(str(OUT/'routing_candidate9.kicad_pcb'));data=[]
for t in b.GetTracks():data.append(dict(kind='via' if isinstance(t,k.PCB_VIA) else 'track',a=[k.ToMM(t.GetStart().x),k.ToMM(t.GetStart().y)],z=[k.ToMM(t.GetEnd().x),k.ToMM(t.GetEnd().y)],w=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth()),net=t.GetNetname(),layer=b.GetLayerName(t.GetLayer())))
for f in b.GetFootprints():
 for p in f.Pads():data.append(dict(kind='pad',a=[k.ToMM(p.GetPosition().x),k.ToMM(p.GetPosition().y)],size=[k.ToMM(p.GetSize().x),k.ToMM(p.GetSize().y)],net=p.GetNetname(),layer=[b.GetLayerName(l) for l in [k.F_Cu,k.B_Cu] if p.IsOnLayer(l)],ref=f.GetReference(),pin=p.GetNumber()))
(OUT/'routing_plot_data.json').write_text(json.dumps(data),encoding='utf8')
