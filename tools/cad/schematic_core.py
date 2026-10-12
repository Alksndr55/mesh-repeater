"""Editable, explicitly wired KiCad schematic primitives for revision S3.

Coordinates are millimetres in page coordinates. Pin numbering follows the
manufacturer rather than the order used to draw a symbol. No graphic wire is
used as a substitute for an electrical KiCad wire.
"""
from pathlib import Path
import json, uuid, re, os

V2_ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('MESHCORE_PROJECT_DIR'):
    raise RuntimeError('Pass MESHCORE_PROJECT_DIR explicitly to the v2 CAD generator')
ROOT = Path(os.environ['MESHCORE_PROJECT_DIR']).resolve()
if not ROOT.is_relative_to(V2_ROOT):
    raise RuntimeError('The v2 CAD generator can only write inside Mesh_Repeater_2_0')
MODEL = json.loads((ROOT / 'model.json').read_text(encoding='utf-8'))
PARTS = {p['ref']: p for p in MODEL['parts']}
PROJECT = MODEL['project']
q = lambda s: json.dumps(str(s), ensure_ascii=False)
uid = lambda: str(uuid.uuid4())
stable = lambda s: str(uuid.uuid5(uuid.NAMESPACE_DNS, PROJECT + ':S2:' + s))
ROOT_ID = stable('root')

def fx(size=1.0, justify='', hide=False):
    return ('(effects (font (size %s %s)) %s %s)' %
            (size, size, '(justify '+justify+')' if justify else '', '(hide yes)' if hide else ''))

DEFS = {}
def line(points, width=.254):
    return '(polyline (pts %s) (stroke (width %s) (type default)) (fill (type none)))' % (
        ' '.join('(xy %s %s)' % (x, -y) for x,y in points), width)
def box(x1,y1,x2,y2, fill='background'):
    return '(rectangle (start %s %s) (end %s %s) (stroke (width .254) (type default)) (fill (type %s)))' % (x1,-y1,x2,-y2,fill)
def define(name, pins, graphics, label_y=-8.89):
    # pins: number,label,x,y,side,type,length(optional)
    DEFS[name] = dict(pins=pins,graphics=graphics,label_y=label_y)
def chip(name, pins, width=30.48,height=40.64):
    define(name,pins,box(-width/2,-height/2,width/2,height/2),-height/2-6.35)
P = 'passive'
for name, horizontal in [('R_H',True),('R_V',False)]:
    pins=[('1','',-5.08,0,'L',P),('2','',5.08,0,'R',P)] if horizontal else [('1','',0,-5.08,'T',P),('2','',0,5.08,'B',P)]
    graphics=box(-2.54,-1.016,2.54,1.016,'none') if horizontal else box(-1.016,-2.54,1.016,2.54,'none')
    define(name,pins,graphics)
define('R_H_REV',[('2','',-5.08,0,'L',P),('1','',5.08,0,'R',P)],box(-2.54,-1.016,2.54,1.016,'none'))
for name,horizontal in [('C_H',True),('C_V',False),('CP_V',False)]:
    pins=[('1','',-5.08,0,'L',P),('2','',5.08,0,'R',P)] if horizontal else [('1','',0,-5.08,'T',P),('2','',0,5.08,'B',P)]
    g = (line([(-2.54,0),(-.635,0)])+line([(.635,0),(2.54,0)])+line([(-.635,-2.54),(-.635,2.54)],.508)+line([(.635,-2.54),(.635,2.54)],.508)) if horizontal else (line([(0,-2.54),(0,-.635)])+line([(0,.635),(0,2.54)])+line([(-2.54,-.635),(2.54,-.635)],.508)+line([(-2.54,.635),(2.54,.635)],.508))
    if name=='CP_V':g+=line([(-3.81,-2.54),(-3.81,0)],.18)+line([(-5.08,-1.27),(-2.54,-1.27)],.18)
    define(name,pins,g)
