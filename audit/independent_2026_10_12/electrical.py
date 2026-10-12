"""Independent read-only electrical audit. Writes only electrical.json beside this file.

Run after KiCad XML exports electrical.power.xml and electrical.logic.xml.
It parses native PCB pads and native exported nets, not model.json connectivity.
Numerical inputs below are explicitly transcribed primary-datasheet limits.
They are not measurements and not values copied from prior project PASS reports.
"""
from pathlib import Path
from hashlib import sha256
import json, math, re, xml.etree.ElementTree as ET

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]

def digest(path):
    return sha256(path.read_bytes()).hexdigest()

def parse_sexpr(path):
    stack = []
    result = None
    for token in re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', path.read_text(encoding='utf8')):
        if token == '(':
            stack.append([])
        elif token == ')':
            value = stack.pop()
            if stack:
                stack[-1].append(value)
            else:
                result = value
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    assert not stack
    return result

def children(node, name):
    return [x for x in node if isinstance(x, list) and x and x[0] == name]

def first(node, name):
    matches = children(node, name)
    return matches[0] if matches else None

def exported_nets(board):
    path = OUT / f'electrical.{board}.xml'
    xml = ET.parse(path).getroot()
    pins = {}
    for net in xml.findall('./nets/net'):
        for node in net.findall('node'):
            key = (node.attrib['ref'], node.attrib['pin'])
            assert key not in pins
            pins[key] = dict(net=net.attrib['name'], **node.attrib)
    return pins

power, logic = exported_nets('power'), exported_nets('logic')
pcb_path = ROOT / 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
pcb = parse_sexpr(pcb_path)
pads = {}
for footprint in children(pcb, 'footprint'):
    ref = next((x[2] for x in children(footprint, 'property') if x[1] == 'Reference'), None)
    if ref not in ('M1', 'M2'):
        continue
    pads[ref] = []
    for pad in children(footprint, 'pad'):
        net, at = first(pad, 'net'), first(pad, 'at')
        native = logic[(ref, pad[1])]
        assert net[-1] == native['net'], (ref, pad[1], net, native)
        pads[ref].append(dict(pin=pad[1], local_xy_mm=list(map(float, at[1:3])),
                              net=net[-1], pinfunction=native.get('pinfunction')))

# Physical positions read from official nice!nano pinout viewed with USB at top.
# The project's footprint places its USB side at local +Y, i.e. rotated 180 degrees.
nice_gpio = {
 '1':'P0.09','2':'P0.10','3':'P1.11','4':'P1.13','5':'P1.15','6':'P0.02',
 '7':'P0.29','8':'P0.31','14':'P1.06','15':'P1.04','16':'P0.11','17':'P1.00',
 '18':'P0.24','19':'P0.22','20':'P0.20','21':'P0.17','24':'P0.08','25':'P0.06'}
for pin, gpio in nice_gpio.items():
    assert logic[('M1', pin)]['pinfunction'].startswith(gpio)
for entry in pads['M1']:
    pin = int(entry['pin'])
    x = -7.62 if pin <= 13 else 7.62
    row = pin-1 if pin <= 13 else pin-14
    y = -15.24 + row*2.54
    assert abs(entry['local_xy_mm'][0]-x)<1e-6 and abs(entry['local_xy_mm'][1]-y)<1e-6
for entry in pads['M2']:
    pin = int(entry['pin'])
    x, y = (-8, -7+(pin-1)*2) if pin<=8 else (8, 7-(pin-9)*2)
    assert entry['local_xy_mm'] == [x,y]

expected_harness = {str(p): 'FILTER_OUT' for p in (1,3,5,7)}
expected_harness.update({str(p): 'GND' for p in (2,4,6,8,10,12)})
expected_harness.update({'9':'BAT','11':'MODE'})
for pin, net in expected_harness.items():
    assert power[('J101',pin)]['net'] == net
    assert logic[('J201',pin)]['net'] == net
assert logic[('J11','1')]['net']=='FILTER_OUT'
assert logic[('J11','2')]['net']=='SYS_3V3'
assert all(logic[('J201',p)]['net']!='SYS_3V3' for p in expected_harness)

def cn_cv(rt, rb=100000, temp_span=0):
    # CN3722 Rev1.2 VFB min/typ/max 2.392/2.416/2.44 V; IFB max 300 nA.
    # Negative IFB minimum is not specified. Min below therefore excludes bias.
    d=.001+25e-6*temp_span
    return dict(typ_without_bias_V=2.416*(1+rt/rb),
                typ_with_50nA_V=2.416*(1+rt/rb)+50e-9*rt,
                min_excluding_unspecified_IFB_V=2.392*(1+rt*(1-d)/(rb*(1+d))),
                max_using_300nA_V=2.44*(1+rt*(1+d)/(rb*(1-d)))+300e-9*rt*(1+d),
                assumed_resistor_fractional_bound=d)

