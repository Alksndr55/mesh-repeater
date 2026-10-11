"""Test zone-geometry hypotheses in audit copies; never edit the source board."""
from pathlib import Path
import hashlib,json,subprocess
from diagnose_v2_ground_islands import ROOT,k

SOURCE=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
OUT=ROOT/'audit/ground_diagnosis';OUT.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def functional(b):
 rows=[]
 for f in b.GetFootprints():
  rows.append(('FP',f.GetReference(),f.GetValue(),f.GetPosition().x,f.GetPosition().y,f.GetOrientationDegrees(),f.GetLayer(),str(f.GetPath().AsString())))
  for p in f.Pads():rows.append(('PAD',f.GetReference(),p.GetNumber(),p.GetNetname(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,p.GetDrillSize().x,p.GetDrillSize().y,p.GetOrientationDegrees()))
 for t in b.GetTracks():rows.append(('TRACK',t.m_Uuid.AsString(),t.GetNetname(),t.GetLayer(),t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth(),t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y,t.GetDrill() if isinstance(t,k.PCB_VIA) else 0))
 return hashlib.sha256(json.dumps(sorted(rows),sort_keys=True).encode()).hexdigest()
def union(b,layer):
 result=k.SHAPE_POLY_SET()
 for z in b.Zones():
  if z.GetNetname()=='GND' and not z.GetIsRuleArea() and z.IsOnLayer(layer):
   p=k.SHAPE_POLY_SET(z.GetFilledPolysList(layer));p.Unfracture();result.BooleanAdd(p)
 return result
def main():
 original_sha=sha(SOURCE);original=k.LoadBoard(str(SOURCE));signature=functional(original);copper={l:union(original,l) for l in (k.F_Cu,k.B_Cu)};results=[]
 for variant in ['remove_unconnected_islands','equal_priorities','remove_duplicate_rf_zone']:
  b=k.LoadBoard(str(SOURCE));modifications=[];removed=[]
  for z in list(b.Zones()):
   if z.GetNetname()!='GND' or z.GetIsRuleArea():continue
   if variant=='remove_unconnected_islands':
    z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS);modifications.append({'zone':z.GetZoneName(),'island_mode':'ALWAYS'})
   elif variant=='equal_priorities' and z.GetZoneName()=='RF_CPW_GND_1':z.SetAssignedPriority(0);modifications.append({'zone':z.GetZoneName(),'priority':0})
   elif variant=='remove_duplicate_rf_zone' and z.GetZoneName()=='RF_CPW_GND_1':
    modifications.append({'zone':z.GetZoneName(),'removed':True});removed.append(z);b.Remove(z)
  k.ZONE_FILLER(b).Fill(b.Zones());assert signature==functional(b)
  changes=[]
  for l in (k.F_Cu,k.B_Cu):
   before=k.SHAPE_POLY_SET(copper[l]);after=union(b,l);before.BooleanXor(after);before.Unfracture();changes.append({'layer':k.LayerName(l),'xor_area_mm2':before.Area()/1e12,'xor_outlines':before.OutlineCount()})
  p=OUT/(variant+'.kicad_pcb');k.SaveBoard(str(p),b)
  settings=json.loads(SOURCE.with_suffix('.kicad_pro').read_text(encoding='utf8'));settings['meta']['filename']=p.with_suffix('.kicad_pro').name
  p.with_suffix('.kicad_pro').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf8')
  p.with_suffix('.kicad_dru').write_bytes(SOURCE.with_suffix('.kicad_dru').read_bytes())
  tables=(SOURCE.parent/'fp-lib-table').read_text(encoding='utf8').replace('${KIPRJMOD}',SOURCE.parent.as_posix());(OUT/'fp-lib-table').write_text(tables,encoding='utf8')
  drc=OUT/(variant+'_drc.json');subprocess.run(['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','-o',str(drc),str(p)],check=True,stdout=subprocess.DEVNULL)
  d=json.loads(drc.read_text(encoding='utf8'));row={'variant':variant,'modifications':modifications,'functional_invariant':signature,'functional_invariant_unchanged':functional(k.LoadBoard(str(p)))==signature,'ground_copper_geometry_delta':changes,'unconnected':d['unconnected_items'],'counts':{x:len(d[x]) for x in ('violations','unconnected_items','ignored_checks')}}
  results.append(row);(OUT/'hypothesis_tests_partial.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({name:row[name] for name in ('variant','functional_invariant_unchanged','ground_copper_geometry_delta','counts')},ensure_ascii=True),flush=True)
 result={'source_sha256':original_sha,'source_unchanged':sha(SOURCE)==original_sha,'results':results};(OUT/'hypothesis_tests.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
if __name__=='__main__':main()