coil=''.join(f'(arc (start {x} 0) (mid {x+.635} 1.27) (end {x+1.27} 0) (stroke (width .254) (type default)) (fill (type none)))' for x in [-2.54,-1.27,0,1.27])
define('L_H',[('1','',-5.08,0,'L',P),('2','',5.08,0,'R',P)],coil)
for name,vert in [('D_H',False),('D_V',True),('LED_V',True)]:
    pins=[('2','A',0,-5.08,'T',P),('1','K',0,5.08,'B',P)] if vert else [('2','A',-5.08,0,'L',P),('1','K',5.08,0,'R',P)]
    g=line([(-1.905,-1.905),(1.905,-1.905),(0,1.905),(-1.905,-1.905)])+line([(-1.905,1.905),(1.905,1.905)]) if vert else line([(-1.905,-1.905),(-1.905,1.905),(1.905,0),(-1.905,-1.905)])+line([(1.905,-1.905),(1.905,1.905)])
    g+=line([(0,-2.54),(0,-1.905)])+line([(0,1.905),(0,2.54)]) if vert else line([(-2.54,0),(-1.905,0)])+line([(1.905,0),(2.54,0)])
    if name=='LED_V':g+=line([(2.54,-1.27),(5.08,-3.81),(4.064,-3.81),(5.08,-3.81),(5.08,-2.794)],.18)+line([(3.81,0),(6.35,-2.54),(5.334,-2.54),(6.35,-2.54),(6.35,-1.524)],.18)
    define(name,pins,g)
# P-channel MOSFET: source left, drain right; gate below. Internal body diode
# is drawn from drain (anode) to source (cathode). AO3401A SOT23: G1 S2 D3.
g=line([(-7.62,0),(-2.54,0),(-2.54,-2.54)])+line([(7.62,0),(2.54,0),(2.54,-2.54)])+line([(-3.81,-2.54),(3.81,-2.54)])+line([(-3.81,0),(-1.27,0)])+line([(0,-.635),(0,.635)])+line([(1.27,0),(3.81,0)])+line([(-3.81,2.54),(3.81,2.54)])+line([(0,2.54),(0,5.08)])+line([(2.54,-2.54),(2.54,-6.35),(-2.54,-6.35),(-2.54,-2.54)])+line([(1.27,-7.62),(1.27,-5.08),(-1.27,-6.35),(1.27,-7.62)])+line([(-1.27,-7.62),(-1.27,-5.08)])+line([(-2.54,-2.54),(-1.27,-3.81),(-1.27,-1.27),(-2.54,-2.54)])
# Rotate the conventional KiCad Q_PMOS_GSD artwork into left-to-right power
# flow. Manufacturer pin numbers stay G1/S2/D3. The body diode is explicit.
pmos_lines=[[(.254,1.905),(.254,-1.905)],[(.254,0),(-2.54,0)],[(.762,2.286),(.762,1.27)],[(.762,1.778),(3.302,1.778),(3.302,-1.778),(.762,-1.778)],[(.762,.508),(.762,-.508)],[(.762,-1.27),(.762,-2.286)],[(2.286,0),(1.27,.381),(1.27,-.381),(2.286,0)],[(2.54,2.54),(2.54,1.778)],[(2.54,-2.54),(2.54,0),(.762,0)],[(2.921,-.381),(3.683,-.381)],[(3.302,-.381),(2.921,.254),(3.683,.254),(3.302,-.381)]]
g=''.join(line([(y,2.54-x) for x,y in pts]) for pts in pmos_lines)
g+='(circle (center 0 -0.889) (radius 2.794) (stroke (width .254) (type default)) (fill (type none)))'
g+=line([(-5.08,0),(-2.54,0)])+line([(5.08,0),(2.54,0)])
define('PMOS',[('2','S',-10.16,0,'L',P,5.08),('3','D',10.16,0,'R',P,5.08),('1','G',0,7.62,'B','input',2.54)],g,-12.7)
define('SW_H',[('1','',-5.08,0,'L',P),('2','',5.08,0,'R',P)],line([(-2.54,0),(2.54,-2.54)])+line([(-1.27,-3.81),(1.27,-3.81)])+line([(0,-3.81),(0,-5.08)]))
define('JUMPER_H',[('1','',-7.62,0,'L',P,5.08),('2','',7.62,0,'R',P,5.08)],
       '(circle (center -2.54 0) (radius .762) (stroke (width .254) (type default)) (fill (type none)))'+
       '(circle (center 2.54 0) (radius .762) (stroke (width .254) (type default)) (fill (type none)))',-7.62)
