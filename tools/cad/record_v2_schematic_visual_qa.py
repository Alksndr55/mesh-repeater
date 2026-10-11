"""Record the separately performed visual review of all native PDF pages.

This does not substitute text extraction for visual inspection. The explicit
flag records the caller's inspection; hashes bind it to the reviewed outputs.
"""
from pathlib import Path
import argparse,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
def entry(p):return {'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--all-pages-inspected',action='store_true',required=True);a=ap.parse_args()
 rows=[]
 for name,n in [('POWER',5),('LOGIC',4)]:
  project='MeshRepeater2_'+name.title();native=ROOT/'design'/project;audit=ROOT/'audit/schematic'/name;pdf=ROOT/'output/pdf'/(project+'_schematic.pdf');erc=json.loads((audit/'erc.json').read_text(encoding='utf8'))
  assert not erc.get('violations') and not erc.get('ignored'),name+' strict ERC must be empty'
  previews=[audit/'previews'/('page-'+str(i)+'.png') for i in range(1,n+1)];assert all(p.is_file() for p in previews)
  manifest=json.loads((native/'schematic_manifest.json').read_text(encoding='utf8'));assert len(manifest['sheets'])==n
  assert all('__V2_' not in x['package'] for sheet in manifest['sheets'] for x in sheet['annotations']),'Visible package leaked internal variant identifier'
  rows.append({'board':name,'pages':n,'native_schematics':[entry(p) for p in sorted(native.glob('*.kicad_sch'))],'native_netlist':entry(audit/'netlist.xml'),'strict_erc':entry(audit/'erc.json'),'pdf':entry(pdf),'reviewed_previews':[entry(p) for p in previews],'visual_review':'Every page inspected after final render: compact physical package captions; no clipping or visible annotation/wire collision; title, page number and sheet links clear.'})
 report={'page_count':9,'every_page_visually_inspected':True,'renderer':'Poppler pdftoppm120dpi; native KiCad10 PDF export','native_editor_files_retained':True,'corrections':'Readable package names sourced from selected physical footprint; compact SPI captions, Kelvin note and LMV431/GPS labels moved clear of conductors; electrical graph and hidden Footprint unchanged.','projects':rows}
 dest=ROOT/'audit/schematic/final_schematic_output_manifest.json';dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 pub={'projects':[{'board':r['board'],'pages':r['pages'],'native_netlist':r['native_netlist'],'strict_erc':r['strict_erc'],'pdf':r['pdf']} for r in rows],'visual_qa':entry(dest)}
 (ROOT/'output/pdf/SCHEMATIC_MANIFEST.json').write_text(json.dumps(pub,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'pages_visually_inspected':9,'ERC':[0,0],'report':str(dest.relative_to(ROOT))}))
if __name__=='__main__':main()
