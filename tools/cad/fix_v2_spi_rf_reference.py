"""Remove only new SPI incursions into the accepted RF reference region."""
import json,subprocess,shutil,hashlib,types,math
from pathlib import Path
import complete_v2_routes as base
import pcbnew as k
ROOT=base.ROOT;P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';A=ROOT/'audit/routing_logic_star';REMOVED=[];KEEP=[]
def uid(t):return str(t.m_Uuid.AsString())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rf=types.ModuleType('spi_rf_router');rf.__file__=base.__file__
code=Path(base.__file__).read_text(encoding='utf-8').replace('CLEAR=.225','CLEAR=.275').replace('edge=.3+','edge=.55+')
code=code.replace('if logic:rect(arr,(12,30.5,24,45.5),.31)','if logic:\n   rect(arr,(12,30.5,24,45.5),.31)\n   rect(arr,(31,.5,45,12),.31)')
exec(code,rf.__dict__)
NAMES={'Net-(M2-MOSI)','Net-(M1-P0.02_{slash}_MISO)'}
def check(label):
 out=A/('drc_spi_rf_'+label+'.json');subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--schematic-parity','--refill-zones','--save-board','-o',str(out),str(P)],check=True,stdout=subprocess.PIPE);return json.loads(out.read_text(encoding='utf-8'))
def bbox_intersects(t):
 a,z=rf.xy(t.GetStart()),rf.xy(t.GetEnd());return min(a[0],z[0])<45.31 and max(a[0],z[0])>30.69 and min(a[1],z[1])<12.31 and max(a[1],z[1])>.19
def main():
 snap=A/'before_spi_rf_fix.kicad_pcb'
 if not snap.exists():shutil.copy2(P,snap)
 b=k.LoadBoard(str(P));KEEP.append(b);original=k.LoadBoard(str(A/'before_star.kicad_pcb'));KEEP.append(original);oldids={uid(t) for t in original.GetTracks()};log=[]
 for t in list(b.GetTracks()):
  if t.GetNetname() in NAMES and uid(t) not in oldids and bbox_intersects(t):
   log.append({'remove_new_RF_reference_incursion':uid(t),'net':t.GetNetname(),'start':rf.xy(t.GetStart()),'end':rf.xy(t.GetEnd())});b.Remove(t);REMOVED.append(t)
 k.SaveBoard(str(P),b);d=check('cut')
 for iteration in range(12):
  b=k.LoadBoard(str(P));KEEP.append(b);lookup={uid(t):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for pd in f.Pads():lookup[uid(pd)]=pd
  remove=[]
  for violation in d['violations']:
   if violation['type'] in ('track_dangling','via_dangling','clearance','copper_edge_clearance'):
    for item in violation['items']:
     t=lookup.get(item['uuid'])
     if isinstance(t,k.PCB_TRACK) and t.GetNetname() in NAMES:remove.append(item['uuid'])
  for n in set(remove):
   t=lookup[n];log.append({'remove_obsolete_SPI_stub':n,'net':t.GetNetname()});b.Remove(t);REMOVED.append(t)
  k.SaveBoard(str(P),b);d=check('clean_'+str(iteration))
  if not d['unconnected_items'] and not remove:break
  b=k.LoadBoard(str(P));KEEP.append(b);lookup={uid(t):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for pd in f.Pads():lookup[uid(pd)]=pd
  for pair in d['unconnected_items']:
   a,z=pair['items']
   if a['uuid'] not in lookup or z['uuid'] not in lookup:continue
   ai,zi=lookup[a['uuid']],lookup[z['uuid']];net=ai.GetNetname()
   if net not in NAMES:raise RuntimeError('Unexpected missing net '+net)
   start=tuple(a['pos'][p] for p in ('x','y'));end=tuple(z['pos'][p] for p in ('x','y'))
   log.append(rf.route(b,net,start,end,.25,base.item_layers(a['description']),base.item_layers(z['description']),True,rf.component_points(b,ai),rf.component_points(b,zi)))
  k.SaveBoard(str(P),b);d=check('route_'+str(iteration));print('round',iteration,'missing',len(d['unconnected_items']),flush=True)
 result={'before_spi_rf_sha256':sha(snap),'final_pcb_sha256':sha(P),'reserved_RF_reference_rectangle_mm':[31,.5,45,12],'preserved_original_RXEN':True,'changes':log,'DRC_non_marking':[v for v in d['violations'] if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance','lib_footprint_mismatch')],'unconnected':len(d['unconnected_items']),'parity':len(d['schematic_parity']),'new_SPI_tracks_intersect_RF_region':[uid(t) for t in b.GetTracks() if t.GetNetname() in NAMES and uid(t) not in oldids and bbox_intersects(t)]}
 (A/'spi_rf_reference_fix.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({n:result[n] for n in ['DRC_non_marking','unconnected','parity','new_SPI_tracks_intersect_RF_region']},ensure_ascii=True))
if __name__=='__main__':main()