define('D_UP',[('1','K',0,-5.08,'T',P),('2','A',0,5.08,'B',P)],line([(-1.905,1.905),(1.905,1.905),(0,-1.905),(-1.905,1.905)])+line([(-1.905,-1.905),(1.905,-1.905)])+line([(0,-2.54),(0,-1.905)])+line([(0,1.905),(0,2.54)]))
define('MountingHole',[], '(circle (center 0 0) (radius 2.54) (stroke (width .254) (type default)) (fill (type none)))',-6.35)
define('TP',[('1','',0,2.54,'B',P)],'(circle (center 0 0) (radius .762) (stroke (width .254) (type default)) (fill (type none)))',-5.08)
define('BAT_V',[('1','+',0,-7.62,'T',P),('2','-',0,7.62,'B',P)],line([(-3.81,-2.54),(3.81,-2.54)],.508)+line([(-1.905,-1.27),(1.905,-1.27)],.762)+line([(-3.81,1.27),(3.81,1.27)],.508)+line([(-1.905,2.54),(1.905,2.54)],.762)+line([(0,-5.08),(0,-2.54)])+line([(0,2.54),(0,5.08)]),-11.43)
define('PWR_FLAG',[('1','',0,2.54,'B','power_out')],line([(0,0),(-1.27,1.27),(0,2.54),(1.27,1.27),(0,0)]),-2.54)
define('GND',[('1','',0,0,'T','power_in',0)],
       line([(0,0),(0,1.27)],.18)+line([(-1.905,1.27),(1.905,1.27)],.18)+
       line([(-1.27,2.54),(1.27,2.54)],.18)+line([(-.635,3.81),(.635,3.81)],.18))
DEFS['BAT_V']['pins'][0]=('1','+',0,-7.62,'T','power_out')
for n in [2,4,6]:
    chip('J'+str(n),[(str(i+1),str(i+1),10.16,(i-(n-1)/2)*5.08,'R',P) for i in range(n)],10.16,n*5.08)
chip('CN3722',[
 ('15','VCC',-20.32,-15.24,'L','power_in'),('16','DRV',-20.32,-5.08,'L','output'),('1','VG',-20.32,5.08,'L','power_out'),('7','MPPT',-20.32,15.24,'L','input'),
 ('13','CSP',20.32,-15.24,'R','input'),('14','BAT',20.32,-7.62,'R','input'),('10','FB',20.32,0,'R','input'),('6','TEMP',20.32,7.62,'R','input'),('4','CHRG',20.32,15.24,'R','open_collector'),('5','DONE',20.32,20.32,'R','open_collector'),
 ('8','COM1',-10.16,40.64,'B',P,15.24),('9','COM2',0,40.64,'B',P,15.24),('11','COM3',10.16,40.64,'B',P,15.24),('2','PGND',-5.08,30.48,'B','power_in'),('3','GND',5.08,30.48,'B','power_in'),('12','NC',20.32,-22.86,'R','no_connect')],30.48,50.8)
chip('TPS2116', [('3','VIN1 USB',-20.32,-7.62,'L','power_in'),('6','VIN2 BAT',-20.32,7.62,'L','power_in'),('2','VOUT',20.32,-7.62,'R',P),('7','VOUT',20.32,-2.54,'R','power_out'),('8','ST',20.32,7.62,'R','open_collector'),('4','PR1',-7.62,20.32,'B','input'),('5','MODE',0,20.32,'B','input'),('1','GND',7.62,20.32,'B','power_in')],30.48,30.48)
chip('TPS63802', [('10','VIN',-20.32,-12.7,'L','power_in'),('1','EN',-20.32,0,'L','input'),('2','MODE',-20.32,12.7,'L','input'),('9','L1',-7.62,-25.4,'T',P),('7','L2',7.62,-25.4,'T',P),('6','VOUT',20.32,-12.7,'R','power_out'),('4','FB',20.32,0,'R','input'),('5','PG',20.32,12.7,'R','open_collector'),('3','AGND',-5.08,25.4,'B','power_in'),('8','PGND',5.08,25.4,'B','power_in')],30.48,40.64)
chip('TPS22918', [('1','VIN',-15.24,-7.62,'L','power_in'),('3','ON',-15.24,7.62,'L','input'),('6','VOUT',15.24,-7.62,'R','power_out'),('5','QOD',15.24,7.62,'R',P),('4','CT',0,17.78,'B',P),('2','GND',-7.62,17.78,'B','power_in')],20.32,25.4)
chip('TPS3808', [('6','VDD',-17.78,-10.16,'L','power_in'),('5','SENSE',-17.78,0,'L','input'),('3','~{MR}',-17.78,10.16,'L','input'),('1','~{RESET}',17.78,0,'R','open_collector'),('4','CT',7.62,20.32,'B',P),('2','GND',-7.62,20.32,'B','power_in')],25.4,30.48)
chip('ATtiny13A', [
 ('8','VCC',-20.32,-12.7,'L','power_in'),('1','PB5 / RESET',-20.32,0,'L','input'),
 ('2','PB3 / TXEN_IN',-20.32,12.7,'L','input'),('3','PB4',20.32,17.78,'R','bidirectional'),
 ('5','PB0 / RESET_OD / MOSI',20.32,-12.7,'R','bidirectional'),
 ('6','PB1 / MISO',20.32,-2.54,'R','bidirectional'),('7','PB2 / SCK',20.32,7.62,'R','input'),
 ('4','GND',0,27.94,'B','power_in')],30.48,45.72)
