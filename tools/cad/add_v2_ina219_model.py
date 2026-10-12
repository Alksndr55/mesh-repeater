"""Apply the explicitly requested INA219 / vertical-header electrical delta.

The frozen S4.16 contract remains immutable. Native PCB copper is edited by
the narrow routing patch after this model update, never rebuilt from baseline.
"""
from pathlib import Path
import json,copy,uuid,hashlib,shutil
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'audit/ina219_and_vertical_2026_10_12'
OUT.mkdir(parents=True,exist_ok=True)
MAP={'1':'FILTER_OUT','2':'GND','3':'FILTER_OUT','4':'GND','5':'FILTER_OUT','6':'GND','7':'SYS_3V3','8':'GND','9':'BAT','10':'SDA','11':'MODE','12':'SCL'}
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
feature={'revision':'V2.0-A2-INA219','date':'2026-10-12','user_request':'INA219 on POWER, 0.1 ohm stock MeshCore calibration, vertical Ali interconnects',
 'baseline_contract_immutable':True,'interboard_pinmap':MAP,'new_references':['U12','R71','R72','R73','C63','C64'],
 'original_net_overrides':{},'series_projection':{'reference':'R71','pins':['1','2'],'nets':['BAT_SYS','BAT'],'purpose':'Only collapse the new series measurement resistor for the legacy endpoint-graph projection; the saved native nets must remain distinct.'},
 'raw_battery_endpoints':[('J8','1'),('J12','1'),('R47','1'),('R15','1'),('TP1','1'),('J101','9')],
 'INA219_expected_nets':{'1':'GND','2':'GND','3':'SDA','4':'SCL','5':'SYS_3V3','6':'GND','7':'INA_VIN_M','8':'INA_VIN_P'},
 'INA219_address':64,'shunt_ohm':0.1,'current_direction':'positive charge; negative discharge',
 'limits':['LTO balancer currents bypass main pack shunt through cell/midpoint branches','INA active current approximately 0.7mA typical, 1mA maximum; stock continuous mode retained','INA current range approximately +/-3.2A, power telemetry not signed','Generic Ali pin section and maximum insertion require actual samples','Accepted inherited LTO limitations are retained; no extra OVP or balancer amplifier']}
