"""Read-only before/after copper identity and star topology proof."""
from pathlib import Path
import json,hashlib,math
import pcbnew as k
from audit_v2_routing_engineering import TraceGraph,uid,mm
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copper(b,net=None):
 rows={}
 for t in b.GetTracks():
  if net is not None and t.GetNetname() not in net:continue
  row={'net':t.GetNetname(),'start':mm(t.GetStart()),'end':mm(t.GetEnd())}
  if isinstance(t,k.PCB_VIA):row.update(kind='via',drill_mm=k.ToMM(t.GetDrill()),diameter_mm=k.ToMM(t.GetWidth(k.F_Cu)))
  else:row.update(kind='track',width_mm=k.ToMM(t.GetWidth()),layer=b.GetLayerName(t.GetLayer()))
  rows[uid(t)]=row
 return rows
def pads(b):
 return {(f.GetReference(),p.GetNumber()):(mm(p.GetPosition()),mm(p.GetSize()),mm(p.GetDrillSize()),p.GetOrientationDegrees(),int(p.GetShape()),int(p.GetAttribute()),str(p.GetLayerSet().FmtBin()),p.GetNetname()) for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()}
def main():
 before=ROOT/'audit/routing_logic_star/before_star.kicad_pcb';after=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';initial={str(p.relative_to(ROOT)):sha(p) for p in (before,after)}
 bs=[k.LoadBoard(str(p)) for p in (before,after)];old,new=[copper(b) for b in bs];g=TraceGraph(bs[1]);j11=g.pads[('J11','2')][0]
 touching={n for n in g.edges[j11] if isinstance(g.items[n],k.PCB_TRACK)}
 star=g.path(['M1','9'],['FB1','1'],.5,banned=touching|{j11})
 changed={n:{'before':old[n],'after':new[n]} for n in set(old)&set(new) if old[n]!=new[n]}
 protected={'/ANT_RF','/ANT_SMA','/RADIO_3V3'}
 result={'stage':'FINAL_LOGIC_COPPER_COMPARISON','source_sha256':initial,'all_numbered_pad_geometries_and_assigned_nets_unchanged':pads(bs[0])==pads(bs[1]),'RF_center_and_local_RADIO_3V3_copper_unchanged':copper(bs[0],protected)==copper(bs[1],protected),'all_GPIO_footprint_positions_unchanged':{f.GetReference():(mm(f.GetPosition()),f.GetOrientationDegrees()) for f in bs[0].GetFootprints()}=={f.GetReference():(mm(f.GetPosition()),f.GetOrientationDegrees()) for f in bs[1].GetFootprints()},'MCU_to_FB1_without_J11_junction_copper':star,'J11_junction_excluded_item_UUIDs':sorted(touching|{j11}),'added_copper_UUIDs':{n:new[n] for n in set(new)-set(old)},'removed_copper_UUIDs':{n:old[n] for n in set(old)-set(new)},'changed_surviving_copper_UUIDs':changed,'unchanged_inputs_at_end':all(sha(ROOT/p)==digest for p,digest in initial.items()),'scope':'Native pad identity, preserved local RF/modem geometry and conductive star topology; no EMI/transient test or zero source/common-ground impedance claim.'}
 result['ok']=all(result[n] for n in ['all_numbered_pad_geometries_and_assigned_nets_unchanged','RF_center_and_local_RADIO_3V3_copper_unchanged','all_GPIO_footprint_positions_unchanged','unchanged_inputs_at_end']) and not star['found_without_zones']
 out=ROOT/'audit/v2_logic_star_fix.json';out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps({'ok':result['ok'],'added':len(result['added_copper_UUIDs']),'removed':len(result['removed_copper_UUIDs']),'changed':len(changed),'star_has_no_alternate_interbranch_join':not star['found_without_zones'],'report':str(out)},ensure_ascii=True))
 if not result['ok']:raise SystemExit(1)
if __name__=='__main__':main()
