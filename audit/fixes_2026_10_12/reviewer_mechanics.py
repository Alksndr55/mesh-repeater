"""Independent read-only focused verification; only writes reviewer proof files."""
from pathlib import Path
import csv, hashlib, json, subprocess, sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def mm(n): return pcbnew.ToMM(n)
paths = [ROOT/'design'/('MeshRepeater2_'+n)/('MeshRepeater2_'+n+'.kicad_pcb') for n in ('Power','Logic')]
initial = {str(p.relative_to(ROOT)):sha(p) for p in paths}
out = {'reviewer':'independent agent, no CAD writes','date':'2026-10-12','native_initial_sha256':initial,'findings':[]}
bom = list(csv.DictReader((ROOT/'bom/V2_COMPONENT_BOM.csv').open(encoding='utf-8-sig')))
extra = list(csv.DictReader((ROOT/'bom/DAN_NEW_PARTS.csv').open(encoding='utf-8-sig')))
selection = json.loads((ROOT/'docs/mechanical_selection.json').read_text(encoding='utf-8'))
byref = {r['Reference']:r for r in bom}
byextra = {r['Refs']:r for r in extra}
houses = byextra['J3_J5_HOUSINGS']; contacts = byextra['J3_J5_CONTACTS']
assert houses['MPN']=='Connfly I-DS1071-SCB01x4' and float(houses['Quantity_per_assembly'])==2
assert contacts['MPN']=='Connfly T-DS1071-SC600' and float(contacts['Quantity_per_assembly'])==8
assert houses['Article']=='208362' and contacts['Article']=='201995'
assert houses['Supplier']==contacts['Supplier']=='ДАН'
assert all('Cable mate:' in byref[r]['Note'] for r in ['J3','J5'])
out['findings'].append({'id':'M-01','status':'PASS_DOCUMENTED_SELECTION','housing_mpn':houses['MPN'],'contact_mpn':contacts['MPN'],'quantity_per_assembly':[2,8],'quantity_five_full_assemblies':[10,40],'saved_stock_observation':[houses['Stock_observed'],contacts['Stock_observed']],'supplier_cards':[houses['Purchase_URL'],contacts['Purchase_URL']],'manufacturer':'https://en.connfly.com/static/upload/file/pdf/DS1071.pdf','manufacturer_visual_check':'DS1071 sheet lists DS1021/DS1022 male family, SQ 0.64±0.05, pitch 2.54, 4-position B10.16/A7.62, female 2.54×14.00, .XX tolerance ±0.25. SC6 terminal tin; AWG28–22.','actual_mating_qualified':False})
holes=[]; switches=[]; headers=[]
for path in paths:
    board=pcbnew.LoadBoard(str(path))
    for f in board.GetFootprints():
        ref=f.GetReference()
        if ref in ('H1','H2','H3','H4'):
            pads=[]
            for p in f.Pads():
                pads.append({'number':p.GetNumber(),'attribute':p.GetAttribute(),'PTH':p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH,'net':p.GetNetname(),'drill_mm':[mm(p.GetDrillSize().x),mm(p.GetDrillSize().y)],'copper_diameter_mm':[mm(p.GetSize().x),mm(p.GetSize().y)]})
            assert len(pads)==1 and pads[0]['PTH'] and pads[0]['net']=='GND'
            row=byref[ref]
            assert all(row[n]=='M3 GND contact' for n in ('Value_NaIon_COLD','Value_NaIon_NoCOLD','Value_LTO_2S'))
            assert 'plated' in row['Note'].lower() and 'NPTH' not in row['Note']
            fields={field.GetName():field.GetText() for field in f.GetFields()}
            assert fields.get('Value_LTO_2S')=='M3 GND contact'
            assert fields.get('Value_NaIon_NoCold')=='M3 GND contact'
            library=path.parent/'Meshcore.pretty'/(str(f.GetFPID().GetLibItemName())+'.kicad_mod')
            current=library.read_bytes()
            baseline=subprocess.run(['git','cat-file','blob','HEAD:'+str(library.relative_to(ROOT)).replace('\\','/')],cwd=ROOT,check=True,capture_output=True).stdout
            assert baseline.replace(b'"M3 NPTH"',b'"M3 GND contact"')==current
            holes.append({'board':str(path.relative_to(ROOT)),'reference':ref,'value':f.GetValue(),'pads':pads,'bom_note':row['Note'],'variant_fields':{n:fields[n] for n in ['Value_LTO_2S','Value_NaIon_NoCold']},'library_change_only_expected_metadata':True,'library_sha256':sha(library)})
        elif ref in ('SW1','SW2'):
            switches.append({'board':str(path.relative_to(ROOT)),'reference':ref,'pose':[mm(f.GetPosition().x),mm(f.GetPosition().y),f.GetOrientationDegrees()],'pads':[{'number':p.GetNumber(),'position_mm':[mm(p.GetPosition().x),mm(p.GetPosition().y)],'drill_mm':[mm(p.GetDrillSize().x),mm(p.GetDrillSize().y)],'attribute':p.GetAttribute()} for p in f.Pads()],'models':[str(m.m_Filename) for m in f.Models()]})
        elif ref in ('J3','J5'):
            pads=[{'number':p.GetNumber(),'net':p.GetNetname(),'position_mm':[mm(p.GetPosition().x),mm(p.GetPosition().y)]} for p in f.Pads()]
            headers.append({'reference':ref,'pose':[mm(f.GetPosition().x),mm(f.GetPosition().y),f.GetOrientationDegrees()],'pads':pads})
            assert len(pads)==4
            if ref=='J3': assert {p['number']:p['net'] for p in pads}=={'1':'SYS_3V3','2':'GND','3':'SCL','4':'SDA'}
            if ref=='J5': assert {p['number']:p['net'] for p in pads}=={'1':'GND','2':'SYS_3V3','3':'UART_TX','4':'UART_RX'}