chip('DS3231', [('2','VCC',-20.32,-15.24,'L','power_in'),('14','VBAT',-20.32,-2.54,'L','power_in'),('15','SDA',20.32,-15.24,'R','bidirectional'),('16','SCL',20.32,-7.62,'R','input'),('3','INT/SQW',20.32,2.54,'R','open_collector'),('4','RST',20.32,12.7,'R','open_collector'),('1','32kHz',20.32,20.32,'R','open_collector')]+[(str(i),'NC',-10.16+(i-5)*2.54,30.48,'B',P) for i in range(5,13)]+[('13','GND',-20.32,20.32,'L','power_in')],30.48,50.8)
chip('DS3231M', [('2','VCC',-20.32,-15.24,'L','power_in'),('6','VBAT',-20.32,-2.54,'L','power_in'),('7','SDA',20.32,-15.24,'R','bidirectional'),('8','SCL',20.32,-7.62,'R','input'),('3','INT/SQW',20.32,2.54,'R','open_collector'),('4','RST',20.32,12.7,'R','open_collector'),('1','32kHz',20.32,20.32,'R','open_collector'),('5','GND',-20.32,20.32,'L','power_in')],30.48,50.8)
# INA219 D/SOIC-8 ordering. DCN/SOT-23-8 has a different pinout.
chip('INA219', [('8','IN+',-20.32,-7.62,'L','input'),('7','IN-',-20.32,7.62,'L','input'),
 ('3','SDA',20.32,-7.62,'R','bidirectional'),('4','SCL',20.32,7.62,'R','input'),
 ('5','VS',0,-30.48,'T','power_in'),('6','GND',0,30.48,'B','power_in'),
 ('2','A0',-7.62,25.4,'B','input'),('1','A1',7.62,25.4,'B','input')],30.48,40.64)
chip('BAT_HEADER_LEFT', [('1','+',-10.16,-2.54,'L',P),('2','GND',-10.16,2.54,'L',P)],10.16,10.16)
# Headers represent the actual installed modules, not inferred clone circuitry.
names=['P0.09 / RADIO_RST','P0.10 / DIO1','P1.11 / SCK','P1.13 / NSS','P1.15 / MOSI','P0.02 / MISO','P0.29 / BUSY','P0.31 / BAT_ADC','VCC / MOD_3V3','RESET','GND','RAW - NC','BAT - NC','P1.06 / spare','P1.04 / SDA','P0.11 / SCL','P1.00 / USER_BTN','P0.24 / GPS_EN / DIGITAL OUT','P0.22 / GPS_RX','P0.20 / GPS_TX','P0.17 / RXEN','GND','GND','P0.08 / UART_RX','P0.06 / UART_TX','GND']
nn_names={str(i+1):n for i,n in enumerate(names)}
nn_left=[9,8,10,17,18,19,20,24,25,15,16,12,13]
nn_right=[1,2,7,3,5,6,4,21,14]
nn_pins=[(str(n),nn_names[str(n)],-40.64,-25.4+i*5.08,'L',P) for i,n in enumerate(nn_left)]
nn_pins +=[(str(n),nn_names[str(n)],40.64,-25.4+i*5.08,'R',P) for i,n in enumerate(nn_right)]
nn_pins +=[(str(n),'GND',-11.43+i*7.62,45.72,'B',P) for i,n in enumerate([11,22,23,26])]
define('NiceNano',nn_pins,box(-35.56,-30.48,35.56,40.64),-36.83)
names=['ANT' if MODEL.get('rf_connector') else 'ANT / IPEX used','GND','3V3','RST','TXEN = DIO2','DIO1','DIO2 = TXEN','DIO3','GND','BUSY','RXEN','SCK','MISO','MOSI','NSS','GND']
ht_names={str(i+1):n for i,n in enumerate(names)}
ht_left=[4,6,10,12,14,13,15,11,5]
ht_pins=[(str(n),ht_names[str(n)],-27.94,-25.4+i*5.08,'L',P) for i,n in enumerate(ht_left)]
ht_pins +=[('7',ht_names['7'],-27.94,20.32,'L',P)]
ht_pins +=[(str(n),ht_names[str(n)],27.94,y,'R',P) for n,y in [(3,-25.4),(1,-7.62),(8,7.62)]]
ht_pins +=[(str(n),'GND',-7.62+i*7.62,30.48,'B',P) for i,n in enumerate([2,9,16])]
define('HT_RA62',ht_pins,box(-22.86,-30.48,22.86,25.4),-36.83)

