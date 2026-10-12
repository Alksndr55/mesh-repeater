from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
sys.path.insert(0,str(ROOT/'audit/independent_2026_10_12'))
import routing_native as a
b,x=a.load('LOGIC',ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb')
(OUT/'routing_after_native.json').write_text(json.dumps(x,indent=2),encoding='utf8')
before=json.load(open(ROOT/'audit/independent_2026_10_12/routing_native.json',encoding='utf8'))['boards']['LOGIC']
for net in ['MOSI_RF','MISO_MCU','RADIO_RST','RADIO_RXEN','SCK_RF','RADIO_DIO1','GPS_TX_MCU','SYS_3V3','ANT_RF','ANT_SMA']:
 def metric(d):
  items=[t for t in d['items'].values() if t['logical_net']==net and t['kind']!='pad'];tracks=[t for t in items if t['kind']=='track'];refs=[t for t in d['opposite_ground_samples'] if t['logical_net']==net]
  return {'whole_net_mm':sum(t['length_mm'] for t in tracks),'via_count':sum(t['kind']=='via' for t in items),'no_opposite_GND_mm':sum(t['length_mm']*t['uncovered_fraction'] for t in refs),'angles_bad':[t['uuid'] for t in tracks if min(abs(t['start'][0]-t['end'][0]),abs(t['start'][1]-t['end'][1]),abs(abs(t['start'][0]-t['end'][0])-abs(t['start'][1]-t['end'][1])))>.00001]}
 print(net,metric(before),metric(x),flush=True)
print('GROUND components',len(x['GND_physical_components']),flush=True)
