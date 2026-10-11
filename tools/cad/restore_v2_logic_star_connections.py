"""Restore local signal cuts around reserved power star; native DRC after each round."""
from pathlib import Path
import argparse,json,subprocess,math
import complete_v2_routes as r
import pcbnew as k
ROOT=r.ROOT;P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
import types
strict=types.ModuleType('star_strict_router');strict.__file__=r.__file__
exec(Path(r.__file__).read_text(encoding='utf-8').replace('CLEAR=.225','CLEAR=.275').replace('edge=.3+','edge=.55+'),strict.__dict__)
r=strict
A=ROOT/'audit/routing_logic_star';CLI='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe';REMOVED=[]
def uid(t):return str(t.m_Uuid.AsString())
def check(label):
 out=A/('drc_'+label+'.json')
 subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--schematic-parity','--refill-zones','--save-board','-o',str(out),str(P)],check=True,stdout=subprocess.PIPE)
 return json.loads(out.read_text(encoding='utf-8'))
def remove(b,t,reason,log):
 log.append({'remove':uid(t),'net':t.GetNetname(),'at':r.xy(t.GetStart()),'reason':reason});b.Remove(t);REMOVED.append(t)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rounds',type=int,default=4);ap.add_argument('--fix-launch',action='store_true');args=ap.parse_args()
 log=[];b=k.LoadBoard(str(P));initial=json.loads((A/'star_initial_changes.json').read_text(encoding='utf-8'));added={x['uuid']:x for x in initial['added_critical_star']};lookup={uid(t):t for t in b.GetTracks()}
 if args.fix_launch:
  points={'MCU_bulk':[[86,25.54],[84.46,27.08],[75.98,18.6],[34.3,18.6],[29.05,13.35]],'FB1_input':[[86,25.54],[84.5,25.54],[75.76,16.8],[34.3,16.8],[32.65,15.15]]}
  for label,pts in points.items():
   items=[x for x in initial['added_critical_star'] if x.get('branch')==label and x['kind']=='track' and x['layer']=='B.Cu']
   for x,(s,e) in zip(items,zip(pts,pts[1:])):
    t=lookup[x['uuid']];t.SetStart(r.vec(s));t.SetEnd(r.vec(e));log.append({'adjust_launch':uid(t),'start':s,'end':e})
  k.SaveBoard(str(P),b)
 drc=check('launch')
 for iteration in range(args.rounds):
  b=k.LoadBoard(str(P));lookup={uid(t):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for pd in f.Pads():lookup[uid(pd)]=pd
  disposable=set()
  protected=set(added)
  if (A/'finish_changes.json').exists():
   finish=json.loads((A/'finish_changes.json').read_text(encoding='utf-8'))
   protected.update(x[key] for x in finish for key in ('join_C25_GND_via','join_C25_GND_track') if key in x)
  for v in drc['violations']:
   if v['type'] in ('track_dangling','via_dangling'):
    for x in v['items']:
     if x['uuid'] in lookup and x['uuid'] not in protected and isinstance(lookup[x['uuid']],k.PCB_TRACK):disposable.add(x['uuid'])
   elif v['type'] in ('shorting_items','clearance','copper_edge_clearance','hole_to_hole','items_not_allowed','track_not_centered_on_via'):
    for x in v['items']:
     t=lookup.get(x['uuid'])
     if isinstance(t,k.PCB_TRACK) and x['uuid'] not in protected and t.GetNetname() not in ('/ANT_RF','/ANT_SMA','/RADIO_3V3','FILTER_OUT'):
      disposable.add(x['uuid'])
  for n in disposable:remove(b,lookup[n],'old orphan or local conflicting signal/GND copper; reconnect from pad contracts',log)
  k.SaveBoard(str(P),b);drc=check('clean_'+str(iteration))
  if not drc['unconnected_items']:break
  b=k.LoadBoard(str(P));lookup={uid(t):t for t in b.GetTracks()}
  for f in b.GetFootprints():
   for pd in f.Pads():lookup[uid(pd)]=pd
  # Reserve FB1 branch as a geometric obstacle while joining auxiliary MCU loads.
  guard=k.NETINFO_ITEM(b,'V2_RESERVED_FB_POWER',999);b.Add(guard)
  branch=[lookup[n] for n,x in added.items() if x.get('branch')=='FB1_input' and n in lookup]
  sysnet=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='SYS_3V3')
  c21=next(p for f in b.GetFootprints() if f.GetReference()=='C21' for p in f.Pads() if p.GetNumber()=='1')
  failures=[]
  for pair in drc['unconnected_items']:
   a,z=pair['items']
   if a['uuid'] not in lookup or z['uuid'] not in lookup:continue
   ai,zi=lookup[a['uuid']],lookup[z['uuid']];net=ai.GetNetname()
   if net!=zi.GetNetname():raise RuntimeError(pair)
   width=.5 if net=='GND' else .4 if net=='SYS_3V3' else .25
   if net=='SYS_3V3':
    main_ids={uid(t) for t in b.GetConnectivity().GetConnectedItems(ai)}
    target=zi if uid(c21) in main_ids or uid(ai)==uid(c21) else ai
    ai=c21;zi=target
   for t in branch:t.SetNet(guard)
   start=tuple(a['pos'][p] for p in ('x','y'));end=tuple(z['pos'][p] for p in ('x','y'))
   try:
    sp=r.component_points(b,ai);tp=r.component_points(b,zi)
    info=r.route(b,net,start,end,width,r.item_layers(a['description']),r.item_layers(z['description']),True,sp,tp);log.append(info)
   except RuntimeError as exc:failures.append(str(exc))
   finally:
    for t in branch:t.SetNet(sysnet)
  b.Remove(guard)
  k.SaveBoard(str(P),b);drc=check('route_'+str(iteration));print('round',iteration,'missing',len(drc['unconnected_items']),'failures',len(failures),flush=True)
  if failures:print(failures,flush=True)
 (A/'restore_changes.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
 print('remaining types',{v['type'] for v in drc['violations']},'missing',len(drc['unconnected_items']),'parity',len(drc['schematic_parity']))
if __name__=='__main__':main()