# Four physical shield legs share schematic pin 2.
define('COAX', [('1','RF',-7.62,0,'L',P),('2','SHIELD',0,7.62,'B',P)],
       '(circle (center 0 0) (radius 2.54) (stroke (width .254) (type default)) (fill (type none)))'
       + line([(-5.08,0),(0,0)],.254) + line([(0,2.54),(0,5.08)],.254), -7.62)
define('SAW', [('2','IN',-12.7,0,'L',P),('5','OUT',12.7,0,'R',P)] +
       [(str(n),'GND',x,12.7,'B',P) for n,x in [(1,-7.62),(3,-2.54),(4,2.54),(6,7.62)]],
       box(-7.62,-5.08,7.62,7.62) + line([(-2.54,-2.54),(0,2.54),(2.54,-2.54)],.18), -10.16)
define('NETTIE', [('1','',-5.08,0,'L',P,2.54),('2','',5.08,0,'R',P,2.54)],
       line([(-2.54,0),(2.54,0)],.508)+line([(-.635,1.905),(.635,-1.905)],.18), -7.62)

# Standard discrete NMOS G1/S2/D3, draw left-to-right input with source down.
nm=[[(.254,-1.905),(.254,1.905)],[(.254,0),(-2.54,0)],[(.762,-2.286),(.762,-1.27)],[(.762,-1.778),(3.302,-1.778),(3.302,1.778),(.762,1.778)],[(.762,-.508),(.762,.508)],[(.762,1.27),(.762,2.286)],[(1.27,0),(2.286,-.381),(2.286,.381),(1.27,0)],[(2.54,-2.54),(2.54,-1.778)],[(2.54,2.54),(2.54,0),(.762,0)],[(2.921,-.381),(3.683,-.381)],[(3.302,-.381),(2.921,.254),(3.683,.254),(3.302,-.381)]]
g=''.join(line(z) for z in nm)+ '(circle (center 1.27 0) (radius 2.794) (stroke (width .254) (type default)) (fill (type none)))'
define('NMOS',[('1','G',-7.62,0,'L','input',5.08),('3','D',2.54,-7.62,'T',P,5.08),('2','S',2.54,7.62,'B',P,5.08)],g,-12.7)
define('NTC_V',[('1','',0,-5.08,'T',P,2.54),('2','',0,5.08,'B',P,2.54)],box(-1.016,-2.54,1.016,2.54,'none')+line([(-2.54,3.81),(2.54,-3.81),(3.81,-3.81)],.18))
# ON LM285Z TO-92: unused pin1, cathode pin2, anode pin3. Reference is fixed,
# so the conventional shunt-diode artwork has no adjustment terminal.
define('LM285Z',[('2','K',0,-7.62,'T',P,5.08),('3','A',0,7.62,'B',P,5.08),('1','NC',-7.62,0,'L','no_connect',2.54)],line([(-1.905,1.905),(1.905,1.905),(0,-1.905),(-1.905,1.905)])+line([(-1.905,-2.54),(-1.905,-1.905),(1.905,-1.905),(1.905,-1.27)])+line([(0,-2.54),(0,-1.905)])+line([(0,1.905),(0,2.54)]),-12.7)
chip('LM393Dual',[('3','+ A',-25.4,-12.7,'L','input'),('2','- A',-25.4,-5.08,'L','input'),('1','OUT A',25.4,-8.89,'R','open_collector'),('5','+ B',-25.4,12.7,'L','input'),('6','- B',-25.4,20.32,'L','input'),('7','OUT B',25.4,16.51,'R','open_collector'),('8','VCC',0,-35.56,'T','power_in',6.35),('4','GND',0,35.56,'B','power_in',6.35)],45.72,58.42)
for cy in (-8.89,16.51):
    DEFS['LM393Dual']['graphics'] += line([(-12.7,cy-8.89),(-12.7,cy+8.89),(12.7,cy),(-12.7,cy-8.89)])
    DEFS['LM393Dual']['graphics'] += line([(-20.32,cy-3.81),(-12.7,cy-3.81)])+line([(-20.32,cy+3.81),(-12.7,cy+3.81)])+line([(12.7,cy),(20.32,cy)])


