from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless();import routing_router as r
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(P));held=[]
d=json.load(open(OUT/'routing_native_drc2.json',encoding='utf8'))
lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
for v in d['violations']:
 if v['type'] in ['items_not_allowed','via_dangling','track_dangling']:
  for i in v['items']:
   t=lookup.get(i['uuid'])
   if t is not None and t not in held:b.Remove(t);held.append(t)
# Endpoints of the removed under-RF stretch, preserving both original endpoint branches.
q=r.route(b,'/RADIO_RXEN',(25.2,9.6),(58.4,9.3),.2,(1,),(1,),True)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P),b)
(OUT/'routing_rf_fix.json').write_text(json.dumps(q,indent=2),encoding='utf8')
