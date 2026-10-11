"""Centre the new auxiliary tap and join the identified C25 ground island."""
import json,subprocess,math
import complete_v2_routes as r
import pcbnew as k
ROOT=r.ROOT;P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';A=ROOT/'audit/routing_logic_star';REMOVED=[]
def uid(t):return str(t.m_Uuid.AsString())
def main():
 b=k.LoadBoard(str(P));log=[]
 for t in list(b.GetTracks()):
  if isinstance(t,k.PCB_VIA) and t.GetNetname()=='SYS_3V3' and math.dist(r.xy(t.GetPosition()),(76,18.6))<.001:
   t.SetPosition(r.vec((75.98,18.6)));log.append({'center_auxiliary_SYS_via':uid(t),'at':[75.98,18.6]})
  elif uid(t) in {'772c3bc5-b02e-43f6-8374-233271929e6e','7a0373e1-768e-4b99-809c-78c090fe0408','b94c1ba3-81df-4373-9ae9-c70b29f066dd'}:
   for get,setter in [(t.GetStart,t.SetStart),(t.GetEnd,t.SetEnd)]:
    x,y=r.xy(get());setter(r.vec((x-.02,y)))
   log.append({'translated_local_aux_SYS_link':uid(t),'dx_mm':-.02})
 ground=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='GND')
 v=k.PCB_VIA(b);v.SetPosition(r.vec((35.5,17.7)));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(ground);b.Add(v);log.append({'join_C25_GND_via':uid(v),'at':[35.5,17.7]})
 for s,e in zip([(33.95,17.3),(34.45,17.3),(34.85,17.7)],[(34.45,17.3),(34.85,17.7),(35.5,17.7)]):
  t=k.PCB_TRACK(b);t.SetStart(r.vec(s));t.SetEnd(r.vec(e));t.SetWidth(k.FromMM(.4));t.SetLayer(k.F_Cu);t.SetNet(ground);b.Add(t);log.append({'join_C25_GND_track':uid(t),'start':s,'end':e})
 k.SaveBoard(str(P),b)
 cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
 for i in range(6):
  out=A/('drc_finish_'+str(i)+'.json');subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--schematic-parity','--refill-zones','--save-board','-o',str(out),str(P)],check=True,stdout=subprocess.PIPE)
  drc=json.loads(out.read_text(encoding='utf-8'));lookup={uid(t):t for t in b.GetTracks()};remove=[]
  for violation in drc['violations']:
   if violation['type'] in ('track_dangling','via_dangling'):
    for item in violation['items']:
     if item['uuid'] in lookup:remove.append(item['uuid'])
  if not remove:break
  for n in set(remove):
   t=lookup[n];log.append({'remove_last_orphan_stub':n,'net':t.GetNetname()});b.Remove(t);REMOVED.append(t)
  k.SaveBoard(str(P),b)
 (A/'finish_changes.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
 print('types',{v['type'] for v in drc['violations']},'missing',len(drc['unconnected_items']),'parity',len(drc['schematic_parity']))
 for v in drc['violations']:
  if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance'):print(json.dumps(v,ensure_ascii=True))
if __name__=='__main__':main()
