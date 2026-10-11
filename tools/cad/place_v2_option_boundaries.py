"""Draw true optional assembly groups on POWER; copper/placement invariants kept."""
import json
from finish_v2_markings import ROOT,k,v,rect,union,grow,Markings,invariant
def copper_signature(b):
 return {'tracks':sorted((t.m_Uuid.AsString(),tuple(k.ToMM(x) for x in (t.GetStart().x,t.GetStart().y,t.GetEnd().x,t.GetEnd().y)),t.GetLayer(),t.GetNetCode(),t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth()) for t in b.GetTracks()),'pads':sorted((f.GetReference(),p.GetNumber(),p.GetNetCode(),tuple(k.ToMM(x) for x in (p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y))) for f in b.GetFootprints() for p in f.Pads()),'placements':sorted((f.GetReference(),f.GetPosition().x,f.GetPosition().y,f.GetOrientation().AsDegrees()) for f in b.GetFootprints())}
project=ROOT/'design/MeshRepeater2_Power';p=project/'MeshRepeater2_Power.kicad_pcb';b=k.LoadBoard(str(p));model=json.loads((project/'model.json').read_text(encoding='utf-8'));before=copper_signature(b);held=[]
for g in list(b.GetDrawings()):
 if isinstance(g,k.PCB_SHAPE) and g.GetLayer()==k.F_SilkS:
  # POWER has only option boundary BOARD_SHAPEs on F.SilkS. Footprint body
  # graphics and Edge.Cuts are separate and retained.
  b.Remove(g);held.append(g)
lab=Markings(b,model);lab.prepare()
switches=['Q4','Q6','Q7','R56']
groups={'BAL1':['R47','R48','R49','R50','U8','C58'],'BAL2':['R51','R52','R53','R54','U9','C59'],'COLD_A':switches,'COLD_B':[q['ref'] for q in model['parts'] if q.get('group')=='cold_charge' and q['ref'] not in switches]}
result={}
for name,refs in groups.items():
 box=grow(union([lab.bodies[r] for r in refs]),.9);x0,y0,x1,y1=box
 if name=='COLD_A':pts=[(27.35,26.35),(42.15,26.35),(42.15,31.0),(27.05,31.0),(27.05,32.35),(23.5,32.35),(23.5,29.8),(27.35,29.8),(27.35,26.35)]
 elif name=='COLD_B':pts=[(40.45,32.55),(43.2,32.55),(43.2,34.0),(49.75,34.0),(49.75,36.75),(51.3,36.75),(51.3,55.195),(23.8,55.195),(23.8,43.15),(40.45,43.15),(40.45,32.55)]
 else:pts=[(x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0)]
 for a,z in zip(pts,pts[1:]):
  g=k.PCB_SHAPE(b);g.SetShape(k.SHAPE_T_SEGMENT);g.SetStart(v(*a));g.SetEnd(v(*z));g.SetLayer(k.F_SilkS);g.SetWidth(k.FromMM(.22));b.Add(g)
 result[name]={'refs':refs,'outline_mm':pts,'note':'COLD boundary excludes mandatory R1/C53/L1 and other main charger/converter parts'}
after=copper_signature(b)
for key in ('tracks','pads','placements'):
 if before.get(key)!=after.get(key):raise AssertionError('Functional invariant changed '+key)
k.SaveBoard(str(p),b);(ROOT/'audit/v2_power_option_outlines.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