def en(rt, rb=49900):
    def bound(v, high):
        a,b=(rt*1.001,rb*.999) if high else (rt*.999,rb*1.001)
        # Conservative signed leakage assumption +/-0.2 uA, not a new TI limit.
        return v*(1+a/b)+(1 if high else -1)*.2e-6*a
    return dict(on_typ_V=1.1*(1+rt/rb),off_typ_V=1*(1+rt/rb),
                on_conservative_V=[bound(1.07,False),bound(1.13,True)],
                off_conservative_V=[bound(.97,False),bound(1.03,True)])

# Nodal solve includes comparator pull-up, feedback and MOSFET gate pull-down.
rt, rb, rh, rp, rg, vref = 130000.,100000.,1150000.,100000.,1001000.,2.5
a,b,c,d = 1/rt+1/rb+1/rh,-1/rh,-1/rh,1/rh+1/rp+1/rg
det=a*d-b*c
vth_warm=(vref/rt*d-b*vref/rp)/det
warm_out=(a*vref/rp-c*vref/rt)/det
def cold_vth(vol):
    return (vref/rt+vol/rh)/(1/rt+1/rb+1/rh)
def ntc_at_vth(v):
    return 100000*v/(vref-v)
rt8016=[(-30,17.7),(-25,13.04),(-20,9.707),(-15,7.293),(-10,5.533),
        (-5,4.232),(0,3.265),(5,2.539),(10,1.990),(15,1.571),(20,1.249),(25,1.)]
def temp_log_interp(r):
    for (t0,r0),(t1,r1) in zip(rt8016,rt8016[1:]):
        if r1*10000 <= r <= r0*10000:
            return t0+(t1-t0)*(math.log(r/10000)-math.log(r0))/(math.log(r1)-math.log(r0))
    raise ValueError(r)
cold_enter_r=ntc_at_vth(vth_warm)
warm_return_r=ntc_at_vth(cold_vth(0))

# LMV431A I-grade full-temperature VREF range, resistor 0.1%, IREF typ 0.15 uA.
# The simple current extrapolation is not a guaranteed out-of-range LMV431 model.
clamp_typ=1.24*(1+122490/100000)+.15e-6*122490
clamp_low=1.215*(1+122490*.999/(100000*1.001))
clamp_high=1.265*(1+122490*1.001/(100000*.999))+.9e-6*122490*1.001
calculated = {
 'CN3722_CV_Na_25C':cn_cv(61900),
 'CN3722_CV_LTO_25C':cn_cv(121000),
 'CN3722_CV_LTO_resistor_65K_offset':cn_cv(121000,temp_span=65),
 'CN3722_LTO_no_battery_typ_OVP_estimate_V':cn_cv(121000)['typ_with_50nA_V']*1.08,
 'CN3722_LTO_no_battery_25C_upper_OVP_envelope_V':cn_cv(121000)['max_using_300nA_V']*1.1,
 'CN3722_MPPT_25C':dict(typ_V=1.04*(1+105000/10000),
   conservative_min_V=1*(1+105000*.999/(10000*1.001))-.1e-6*105000*.999,
   conservative_max_V=1.08*(1+105000*1.001/(10000*.999))+.1e-6*105000*1.001),
 'EN_Na':en(40200),'EN_LTO':en(130000),
 'CN3722_cold_A':dict(typ=.2/(.28+1.8),min=.185/((.28+1.8)*1.01),max=.215/((.28+1.8)*.99)),
 'CN3722_noCold_or_LTO_A':dict(typ_ideal_shunt=.2/.28,min=.185/(.28*1.01),max=.215/(.28*.99)),
 'CN3722_warm_Rds_estimate_A':.2/(.28+1/(3/.085+1/1.8)),
 'TPS_VOUT_25C':dict(typ_V=.5*(1+56000/10000),
   min_excluding_unspecified_FB_bias_V=.495*(1+56000*.999/(10000*1.001)),
   max_using_100nA_V=.505*(1+56000*1.001/(10000*.999))+100e-9*56000*1.001),
 'COLD_nominal_R_T8016_log_interpolation':dict(VTH_warm=vth_warm,VWARM=warm_out,
   cold_enter_NTC_ohm=cold_enter_r,cold_enter_C=temp_log_interp(cold_enter_r),
   warm_return_ideal_VOL_NTC_ohm=warm_return_r,warm_return_ideal_VOL_C=temp_log_interp(warm_return_r),
   warm_return_with_210mV_VOL_C=temp_log_interp(ntc_at_vth(cold_vth(.210)))),
 'LTO_balancer':dict(clamp_typ_V=clamp_typ,clamp_conservative_low_V=clamp_low,
   clamp_conservative_high_with_0p9uA_assumption_V=clamp_high,
   current_simple_extrapolation_at_cell2p8V_lowcorner_A=(2.8-clamp_low)/1.98,
   cathode_power_if_30mA_and_typ_clamp_W=.03*clamp_typ),
 'BAT_ADC':dict(ratio_typ=.5,ratio_resistor_bounds=[.4995,.5005],Rthevenin_ohm=1100000,
   tau_s=.11,settling_1percent_s=-math.log(.01)*.11,
   settling_0p1percent_s=-math.log(.001)*.11,
   battery_error_V_per_1nA_ADC_leak=.0022,
   stock_multiplier=1.815,ideal_multiplier_3p6V_12bit=7200/4095,
   stock_vs_ideal_relative=1.815/(7200/4095)-1),
 'LC':dict(nominal_per_stage_uF=1000,min_bias_factor_for_330uF_with20percent_tolerance15percent_temp=.330/(1*.8*.85),
   undamped_single_stage_frequency_at330uF_Hz=1/(2*math.pi*math.sqrt(2.4e-6*330e-6)),
   undamped_single_stage_frequency_at1000uF_Hz=1/(2*math.pi*math.sqrt(2.4e-6*1000e-6))),
 'watchdog':dict(no_tx_nominal_seconds=1350*8,reset_nominal_seconds=1)
}

