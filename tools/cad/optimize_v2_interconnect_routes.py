"""Retain reviewed ADC/I2C routes and add only local vertical-header branches."""
from pathlib import Path
import json, math, subprocess, types
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
import complete_v2_routes as base
ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'audit/ina219_vertical_interconnect_2026_10_12'
PCB=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
KEEP=[]
def xy(p):return k.ToMM(p.x),k.ToMM(p.y)
def vec(p):return k.VECTOR2I(k.FromMM(p[0]),k.FromMM(p[1]))
def uid(t):return str(t.m_Uuid.AsString())
def drc(label):
 p=AUDIT/('logic_preserved_'+label+'_drc.json')
 subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--refill-zones','--save-board','-o',str(p),str(PCB)],check=True,stdout=subprocess.PIPE)
 return json.loads(p.read_text(encoding='utf-8'))
def main():
 b=k.LoadBoard(str(PCB));old=k.LoadBoard(str(AUDIT/'MeshRepeater2_Logic_before.kicad_pcb'));KEEP.extend([b,old])
 nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
 oldids={uid(t)for t in old.GetTracks()}
 removed=[];retained=[]
 for t in list(b.GetTracks()):
  if t.GetNetname() in ['SDA','SCL','BAT'] or (t.GetNetname() in ['FILTER_OUT','SYS_3V3'] and uid(t)not in oldids):
   removed.append(uid(t));b.Remove(t);KEEP.append(t)
 for t in old.GetTracks():
  if t.GetNetname() not in ['SDA','SCL','BAT']:continue
  a,z=xy(t.GetStart()),xy(t.GetEnd())
  if t.GetNetname()=='BAT' and max(a[0],z[0])>64.61 and min(a[1],z[1])>47.69:continue
  u=t.Duplicate();u.SetUuid(t.m_Uuid);u.SetNet(nets[t.GetNetname()]);b.Add(u);retained.append(uid(u))
 # Existing BAT trace ends at(64.6,47.7). Two45/90segments reach the new
 # battery-sense pin without rerouting the distant ADC divider escape.
 for a,z in [((64.6,47.7),(73.0,47.7)),((73.0,47.7),(74.3,49.0))]:
  t=k.PCB_TRACK(b);t.SetStart(vec(a));t.SetEnd(vec(z));t.SetWidth(k.FromMM(.25));t.SetLayer(k.B_Cu);t.SetNet(nets['BAT']);t.SetLocked(True);b.Add(t)
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(PCB),b)
 router=types.ModuleType('retained_i2c_router');router.__file__=base.__file__
 code=Path(base.__file__).read_text(encoding='utf-8').replace('edge=.3+','edge=.55+')
 code=code.replace('if logic:rect(arr,(12,30.5,24,45.5),.31)','if logic:\n   rect(arr,(12,30.5,24,45.5),.31)\n   rect(arr,(31,.5,45,12),.31)')
 exec(code,router.__dict__)
 routes=[]
 for iteration in range(4):
  d=drc(str(iteration));b=k.LoadBoard(str(PCB));KEEP.append(b)
  lookup={uid(t):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for p in f.Pads():lookup[uid(p)]=p
  if not d['unconnected_items']:break
  for pair in d['unconnected_items']:
   a,z=pair['items'];ai,zi=lookup.get(a['uuid']),lookup.get(z['uuid'])
   if ai is None or zi is None:raise RuntimeError('Unknown missing endpoint')
   net=ai.GetNetname()
   if net not in ['SDA','SCL','FILTER_OUT','SYS_3V3']:raise RuntimeError('Unexpected missing net '+net)
   start=tuple(a['pos'][p]for p in ['x','y']);end=tuple(z['pos'][p]for p in ['x','y'])
   width=.8 if net=='FILTER_OUT' else .2 if net=='SDA' else .25
   selected=router
   if net=='SYS_3V3':
    # J201.7 returns only INA219's <1mA supply to POWER; it is not a bulk
    # load feed. Use0.25mm in the0.74mm space between neighbouringPTHlands.
    selected=types.ModuleType('ina_supply_router');selected.__file__=base.__file__
    exec(code.replace('CLEAR=.275','CLEAR=.225'),selected.__dict__)
   routes.append(selected.route(b,net,start,end,width,base.item_layers(a['description']),base.item_layers(z['description']),True,base.component_points(b,ai),base.component_points(b,zi)))
   k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(PCB),b)
  k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(PCB),b)
 d=drc('final')
 (AUDIT/'logic_retained_route_optimization.json').write_text(json.dumps({'preserved_SDA_SCL_BAT_old_track_ids':retained,'removed_recreated_routes':removed,'new_i2c_branches':routes,'battery_local_new_segments':2,'DRC_counts':{n:len(d.get(n,[]))for n in ['violations','unconnected_items','schematic_parity']},'DRC_violations':d['violations']},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'DRC':{n:len(d.get(n,[]))for n in ['violations','unconnected_items','schematic_parity']}}),flush=True)
if __name__=='__main__':main()
