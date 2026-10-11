"""Final local geometry corrections found by native DRC and mechanics."""
import argparse,json,subprocess
from finish_v2_copper import ROOT,k,xy,vec,stub,REMOVED

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',choices=['POWER','LOGIC'],required=True);args=ap.parse_args()
 name='MeshRepeater2_'+args.board.title();project=ROOT/'design'/name;pcb=project/(name+'.kicad_pcb');b=k.LoadBoard(str(pcb));changes=[]
 ref,target=('J101',(64.15,11)) if args.board=='POWER' else ('J201',(76.85,49))
 f=next(f for f in b.GetFootprints() if f.GetReference()==ref);before=xy(f.GetPosition());old={p.GetNumber():xy(p.GetPosition()) for p in f.Pads()}
 if before!=target:
  f.SetPosition(vec(target))
  for p in f.Pads():
   for layer in (k.F_Cu,k.B_Cu):
    if not p.IsOnLayer(layer):continue
    template=k.PCB_TRACK(b);template.SetLayer(layer);template.SetWidth(k.FromMM(.8 if p.GetNetname() in ('GND','FILTER_OUT') else .25));template.SetNetCode(p.GetNetCode())
    stub(b,old[p.GetNumber()],xy(p.GetPosition()),template)
  changes.append({'connector_shift':ref,'from':before,'to':target,'clearance_reason':'1mm added to washer/hex-standoff clearance'})
  model=json.loads((project/'model.json').read_text(encoding='utf-8'))
  for p in model['parts']:
   if p['ref']==ref:p['x'],p['y']=target
  (project/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
 if args.board=='LOGIC':
  for f in b.GetFootprints():
   for p in f.Pads():
    if f.GetReference()=='U4' and p.GetNumber()=='3':
     net=p.GetNet();net.SetNetname('unconnected-(U4-INT{slash}SQW-Pad3)')
 for z in b.Zones():
  if z.GetNetname()=='GND' and not z.GetIsRuleArea():z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
 audit=ROOT/'audit'/('routing_'+args.board.lower());cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'
 for i in range(8):
  k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(pcb),b)
  report=audit/f'drc_refine_{i}.json';subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--schematic-parity','-o',str(report),str(pcb)],check=True,stdout=subprocess.PIPE)
  drc=json.loads(report.read_text(encoding='utf-8'));lookup={t.m_Uuid.AsString():t for t in b.GetTracks()};remove=[]
  for v in drc['violations']:
   if v['type']=='track_dangling':remove.extend(x['uuid'] for x in v['items'] if x['uuid'] in lookup)
   elif v['type'] in ('items_not_allowed','track_not_centered_on_via','clearance','hole_to_hole'):
    # A new stitching via is disposable; functional signal and power traces
    # are never discarded to hide a clearance failure.
    for x in v['items']:
     t=lookup.get(x['uuid'])
     if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND':remove.append(x['uuid'])
  if not remove:break
  for uid in set(remove):
   t=lookup[uid];changes.append({'remove_obsolete_stub_or_conflicting_ground_stitch':uid,'net':t.GetNetname(),'position':xy(t.GetStart())});b.Remove(t);REMOVED.append(t)
 (audit/'refinement_log.json').write_text(json.dumps({'changes':changes,'final_report':str(report.relative_to(ROOT)),'unconnected':len(drc['unconnected_items']),'parity':len(drc['schematic_parity'])},indent=2),encoding='utf-8')
 print(args.board,'unconnected',len(drc['unconnected_items']),'parity',len(drc['schematic_parity']))
 for v in drc['violations']:
  if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance'):print(json.dumps(v,ensure_ascii=False))
if __name__=='__main__':main()
