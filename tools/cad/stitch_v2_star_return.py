"""Find actual safe grounded F copper above the inter-star B ground corridor."""
import math,json
import restore_v2_logic_star_connections as s
import pcbnew as k
from diagnose_v2_ground_islands import distance
def main():
 b=k.LoadBoard(str(s.P));zones=[z for z in b.Zones() if z.GetNetname()=='GND' and z.GetLayer()==k.F_Cu and not z.GetIsRuleArea()]
 fpolys=[]
 for z in zones:
  poly=k.SHAPE_POLY_SET(z.GetFilledPolysList(k.F_Cu));poly.Unfracture()
  for i in range(poly.OutlineCount()):
   if z.GetZoneName()=='GND_TOP' and i==7:continue
   p=k.SHAPE_POLY_SET();p.AddOutline(poly.COutline(i))
   for h in range(poly.HoleCount(i)):p.AddHole(poly.CHole(i,h),0)
   fpolys.append(p)
 candidates=[]
 for ix in range(365,650):
  at=(ix/10,17.7)
  samples=[at]+[(at[0]+.3*math.cos(n*math.pi/8),at[1]+.3*math.sin(n*math.pi/8)) for n in range(16)]
  if not all(any(p.Contains(s.r.vec(q)) for p in fpolys) for q in samples):continue
  okay=True
  for t in b.GetTracks():
   if t.GetNetname()=='GND':continue
   w=k.ToMM(t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth())
   if distance(at,s.r.xy(t.GetStart()),s.r.xy(t.GetEnd()))<w/2+.3+.19999:okay=False;break
   if t.IsOnLayer(k.B_Cu) and distance(at,s.r.xy(t.GetStart()),s.r.xy(t.GetEnd()))<w/2+.2+.2:okay=False;break
  if not okay:continue
  for f in b.GetFootprints():
   for p in f.Pads():
    if p.GetNetname()=='GND':continue
    box=p.GetBoundingBox();m=.5
    if k.ToMM(box.GetLeft())-m<=at[0]<=k.ToMM(box.GetRight())+m and k.ToMM(box.GetTop())-m<=at[1]<=k.ToMM(box.GetBottom())+m:okay=False;break
   if not okay:break
  if okay:candidates.append(at)
 if not candidates:raise RuntimeError('No safe actual F-ground candidate')
 at=candidates[0];ground=next(n for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()=='GND')
 v=k.PCB_VIA(b);v.SetPosition(s.r.vec(at));v.SetWidth(k.FromMM(.6));v.SetDrill(k.FromMM(.3));v.SetLayerPair(k.F_Cu,k.B_Cu);v.SetNet(ground);b.Add(v)
 t=k.PCB_TRACK(b);t.SetStart(s.r.vec((35.5,17.7)));t.SetEnd(s.r.vec(at));t.SetLayer(k.B_Cu);t.SetWidth(k.FromMM(.4));t.SetNet(ground);b.Add(t)
 k.SaveBoard(str(s.P),b);d=s.check('star_final');out={'actual_main_F_ground_at':at,'via_uuid':s.uid(v),'ground_track_uuid':s.uid(t),'DRC_file':'drc_star_final.json','nonmarking_violations':[v for v in d['violations'] if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance')],'unconnected':len(d['unconnected_items']),'parity':len(d['schematic_parity'])}
 (s.A/'ground_return_stitch.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=True))
if __name__=='__main__':main()
