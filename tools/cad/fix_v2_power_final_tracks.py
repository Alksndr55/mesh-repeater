"""Remove exact duplicate POWER tracks and separate the negative Kelvin exit.

No other native object is changed. Exact saved S-expression checks bracket
the patch; the deduplicated union is equal except for one explicit segment.
"""
from finish_v2_markings import ROOT,k,v
from sync_v2_native_metadata import parse,first_difference
from pathlib import Path
import collections,hashlib,json,subprocess

PCB=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb'
BASELINE=ROOT/'audit/ina219_and_vertical_2026_10_12/power_patch/before_power.kicad_pcb'
OUT=ROOT/'audit/ina219_and_vertical_2026_10_12/final_track_patch'
KELVIN='689c50b2-29a2-4760-b5e3-4f055e8a820e'
KEEP=[]

def sha(data):return hashlib.sha256(data).hexdigest()
def uuid(node):
 return next(q[1].strip('"')for q in node if isinstance(q,list)and q and q[0]=='uuid')
def tracks(tree):return {uuid(q):q for q in tree if isinstance(q,list)and q and q[0]=='segment'}
def without_tracks(tree):return [q for q in tree if not(isinstance(q,list)and q and q[0]=='segment')]
def signature(t):
 endpoints=sorted([[t.GetStart().x,t.GetStart().y],[t.GetEnd().x,t.GetEnd().y]])
 return json.dumps([t.GetNetname(),int(t.GetLayer()),t.GetWidth(),endpoints],separators=(',',':'))
def main():
 initial=PCB.read_bytes();source_sha=sha(initial)
 assert source_sha=='08fee4d2f8f42a855a8bd4ad5e6092be5eeb613137ffdd8e58b7419a51cb223e','Unexpected source revision; review before applying'
 project=PCB.with_suffix('.kicad_pro');project_initial=project.read_bytes()
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'before_power.kicad_pcb').write_bytes(initial)
 before_tree=parse(initial.decode('utf8'));before_tracks=tracks(before_tree)
 baseline_ids=set(tracks(parse(BASELINE.read_text(encoding='utf8'))))
 b=k.LoadBoard(str(PCB));KEEP.append(b)
 native_tracks={t.m_Uuid.AsString():t for t in b.GetTracks()if type(t)==k.PCB_TRACK}
 assert len(native_tracks)==len(before_tracks)
 groups=collections.defaultdict(list)
 for id,t in native_tracks.items():groups[signature(t)].append(id)
 duplicates=[ids for ids in groups.values()if len(ids)>1]
 assert len(duplicates)==11 and all(len(ids)==2 for ids in duplicates),duplicates
 removals=[]
 for ids in duplicates:
  previous=[id for id in ids if id in baseline_ids]
  retained=previous[0]if previous else ids[0]
  removed=next(id for id in ids if id!=retained)
  removals.append({'retained_uuid':retained,'removed_uuid':removed,'retained_pre_ina_uuid':retained in baseline_ids,'both_duplicates_pre_ina':len(previous)==2,'identical_copper_signature':signature(native_tracks[removed])})
 expected={id:node for id,node in before_tracks.items()if id not in {q['removed_uuid']for q in removals}}
 # Independent expected saved node preserves every segment attribute and UUID.
 kelvin_before=json.loads(json.dumps(expected[KELVIN]))
 expected[KELVIN]=json.loads(json.dumps(expected[KELVIN]))
 start=next(q for q in expected[KELVIN]if isinstance(q,list)and q and q[0]=='start')
 assert start[1:]==['46.5','4.099999'],start
 start[1:]=['47.2','4.1']
 for row in removals:b.Remove(native_tracks[row['removed_uuid']])
 t=native_tracks[KELVIN]
 assert t.GetStart()==v(46.5,4.099999) and t.GetEnd()==v(47.2,4.8)
 assert k.LayerName(t.GetLayer())=='B.Cu'and t.GetWidth()==k.FromMM(.25)
 r71=next(f for f in b.GetFootprints()if f.GetReference()=='R71')
 pad2=next(p for p in r71.Pads()if p.GetNumber()=='2')
 # These requested decimal coordinates have exact integer-nanometre values;
 # avoid FromMM's binary-float truncation of4.1 to4.099999.
 newstart=k.VECTOR2I(47200000,4100000)
 assert pad2.HitTest(newstart), 'New pickup must lie inside R71.2'
 t.SetStart(newstart)
 newgroups=collections.Counter(signature(t)for t in b.GetTracks()if type(t)==k.PCB_TRACK)
 assert not any(count>1 for count in newgroups.values())
 try:
  assert PCB.read_bytes()==initial,'Concurrent native mutation'
  k.SaveBoard(str(PCB),b)
  if project.read_bytes()!=project_initial:project.write_bytes(project_initial)
  final=PCB.read_bytes();after_tree=parse(final.decode('utf8'));after_tracks=tracks(after_tree)
  assert after_tracks==expected,('Unexpected segment mutation',[(id,expected.get(id),after_tracks.get(id))for id in sorted(set(expected)|set(after_tracks))if expected.get(id)!=after_tracks.get(id)])
  assert without_tracks(before_tree)==without_tracks(after_tree),('Non-track native mutation',first_difference(without_tracks(before_tree),without_tracks(after_tree)))
  cli='C:/Program Files/KiCad/10.0/bin/kicad-cli.exe';drcpath=OUT/'POWER_strict_drc.json'
  run=subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--schematic-parity','-o',str(drcpath),str(PCB)],capture_output=True,text=True,encoding='utf8',errors='replace')
  (OUT/'drc_console.txt').write_text(run.stdout+run.stderr,encoding='utf8')
  drc=json.loads(drcpath.read_text(encoding='utf8'))
  counts={name:len(drc.get(name,[]))for name in ['violations','unconnected_items','schematic_parity']}
  assert run.returncode==0 and not any(counts.values()),('Strict DRC failed',run.returncode,counts)
  result={'status':'ONLY_EXACT_DUPLICATES_AND_NEGATIVE_KELVIN_EXIT_CHANGED','source_pcb_sha256':source_sha,'final_pcb_sha256':sha(final),'baseline_sha256':sha(BASELINE.read_bytes()),'removed_track_count':len(removals),'removals':removals,'kelvin_uuid':KELVIN,'kelvin_before':kelvin_before,'kelvin_after':expected[KELVIN],'kelvin_new_start_inside_R71_pad2':True,'duplicates_preserve_identical_copper_union':True,'all_other_track_attributes_and_uuid_preserved':True,'all_non_segment_native_tokens_exactly_unchanged':True,'remaining_exact_track_duplicates':0,'strict_drc':counts,'drc_exit_code':run.returncode,'saved_no_refill':True,'unchanged':['vias','footprints and all fields','positions and rotations','3D','nets and schematic paths','zones and existing filled geometry','silk/Fab/caption styles','project settings']}
  (OUT/'proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps(result,ensure_ascii=False),flush=True)
 except BaseException:
  PCB.write_bytes(initial);project.write_bytes(project_initial);raise
if __name__=='__main__':main()
