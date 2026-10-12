"""Repair the four local candidate crossings and finish signal connections."""
import json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import route_v2_ina219_power as r

def main():
 b=r.k.LoadBoard(str(r.PCB));origboard=r.k.LoadBoard(str(r.AUDIT/'before_power.kicad_pcb'));r.HELD.extend((b,origboard))
 orig={r.uid(t) for t in origboard.GetTracks()};fps={f.GetReference():f for f in b.GetFootprints()};nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()};log=[]
 def delete(t):log.append(dict(remove=r.describe(t)));b.Remove(t);r.HELD.append(t)
 def trace(net,pts,width=.25,layer=r.k.B_Cu):
  for a,z in zip(pts,pts[1:]):
   if math.dist(a,z)<1e-8:continue
   t=r.k.PCB_TRACK(b);t.SetStart(r.vec(a));t.SetEnd(r.vec(z));t.SetWidth(r.k.FromMM(width));t.SetLayer(layer);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t)
 def via(net,at,diam=.6,drill=.3):
  t=r.k.PCB_VIA(b);t.SetPosition(r.vec(at));t.SetWidth(r.k.FromMM(diam));t.SetDrill(r.k.FromMM(drill));t.SetLayerPair(r.k.F_Cu,r.k.B_Cu);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t)
 def pad(ref,p):return next(x for x in fps[ref].Pads() if x.GetNumber()==str(p))
 # New main source avoids both front CHRG tracks without altering them.
 for t in list(b.GetTracks()):
  at=r.xy(t.GetStart());end=r.xy(t.GetEnd())
  if r.uid(t) not in orig and not isinstance(t,r.k.PCB_VIA) and t.GetNetname()=='BAT' and r.k.ToMM(t.GetWidth())>.7:delete(t)
  elif r.uid(t) not in orig and t.GetNetname()=='BAT' and not isinstance(t,r.k.PCB_VIA):delete(t)
  elif r.uid(t) not in orig and t.GetNetname()=='BAT_SYS' and not isinstance(t,r.k.PCB_VIA) and t.GetLayer()==r.k.B_Cu and r.k.ToMM(t.GetWidth())<.3:delete(t)
  elif r.uid(t) in {'0bd02c1c-4b46-45cf-89b1-671812f25ed2','69783470-2bc9-4faf-95cd-74680a9ad894','7dc86aef-8192-4e30-b3f9-b3427abd5cc6','8b95383e-9f3d-4b67-abd0-7171c879dc5c','adb4c6b6-909b-43ba-9307-5c5d4ee7f1ab','d31b650b-ac18-48ce-b672-f79eeab482fa','f3247ad8-6b71-46c2-b72c-736422843bad'}:delete(t)
  elif r.uid(t)=='deead2cc-cfa6-48e2-8fe4-907974623c21':delete(t)
 # One of two identical supply vias from the provisional second pass.
 co=[]
 for t in list(b.GetTracks()):
  if isinstance(t,r.k.PCB_VIA) and t.GetNetname()=='SYS_3V3' and r.xy(t.GetPosition())==(61.0,12.2):co.append(t)
 for t in co[1:]:delete(t)
 trace('BAT',[(46.5,3.4),(46.5,6.0),(41.9,6.0)],.8,r.k.F_Cu)
 trace('BAT',[(22.0,9.3),(22.0,5.6),(25.6,2.0),(71.04,2.0),(73.04,4.0),(73.04,5.0)])
 via('BAT',(73.04,5.0));trace('BAT',[(73.04,5.0),(73.04,9.73),(74.31,11.0)],.25,r.k.F_Cu)
 # Drop the matching front guard spoke; the same GND pin still has the B.Cu
 # spoke and both full polygons, so this does not remove a circuit return.
 for t in list(b.GetTracks()):
  if isinstance(t,r.k.PCB_VIA) or t.GetNetname()!='GND' or t.GetLayer()!=r.k.F_Cu:continue
  p=pad('J101',8)
  if p.HitTest(t.GetStart(),r.k.FromMM(.3)) or p.HitTest(t.GetEnd(),r.k.FromMM(.3)):delete(t)
 trace('BAT_SYS',[(46.5,8.9),(48.2,8.9),(49.2,7.9),(49.2,6.1),(50.2,6.1),(52.2,8.1),(52.2,12.2),(53.1,12.2)])
 trace('BAT',[(46.5,4.1),(47.2,4.8),(49.8,4.8),(53.0,8.0),(53.0,9.8),(53.1,9.8)])
 # Delete GND stitches colliding with any newly added copper only.
 for t in list(b.GetTracks()):
  if not isinstance(t,r.k.PCB_VIA) or t.GetNetname()!='GND':continue
  pos=r.xy(t.GetPosition());hit=False
  for n in b.GetTracks():
   if r.uid(n) in orig or n.GetNetname()=='GND':continue
   a,z=r.xy(n.GetStart()),r.xy(n.GetEnd());dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy;q=max(0,min(1,((pos[0]-a[0])*dx+(pos[1]-a[1])*dy)/den)) if den else 0
   radius=r.k.ToMM(n.GetWidth(r.k.F_Cu) if isinstance(n,r.k.PCB_VIA) else n.GetWidth())/2+.3+.225
   if math.dist(pos,(a[0]+q*dx,a[1]+q*dy))<radius:hit=True
  if hit:delete(t)
 r.k.ZONE_FILLER(b).Fill(b.Zones());r.k.SaveBoard(str(r.PCB),b)
 # Complete the force path between J12 and the raw shunt land independently
 # of the narrow Kelvin and ADC conductors. Temporarily mark those as blockers.
 changed=[]
 for t in b.GetTracks():
  if t.GetNetname()=='BAT' and not isinstance(t,r.k.PCB_VIA) and r.k.ToMM(t.GetWidth())<.5:changed.append(t);t.SetNet(nets['GND'])
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.GetNetname()=='BAT' and f.GetReference() not in ('J12','J8','R71'):changed.append(p);p.SetNet(nets['GND'])
 try:
  a,z=pad('J12',1),pad('R71',2)
  info=r.route(b,'BAT',r.xy(a.GetPosition()),r.xy(z.GetPosition()),.8,(0,1),(1,));log.append(info)
 finally:
  for t in changed:t.SetNet(nets['BAT'])
 r.k.ZONE_FILLER(b).Fill(b.Zones());r.k.SaveBoard(str(r.PCB),b)
 (r.AUDIT/'finish_delta_log.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8');print('prepared for remaining local signal routes')
if __name__=='__main__':main()
