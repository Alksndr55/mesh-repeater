from pathlib import Path
import sys,json,subprocess,math
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
import routing_router as r
P=OUT/'routing_candidate6.kicad_pcb';b=k.LoadBoard(str(P));log=[]
cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
priority={'Net-(M2-SCK)':0,'Net-(M2-NSS)':1,'/RADIO_BUSY':2,'RADIO_TXEN':3,'MCU_RESET':4,'GPS_TX_MCU':5,'GPS_RX_MCU':6,'SCL':7,'/RADIO_RXEN':8}
for it in range(1):
 if it:
  k.SaveBoard(str(P),b);subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--all-track-errors','--refill-zones','--save-board','-o',str(OUT/'routing_reconnect_drc.json'),str(P)],stdout=subprocess.PIPE,check=True)
 drc=json.loads((OUT/('routing_candidate6_drc.json' if it==0 else 'routing_reconnect_drc.json')).read_text(encoding='utf8'))
 missing=[v for v in drc['unconnected_items'] if all(i['uuid'] in {str(t.m_Uuid.AsString()) for t in b.GetTracks()}|{str(p.m_Uuid.AsString()) for f in b.GetFootprints() for p in f.Pads()} for i in v['items'])];lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
 for f in b.GetFootprints():
  for p in f.Pads():lookup[str(p.m_Uuid.AsString())]=p
 missing.sort(key=lambda x:priority.get(lookup[x['items'][0]['uuid']].GetNetname(),99))
 for pair in missing:
  a,z=pair['items'];aa,zz=lookup[a['uuid']],lookup[z['uuid']];net=aa.GetNetname()
  sp=r.component_points(b,aa);tp=r.component_points(b,zz)
  # Avoid connecting already joined components from a stale DRC pair.
  if set((tuple(at),l) for at,l in sp)&set((tuple(at),l) for at,l in tp):continue
  pre={str(t.m_Uuid.AsString()) for t in b.GetTracks()}
  q=r.route(b,net,r.xy(aa.GetPosition()),r.xy(zz.GetPosition()),.2 if net!='GND' else .4,(0,1) if isinstance(aa,k.PAD) and aa.GetDrillSize().x>0 else r.item_layers(a['description']),r.item_layers(z['description']),True,sp,tp)
  ts=[t for t in b.GetTracks() if str(t.m_Uuid.AsString()) not in pre];q['length_mm']=sum(k.ToMM(t.GetLength()) for t in ts if not isinstance(t,k.PCB_VIA));print('gap',net,q['length_mm'],flush=True);log.append(q)
 if not missing:break
k.SaveBoard(str(OUT/'routing_candidate7.kicad_pcb'),b)
(OUT/'routing_reconnect.json').write_text(json.dumps(log,indent=2),encoding='utf8')
