"""Read the final POWER geometry and append a current, hash-bound proof.

Historical routing trials remain in their original reports. No PCB is saved.
Route resistance assumes 35 um copper at20C; it is not an EMC or ampacity test.
"""
from finish_v2_markings import ROOT,k,xy
import hashlib,json,sys
sys.path.insert(0,str(ROOT/'tools'))
from audit_v2_routing_engineering import TraceGraph

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 pcb=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb';b=k.LoadBoard(str(pcb));source=sha(pcb);g=TraceGraph(b)
 folder=ROOT/'output/POWER';drcpath=folder/'MeshRepeater2_Power_drc.json';drc=json.loads(drcpath.read_text(encoding='utf8'));exports=json.loads((folder/'MeshRepeater2_Power_exports.json').read_text(encoding='utf8'))
 assert exports['sha256']==source,'Re-export final native source before proving its DRC'
 assert all(not drc.get(n,[]) for n in ('violations','unconnected_items','schematic_parity','ignored')),'Native DRC/parity must be completely empty'
 feed=g.path(['J8','1'],['U2','10'],1.25);sense=g.path(['J8','1'],['J101','9'],1.25e-6);to_c53=g.path(['J8','1'],['C53','1'],1.25);from_c53=g.path(['C53','1'],['U2','10'],1.25)
 assert all(x['found_without_zones'] for x in (feed,sense,to_c53,from_c53))
 c53=b.FindFootprintByReference('C53');land=[p for p in c53.Pads() if p.GetNumber()=='1'][0]
 routed=[g.items[uid] for uid in feed['track_UUIDs']]
 touches_land=any(land.HitTest(t.GetStart(),0) or land.HitTest(t.GetEnd(),0) for t in routed)
 shared=sorted(set(feed['track_UUIDs'])&set(sense['track_UUIDs']))
 assert touches_land,'The final main battery route must actually touch C53.1'
 assert not shared,'The battery ADC Kelvin branch must not share main-current tracks'
 proof={'final_pcb_sha256':source,'native_drc_sha256':sha(drcpath),'native_drc':{'violations':0,'unconnected_items':0,'schematic_parity':0,'ignored':[]},'C53_final_pose_mm':xy(c53.GetPosition()),'main_feed':feed,'J8_to_C53':to_c53,'C53_to_TPS':from_c53,'sense_feed':sense,'main_route_touches_C53_1':touches_land,'shared_main_and_kelvin_track_UUIDs':shared,'assumptions':'One complete native segment route,35umCu,20C; contact and cable resistance excluded; not transient/EMI certification.'}
 for name in ('v2_power_battery_sense_fix.json','v2_short_battery_feed.json'):
  file=ROOT/'audit'/name;doc=json.loads(file.read_text(encoding='utf8'));doc['final_validation']=proof;doc['status']='final native source: DRC0/unconnected0/parity0, C53 main-feed land reached, Kelvin shared-track count0';file.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
 dest=ROOT/'audit/v2_power_final_feed_check.json';dest.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8');assert sha(pcb)==source
 print(json.dumps({'feed_mm':feed['route_segment_length_mm'],'R20_mohm':feed['one_route_R20_mohm'],'sense_mm':sense['route_segment_length_mm'],'C53_feed':touches_land,'shared_tracks':len(shared),'sha256':source}))
if __name__=='__main__':main()
