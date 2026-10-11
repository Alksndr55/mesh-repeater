"""Give the ADC cable a dedicated battery-pad branch; preserve load routes."""
from pathlib import Path
import hashlib, json, math, subprocess, sys
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
from complete_v2_routes import route, component_points, xy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_v2_routing_engineering import TraceGraph, uid
ROOT=Path(__file__).resolve().parents[2]
PCB=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb'
REMOVED=[]

def main():
 b=k.LoadBoard(str(PCB)); initial=hashlib.sha256(PCB.read_bytes()).hexdigest()
 plan=json.loads((ROOT/'audit/v2_routing_correction_plan.json').read_text())['BATsense']
 fps={f.GetReference():f for f in b.GetFootprints()}
 def pad(ref,pin):return next(p for p in fps[ref].Pads() if p.GetNumber()==pin)
 source,target=pad('J8','1'),pad('J101','9')
 lookup={uid(t):t for t in b.GetTracks()}
 deleted=[]
 for item in plan['connector_leaf_remove']:
  t=lookup[item['uuid']]; b.Remove(t);REMOVED.append(t);deleted.append(uid(t))
 # The detached old connector leaf must contain no other functional pads.
 reached=component_points(b,target)
 b.BuildConnectivity();g=TraceGraph(b);seen={uid(target)};q=[uid(target)]
 while q:
  n=q.pop()
  for z in g.edges[n]:
   if z not in seen:seen.add(z);q.append(z)
 other=[g.labels[u] for u in seen if u in g.labels and u!=uid(target)]
 if other:raise RuntimeError(('unexpected retained load in connector leaf',other))
 for u in sorted(seen):
  if u in lookup and u not in deleted:
   t=lookup[u];b.Remove(t);REMOVED.append(t);deleted.append(u)
 # Temporarily mark other BAT copper/pads as obstacles, except the battery
 # source pad. Restore every original net immediately after candidate routing.
 bat=source.GetNet();gnd=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='GND')
 changed=[]
 for t in b.GetTracks():
  if t.GetNetname()=='BAT': changed.append(t);t.SetNet(gnd)
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.GetNetname()=='BAT' and uid(p) not in (uid(source),uid(target)):
    changed.append(p);p.SetNet(gnd)
 # Existing load tracks exit this THT pad. Permit only a sub-pad source launch,
 # then route from a point to the left of the battery pad on B.Cu.
 start=(22.0,9.3)
 try:
  info=route(b,'BAT',start,xy(target.GetPosition()),.25,starts=(1,),ends=(0,1))
 finally:
  for t in changed:t.SetNet(bat)
 t=k.PCB_TRACK(b);t.SetStart(source.GetPosition());t.SetEnd(k.VECTOR2I(k.FromMM(start[0]),k.FromMM(start[1])));t.SetLayer(k.B_Cu);t.SetWidth(k.FromMM(.25));t.SetNet(bat);t.SetLocked(True);b.Add(t)
 k.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 g=TraceGraph(b);main_path=g.path(['J8','1'],['U2','10'],1.25);sense=g.path(['J8','1'],['J101','9'],1.25e-6)
 shared=set(main_path.get('track_UUIDs',[]))&set(sense.get('track_UUIDs',[]))
 if shared:raise RuntimeError(('sense still shares load tracks',list(shared)))
 if not sense['found_without_zones']:raise RuntimeError('Sense branch remains unconnected')
 k.SaveBoard(str(PCB),b)
 proof={'before_sha256':initial,'after_sha256':hashlib.sha256(PCB.read_bytes()).hexdigest(),'removed_connector_only_tracks':deleted,'route':info,'sense_path':sense,'main_path':main_path,'shared_main_tracks':sorted(shared),'source':'J8.1 battery connector pad','functional_values_changed':False}
 (ROOT/'audit/v2_power_battery_sense_fix.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'saved':True,'sense_length_mm':sense['route_segment_length_mm'],'shared_tracks':len(shared),'removed':len(deleted)}))
if __name__=='__main__':main()