assert len(holes)==4 and len(switches)==2 and len(headers)==2
model_path=ROOT/'design/MeshRepeater2_Power/model.json'
model=json.loads(model_path.read_text(encoding='utf-8'))
for ref in ('H1','H2','H3','H4'):
    part=next(p for p in model['parts'] if p['ref']==ref)
    assert all(part[n]=='M3 GND contact' for n in ['value','value_lto2s','value_naion_no_cold'])
    assert all(model['assembly_variants_authoritative'][ref][n]=='M3 GND contact' for n in ['Value_NaIon','Value_LTO_2S','Value_NaIon_NoCold'])
schematic_path=ROOT/'design/MeshRepeater2_Power/Interconnect.kicad_sch'
schematic=schematic_path.read_bytes()
old_schematic=subprocess.run(['git','cat-file','blob','HEAD:'+str(schematic_path.relative_to(ROOT)).replace('\\','/')],cwd=ROOT,check=True,capture_output=True).stdout
assert old_schematic.replace(b'"M3 NPTH"',b'"M3 GND contact"')==schematic
generator=(ROOT/'tools/build_v2_component_bom.py').read_text(encoding='utf-8')
assert generator.count('p["value"] if p["kind"] == "MountingHole" else')==3
out['findings'].append({'id':'DOC-01','status':'PASS','holes':holes,'generator_all_three_variants_current_mounting_value':True,'model_authoritative_variant_labels_synchronized':True,'schematic_changed_only_expected_metadata':True})
out['switches_native']=switches;out['headers_native']=headers
out['native_unchanged_by_review']=initial=={str(p.relative_to(ROOT)):sha(p) for p in paths}
assert out['native_unchanged_by_review']
out['input_sha256']={s:sha(ROOT/s) for s in ['bom/V2_COMPONENT_BOM.csv','bom/DAN_NEW_PARTS.csv','docs/mechanical_selection.json','tools/build_v2_component_bom.py','tools/cad/build_v2_mechanical_library.py']}
(ROOT/'audit/fixes_2026_10_12/reviewer_mechanics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'findings':[(f['id'],f['status']) for f in out['findings']], 'native_unchanged':out['native_unchanged_by_review']},ensure_ascii=False))
