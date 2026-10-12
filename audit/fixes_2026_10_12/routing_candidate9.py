from pathlib import Path
import sys,json,hashlib,subprocess
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
OUT=Path(__file__).parent
b=k.LoadBoard(str(OUT/'routing_before.kicad_pcb'));held=[]
cut=['Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)','/RADIO_RST','/RADIO_RXEN']
for t in list(b.GetTracks()):
 if t.GetNetname() in cut: b.Remove(t);held.append(t)
fps={f.GetReference():f for f in b.GetFootprints()}
def pd(ref,pin):return next(p for p in fps[ref].Pads() if p.GetNumber()==pin)
log=[]
for net,ar,ap,zr,zp in [('Net-(M2-MOSI)','R24','2','M2','14'),('Net-(M1-P0.02_{slash}_MISO)','R26','2','M1','6'),('/RADIO_RST','M1','1','M2','4'),('/RADIO_RXEN','M1','21','M2','11')]:
 a,z=pd(ar,ap),pd(zr,zp)
 pre={str(t.m_Uuid.AsString()) for t in b.GetTracks()}
 q=r.route(b,net,r.xy(a.GetPosition()),r.xy(z.GetPosition()),.2,(0,1) if a.GetDrillSize().x>0 else (0,),(0,1) if z.GetDrillSize().x>0 else (0,),True)
 ts=[t for t in b.GetTracks() if str(t.m_Uuid.AsString()) not in pre]
 q['length']=sum(k.ToMM(t.GetLength()) for t in ts if not isinstance(t,k.PCB_VIA))
 q['items']=[{'net':t.GetNetname(),'start':r.xy(t.GetStart()),'end':r.xy(t.GetEnd()),'layer':b.GetLayerName(t.GetLayer())} for t in ts]
 log.append(q);print('total',q['length'],flush=True)
k.SaveBoard(str(OUT/'routing_candidate9.kicad_pcb'),b)
(OUT/'routing_candidate9.json').write_text(json.dumps(log,indent=2),encoding='utf8')