raw=set(tuple(v) for v in feature['raw_battery_endpoints'])
for board,ref in [('Power','J101'),('Logic','J201')]:
 folder=ROOT/'design'/('MeshRepeater2_'+board);path=folder/'model.json'
 model=json.loads(path.read_text(encoding='utf-8'))
 before=OUT/'before'/folder.name;before.mkdir(parents=True,exist_ok=True)
 if not (before/'model.json').exists():shutil.copy2(path,before/'model.json')
 if any(p['ref']=='U12' for p in model['parts']):raise RuntimeError('Already applied; do not duplicate positions')
 if board=='Power':
  for p in model['parts']:
   for pin,net in list(p['nets'].items()):
    if net=='BAT' and (p['ref'],pin) not in raw:
     p['nets'][pin]='BAT_SYS';feature['original_net_overrides'].setdefault('POWER',{}).setdefault(p['ref'],{})[pin]='BAT_SYS'
 cp=next(p for p in model['parts'] if p['ref']==ref)
 cp.update(nets=MAP.copy(),footprint='Meshcore:'+('Ali_PinHeader_2x06_P2.54_L35_A3C6' if board=='Power' else 'Ali_PinSocket_2x06_P2.54_H8.5_v2_mirror'),
  x=64.15,y=11.0 if board=='Power' else 49.0,rotation=90,value='INTERBOARD 2x6 VERTICAL',
  mpn='E-SIMPO L35mm A3C6 2x6P' if board=='Power' else 'MTJ H8.5 2X6P 10PCS',
  vendor='AliExpress',vendor_url='https://aliexpress.ru/item/1005011978353933.html?sku_id=12000057202232448' if board=='Power' else 'https://aliexpress.ru/item/1005008954873458.html?sku_id=12000047353417475',
  package='THT 2x6 / 2.54 / vertical',package_short='THT 2x6 / 2.54 / vertical',procurement_checked_at='2026-10-12',
  note='Direct vertical connection through 12 isolated screen holes. Mirrored female pad grid gives physical 1:1 after LOGIC X180. Pin7 returns SYS_3V3 to INA219 only; remove J11 before USB as before. Exact generic pin section and mating limits require sample check.',
  mpn_lto2s='E-SIMPO L35mm A3C6 2x6P' if board=='Power' else 'MTJ H8.5 2X6P 10PCS',mpn_naion_no_cold='E-SIMPO L35mm A3C6 2x6P' if board=='Power' else 'MTJ H8.5 2X6P 10PCS')
 cp.pop('source_footprint_before_v2_graphic_variant',None)
 model.update(revision='V2.0-A2-INA219',schematic_revision='V2.0-A2',schematic_date='2026-10-12',interboard_connector={'reference':ref,'pinmap':MAP,'method':'vertical through shield','male_length_mm':35,'female_height_mm':8.5})
 if board=='Power':
  def new(ref,kind,value,nets,fp,x,y,rot,mpn,layer='F.Cu',vendor='Danomsk',url='',package='0805'):
   sid=lambda key:str(uuid.uuid5(uuid.NAMESPACE_DNS,model['project']+':S2:'+key))
   return dict(ref=ref,kind=kind,value=value,nets=nets,footprint='Meshcore:'+fp,x=x,y=y,rotation=rot,native_layer=layer,
    mpn=mpn,lcsc='',note='INA219 battery monitor; fitted in Na-ion and LTO variants.',dnp=False,group='battery_monitor',vendor=vendor,vendor_url=url,
    package=package,package_short=package,procurement_package=package,procurement_checked_at='2026-10-12',
    fit_naion=True,fit_lto2s=True,fit_naion_no_cold=True,assembly_default_dnp=False,assembly='All variants: FIT',
    value_lto2s=value,value_naion_no_cold=value,mpn_lto2s=mpn,mpn_naion_no_cold=mpn,
    schematic_uuid=sid('component:'+ref),sheet_path='/'+sid('root')+'/'+sid('sheet:BatteryMonitor'))
  parts=[
   new('U12','INA219','INA219AIDR',feature['INA219_expected_nets'].copy(),'SOIC-8_3.9x4.9mm_P1.27mm',58.2,12.8,90,'INA219AIDR',vendor='ChipDip',url='https://www.chipdip.ru/product/ina219aidr-monitor-toka-high-side-texas-instruments-9001599766',package='SOIC-8 / 3.9x4.9 / P1.27'),
   new('R71','R','0.1R 1% 1W',{'1':'BAT_SYS','2':'BAT'},'R_2512_6332Metric',27.8,12.5,0,'RL2512FK-070R1L','B.Cu',url='https://www.danomsk.ru/shop/6-rezistory/86-rezistory-postoyannye/501-rezistory-chip-1210-2512/145965-chip-2512-0-1-1-rl2512fk-070r1l-yageo/',package='2512 / 1W'),
   new('R72','R','10R 1%',{'1':'BAT_SYS','2':'INA_VIN_P'},'R_0805_2012Metric',54.0,12.2,0,'RC0805FR-0710RL','B.Cu'),
   new('R73','R','10R 1%',{'1':'BAT','2':'INA_VIN_M'},'R_0805_2012Metric',54.0,14.8,0,'RC0805FR-0710RL','B.Cu'),
   new('C63','C','100nF 50V X7R',{'1':'SYS_3V3','2':'GND'},'C_0805_2012Metric',60.4,12.8,90,'CC0805KRX7R9BB104','B.Cu'),
   new('C64','C','100nF 50V X7R',{'1':'INA_VIN_P','2':'INA_VIN_M'},'C_0805_2012Metric',57.8,16.0,90,'CC0805KRX7R9BB104','B.Cu')]
  parts[0]['datasheet']='https://www.ti.com/lit/ds/symlink/ina219.pdf'
  parts[1]['note']='0.1 ohm stock INA219 calibration. Kelvin pickups at inner shunt pad edges. Normal 1.25A causes 125mV drop and 156mW; 1W device is not qualified for continuous 4A. TCR +/-600ppm/C for chosen Yageo 0.1ohm.'
  model['parts'].extend(parts)
  model['battery_monitor']={'reference':'U12','address':'0x40','shunt':'R71','shunt_ohm':0.1,'IN_plus':'BAT_SYS','IN_minus':'BAT','supply':'SYS_3V3 from LOGIC via J101.7','charge_cv_sense':'BAT_SYS (unchanged charger side)','cutoff_sense':'BAT (raw)','balancer_current_measured':False,'telemetry':'Voltage raw battery; signed current: charge positive; discharge negative; power not signed'}
 save(path,model)
feature['baseline_contract_sha256']=hashlib.sha256((ROOT/'design/v2_electrical_contract.json').read_bytes()).hexdigest()
save(ROOT/'design/feature_ina219_vertical.json',feature)
cable={'project':'Mesh Repeater2.0','revision':'V2_VERTICAL_INA219_A2','date':'2026-10-12','status':'NATIVE_VERTICAL_INTERCONNECT_IN_PROGRESS_SAMPLE_QUALIFICATION_PENDING',
 'connector_POWER':'J101','connector_LOGIC':'J201','contacts':12,'cable_route':'No ribbon cable. Direct long posts through isolated middle-screen apertures.',
 'geometry_status':'Nominal L35/H8.5 dimensions and reversed upper-board orientation; incoming pin/fit and assembly tolerance verification required.',
 'connections':[{'net':net,'power':{'ref':'J101','pin':pin},'logic':{'ref':'J201','pin':pin}} for pin,net in MAP.items()]}
save(ROOT/'design/interboard_cable.json',cable)
print(json.dumps({'new_components':feature['new_references'],'pinmap':MAP,'models_updated':True,'native_PCBs_modified':False},ensure_ascii=False))