def lib_symbol(name,qualified=True):
    d=DEFS[name]; pins=[]
    for row in d['pins']:
        num,label,x,y,side,typ,*rest=row
        length=rest[0] if rest else (5.08 if name not in ['R_H','R_H_REV','R_V','C_H','C_V','CP_V','L_H','D_H','D_V','D_UP','LED_V','SW_H','TP','BAT_V','PWR_FLAG'] else 2.54)
        angle={'L':0,'R':180,'T':270,'B':90}[side]
        pins.append(f'(pin {typ} line (at {x} {-y} {angle}) (length {length}) (name {q(label or "~")} {fx(.95)}) (number {q(num)} {fx(.9)}))')
    passive = name in ['R_H','R_H_REV','R_V','C_H','C_V','CP_V','L_H','D_H','D_V','D_UP','LED_V','SW_H','TP','BAT_V','GND']
    power = '(power)' if name=='GND' else ''
    pin_numbers = '(pin_numbers hide)' if passive else ''
    return f'(symbol {q(("Meshcore:" if qualified else "")+name)} {power} {pin_numbers} (pin_names (offset .6)) (exclude_from_sim no) (in_bom yes) (on_board yes) (property "Reference" "U" (at 0 {-d["label_y"]} 0) {fx()}) (property "Value" {q(name)} (at 0 {-d["label_y"]-2.54} 0) {fx()}) (symbol {q(name+"_0_1")} {d["graphics"]}) (symbol {q(name+"_1_1")} {" ".join(pins)}))'

