import pcbnew as k, json, hashlib, sys, os
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tools/cad'));from kicad_headless import configure_headless
configure_headless();r={}
def xy(v):return [k.ToMM(v.x),k.ToMM(v.y)]
def bb(v):return [k.ToMM(v.GetX()),k.ToMM(v.GetY()),k.ToMM(v.GetRight()),k.ToMM(v.GetBottom())]
for board in ['Power','Logic','Shield']:
 p=Path(f'design/MeshRepeater2_{board}/MeshRepeater2_{board}.kicad_pcb');b=k.LoadBoard(str(p));rr={'source':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'edge_bbox':bb(b.GetBoardEdgesBoundingBox()),'thickness':k.ToMM(b.GetDesignSettings().GetBoardThickness()),'parts':{},'texts':[]}
 for f in b.GetFootprints():
  ref=f.GetReference(); rr['parts'][ref]={'lib':str(f.GetFPID().GetLibItemName()),'at':xy(f.GetPosition()),'rotation':f.GetOrientationDegrees(),'pads':[{'n':p.GetNumber(),'at':xy(p.GetPosition()),'size':xy(p.GetSize()),'drill':xy(p.GetDrillSize()),'net':p.GetNetname(),'mask_expansion':k.ToMM(p.GetSolderMaskExpansion(k.F_Mask)),'layers':str(p.GetLayerSet().FmtBin())} for p in f.Pads()],'models':[{'name':m.m_Filename,'offset':[m.m_Offset.x,m.m_Offset.y,m.m_Offset.z],'rotate':[m.m_Rotation.x,m.m_Rotation.y,m.m_Rotation.z]} for m in f.Models()]}
 for t in list(b.GetDrawings())+[g for f in b.GetFootprints() for g in [f.Reference(),f.Value(),*f.GraphicalItems()]]:
  if isinstance(t,k.PCB_TEXT):
   rr['texts'].append({'text':t.GetText(),'at':xy(t.GetPosition()),'size':xy(t.GetTextSize()),'angle':t.GetTextAngle().AsDegrees(),'layer':b.GetLayerName(t.GetLayer()),'mirror':t.IsMirrored(),'visible':t.IsVisible(),'bbox':bb(t.GetBoundingBox())})
 rr['silk_min']=min(min(t['size']) for t in rr['texts'] if t['visible'] and 'Silk' in t['layer']);r[board]=rr
 print(board,rr['edge_bbox'],rr['thickness'],rr['silk_min'])
 for ref in ['D3','D4','J7','J8','J12','J101','J201','J3','J4','J5','J10','J11','J13','M1','SW1','SW2','H101','H201']:
  if ref in rr['parts']: print(ref,rr['parts'][ref]['at'],rr['parts'][ref]['rotation'])
(Path('audit/independent_2026_10_12')/'mechanics.native.json').write_text(json.dumps(r,indent=2),encoding='utf8')

