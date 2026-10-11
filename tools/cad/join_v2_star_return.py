"""Join the independently identified C25/inter-star ground island to main F ground."""
import json,subprocess
import restore_v2_logic_star_connections as s
import pcbnew as k
def main():
 b=k.LoadBoard(str(s.P));source=next(p for f in b.GetFootprints() if f.GetReference()=='C25' for p in f.Pads() if p.GetNumber()=='2')
 target=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.GetNetname()=='GND' and f.GetReference()!='C25' and p.IsOnLayer(k.F_Cu):target.append((s.r.xy(p.GetPosition()),0))
 log=s.r.route(b,'GND',(33.95,17.3),(37.6,13.1),.4,(0,),(0,),True,s.r.component_points(b,source),target)
 k.SaveBoard(str(s.P),b);d=s.check('star_final');(s.A/'ground_return_fix.json').write_text(json.dumps({'new_connection':log,'violations':[v for v in d['violations'] if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance')],'unconnected':len(d['unconnected_items']),'parity':len(d['schematic_parity'])},indent=2),encoding='utf-8')
 print('nonmarking',{v['type'] for v in d['violations'] if v['type'] not in ('text_height','silk_overlap','silk_over_copper','silk_edge_clearance')},'unconnected',len(d['unconnected_items']),'parity',len(d['schematic_parity']))
if __name__=='__main__':main()
