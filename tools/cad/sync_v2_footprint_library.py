"""Match exact native assembly instances to approved local graphic variants.

Only the library identifier and model.footprint metadata change on the board.
Pad, Fab, courtyard, 3D, MPN, values and physical placement are invariant.
Rebuild schematic/netlist afterwards so its hidden Footprint agrees with PCB.
"""
from finish_v2_markings import ROOT,k,v,safe,invariant
import argparse,hashlib,json,re
KEEP=[]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def normal_angle(angle):return round(float(angle)%360,9)
def local_geometry(f,detail=False):
 rows=[]
 for p in f.Pads():
  row=['pad',p.GetNumber(),p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,p.GetDrillSize().x,p.GetDrillSize().y,normal_angle(p.GetOrientationDegrees()),int(p.GetShape()),int(p.GetDrillShape()),int(p.GetAttribute()),str(p.GetLayerSet().FmtBin()),p.GetOffset().x,p.GetOffset().y,p.GetRoundRectRadiusRatio(),p.GetChamferRectRatio()]
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
 def textstyle(g,hidden_field=False):
  # KiCad upright handling may represent a hidden property as0 or180deg.
  # Its exact layer/position/size/text/visibility remain compared; actual native
  # fields are untouched. Visible text and all physical geometry keep360deg
  # angle distinction. This equivalence never applies to pads or 3D models.
  angle=normal_angle(g.GetTextAngle().AsDegrees())
  if hidden_field and not g.IsVisible():angle%=180
  return[g.GetLayer(),g.GetPosition().x,g.GetPosition().y,g.GetTextSize().x,g.GetTextSize().y,g.GetTextThickness(),angle,g.IsMirrored(),g.IsVisible(),int(g.GetHorizJustify()),int(g.GetVertJustify()),g.IsKeepUpright()]
 texts=sorted([g.GetText(),*textstyle(g)]for g in f.GraphicalItems()if isinstance(g,k.PCB_TEXT))
 fields=sorted([g.GetName(),g.GetText(),*textstyle(g,True)]for g in f.GetFields()if g.GetName()not in ('Reference','Value'))
 data={'side':int(f.GetLayer()),'pad_and_fab_courtyard_silk_geometry':sorted(rows,key=lambda x:json.dumps(x)),'fp_user_text_geometry':texts,'3d':models,'engineering_fields_and_style':fields}
 return data if detail else hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
