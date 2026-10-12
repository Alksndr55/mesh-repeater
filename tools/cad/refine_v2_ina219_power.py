"""Replace candidate detours with local manual battery and INA connections."""
import json,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import route_v2_ina219_power as r

def main():
 b=r.k.LoadBoard(str(r.PCB));old=r.k.LoadBoard(str(r.AUDIT/'before_power.kicad_pcb'));r.HELD.extend((b,old))
 orig={r.uid(t):t for t in old.GetTracks()};fps={f.GetReference():f for f in b.GetFootprints()};nets={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()};log=[]
 def delete(t,reason):log.append(dict(remove=r.describe(t),reason=reason));b.Remove(t);r.HELD.append(t)
 def pad(ref,pin):return next(p for p in fps[ref].Pads() if p.GetNumber()==str(pin))
 def trace(net,points,width=.25,layer=r.k.F_Cu):
  for a,z in zip(points,points[1:]):
   if math.dist(a,z)<1e-8:continue
   t=r.k.PCB_TRACK(b);t.SetStart(r.vec(a));t.SetEnd(r.vec(z));t.SetWidth(r.k.FromMM(width));t.SetLayer(layer);t.SetNet(nets[net]);t.SetLocked(True);b.Add(t);log.append(dict(add=r.describe(t)))
 def via(net,pos,diam=.6,drill=.3):
  v=r.k.PCB_VIA(b);v.SetPosition(r.vec(pos));v.SetWidth(r.k.FromMM(diam));v.SetDrill(r.k.FromMM(drill));v.SetLayerPair(r.k.F_Cu,r.k.B_Cu);v.SetNet(nets[net]);v.SetLocked(True);b.Add(v);log.append(dict(add=r.describe(v)))
 # Final cluster: shunt directly beside C53, short sense pair toward the INA.
 for ref,pos,ang,layer in [('R71',(46.5,6.5),90,'B.Cu'),('C64',(57.8,7.7),90,'B.Cu')]:
  f=fps[ref]
  if r.k.LayerName(f.GetLayer())!=layer:f.Flip(f.GetPosition(),False)
  f.SetPosition(r.vec(pos));f.SetOrientationDegrees(ang)
 mfile=r.PROJECT/'model.json';model=json.loads(mfile.read_text(encoding='utf-8'))
 for p in model['parts']:
  if p['ref']=='R71':p.update(x=46.5,y=6.5,rotation=90,native_layer='B.Cu')
  if p['ref']=='C64':p.update(x=57.8,y=7.7,rotation=90,native_layer='B.Cu')
 mfile.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
 # Remove only our candidate main-power detours and input routes.
 for t in list(b.GetTracks()):
  if t.GetNetname() in ('INA_VIN_P','INA_VIN_M') or (r.uid(t) not in orig and t.GetNetname() in ('BAT','BAT_SYS')):delete(t,'replace own candidate by short manual path')
 # Old J12->R15 branch crosses the new main-current corridor. Reconnect this
 # microamp EN sense after the main power route, without moving its divider.
 old.BuildConnectivity();g=r.TraceGraph(old);cut={x['uuid'] for x in json.loads((r.AUDIT/'initial_addition.json').read_text())['partition']['removed']}
 j12=g.pads[('J12','1')][0];seen={j12};q=[j12]
 while q:
  u=q.pop()
  for v in g.edges[u]:
   if v not in cut and v not in seen:seen.add(v);q.append(v)
 lookup={r.uid(t):t for t in b.GetTracks()}
 for u in seen:
  if u in lookup:delete(lookup[u],'old J12/R15 raw branch must move around the new system corridor')
 # Remove the unused raw trunk tail formerly running to C53.
 for t in list(b.GetTracks()):
  if r.uid(t) in {'5b92603b-06b4-4b8b-b5d2-c2ca720839e7','eb68f086-d778-48fe-a0fd-302372523454','8fb87779-262e-4d72-b875-d02a1bff57f4','638d1eae-bbf4-4341-a942-6f0c841a813b'}:delete(t,'raw copper no longer extends beyond the inserted measurement shunt')
  elif r.uid(t)=='0eeaa0eb-fe94-415e-a674-d88a91c6d1f1':t.SetEnd(r.vec((41.9,6.0)))
 via('BAT',(46.5,3.4),.8,.4);trace('BAT',[(46.5,3.4),(44.5,3.4),(41.9,6.0)],.8);trace('BAT',[(35.25,6.0),(35.25,9.3)],.8)
 via('BAT_SYS',(46.5,9.6),.8,.4);trace('BAT_SYS',[(46.5,9.6),(46.5,11.9)],.8)
 # Keep BAT_ADC an independent connector-pad branch, without sharing new
 # force-current or Kelvin segments. The top B.Cu corridor is quiet.
 adc=json.loads((r.ROOT/'audit/v2_power_final_feed_check.json').read_text())['sense_feed']['track_UUIDs']
 for t in list(b.GetTracks()):
  if r.uid(t) in adc:delete(t,'ADC branch moves into top quiet corridor to clear the new monitor')
 trace('BAT',[(22.0,9.3),(22.0,5.6),(25.6,2.0),(71.04,2.0),(73.04,4.0),(73.04,9.73),(74.31,11.0)],.25,r.k.B_Cu)
 # Short input paths, both filtered at the IC. Resistor outputs go directly
 # through a via in their own copper land; input cap is on the IC side.
 via('INA_VIN_P',(54.9,12.2));trace('INA_VIN_P',[(54.9,12.2),(54.9,11.7),(56.3,10.3)])
 via('INA_VIN_P',(56.3,9.5));trace('INA_VIN_P',[(56.3,9.5),(56.3,10.3)])
 trace('INA_VIN_P',[(57.8,8.65),(57.8,9.0),(57.3,9.5),(56.3,9.5)],.25,r.k.B_Cu)
 via('INA_VIN_M',(57.6,10.3));trace('INA_VIN_M',[(54.9,9.8),(55.9,8.8),(55.9,6.75),(57.8,6.75)],.25,r.k.B_Cu)
 trace('INA_VIN_M',[(57.8,6.75),(58.25,6.75),(59.1,7.6),(59.1,9.7),(58.5,10.3),(57.6,10.3)],.25,r.k.B_Cu)
 # Differential Kelvin launches at the inner sides of the resistor lands.
 trace('BAT_SYS',[(46.5,8.9),(48.2,8.9),(48.2,5.8),(50.0,5.8),(52.2,8.0),(52.2,12.2),(53.1,12.2)],.25,r.k.B_Cu)
 trace('BAT',[(46.5,4.1),(47.2,4.8),(49.8,4.8),(53.0,8.0),(53.0,9.8),(53.1,9.8)],.25,r.k.B_Cu)
 # Local supply capacitor at the VS pad, from upper board supply return.
 via('SYS_3V3',(61.0,12.2));trace('SYS_3V3',[(61.0,12.2),(60.1,11.3),(60.1,10.3)],.3)
 trace('SYS_3V3',[(61.0,12.2),(61.0,12.35)],.3,r.k.B_Cu)
 # Remove only stitches conflicting with added manual copper. Existing hot
 # loops, active grounds and every non-battery signal remain untouched.
 for t in list(b.GetTracks()):
  if not isinstance(t,r.k.PCB_VIA) or t.GetNetname()!='GND':continue
  p=r.xy(t.GetPosition());hit=False
  for n in b.GetTracks():
   if r.uid(n) in orig or n.GetNetname()=='GND':continue
   a,z=r.xy(n.GetStart()),r.xy(n.GetEnd());dx,dy=z[0]-a[0],z[1]-a[1];den=dx*dx+dy*dy
   q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/den)) if den else 0
   radius=r.k.ToMM(n.GetWidth(r.k.F_Cu) if isinstance(n,r.k.PCB_VIA) else n.GetWidth())/2+.3+.225
   if math.dist(p,(a[0]+q*dx,a[1]+q*dy))<radius:hit=True
  if hit:delete(t,'stitch conflicts with a new monitor or battery track')
 r.k.ZONE_FILLER(b).Fill(b.Zones());r.k.SaveBoard(str(r.PCB),b)
 (r.AUDIT/'manual_refinement.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8');print('saved',r.sha(r.PCB),'changes',len(log))
if __name__=='__main__':main()
