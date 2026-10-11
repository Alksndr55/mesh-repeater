"""Replace the peripheral BAT detour with a bulk-cap feed near TPS input."""
import sys,json,hashlib,subprocess
from pathlib import Path
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
from complete_v2_routes import route,xy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audit_v2_routing_engineering import TraceGraph,uid
ROOT=Path(__file__).resolve().parents[2]
PCB=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb'
HOLD=[]
def main():
 b=k.LoadBoard(str(PCB));before=hashlib.sha256(PCB.read_bytes()).hexdigest();fps={f.GetReference():f for f in b.GetFootprints()}
 def pad(ref,pin):return next(p for p in fps[ref].Pads() if p.GetNumber()==pin)
 g=TraceGraph(b);old=g.path(['J8','1'],['U2','10'],1.25)
 oldfeed=g.path(['J8','1'],['C53','1'],1.25)['track_UUIDs'];cut=oldfeed[oldfeed.index('c24661d3-f05c-4869-8054-d97c915189aa'):]
 oldlocal=g.path(['C53','1'],['U2','10'],1.25)['track_UUIDs'][:6]
 remove=set(cut+oldlocal+['85847f08-74cd-44f7-af28-7a368e1aaf2b'])
 for t in list(b.GetTracks()):
  if uid(t) in remove:b.Remove(t);HOLD.append(t)
 oldpose=xy(fps['C53'].GetPosition());fps['C53'].SetPosition(k.VECTOR2I(k.FromMM(44.7),k.FromMM(12.8)))
 for t in list(b.GetTracks()):
  if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND':
   x,y=xy(t.GetPosition())
   if 42.2<x<47.2 and 11.3<y<14.3:
    remove.add(uid(t));b.Remove(t);HOLD.append(t)
 routes=[];sense_ids=set(g.path(['J8','1'],['J101','9'],1.25e-6)['track_UUIDs']);protected=[]
 bat=pad('J8','1').GetNet();gnd=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='GND')
 for t in b.GetTracks():
  if uid(t) in sense_ids:protected.append(t);t.SetNet(gnd)
 try:
  for ref,pin in [('J8','1'),('J12','1'),('R1','2'),('C12','1')]:
   # Connector-to-bulk and bulk-to-load paths use the same pad as a star.
   p=pad(ref,pin);routes.append(route(b,'BAT',xy(pad('C53','1').GetPosition()),xy(p.GetPosition()),.8,starts=(0,),ends=(0,)))
 finally:
  for t in protected:t.SetNet(bat)
 k.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 afterg=TraceGraph(b);new=afterg.path(['J8','1'],['U2','10'],1.25);sense=afterg.path(['J8','1'],['J101','9'],1.25e-6)
 shared=set(new.get('track_UUIDs',[]))&set(sense.get('track_UUIDs',[]))
 assert not shared,shared
 k.SaveBoard(str(PCB),b)
 mp=PCB.with_name('model.json');m=json.loads(mp.read_text(encoding='utf8'));part=next(p for p in m['parts'] if p['ref']=='C53');part['x']=44.7;part['y']=12.8;mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf8')
 proof={'before_sha256':before,'after_sha256':hashlib.sha256(PCB.read_bytes()).hexdigest(),'C53_old_pose':oldpose,'C53_new_pose':[44.7,12.8],'removed_detour_UUIDs':sorted(remove),'new_routes':routes,'old_main_path':old,'new_main_path':new,'shared_with_sense_tracks':sorted(shared),'nominals_and_functional_nets_changed':False,'status':'native DRC and dangling-tail pruning pending'}
 (ROOT/'audit/v2_short_battery_feed.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'old_mm':old['route_segment_length_mm'],'new_mm':new['route_segment_length_mm'],'old_mohm':old['one_route_R20_mohm'],'new_mohm':new['one_route_R20_mohm'],'sense_shared':len(shared)}))
if __name__=='__main__':main()
