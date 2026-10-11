"""Explicit physical one-copper screen stackup in a valid KiCad container.

KiCad's native file syntax is documented at:
https://dev-docs.kicad.org/en/file-formats/sexpr-pcb/#stack-up-settings
The mask is physical 10um; STEP exports core+foil, not the mask solid.
"""
from pathlib import Path
import hashlib,json
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
STACK='''\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "core") (thickness 1.475) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen"))
\t\t\t(dielectric_constraints no)
\t\t)
'''

def ensure(path):
 path=Path(path).resolve();assert path.is_relative_to(ROOT)
 raw=path.read_text(encoding='utf8');needle='\t(setup\n';assert needle in raw
 if '\t\t(stackup\n' in raw:
  start=raw.index('\t\t(stackup\n');depth=0;quote=False;escape=False;end=None
  for i in range(start,len(raw)):
   c=raw[i]
   if quote:
    if escape:escape=False
    elif c=='\\':escape=True
    elif c=='"':quote=False
   elif c=='"':quote=True
   elif c=='(':depth+=1
   elif c==')':
    depth-=1
    if depth==0:end=i+1;break
  assert end;raw=raw[:start]+STACK.rstrip()+raw[end:]
 else:raw=raw.replace(needle,needle+STACK,1)
 path.write_text(raw,encoding='utf8',newline='\n')

def main():
 path=ROOT/'design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pcb';pro=path.with_suffix('.kicad_pro');settings=pro.read_bytes();oldsha=hashlib.sha256(path.read_bytes()).hexdigest()
 ensure(path);b=k.LoadBoard(str(path));assert b and b.GetDesignSettings().m_HasStackup
 assert abs(k.ToMM(b.GetDesignSettings().GetBoardThickness())-1.52)<1e-9
 for t in b.GetDrawings():
  if isinstance(t,k.PCB_TEXT) and 'FR4 1.52mm' in t.GetText():t.SetText(t.GetText().replace('FR4 1.52mm','PCB 1.52mm'))
 k.SaveBoard(str(path),b);pro.write_bytes(settings);again=k.LoadBoard(str(path));assert again and again.GetDesignSettings().m_HasStackup
 saved=path.read_text(encoding='utf8');assert '(thickness 1.475)' in saved and saved.count('(thickness 0)')>=2
 proof={'source_sha256':oldsha,'pcb_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'native_reload_has_explicit_stackup':True,'physical_manufacturing_copper_layers':1,'native_container_copper_layers':again.GetCopperLayerCount(),'layers_mm':{'F.Mask':.01,'F.Cu':.035,'dielectric_FR4':1.475,'B.Cu':0,'B.Mask':0},'nominal_total_thickness_mm':1.52,'step_expected_core_foil_thickness_mm':1.51,'step_excludes_mask_thickness_mm':.01,'back_surface':'bare_FR4_with_silkscreen_guide','minimum_thickness_is_nominal_not_tolerance':True}
 (ROOT/'audit/v2_shield_stackup.json').write_text(json.dumps(proof,indent=2),encoding='utf8');print(json.dumps(proof),flush=True)
if __name__=='__main__':main()
