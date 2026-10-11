"""Apply only authorised mechanical package/placement edits in v2."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]
mech=json.loads((ROOT/'docs/mechanical_selection.json').read_text(encoding='utf-8'))
by_ref={r:p for p in mech['parts'] for r in p['refs'] if p.get('footprint')}
positions={
 'J7':(11.35,9.3,0),'J8':(22.75,9.3,0),'J12':(35.25,9.3,0),
 'D3':(51,2.2,180),'D4':(56,2.2,0),'R10':(51,7,0),'R11':(56,7,0),
 'J101':(64.15,11.0,90),'J201':(76.85,49.0,270),
 'J3':(86,12,0),'J5':(2.5,18.12,180),'J11':(86,23,0),
 'SW1':(29,58.2,180),'SW2':(41,58.2,180),'SH1':(45,34.5,0),
}
hole_fp='GND_M3_D3.2_OD6'
hole_src=f'''(footprint "{hole_fp}" (version 20260206) (generator "pcbnew") (layer "F.Cu")
 (descr "M3 conductive clamping land OD6mm drill3.2; exposed copper on both faces; no solder paste. Metal washer OD6 max.")
 (property "Reference" "REF**" (at 0 -3.8) (layer "F.Fab") (effects (font (size .8 .8) (thickness .13))))
 (property "Value" "M3 GND" (at 0 3.8) (layer "F.Fab") (effects (font (size .8 .8) (thickness .13))))
 (attr through_hole exclude_from_pos_files exclude_from_bom)
 (fp_circle (center 0 0) (end 3.25 0) (stroke (width .05) (type solid)) (fill no) (layer "F.CrtYd"))
 (pad "1" thru_hole circle (at 0 0) (size 6 6) (drill 3.2) (layers "*.Cu" "*.Mask") (zone_connect 2) (remove_unused_layers no))
 (embedded_fonts no))\n'''
for board in ['Power','Logic']:
 project=ROOT/'design'/('MeshRepeater2_'+board);model=json.loads((project/'model.json').read_text(encoding='utf-8'))
 (project/'Meshcore.pretty'/(hole_fp+'.kicad_mod')).write_text(hole_src,encoding='utf-8')
 for p in model['parts']:
  ref=p['ref']
  if ref in by_ref:
   m=by_ref[ref];p.update(footprint=m['footprint'],mpn=m['mpn'],vendor='Danomsk',vendor_url=m['dan_url'],procurement_checked_at=m['stock_checked'],procurement_package=m['footprint'].split(':')[-1],note=m.get('note','')+' Mechanical v2 package; original functional pin numbers retained.')
  if ref in ['J3','J5']:
   p.update(footprint='Meshcore:Connfly_DS1022_1x04RUF11_B_Horizontal',mpn='DS1022-1x40RUF11-B cut to4pins',vendor='Danomsk',procurement_package='THT right angle P2.54 1x4',vendor_url=by_ref['J11']['dan_url'])
  if ref in positions:p['x'],p['y'],p['rotation']=positions[ref]
  if p['kind']=='MountingHole':p.update(footprint='Meshcore:'+hole_fp,mpn='PCB land M3 GND OD6 drill3.2',procurement_package='PCB conductive mounting land')
  if ref=='SH1':p['note']='S4.16 frame retained; lid removed. Clearance to continuous shield checked separately.'
 model['revision']='V2.0-A1_LAYOUT';model['mechanical_selection']='docs/mechanical_selection.json';model['board']['mounting_keepout_od_mm']=6.5
 (project/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'packages_applied':sorted(by_ref),'position_edits':positions,'isp_preserved':[35.7,31.3,0]},ensure_ascii=True))