class Sheet:
    def __init__(self,name,title,page,root=False):
        page = MODEL.get('sheet_pages',{}).get(name,page)
        root = name == MODEL.get('root_sheet', 'Charger')
        self.name,self.title,self.page,self.root=name,title,page,root
        self.path='/'+ROOT_ID if root else '/'+ROOT_ID+'/'+stable('sheet:'+name)
        self.id=ROOT_ID if root else stable('sheetroot:'+name)
        self.items=[];self.placed={};self.styles={};self.coords={};self.refs=[];self.power_count=0
        self.global_labels=[];self.wires=[];self.parts_table=[];self.component_annotations=[]
    def sym(self,ref,x,y,style=None, label=None):
        p=PARTS[ref];style=style or {'R':'R_H','C':'C_V','Inductor':'L_H','Diode':'D_H','LED':'LED_V','PMOS_GSD':'PMOS','Connector2':'J2','Connector4':'J4','Connector6':'J6','ATtiny13A':'ATtiny13A','Switch':'SW_H','TestPoint':'TP','CN3722':'CN3722','TPS2116':'TPS2116','TPS63802':'TPS63802','TPS22918':'TPS22918','TPS3808':'TPS3808','DS3231':'DS3231','DS3231M':'DS3231M','INA219':'INA219','Battery':'BAT_V','NiceNano_Modified':'NiceNano','HT_RA62':'HT_RA62','MountingHole':'MountingHole','NMOS_GSD':'NMOS','NTC':'NTC_V','LM285Z':'LM285Z','LM393Dual':'LM393Dual'}[p['kind']]
        if p['kind']=='MountingHole' and p['nets']:
            style='GND_BOLT'
            if style not in DEFS:
                define(style,[('1','GND',0,5.08,'B',P)],'(circle (center 0 0) (radius 2.54) (stroke (width .254) (type default)) (fill (type none)))',-6.35)
        assert ref not in self.placed,ref
        d=DEFS[style];self.placed[ref]=(x,y);self.styles[ref]=style;self.refs.append(ref)
        ly=d['label_y'];lx=x
        vertical = style in ['R_V','C_V','CP_V','D_V','D_UP','LED_V']
        if label is None and vertical:
            offset=8.89 if style=='LED_V' else 3.81
            rx,ry,vx,vy=(x+offset,y-1.27,x+offset,y+1.27)
        else:rx,ry,vx,vy=(x,y+ly,x,y+ly+2.54) if label is None else label
        hidden=(p['kind'] in ['TestPoint'])
        justify=('left' if rx>x else 'right' if rx<x else '') if vertical else ''
        display_lines={'C2':['100nF 50V','X7R'],'C5':['470pF 50V','C0G'],'C14':['22uF 25V','X5R']}.get(ref)
        if ref in ('R3','R4') and MODEL.get('battery_dividers'):
            display_lines=[p['value'].split(' <=')[0]]
        props=f'(property "Reference" {q(ref)} (at {rx} {ry} 0) {fx(1.27,justify)}) (property "Value" {q(p["value"])} (at {vx} {vy} 0) {fx(1.27,justify,hide=hidden or bool(display_lines))})'
        # Keep the true Value unchanged for BOM/netlist/PCB parity. Only these
        # three crowded graphical presentations use two editable display lines.
        if display_lines:
            dx,dy,djustify=(x+3.81,y-2.54,'left') if ref=='C5' else (vx,vy,justify)
            for i,line in enumerate(display_lines):
                props+=f'(property {q("Value display "+str(i+1))} {q(line)} (at {dx} {dy+i*2.54} 0) {fx(1.27,djustify)})'
        for key,val in [('Footprint',p['footprint']),('Description',p.get('note','')),('MPN',p.get('mpn','')),('LCSC',p.get('lcsc','')),('Vendor',p.get('vendor','')),('Vendor URL',p.get('vendor_url',''))]:props+=f'(property {q(key)} {q(val)} (at {x} {y} 0) {fx(hide=True)})'
        if p.get('datasheet'):
            props+=f'(property "Datasheet" {q(p["datasheet"])} (at {x} {y} 0) {fx(hide=True)})'
        if MODEL.get('assembly_policy'):
            from assembly_s4_10 import fields
            for key,val in fields(p).items():props+=f'(property {q(key)} {q(val)} (at {x} {y} 0) {fx(hide=True)})'
        sid=stable('component:'+ref)
        inbom='no' if p['kind'] in ['TestPoint','MountingHole','NetTie'] else 'yes'
        self.items.append(f'(symbol (lib_id {q("Meshcore:"+style)}) (at {x} {y} 0) (unit 1) (exclude_from_sim no) (in_bom {inbom}) (on_board yes) (dnp {"yes" if p["dnp"] else "no"}) (uuid {q(sid)}) {props} '+ ' '.join(f'(pin {q(z[0])} (uuid {q(uid())}))' for z in d['pins'])+f'(instances (project {q(PROJECT)} (path {q(self.path)} (reference {q(ref)}) (unit 1)))))')
        p['schematic_uuid']=sid;p['sheet_path']=self.path
        for n,_,dx,dy,*_ in d['pins']:self.coords[(ref,str(n))]=(round(x+dx,5),round(y+dy,5))
        return self
    def pin(self,ref,n):return self.coords[(ref,str(n))]
    def point(self,p):return self.pin(*p) if isinstance(p[0],str) else p
    def wire(self,*points):
        pts=[tuple(round(v,5) for v in self.point(p)) for p in points]
        for (x,y),(a,b) in zip(pts,pts[1:]):
            if (x,y)==(a,b):continue
            self.wires.append(((x,y),(a,b)))
            self.items.append(f'(wire (pts (xy {x} {y}) (xy {a} {b})) (stroke (width 0) (type default)) (uuid {q(uid())}))')
    def dot(self,point):
        x,y=self.point(point);self.items.append(f'(junction (at {x} {y}) (diameter 0) (color 0 0 0 0) (uuid {q(uid())}))')
    def label(self,name,point,angle=0,global_=False):
        x,y=self.point(point)
        if global_:
            assert angle in (0,180), 'Global labels must remain horizontal'
            self.global_labels.append(dict(name=name,at=[x,y],angle=angle))
            self.items.append(f'(global_label {q(name)} (shape input) (at {x} {y} {angle}) {fx(.95,"right" if angle==0 else "left")} (uuid {q(uid())}) (property "Intersheetrefs" "" (at {x} {y} {angle}) {fx(hide=True)}))')
        else:self.items.append(f'(label {q(name)} (at {x} {y} {angle}) {fx(.95,"left bottom")} (uuid {q(uid())}))')
    def global_stub(self,name,*points,angle=0):
        """A global name terminates a real horizontal wire, outside the rail."""
        assert len(points)>=2
        before,end=map(self.point,points[-2:])
        assert abs(before[1]-end[1])<1e-5 and before[0]!=end[0]
        assert (before[0]>end[0]) == (angle==0), (name,before,end,angle)
        self.wire(*points)
        self.label(name,end,angle,True)
    def net(self,ref,n,length=7.62,name=None):
        if (name or PARTS[ref]['nets'][str(n)])=='GND':
            self.ground((ref,n),0 if PARTS[ref]['kind'].startswith('Connector') else 3.81)
            return self.pin(ref,n)
        point=self.pin(ref,n);d=DEFS[self.styles[ref]]
        side=next(row[4] for row in d['pins'] if row[0]==str(n))
        dx,dy={'L':(-length,0),'R':(length,0),'T':(0,-length),'B':(0,length)}[side]
        end=(round(point[0]+dx,5),round(point[1]+dy,5));self.wire(point,end)
        if side in ('T','B'):
            tip=(round(end[0]-5.08,5),end[1])
            self.global_stub(name or PARTS[ref]['nets'][str(n)],end,tip)
            end=tip
        else:self.label(name or PARTS[ref]['nets'][str(n)],end,0 if side=='L' else 180,True)
        return end
    def nc(self,ref,n):
        x,y=self.pin(ref,n);self.items.append(f'(no_connect (at {x} {y}) (uuid {q(uid())}))')
    def ground(self,point,length=5.08):
        x,y=self.point(point);end=(x,round(y+length,5));self.wire((x,y),end)
        self.power_count+=1;ref=f'#PWR{self.page}{self.power_count:03}'
        sid=stable(ref)
        self.items.append(f'(symbol (lib_id "Meshcore:GND") (at {end[0]} {end[1]} 0) (unit 1) (exclude_from_sim no) (in_bom no) (on_board no) (dnp no) (uuid {q(sid)}) (property "Reference" {q(ref)} (at {end[0]} {end[1]} 0) {fx(hide=True)}) (property "Value" "GND" (at {end[0]} {end[1]} 0) {fx(hide=True)}) (pin "1" (uuid {q(uid())})) (instances (project {q(PROJECT)} (path {q(self.path)} (reference {q(ref)}) (unit 1)))))')
    def graphic(self,pts,width=.18):
        self.items.append(f'(polyline (pts {" ".join(f"(xy {x} {y})" for x,y in pts)}) (stroke (width {width}) (type default)) (fill (type none)) (uuid {q(uid())}))')
    def text(self,msg,x,y,size=1.15,justify='left'):
        self.items.append(f'(text {q(msg)} (at {x} {y} 0) {fx(size,justify)} (uuid {q(uid())}))')
    def flag(self,name,x,y,index):
        ref='#FLG'+str(index);sid=stable(ref)
        self.items.append(f'(symbol (lib_id "Meshcore:PWR_FLAG") (at {x} {y} 0) (unit 1) (exclude_from_sim no) (in_bom no) (on_board no) (dnp no) (uuid {q(sid)}) (property "Reference" {q(ref)} (at {x} {y-2.54} 0) {fx(hide=True)}) (property "Value" "PWR_FLAG" (at {x} {y-5.08} 0) {fx(hide=True)}) (pin "1" (uuid {q(uid())})) (instances (project {q(PROJECT)} (path {q(self.path)} (reference {q(ref)}) (unit 1)))))')
        if name=='GND':self.ground((x,y+2.54),3.81)
        else:self.global_stub(name,(x,y+2.54),(x-5.08,y+2.54))
    def write(self):
        self.text(self.title,15,15,1.7)
        revision=MODEL.get('schematic_revision','S4.1' if MODEL.get('usb_isolation_jumper') else 'S3')
        date=MODEL.get('schematic_date','2026-10-05')
        self.text(revision+' / '+date+' / инженерный прототип',15,22,1.27)
        embedded=' '.join(lib_symbol(n) for n in DEFS)
        # Place every electrical endpoint on KiCad's standard 50-mil grid.
        # Local symbol pin coordinates already use the same grid, so snapping
        # symbol centres and absolute wire/junction/label points preserves all
        # intended pin coincidences. Library artwork is deliberately unchanged.
        def snap(match):
            a=round(round(float(match[2])/1.27)*1.27,5)
            b=round(round(float(match[3])/1.27)*1.27,5)
            return match[1]+str(a)+' '+str(b)
        drawing=re.sub(r'(\((?:at|xy)\s+)(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)',snap,'\n'.join(self.items))
        short_title={'Charger':'CN3722 / зарядка Na-ion и LTO','Powerpath':'TPS2116 / выбор источника','Converter':'TPS63802 / питание и фильтр','Modules':'Nice!Nano / HT-RA62','RTC_IO':'DS3231M / разъёмы','Watchdog':'ATtiny13A / watchdog','LTO_Balancer':'LMV431A / LTO 2S опция','Thermal':'LM393XK / холодный заряд Na-ion','BatteryMonitor':'INA219 / батарея и ток','Interconnect':'Межплатное соединение / POWER ↔ LOGIC'}[self.name]
        content=f'(kicad_sch (version 20250114) (generator "eeschema") (uuid {q(self.id)}) (paper "A3") (title_block (title {q(short_title)}) (date {q(date)}) (rev {q(revision)}) (comment 1 "Электрическая принципиальная; прототип")) (lib_symbols {embedded}) '+ drawing
        if self.root:content+=' (sheet_instances (path "/" (page "1")))'
        content+=' (embedded_fonts no))'
        filename=PROJECT if self.root else self.name
        (ROOT/(filename+'.kicad_sch')).write_text(content,encoding='utf-8')

def library():
    (ROOT/'Meshcore.kicad_sym').write_text('(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor") '+' '.join(lib_symbol(n,False) for n in DEFS)+')',encoding='utf-8')
