"""Fresh A2 CAD gate; inherited A1 manuals are explicitly historical.

Does not qualify real connector contacts, cell behavior, EMC or manufacture.
Run after native metadata, local-library, schematic, DRC and STEP refresh.
"""
from pathlib import Path
import hashlib,json
from v2_feature_contract import load_feature

ROOT=Path(__file__).resolve().parents[1]

def main():
    checks=[];inputs={}
    def check(name,passed,detail=None):checks.append({'name':name,'pass':bool(passed),'detail':detail})
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    def read(relative):
        path=ROOT/relative;inputs[relative]=sha(path)
        return json.loads(path.read_text(encoding='utf-8-sig'))
    def bound(relative,expected):
        path=ROOT/str(relative).replace('\\','/')
        actual=sha(path) if path.is_file() else None
        check('SHA256 '+str(relative),actual==expected,{'expected':expected,'actual':actual})
    def hashes(doc):
        for path,digest in doc.get('inputs',{}).items():bound(path,digest)
    def records(doc):
        if isinstance(doc,dict):
            if 'path' in doc and 'sha256' in doc:bound(doc['path'],doc['sha256'])
            for item in doc.values():records(item)
        elif isinstance(doc,list):
            for item in doc:records(item)
    feature=load_feature(ROOT/'design/v2_electrical_contract.json')
    check('Authorized A2 addition with immutable S4.16 contract',bool(feature))
    for name in ('v2_native_boards_final','v2_schematic_equivalence'):
        doc=read('audit/'+name+'.json')
        check(name,doc.get('ok') and all(x['pass'] for x in doc['checks']),len(doc['checks']))
        hashes(doc)
    geometry_review='audit/routing_geometry_2026_10_12/independent_final.json'
    review_path=geometry_review if (ROOT/geometry_review).is_file() else 'audit/ina219_and_vertical_2026_10_12/independent_final_review.json'
    independent=read(review_path)
    check('Independent final A2 PCB review',independent.get('ok') and all(x['pass'] for x in independent['checks']),independent.get('checks'))
    hashes(independent)
    if review_path==geometry_review:
        check('Independent routing geometry review covers both saved boards',independent.get('routing_geometry_review_complete') is True)
    closure_path='audit/routing_geometry_2026_10_12/closure_review.json'
    if (ROOT/closure_path).is_file():
        closure=read(closure_path)
        records(closure)
        check('All 18 initial audit findings have a verified disposition',len(closure['issues'])==18 and not closure['genuine_unapplied_safe_actions'] and closure['independent_saved_native_gate_pass'])
    mating=read('audit/ina219_vertical_interconnect_2026_10_12/vertical_coordinate_mating.json')
    check('All 12 physical pairs and actual isolated screen holes align',mating['status']=='SAVED_NATIVE_THREE_BOARD_ALIGNMENT_PASS' and len(mating['matched_pins'])==12)
    for board,digest in mating['input_sha256'].items():
        name='MeshRepeater2_'+board.title();bound(f'design/{name}/{name}.kicad_pcb',digest)
    for board in ('POWER','LOGIC','SHIELD'):
        name='MeshRepeater2_'+board.title()
        doc=read(f'output/{board}/{name}_drc.json')
        counts={key:len(doc.get(key,[])) for key in ('violations','unconnected_items','schematic_parity','ignored_checks')}
        check(board+' strict DRC including parity where applicable',not any(counts.values()),counts)
        exports=read(f'output/{board}/{name}_exports.json')
        bound(exports['pcb'],exports['sha256'])
        for artifact in exports['artifacts']:bound(artifact['path'],artifact['sha256'])
    for board in ('POWER','LOGIC'):
        doc=read(f'audit/schematic/{board}/erc.json')
        count=sum(len(s.get('violations',[])) for s in doc['sheets'])
        check(board+' strict ERC',not count and not doc.get('ignored_checks'),count)
    qa=read('audit/schematic/final_schematic_output_manifest.json')
    check('Both current A2 schematic PDFs visually reviewed',qa.get('revision')=='V2.0-A2' and qa['page_count']==10 and qa['every_page_visually_inspected'])
    records(qa);records(read('output/pdf/SCHEMATIC_MANIFEST.json'))
    geometry=read('docs/mechanics/assembly_geometry_report.json')
    bound(geometry['stack_source'],geometry['stack_contract_sha256'])
    for record in geometry['inputs'].values():
        bound(record['path'],record['sha256'])
        source=record['verified_pcb_source'];bound(source['path'],source['sha256'])
    assembly=geometry['artifacts']['MeshRepeater2_assembly']
    for key in ('pcb_intersections','hardware_to_component_clearances'):
        check('A2 native '+key, bool(assembly[key]) and all(x['pass'] for x in assembly[key]),assembly[key])
    gap=assembly['vertical_envelope_clearances']
    check('Ordinary components clear screen; intentional pins checked by full Boolean',gap['power_nonpassing_envelope_to_screen_mm']>0 and gap['logic_envelope_to_screen_mm']>0 and gap['intentional_header_passage']['Boolean_collision_check_includes_all_solids'],gap)
    rendered=read('docs/mechanics/native_render_report.json')
    check('Three current A2 native assembly views',rendered.get('revision')=='V2.0-A2' and len(rendered.get('renders',[]))==3)
    for view in rendered.get('renders',[]):
        bound(view['image'],view['image_sha256'])
        for source in view['verified_native_inputs'].values():
            bound(source['path'],source['sha256'])
            bound(source['verified_pcb_source']['path'],source['verified_pcb_source']['sha256'])
    transport=read('docs/step_transport.json')
    check('Four lossless current STEP transport copies',len(transport['files'])==4)
    for row in transport['files']:
        bound(row['original_path'],row['original_sha256'])
        bound(row['transport_path'],row['gzip_sha256'])
        check('Lossless STEP '+row['original_path'],row['verified_decompressed_sha256']==row['original_sha256'])
    routing=read('audit/v2_routing_engineering.json');hashes(routing)
    check('Routing audit stable snapshot',routing['snapshot_stable'] and not routing['changed_inputs'])
    for board in ('POWER','LOGIC'):
        data=routing['boards'][board]
        check(board+' routing continuity',data['native_unconnected_count']==0 and all(x['found_without_zones'] for x in data['paths'].values()),{n:x for n,x in data['paths'].items() if not x['found_without_zones']})
    bom=read('audit/v2_component_bom.json');hashes(bom)
    bound('bom/V2_COMPONENT_BOM.csv',bom['bom_sha256'])
    check('BOM accounts for old positions and new INA',bom['baseline_positions_fully_accounted'] and not bom['model_selection_sync_pending_refs'] and len(bom['new_INA219_positions'])==6)
    frozen=read('baseline/S4_16/freeze_manifest.json')
    for path,digest in frozen['files'].items():bound('baseline/S4_16/'+path,digest)
    for relative in ('design/feature_ina219_vertical.json','design/interboard_cable.json','docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md','docs/V2_LIMITATIONS_RU.md','README.md','output/pdf/MeshRepeater2_Power_V2_A2_INA219_schematic.pdf','output/pdf/MeshRepeater2_Logic_V2_A2_schematic.pdf'):
        path=ROOT/relative;check('Current A2 file '+relative,path.is_file() and path.stat().st_size>0)
        if path.is_file():inputs[relative]=sha(path)
    out=ROOT/'audit/V2_FINAL_ACCEPTANCE.json'
    previous=ROOT/'audit/ina219_and_vertical_2026_10_12/before/V2_FINAL_ACCEPTANCE_A1.json'
    if out.is_file() and not previous.exists():previous.parent.mkdir(parents=True,exist_ok=True);previous.write_bytes(out.read_bytes())
    report={'stage':'V2_0_A2_INA219_VERTICAL_SAVED_CAD_GATE','ok':all(x['pass'] for x in checks),'checks':checks,'inputs_sha256':inputs,'physical_tests_performed':False,'manufacturing_release':False,'remaining_physical_checks':independent.get('remaining_physical_checks',[]),'accepted_inherited_LTO_limitations':'PRESERVE_EXISTING_LTO_AND_ACCEPT_NOTED_LIMITATIONS','historical_A1_documents':['output/pdf/MeshRepeater2_assembly_manual_RU.pdf','output/pdf/MeshRepeater2_assembly_dimensions.pdf','output/pdf/MeshRepeater2_Power_schematic.pdf','output/pdf/MeshRepeater2_Logic_schematic.pdf','audit/v2_independent_final_review.json','audit/fixes_2026_10_12/reviewer.json','docs/mechanical_library_checks.json','docs/mechanical_model_checks.json'],'current_instructions':'docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md'}
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'passed':sum(x['pass'] for x in checks),'total':len(checks),'failed':[x for x in checks if not x['pass']]},ensure_ascii=True))
    if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
