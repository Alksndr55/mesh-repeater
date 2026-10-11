"""Replace only audited common SYS power trunk, preserving all pin assignments."""
from pathlib import Path
import json, hashlib, shutil, subprocess
import complete_v2_routes as r
import pcbnew as k
ROOT=r.ROOT
import sys
sys.path.insert(0,str(ROOT/'tools'))
from plan_v2_routing_corrections import manual, desc
REMOVED=[]
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
AUDIT=ROOT/'audit/routing_logic_star';AUDIT.mkdir(exist_ok=True)
def uid(t):return str(t.m_Uuid.AsString())
def hashp(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 backup=AUDIT/'before_star.kicad_pcb'
 if backup.exists():raise RuntimeError('Already started: do not replay destructive initial cut')
 shutil.copy2(P,backup)
 source=hashp(P);b=k.LoadBoard(str(P));lookup={uid(t):t for t in b.GetTracks()}
 audit=json.loads((ROOT/'audit/v2_routing_engineering.json').read_text(encoding='utf-8'))
 old=audit['boards']['LOGIC'];cut=set(old['MCU_modem_common_SYS_feed']['track_UUIDs']) | {'eb7d2d32-8a09-47f7-9d77-5b31c103ed5a','82a80147-dbc9-45db-94df-65eb53d638a5'}
 removed=[]
 def remove(t,reason):
  removed.append(dict(desc(b,t),net=t.GetNetname(),reason=reason));b.Remove(t);REMOVED.append(t)
 for n in cut:
  if n not in lookup:raise RuntimeError('Baseline trunk missing '+n)
  remove(lookup[n],'old common SYS trunk or C22-FB tie')
 def segs(points,layer):return [dict(start=a,end=z,layer=layer) for a,z in zip(points,points[1:])]
 routes=[manual(b,'SYS_3V3','MCU_bulk',segs([[86,25.54],[84,25.54],[77.06,18.6],[34.3,18.6],[29.05,13.35]],'B.Cu')+segs([[29.05,13.35],[29.05,12.25]],'F.Cu')),manual(b,'SYS_3V3','FB1_input',segs([[86,25.54],[86,24],[78.8,16.8],[34.3,16.8],[32.65,15.15]],'B.Cu')+segs([[32.65,15.15],[32.65,14.45]],'F.Cu'))]
 protected={'/ANT_RF','/ANT_SMA','/RADIO_3V3','FILTER_OUT'}
 conflicts={x['uuid'] for route in routes for x in route['nonmatching_track_conflicts_for_local_rework']}
 for n in conflicts:
  t=lookup.get(n)
  if t is None or t in REMOVED:continue
  if t.GetNetname() in protected:raise RuntimeError('Protected local geometry conflict '+t.GetNetname())
  remove(t,'local conflicting signal or GND stitch; connectivity restored after power reservation')
 net=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='SYS_3V3')
 added=[]
 for route in routes:
  for seg in route['segments']:
   t=k.PCB_TRACK(b);t.SetStart(r.vec(seg['start']));t.SetEnd(r.vec(seg['end']));t.SetWidth(k.FromMM(.8));t.SetLayer(k.F_Cu if seg['layer']=='F.Cu' else k.B_Cu);t.SetNet(net);t.SetLocked(True);b.Add(t);added.append(dict(desc(b,t),branch=route['label']))
 for at,label in [([29.05,13.35],'MCU_bulk'),([32.65,15.15],'FB1_input')]:
  v=k.PCB_VIA(b);v.SetPosition(r.vec(at));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(net);v.SetLocked(True);b.Add(v);added.append(dict(desc(b,v),branch=label))
 # Local MCU bulk links are local feed, not the modem upstream branch.
 for n in ['9ee7ca94-a4a6-40ac-bee1-e7a9e889230a','805fcbff-6714-4649-b87f-b6c1bf646788']:
  lookup[n].SetWidth(k.FromMM(.6))
 rules=P.with_suffix('.kicad_dru')
 rules.write_text('(version 1)\n(rule "RF GND gap 0.25 mm" (layer F.Cu) (condition "((A.NetName == \'/ANT_RF\' || A.NetName == \'/ANT_SMA\') && B.NetName == \'GND\') || ((B.NetName == \'/ANT_RF\' || B.NetName == \'/ANT_SMA\') && A.NetName == \'GND\')") (constraint clearance (min 0.25mm)))\n',encoding='utf-8')
 for z in b.Zones():
  if z.GetNetname()=='GND' and not z.GetIsRuleArea():
   z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
   if z.GetZoneName().startswith('RF_CPW_GND'):z.SetLocalClearance(k.FromMM(.25))
 k.SaveBoard(str(P),b)
 (AUDIT/'star_initial_changes.json').write_text(json.dumps({'source_sha256':source,'removed':removed,'added_critical_star':added,'routes':routes,'local_MCU_links_widened_to_mm':.6,'RF_rule_native_names_corrected':True},indent=2),encoding='utf-8')
 cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
 subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--schematic-parity','--refill-zones','--save-board','-o',str(AUDIT/'drc_initial.json'),str(P)],check=True)
 print('Reserved star branches; restore missing signal and auxiliary SYS connections using native DRC.')
if __name__=='__main__':main()
