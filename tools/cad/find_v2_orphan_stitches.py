"""Read-only search for vias joining a local GND island to the main plane."""
from diagnose_v2_ground_islands import ROOT,k,vec,xy,distance
import math,json

def main():
 b=k.LoadBoard(str(ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'))
 groups={}
 for z in b.Zones():
  if z.GetNetname()!='GND' or z.GetIsRuleArea():continue
  p=k.SHAPE_POLY_SET(z.GetFilledPolysList(z.GetLayer()));p.Unfracture()
  for i in range(p.OutlineCount()):
   q=k.SHAPE_POLY_SET();q.AddOutline(p.COutline(i))
   for h in range(p.HoleCount(i)):q.AddHole(p.CHole(i,h),0)
   groups[(z.GetZoneName(),i)]=q
 pads=[p for f in b.GetFootprints() for p in f.Pads()];tracks=list(b.GetTracks());results=[]
 for src,orphan,near in [('GND_TOP',7,(29.05,10.35)),('GND_TOP',5,(29.8,14.6875)),('GND_REFERENCE',9,(29.05,10.35)),('GND_REFERENCE',7,(29.8,14.6875))]:
  source=groups[src,orphan];target=k.SHAPE_POLY_SET();candidates=[]
  if src=='GND_TOP':
   for n in range(11):
    if n not in (7,9):target.BooleanAdd(groups['GND_REFERENCE',n])
  else:
   for n in range(18):
    if n not in (5,7):target.BooleanAdd(groups['GND_TOP',n])
   target.BooleanAdd(groups['RF_CPW_GND_1',0])
  for ix in range(240,355):
   for iy in range(75,205):
    at=(ix/10,iy/10)
    samples=[at]+[(at[0]+.31*math.cos(n*math.pi/8),at[1]+.31*math.sin(n*math.pi/8)) for n in range(16)]
    if not all(source.Contains(vec(a)) and target.Contains(vec(a)) for a in samples):continue
    if any(z.GetIsRuleArea() and z.Outline().Contains(vec(at)) for z in b.Zones()):continue
    safe=True
    for p in pads:
     if p.GetNetname()=='GND' and p.GetAttribute()!=k.PAD_ATTRIB_NPTH:continue
     box=p.GetBoundingBox();m=.55
     if k.ToMM(box.GetLeft())-m<=at[0]<=k.ToMM(box.GetRight())+m and k.ToMM(box.GetTop())-m<=at[1]<=k.ToMM(box.GetBottom())+m:safe=False;break
    if not safe:continue
    for t in tracks:
     if isinstance(t,k.PCB_VIA) and math.dist(at,xy(t.GetPosition()))<k.ToMM(t.GetDrill())/2+.45:safe=False;break
     if t.GetNetname()=='GND':continue
     w=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth())
     if distance(at,xy(t.GetStart()),xy(t.GetEnd()))<w/2+.55:safe=False;break
    if safe:candidates.append((math.dist(at,near),at))
  rows=[{'distance_mm':d,'at_mm':a} for d,a in sorted(candidates)[:20]]
  results.append({'source_zone':src,'orphan_island':orphan,'near_pad':near,'candidates':rows})
 out=ROOT/'audit/ground_diagnosis/stitch_candidates.json';out.write_text(json.dumps(results,indent=2),encoding='utf8');print(json.dumps(results))
if __name__=='__main__':main()