def masked_signature(b,old):
 current={f.GetReference():str(f.GetFPID().GetLibItemName()) for f in b.GetFootprints()}
 for f in b.GetFootprints():f.SetFPID(k.LIB_ID('Meshcore',old[f.GetReference()].split(':',1)[1]))
 result=invariant(b)
 for f in b.GetFootprints():f.SetFPID(k.LIB_ID('Meshcore',current[f.GetReference()]))
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pcb',required=True);ap.add_argument('--model',required=True);ap.add_argument('--out-model');ap.add_argument('--report');a=ap.parse_args()
 pcb=safe(a.pcb);modelpath=safe(a.model);outmodel=safe(a.out_model or modelpath);report=safe(a.report or ROOT/'audit'/(pcb.stem+'_footprint_variants.json'))
 srcsha=digest(pcb);modelsha=digest(modelpath);model=json.loads(modelpath.read_text(encoding='utf8'));parts={p['ref']:p for p in model['parts']};b=k.LoadBoard(str(pcb));KEEP.append(b);fps={f.GetReference():f for f in b.GetFootprints()};assert set(fps)==set(parts)
 before=invariant(b);original={r:'Meshcore:'+str(f.GetFPID().GetLibItemName()) for r,f in fps.items()};lib=pcb.parent/'Meshcore.pretty';lib.mkdir(exist_ok=True);maps=[]
 for ref,f in sorted(fps.items()):
  part=parts[ref];old=original[ref];assert str(f.GetFPID().GetLibNickname())=='Meshcore'
  base=re.sub(r'__V2_[A-Za-z0-9_]+$','',old.split(':',1)[1]);name=base+'__V2_'+ref
  prototype=k.Cast_to_FOOTPRINT(f.Duplicate(False));prototype.SetPosition(v(0,0))
  KEEP.append(prototype)
  # KiCad libraries load in canonical F.Cu orientation. A B.Cu instance must
  # first be physically reflected back to F with the same inverse flip axis;
  # normalizing only its angle leaves a B-layer primitive that the loader
  # silently reinterprets, swapping side/layer geometry.
  source_is_back=f.GetLayer()==k.B_Cu
  if source_is_back:prototype.Flip(v(0,0),False)
  prototype.SetOrientationDegrees(0);assert prototype.GetLayer()==k.F_Cu
  prototype.SetFPID(k.LIB_ID('Meshcore',name));prototype.SetReference('REF**');prototype.SetValue(name);prototype.SetDNP(False)
  for p in prototype.Pads():p.SetNetCode(0)
  # GuessPluginTypeFromLibPath returns NONE for an empty new .pretty directory.
  k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(lib),prototype);variant=lib/(name+'.kicad_mod');assert variant.is_file()
  loaded=k.FootprintLoad(str(lib),name);geometry=local_geometry(prototype);assert local_geometry(loaded)==geometry,('Saved library geometry changed',ref)
  KEEP.append(loaded)
  # Reconstruct the source native pose from the freshly loaded canonical
  # library footprint. This catches B-side pad1/2 reversal, artwork mirroring,
  # field-style changes and 3D transform changes in a future Update PCB.
  reconstructed=k.Cast_to_FOOTPRINT(loaded.Duplicate(False))
  # Flip queries board copper-layer mapping. The detached verification copy
  # borrows only the source parent pointer, without adding another footprint
  # to the board or constructing a second BOARD/project context.
  reconstructed.SetParent(b)
  KEEP.append(reconstructed)
  if source_is_back:reconstructed.Flip(v(0,0),False)
  reconstructed.SetOrientationDegrees(f.GetOrientationDegrees());reconstructed.SetPosition(f.GetPosition())
  actual_geometry=local_geometry(f);reconstructed_geometry=local_geometry(reconstructed)
  assert reconstructed_geometry==actual_geometry,('Library inverse assembly geometry changed',ref)
  f.SetFPID(k.LIB_ID('Meshcore',name));part.setdefault('source_footprint_before_v2_graphic_variant',part['footprint']);part['footprint']='Meshcore:'+name
  maps.append({'ref':ref,'approved_selected_footprint':part['source_footprint_before_v2_graphic_variant'],'previous_instance_footprint':old,'graphic_variant':part['footprint'],'library_file':str(variant.relative_to(ROOT)),'library_sha256':digest(variant),'source_native_side':k.LayerName(f.GetLayer()),'canonical_library_side':'F.Cu','inverse_flip_axis':'same pcbnew Flip(origin,False) as normalization'if source_is_back else None,'hidden_engineering_field_angle_comparison':'mod180 only while invisible; exact values/layer/position/size/style and native fields preserved; visible text uses mod360','normalized_native_geometry_sha256':geometry,'saved_library_geometry_sha256':local_geometry(loaded),'source_assembly_geometry_sha256':actual_geometry,'inverse_assembly_geometry_sha256':reconstructed_geometry,'same_pads_fab_courtyard_silk_text_field_style_3d_mpn_package':True,'same_pads_fab_courtyard_3d_mpn_package':True})
 print('Verified canonical and inverse library geometry for '+str(len(maps))+' footprints',flush=True)
 assert masked_signature(b,original)==before,'Engineering geometry or fields changed'
 print('Verified assembly invariance before save',flush=True)
 assert digest(pcb)==srcsha and digest(modelpath)==modelsha,'Concurrent mutation detected'
 settings=pcb.with_suffix('.kicad_pro').read_bytes();k.SaveBoard(str(pcb),b);pcb.with_suffix('.kicad_pro').write_bytes(settings)
 print('Saved library identifiers without geometry changes',flush=True)
 (pcb.parent/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Meshcore") (type "KiCad") (uri "${KIPRJMOD}/Meshcore.pretty") (options "") (descr "V2 local exact assembly graphic variants")))\n',encoding='utf8')
 again=k.LoadBoard(str(pcb));KEEP.append(again);assert masked_signature(again,original)==before,'Saved/reloaded engineering geometry differs'
 outmodel.parent.mkdir(parents=True,exist_ok=True);outmodel.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf8')
 result={'source_pcb_sha256':srcsha,'pcb_sha256':digest(pcb),'source_model_sha256':modelsha,'model_sha256':digest(outmodel),'invariant_before':before,'invariant_after_with_original_identifiers':masked_signature(again,original),'engineering_geometry_and_mpn_values_unchanged':True,'changes':'library identifier and matching schematic model Footprint only; actual instance graphics are the approved native Silk/Fab geometry','maps':maps,'schematic_rebuild_required':True}
 report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'pcb':str(pcb.relative_to(ROOT)),'variants':len(maps),'engineering_geometry_and_mpn_values_unchanged':True}),flush=True)
if __name__=='__main__':main()
