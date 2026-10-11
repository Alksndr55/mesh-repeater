"""Match exact native assembly instances to approved local graphic variants.

Only the library identifier and model.footprint metadata change on the board.
Pad, Fab, courtyard, 3D, MPN, values and physical placement are invariant.
Rebuild schematic/netlist afterwards so its hidden Footprint agrees with PCB.
"""
from finish_v2_markings import ROOT,k,v,safe,invariant
import argparse,hashlib,json,re

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def local_geometry(f):
 rows=[]
 for p in f.Pads():
  row=['pad',p.GetNumber(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,p.GetDrillSize().x,p.GetDrillSize().y,p.GetOrientationDegrees(),int(p.GetShape()),int(p.GetDrillShape()),int(p.GetAttribute()),str(p.GetLayerSet().FmtBin()),p.GetOffset().x,p.GetOffset().y,p.GetRoundRectRadiusRatio(),p.GetChamferRectRatio()]
  rows.append(row)
 for g in f.GraphicalItems():
  if not isinstance(g,k.PCB_SHAPE):continue
  poly=g.GetPolyShape();chains=[]
  for i in range(poly.OutlineCount()):
   line=poly.COutline(i);chains.append([(line.CPoint(n).x,line.CPoint(n).y) for n in range(line.PointCount())])
  rows.append(['figure',g.GetLayer(),int(g.GetShape()),g.GetStart().x,g.GetStart().y,g.GetEnd().x,g.GetEnd().y,g.GetWidth(),int(g.GetFillMode()),chains])
 models=[]
 for m in f.Models():
  q=lambda a:[a.x,a.y,a.z]
  models.append([str(m.m_Filename),q(m.m_Offset),q(m.m_Rotation),q(m.m_Scale),m.m_Show,m.m_Opacity])
 data={'pad_and_fab_courtyard_silk_geometry':sorted(rows,key=lambda x:json.dumps(x)),'3d':models,'engineering_fields':sorted((g.GetName(),g.GetText()) for g in f.GetFields() if g.GetName() not in ('Reference','Value'))}
 return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
def masked_signature(b,old):
 current={f.GetReference():str(f.GetFPID().GetLibItemName()) for f in b.GetFootprints()}
 for f in b.GetFootprints():f.SetFPID(k.LIB_ID('Meshcore',old[f.GetReference()].split(':',1)[1]))
 result=invariant(b)
 for f in b.GetFootprints():f.SetFPID(k.LIB_ID('Meshcore',current[f.GetReference()]))
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pcb',required=True);ap.add_argument('--model',required=True);ap.add_argument('--out-model');ap.add_argument('--report');a=ap.parse_args()
 pcb=safe(a.pcb);modelpath=safe(a.model);outmodel=safe(a.out_model or modelpath);report=safe(a.report or ROOT/'audit'/(pcb.stem+'_footprint_variants.json'))
 srcsha=digest(pcb);modelsha=digest(modelpath);model=json.loads(modelpath.read_text(encoding='utf8'));parts={p['ref']:p for p in model['parts']};b=k.LoadBoard(str(pcb));fps={f.GetReference():f for f in b.GetFootprints()};assert set(fps)==set(parts)
 before=invariant(b);original={r:'Meshcore:'+str(f.GetFPID().GetLibItemName()) for r,f in fps.items()};lib=pcb.parent/'Meshcore.pretty';lib.mkdir(exist_ok=True);maps=[]
 for ref,f in sorted(fps.items()):
  part=parts[ref];old=original[ref];assert str(f.GetFPID().GetLibNickname())=='Meshcore'
  base=re.sub(r'__V2_[A-Za-z0-9_]+$','',old.split(':',1)[1]);name=base+'__V2_'+ref
  prototype=k.Cast_to_FOOTPRINT(f.Duplicate(False));prototype.SetPosition(v(0,0));prototype.SetOrientationDegrees(0);prototype.SetFPID(k.LIB_ID('Meshcore',name));prototype.SetReference('REF**');prototype.SetValue(name);prototype.SetDNP(False)
  for p in prototype.Pads():p.SetNetCode(0)
  # GuessPluginTypeFromLibPath returns NONE for an empty new .pretty directory.
  k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(lib),prototype);variant=lib/(name+'.kicad_mod');assert variant.is_file()
  loaded=k.FootprintLoad(str(lib),name);geometry=local_geometry(prototype);assert local_geometry(loaded)==geometry,('Saved library geometry changed',ref)
  f.SetFPID(k.LIB_ID('Meshcore',name));part.setdefault('source_footprint_before_v2_graphic_variant',part['footprint']);part['footprint']='Meshcore:'+name
  maps.append({'ref':ref,'approved_selected_footprint':part['source_footprint_before_v2_graphic_variant'],'previous_instance_footprint':old,'graphic_variant':part['footprint'],'library_file':str(variant.relative_to(ROOT)),'library_sha256':digest(variant),'normalized_native_geometry_sha256':geometry,'saved_library_geometry_sha256':local_geometry(loaded),'same_pads_fab_courtyard_3d_mpn_package':True})
 assert masked_signature(b,original)==before,'Engineering geometry or fields changed'
 assert digest(pcb)==srcsha and digest(modelpath)==modelsha,'Concurrent mutation detected'
 settings=pcb.with_suffix('.kicad_pro').read_bytes();k.SaveBoard(str(pcb),b);pcb.with_suffix('.kicad_pro').write_bytes(settings)
 (pcb.parent/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Meshcore") (type "KiCad") (uri "${KIPRJMOD}/Meshcore.pretty") (options "") (descr "V2 local exact assembly graphic variants")))\n',encoding='utf8')
 again=k.LoadBoard(str(pcb));assert masked_signature(again,original)==before,'Saved/reloaded engineering geometry differs'
 outmodel.parent.mkdir(parents=True,exist_ok=True);outmodel.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf8')
 result={'source_pcb_sha256':srcsha,'pcb_sha256':digest(pcb),'source_model_sha256':modelsha,'model_sha256':digest(outmodel),'invariant_before':before,'invariant_after_with_original_identifiers':masked_signature(again,original),'engineering_geometry_and_mpn_values_unchanged':True,'changes':'library identifier and matching schematic model Footprint only; actual instance graphics are the approved native Silk/Fab geometry','maps':maps,'schematic_rebuild_required':True}
 report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'pcb':str(pcb.relative_to(ROOT)),'variants':len(maps),'engineering_geometry_and_mpn_values_unchanged':True}),flush=True)
if __name__=='__main__':main()
