"""Record the narrowly scoped mechanical/BOM fixes and their fresh proofs."""
from pathlib import Path
import csv
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
before=json.loads((OUT/'mechanics.before.json').read_text(encoding='utf-8'))
for rel in ('docs/mechanical_model_checks.json','docs/mechanical_library_checks.json',
            'docs/mechanics_findings_RU.md','tools/build_v2_component_bom.py'):
    raw=subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT)
    before[rel]=hashlib.sha256(raw).hexdigest()
(OUT/'mechanics.before.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
rows=list(csv.DictReader((ROOT/'bom/V2_COMPONENT_BOM.csv').open(encoding='utf-8-sig')))
assert len(rows)==172 and len({r['Reference']for r in rows})==172
for row in rows:
    if row['Reference']in ('H1','H2','H3','H4','H201','H202','H203','H204'):
        assert all(row[k]=='M3 GND contact'for k in ('Value_NaIon_COLD','Value_NaIon_NoCOLD','Value_LTO_2S'))
    if row['Reference']in ('J3','J5'):
        assert 'I-DS1071-SCB01x4' in row['Note']
accessories=list(csv.DictReader((ROOT/'bom/DAN_NEW_PARTS.csv').open(encoding='utf-8-sig')))
extra={r['Refs']:r for r in accessories if r['Refs'].startswith('J3_J5_')}
assert int(extra['J3_J5_HOUSINGS']['Quantity_per_assembly'])==2
assert int(extra['J3_J5_CONTACTS']['Quantity_per_assembly'])==8
models=json.loads((OUT/'mechanics.models.json').read_text(encoding='utf-8'))
pads=json.loads((OUT/'mechanics.footprint_checks.json').read_text(encoding='utf-8'))
paths=[p for p in before if not p.endswith('.kicad_mod')]
paths+=['docs/mechanics/Connfly_DS1071_SCB01x4_Mated_Envelope.step']
result={'date':'2026-10-12','scope':'Mesh Repeater 2.0 only',
  'findings':[
    {'id':'M-01','status':'FIXED_CAD_AND_PROCUREMENT_DOCUMENTS',
     'change':'Selected two original Connfly I-DS1071-SCB01x4 cable housings and eight T-DS1071-SC600 contacts. Added all-variant quantities, supplier URLs/current stock, manufacturer family compatibility, pin map and conservative housing envelope.',
     'proof':['bom/DAN_NEW_PARTS.csv','docs/mechanical_selection.json','docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md','audit/fixes_2026_10_12/mechanics_sources/Connfly_DS1071.pdf','audit/fixes_2026_10_12/mechanics.models.json'],
     'availability_checked':'2026-10-12','stock_housings':170,'stock_contacts':6746,
     'per_full_assembly':{'housings':2,'contacts':8},
     'quantity_for_five_full_assemblies':{'housings':10,'contacts':40},
     'hardware_mating_proven':False},
    {'id':'M-02','status':'FIXED_MODEL',
     'change':'TE switch nominal bracket envelope widened from 7.66 to 8.41 mm, 0.375 mm per side. Both actively used local STEP libraries match. No footprint/pad/courtyard change.',
     'proof':['docs/mechanical_model_checks.json','docs/mechanical_library_checks.json','audit/fixes_2026_10_12/mechanics.models.json','audit/fixes_2026_10_12/mechanics.footprint_checks.json']},
    {'id':'DOC-01','status':'FIXED_BOM_AND_GENERATOR',
     'change':'H1–H4 values in all three BOM variants now match current model/native M3 GND contact. Their existing Note explicitly says plated mounting hole. BOM generator now uses current MountingHole value rather than historical S4.16 NPTH variant labels.',
     'proof':['bom/V2_COMPONENT_BOM.csv','tools/build_v2_component_bom.py'],
     'physical_position_rows':172},
  ],
  'all_library_footprint_files_hash_unchanged':pads['all_library_footprint_files_hash_unchanged'],
  'fresh_mechanical_base_footprints_loaded':len(pads['mechanical_base_footprints']),
  'switch_width_after_mm':8.41,
  'mate_envelope_dimensions_max_mm':models['mate_model']['dimensions_max_mm'],
  'mate_min_stand_clearance_mm':{f['reference']:f['minimum_stand_clearance_mm']for f in models['mate_fit_nominal_stack']},
  'model_checks_previous_copy':'audit/fixes_2026_10_12/mechanical_model_checks.before.json',
  'footprint_checks_previous_copy':'audit/fixes_2026_10_12/mechanical_library_checks.before.json',
  'before_sha256':{p:before.get(p)for p in paths},
  'after_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in paths},
  'native_cad_written_by_this_task':False,
  'version1_changed_by_this_task':False,
  'remaining_measurements':'Physical crimp, housing stop/mating depth, cable retention, pin polarity and actual hardware access; none claimed as measured or proven by an envelope model.',
}
(OUT/'mechanics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'findings':{f['id']:f['status']for f in result['findings']},
                  'positions':172,'unchanged_footprints':result['all_library_footprint_files_hash_unchanged']},ensure_ascii=False))
