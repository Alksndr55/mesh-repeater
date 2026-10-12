from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
sys.path.insert(0,str(ROOT/'tools'))
from plan_v2_routing_corrections import manual,desc,mm,segment_gap
b=k.LoadBoard(str(ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'))
a=k.LoadBoard(str(ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pcb'))
fps={f.GetReference():f for f in b.GetFootprints()}
for ref in ['M1','M2','R23','R24','R25','R26','J10','FB1','C21','C22']:
 f=fps[ref];print(ref,mm(f.GetPosition()),f.GetOrientationDegrees(),[(p.GetNumber(),p.GetNetname(),mm(p.GetPosition())) for p in f.Pads()])
for net in ['Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)','/3. Modules/RADIO_RST']:
 orig=[t for t in a.GetTracks() if t.GetNetname()==net]
 print('\nBASELINE',net,len(orig))
 for t in orig:
  d=desc(a,t);print(json.dumps(d))
  if not isinstance(t,k.PCB_VIA):
   hits=manual(b,net,'base',[dict(start=d['start'],end=d['end'],layer=d['layer'])],d['width_mm'])['nonmatching_track_conflicts_for_local_rework']
   print('CONFLICTS',[(h['net'],h.get('start',h.get('at')),h.get('end'),h['uuid']) for h in hits])