inputs = {}
for folder in ['MeshRepeater2_Power','MeshRepeater2_Logic']:
    for path in sorted((ROOT/'design'/folder).glob('*.kicad_sch')):
        inputs[str(path.relative_to(ROOT)).replace('\\','/')]=digest(path)
inputs[str(pcb_path.relative_to(ROOT)).replace('\\','/')]=digest(pcb_path)
for name in ['electrical.power.xml','electrical.logic.xml']:
    inputs['audit/independent_2026_10_12/'+name]=digest(OUT/name)
for name in ['main.c','Makefile']:
    path=ROOT/'design/watchdog_reference'/name
    inputs[str(path.relative_to(ROOT)).replace('\\','/')]=digest(path)

result=dict(audit_date='2026-10-12',head='547740fee937f891568f18485c7a6a3733c234c9',
    method='Fresh native KiCad XML, direct native PCB pad parser, primary datasheets, independent arithmetic. No CAD mutations.',
    input_sha256=inputs,findings_new_V2=[],
    inherited_accepted_risks=[
      dict(id='E-I1',severity='high',origin='inherited_S4.16_accepted',ref='U8/U9.3; R47/R51',
           evidence='2 ohm shunts do not bound LMV431 cathode current to recommended15mA or absolute30mA under cell imbalance.',
           location='design/MeshRepeater2_Power/LTO_Balancer.kicad_sch:10703; :9957; electrical.power.xml:4594; :4650',
           baseline_location='baseline/S4_16/assembly_variants_S4_16.csv:124; :130',
           primary_source='https://www.ti.com/lit/ds/symlink/lmv431.pdf',
           recommended_fix='If electrical redesign is later authorized, current-limit the balancing path or use a qualified balancer/protection; until then characterize current and temperature.'),
      dict(id='E-I2',severity='high',origin='inherited_S4.16_accepted',ref='U1.14 BAT -> U2.10 VIN',
           evidence='CN3722 no-battery OVP estimate exceeds TPS63802 recommended5.5V, with highcorner envelope approaching6V absolute.',
           location='design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_sch:16606; design/MeshRepeater2_Power/Converter.kicad_sch:21247; electrical.power.xml:1653; :3949',
           baseline_location='baseline/S4_16/assembly_variants_S4_16.csv:12',
           primary_sources=['https://consonance-elec.com/static/upload/file/20231218/1702867485736775.pdf','https://www.ti.com/lit/ds/symlink/tps63802.pdf'],
           recommended_fix='If redesign is authorized, add independently qualified voltage limiting; qualify startup/unplug transients and exclude unqualified no-battery operation.')],
    calculated=calculated,native_harness=expected_harness,native_module_pads=pads,
    physical_pinout_checked_sources=[
      'https://nicekeyboards.com/docs/nice-nano/pinout-schematic/',
      'https://resource.heltec.cn/download/HT-RA62/HT-RA62(Rev1.1).pdf',
      'https://resource.heltec.cn/download/HT-RA62/HT-RA62_Schematic_diagram.pdf'],
    limitations='This is circuit/CAD evidence, not bench qualification. Actual chosen NiceNano clone/rework, panel/cells, Ceff, transient stability, cable assembly and firmware failure recovery remain unverified.')
(OUT/'electrical.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(new_findings=0,native_module_pads=len(pads['M1'])+len(pads['M2']),calculated=calculated),ensure_ascii=True,indent=2))
