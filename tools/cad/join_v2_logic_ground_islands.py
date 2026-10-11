"""Join the two proven local ground islands with new octilinear GND copper.

All existing footprints, pads, tracks, vias, zone definitions and RF geometry
remain unchanged. Candidate is checked in audit first; --apply copies it only
after strict native DRC confirms zero unconnected items and zero copper errors.
"""
from complete_v2_routes import ROOT,k,xy,route
from test_v2_ground_fill import functional
from pathlib import Path
import argparse,json,hashlib,subprocess

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');a=ap.parse_args()
 source=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
 srcsha=digest(source);b=k.LoadBoard(str(source));before=functional(b);original_uids={t.m_Uuid.AsString() for t in b.GetTracks()}
 diagnostic=json.loads((ROOT/'audit/logic_ground_island_diagnosis.json').read_text(encoding='utf8'));assert diagnostic['source_sha256']==srcsha
 orphan_names=set()
 for z in diagnostic['zones']:
  for i in z['islands']:
   if (z['name']=='GND_TOP' and i['index'] in (5,7)) or (z['name']=='GND_REFERENCE' and i['index'] in (7,9)):
    orphan_names.update(c['name'] for c in i['contacts'])
 target_names=set(c['name'] for z in diagnostic['zones'] for i in z['islands'] for c in i['contacts'])-orphan_names
 targets=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if f.GetReference()+'.'+p.GetNumber() not in target_names:continue
   for l,idx in [(k.F_Cu,0),(k.B_Cu,1)]:
    if p.IsOnLayer(l):targets.append((xy(p.GetPosition()),idx))
 for t in b.GetTracks():
  if t.m_Uuid.AsString() not in target_names:continue
  for l,idx in [(k.F_Cu,0),(k.B_Cu,1)]:
   if t.IsOnLayer(l):
    for pos in (t.GetStart(),t.GetEnd()):targets.append((xy(pos),idx))
 changes=[]
 for label,at,width in [('C21_GND',(28,10.35),.5),('R28_GND',(29.9,14.6),.5)]:
  changes.append(dict(label=label,**route(b,'GND',at,(1.5,1.5),width,(0,1),(0,1),True,[(at,0),(at,1)],targets)))
 k.ZONE_FILLER(b).Fill(b.Zones())
 # Temporarily exclude only the new authorised GND items from signature.
 added=[t for t in b.GetTracks() if t.m_Uuid.AsString() not in original_uids]
 assert all(t.GetNetname()=='GND' for t in added)
 for t in added:b.Remove(t)
 assert before==functional(b),'Existing functional copper changed'
 for t in added:b.Add(t)
 out=ROOT/'audit/ground_diagnosis/joined_ground.kicad_pcb';k.SaveBoard(str(out),b)
 settings=source.with_suffix('.kicad_pro').read_bytes();out.with_suffix('.kicad_pro').write_bytes(settings);out.with_suffix('.kicad_dru').write_bytes(source.with_suffix('.kicad_dru').read_bytes())
 (out.parent/'fp-lib-table').write_text((source.parent/'fp-lib-table').read_text(encoding='utf8').replace('${KIPRJMOD}',source.parent.as_posix()),encoding='utf8')
 drcout=out.with_name('joined_ground_drc.json');subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','-o',str(drcout),str(out)],check=True)
 drc=json.loads(drcout.read_text(encoding='utf8'));copper=[v for v in drc['violations'] if v['type'] not in ('silk_over_copper','silk_overlap','silk_edge_clearance','text_height','text_thickness','lib_footprint_mismatch','footprint_type_mismatch')]
 result={'source_sha256':srcsha,'changes':changes,'new_gnd_copper_uuids':[t.m_Uuid.AsString() for t in added],'existing_functional_copper_unchanged':True,'counts':{x:len(drc[x]) for x in ('violations','unconnected_items','ignored_checks')},'non_marking_violations':copper,'applied':False}
 if a.apply:
  assert not drc['unconnected_items'] and not drc['ignored_checks'] and not copper,result
  assert digest(source)==srcsha,'Source changed concurrently'
  source.write_bytes(out.read_bytes());source.with_suffix('.kicad_pro').write_bytes(settings);result['applied']=True;result['result_sha256']=digest(source)
 (ROOT/'audit/logic_ground_island_fix.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=True),flush=True)
if __name__=='__main__':main()
