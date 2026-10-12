from pathlib import Path
import sys,json,csv,hashlib,re
ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew
configure_headless()
OUT=ROOT/'audit/vertical_interconnect_2026_10_12'
paths={
'power_board':'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb',
'power_model':'design/MeshRepeater2_Power/model.json',
'power_schematic':'design/MeshRepeater2_Power/Thermal.kicad_sch',
'power_footprint':'design/MeshRepeater2_Power/Meshcore.pretty/SOT-23__V2_Q5.kicad_mod',
'baseline_board':'design/Meshcore_NaIon/Meshcore_NaIon.kicad_pcb',
'baseline_schematic':'design/Meshcore_NaIon/Thermal.kicad_sch',
'current_bom':'bom/V2_COMPONENT_BOM.csv',
'baseline_bom':'bom/legacy_S4_16/shopping_S4_16_REFERENCE_ONLY.csv',
'dan_card':'audit/vertical_interconnect_2026_10_12/q5_selection_sources/dan_bss138.html',
'manufacturer_pdf':'audit/vertical_interconnect_2026_10_12/q5_selection_sources/hottech_bss138.pdf'}
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
evidence={k:{'path':v,'sha256':sha(ROOT/v)} for k,v in paths.items()}
def native(path):
 b=pcbnew.LoadBoard(str(ROOT/path));f=next(f for f in b.GetFootprints() if f.GetReference()=='Q5')
 return {'value':f.GetValue(),'footprint':str(f.GetFPID().GetLibNickname())+':'+str(f.GetFPID().GetLibItemName()),'position_mm':[pcbnew.ToMM(f.GetPosition().x),pcbnew.ToMM(f.GetPosition().y)],'rotation_deg':f.GetOrientationDegrees(),'pads':{p.GetNumber():{'net':p.GetNetname(),'size_mm':[pcbnew.ToMM(p.GetSize().x),pcbnew.ToMM(p.GetSize().y)],'position_mm':[pcbnew.ToMM(p.GetPosition().x),pcbnew.ToMM(p.GetPosition().y)],'attribute':int(p.GetAttribute())} for p in f.Pads()},'model_paths':[m.m_Filename for m in f.Models()]}
current=native(paths['power_board']);baseline=native(paths['baseline_board'])
model=json.loads((ROOT/paths['power_model']).read_text(encoding='utf-8')); part=next(p for p in model['parts'] if p['ref']=='Q5')
with (ROOT/paths['current_bom']).open(encoding='utf-8-sig',newline='') as f: bom=next(r for r in csv.DictReader(f) if r.get('Reference')=='Q5' or r.get('reference')=='Q5' or r.get('Ref')=='Q5')
card=(ROOT/paths['dan_card']).read_text(encoding='utf-8')
stock=int(re.search(r'На складе:\s*(\d+)',card).group(1))
checks={
'value_is_BSS138':current['value']=='BSS138',
'footprint_is_SOT23':current['footprint']=='Meshcore:SOT-23__V2_Q5',
'3D_model_is_SOT23':current['model_paths']==['${KICAD10_3DMODEL_DIR}/Package_TO_SOT_SMD.3dshapes/SOT-23.step'],
'pin1_is_gate':current['pads']['1']['net'].split('/')[-1]=='CHG_G_ENABLE',
'pin2_is_source_ground':current['pads']['2']['net']=='GND',
'pin3_is_drain':current['pads']['3']['net'].split('/')[-1]=='CHG_PULLDOWN',
'fit_NaIon_only':part['fit_naion'] and not part['fit_lto2s'] and not part['fit_naion_no_cold'],
'baseline_already_same_MPN':baseline['value']==current['value'],
'baseline_already_SOT23':baseline['footprint']=='Meshcore:SOT-23',
'shop_has_stock':stock>0,
}
r={'status':'PASS' if all(checks.values()) else 'FAIL','date_local':'2026-10-12','scope':'Q5 transistor selection; read-only; no CAD, BOM, model or document mutation','selected_MPN':'BSS138','manufacturer':'Hottech','package':'SOT-23','recommendation':'Retain existing BSS138. The user-requested SOT-23 package is already implemented; no electrically distinct replacement is necessary. If changing to a different MPN despite this, it must be separately selected, not automatic 2N7002 substitution.','procurement':{'shop':'Danomsk','article':'79502','stock':stock,'single_price_rub':4.5,'url':part['vendor_url'],'timestamp_scope':'availability observed on 2026-10-12; can change'},'checks':checks,'current_native_Q5':current,'baseline_native_Q5':baseline,'current_model_Q5':part,'current_BOM_Q5':bom,'source_hashes':evidence,'electrical_role':{'gate':'R66=1k from CHG_WARM; R67=1M to ground; R63=100k pullup to LM285 2.5V reference. Not a 3.3V MCU or BAT gate driver.','drain':'R68=1k to CHG_G_SHUNT; R58=100k connects common PMOS gate to CS_P. Sink only gate-control current; does not carry charge power current.','nominal_static_Vgs_without_hysteresis_V':2.5*1e6/(1e6+100e3+1e3),'worst_control_current_5_5V_R1percent_A':5.5/(0.99*(100e3+1e3)),'qualification':'Manufacturer PDF lists RDS(on) max 2.5 ohm at VGS=1.8 V / ID=50mA / TA=25C; this is ample for nominal tens-of-uA drain-control current. Cold-temperature startup and full T2 transient qualification remain physical checks, not newly claimed proven.'},'pin_mapping_exception_needed':False,'baseline_preservation_exception_needed':False}
(OUT/'q5_selection.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':r['status'],'checks':checks,'stock':stock,'native':current},ensure_ascii=False,indent=2))


