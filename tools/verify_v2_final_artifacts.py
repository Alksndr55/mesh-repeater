"""Verify final saved artifacts and their provenance without modifying CAD."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
BASE='cf54f9970e716272d477afdb252b4e195d595cb6'

def load(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def resolve(p):return ROOT/str(p).replace('\\','/')

def main():
 checks=[];inputs={}
 def check(name,ok,detail=None):checks.append({'name':name,'pass':bool(ok),'detail':detail})
 def bound(path,expected):
  p=resolve(path);actual=sha(p) if p.is_file() else None
  check('SHA256 '+str(path),actual==expected,{'expected':expected,'actual':actual})
 def objects(data):
  if isinstance(data,dict):
   if 'path' in data and 'sha256' in data:bound(data['path'],data['sha256'])
   for v in data.values():objects(v)
  elif isinstance(data,list):
   for v in data:objects(v)
 for name in ['v2_native_boards_final','v2_schematic_equivalence']:
  doc=load('audit/'+name+'.json')
  check(name+' all conditions',doc.get('ok') and all(x.get('pass') for x in doc['checks']),len(doc['checks']))
  for p,h in doc.get('inputs',{}).items():bound(p,h)
 for board in ('POWER','LOGIC','SHIELD'):
  d=load(f'output/{board}/MeshRepeater2_{board.title()}_drc.json')
  counts={k:len(d.get(k,[])) for k in ('violations','unconnected_items','schematic_parity','ignored_checks')}
  check(board+' strict DRC',not any(counts.values()),counts)
  m=load(f'output/{board}/MeshRepeater2_{board.title()}_exports.json')
  bound(m['pcb'],m['sha256']);objects(m['artifacts'])
 for board in ('POWER','LOGIC'):
  d=load(f'audit/schematic/{board}/erc.json')
  count=sum(len(x.get('violations',[])) for x in d['sheets'])
  check(board+' strict ERC',count==0 and not d.get('ignored_checks'),{'violations':count,'ignored':d.get('ignored_checks',[])})
 for p in ('output/pdf/SCHEMATIC_MANIFEST.json','docs/mechanics/assembly_geometry_report.json','docs/mechanics/native_render_report.json','docs/mechanics/assembly_pdf_audit.json','audit/v2_manual_pdf_audit.json'):
  d=load(p);objects(d);inputs[p]=sha(ROOT/p)
  for image in d.get('renders',[]):bound(image['image'],image['image_sha256'])
  if 'pdf_sha256' in d and isinstance(d.get('pdf'),str):bound(d['pdf'],d['pdf_sha256'])
  for source,h in d.get('source_sha256',{}).items():bound(source,h)
 d=load('docs/mechanics/assembly_geometry_report.json')
 bound(d['stack_source'],d['stack_contract_sha256'])
 for artifact,proof in d['artifacts'].items():
  for key in ('pcb_intersections','hardware_to_component_clearances'):
   check(artifact+' '+key,all(x.get('pass') for x in proof.get(key,[])),proof.get(key))
  if artifact.endswith('assembly'):
   gaps=proof['vertical_envelope_clearances']
   check('Modeled component gaps above zero',gaps['power_envelope_to_screen_mm']>0 and gaps['logic_envelope_to_screen_mm']>0,gaps)
 frozen=load('baseline/S4_16/freeze_manifest.json')
 for p,h in frozen['files'].items():bound('baseline/S4_16/'+p,h)
 check('Frozen S4.16 commit',frozen['published_commit']==BASE)
 required=['output/pdf/MeshRepeater2_assembly_manual_RU.pdf','output/pdf/MeshRepeater2_assembly_dimensions.pdf','output/V2_OVERVIEW_RU.html','bom/V2_COMPONENT_BOM.csv','bom/DAN_NEW_PARTS.csv']
 for p in required:check('Present '+p,(ROOT/p).is_file() and (ROOT/p).stat().st_size>0)
 for p in ('README.md','docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md','docs/V2_LIMITATIONS_RU.md','audit/v2_native_boards_final.json','audit/v2_schematic_equivalence.json','audit/v2_routing_engineering.json','audit/v2_independent_final_review.json','docs/step_transport.json',*required):
  if (ROOT/p).is_file():inputs[p]=sha(ROOT/p)
 report={'stage':'FINAL_SAVED_CAD_AND_ARTIFACT_GATE','ok':all(c['pass'] for c in checks),'base_commit':BASE,'base_tag':'v1.0','branch':'mesh-repeater-2.0','CAD_modified':False,'checks':checks,'inputs_sha256':inputs,'physical_tests_performed':False,'remaining_physical_checks':['Exact NiceNano clone USB/LDO/charger modification','Actual IDC mate, cable length and all 12 conductors','Thread engagement and mechanical assembly sample','EMI and converter/LC transient stability','Inherited cell and LTO balancer operating limitations; see V2_LIMITATIONS_RU.md']}
 out=ROOT/'audit/V2_FINAL_ACCEPTANCE.json';out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'ok':report['ok'],'passed':sum(c['pass'] for c in checks),'total':len(checks),'failed':[c for c in checks if not c['pass']],'report':str(out)},ensure_ascii=False))
 if not report['ok']:sys.exit(1)

if __name__=='__main__':main()
