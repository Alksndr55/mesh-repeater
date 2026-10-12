"""Record the user's explicit choice and refresh only documentation bindings."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
decision={
 'date':'2026-10-12','timezone':'Asia/Omsk',
 'authority':'Explicit human reply in this conversation',
 'user_answer':'Сохранить прежнюю схему LTO и отмеченные ограничения',
 'status':'PRESERVE_EXISTING_LTO_AND_ACCEPT_NOTED_LIMITATIONS',
 'scope':['E-I1','E-I2'],
 'implementation':'Existing LMV431 direct balancers and 2-ohm resistors retained; existing CN3722 divider retained; no balancer current booster or independent TPS63802 VIN overvoltage disconnect added.',
 'risks_mitigated':False,'CAD_modified_for_this_decision':False,
 'limitations':['LMV431 cathode current limit is not guaranteed by the existing 2-ohm circuit.','CN3722 divider alone does not guarantee TPS63802 VIN<=5.5V with the battery absent or during OVP transients.'],
 'native_boards':[]
}
expected={'Power':'c4efced02420f48fea993d166091e3ba3ec7be7cf9bc30feec164d067077cc3b','Logic':'6cbd7850caa14163ebe4d40aba4435ac8fe17f327d68419dfb94e0a1bc361bc8','Shield':'4ba1d2a7b47dd392b2ac79fa9a7e10fbf8e98be6b8a3423c813d8530ddb25147'}
for name,digest in expected.items():
 rel=f'design/MeshRepeater2_{name}/MeshRepeater2_{name}.kicad_pcb'
 assert sha(ROOT/rel)==digest,rel
 decision['native_boards'].append({'path':rel,'sha256':digest})
path=OUT/'user_decision.json'
path.write_text(json.dumps(decision,ensure_ascii=False,indent=2),encoding='utf-8')
wrapper_path=ROOT/'audit/v2_independent_final_review.json'
wrapper=json.loads(wrapper_path.read_text(encoding='utf-8'))
updated={'docs/V2_CHANGES_FROM_S4_16_RU.md','docs/V2_ROUTING_ENGINEERING_AUDIT_RU.md'}
for record in wrapper['inputs']:
 actual=sha(ROOT/record['path'])
 if record['path'] in updated:record['sha256']=actual
 else:assert record['sha256']==actual,record['path']
wrapper['inherited_design_decision']={
 'status':decision['status'],'date':decision['date'],
 'user_answer':decision['user_answer'],'risks_mitigated':False,
 'retained':'2-ohm direct LMV431 balancers and existing CN3722 divider without independent overvoltage protection.',
 'not_applied':'Proposed current booster and low-resistance VIN disconnect.',
 'evidence':{'path':str(path.relative_to(ROOT)),'sha256':sha(path)}
}
wrapper_path.write_text(json.dumps(wrapper,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'choice_recorded':True,'native_boards_unchanged':True,'risks_mitigated':False}))
