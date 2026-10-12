"""V2 only. Dimensioned connector footprints and simplified envelope STEP models.

Run with bundled Python --footprints; run with FreeCAD/bin/python.exe --models.
For a narrow model update use --models --only-model NAME; it leaves contracts,
footprints and other models unchanged.
Does not edit boards, schematic, source v1, or footprints placed on a board.
Manufacturer drawings are listed in docs/mechanical_selection.json.
"""
from pathlib import Path
import argparse
import json
import math
import copy
import csv

ROOT = Path(__file__).resolve().parents[2]
DESIGNS = [ROOT / 'design' / n for n in ('MeshRepeater2_Power', 'MeshRepeater2_Logic')]

DEFINITIONS = {
    'JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal': {
        'mpn': 'JST S2B-XH-A(LF)(SN)', 'refs': ['J7', 'J8'], 'article': 167075,
        'pads': [(str(i+1), 2.5*i, 0, 1.0, 'THT') for i in range(2)],
        'bbox': [-2.45, -9.2, 4.95, 2.3], 'height': 6.1, 'tail': 3.4, 'mating': [0, -1],
        'source': 'https://www.danomsk.ru/upload/iblock/11a/167075_e8e7acdd79497cc6a7262e2649317f11.pdf#page=3',
    },
    'KLS_XH_L_KLS1_2_50_04_R_Horizontal': {
        'mpn': 'KLS L-KLS1-2.50-04-R', 'refs': ['J12'], 'article': 38160,
        'pads': [(str(i+1), 2.5*i, 0, 1.0, 'THT') for i in range(4)],
        'bbox': [-2.5, -9.2, 10.0, 2.4], 'height': 5.8, 'tail': 3.4, 'mating': [0, -1],
        'source': 'https://img.klsele.com/admin/product_upload/20250303165321L-KLS1-2.50.pdf#page=6',
        'note': '4 positions: pins1..3 preserve former LTO nets; pin4 is NC. Matching4pole cable housing required.',
    },
    'Connfly_DS1013_12RSIB_B_0_Horizontal': {
        'mpn': 'Connfly DS1013-12RSIB-B-0', 'refs': ['J101', 'J201'], 'article': 134861,
        'pads': [(str(i+1), 2.54*(i%2), 2.54*(i//2), 1.02, 'THT') for i in range(12)],
        'bbox': [5.0, -5.07, 13.8, 17.77], 'height': 9.1, 'tail': 2.9, 'mating': [1, 0],
        'source': 'https://en.connfly.com/static/upload/file/pdf/DS1013.pdf#page=1',
        'note': 'R/A drawing rotated to solder tails down.13.8mm is plan reach;9.1mm is assembled height. Body depth8.8mm. Hole1.02±0.05.',
    },
    'Connfly_DS1022_1x02RUF11_B_Horizontal': {
        'mpn': 'Connfly DS1022-1x40RUF11-B cut to2pins', 'refs': ['J11'], 'article': 202688,
        'pads': [('1', 0, 0, 1.02, 'THT'), ('2', 0, 2.54, 1.02, 'THT')],
        'bbox': [-1.25, -1.27, 1.25, 3.81], 'height': 2.5, 'tail': 3.0,
        'overall_height': 6.07, 'mating_length': 6.0, 'mating': [1, 0],
        'source': 'https://en.connfly.com/static/upload/file/pdf/DS1022.pdf#page=1',
        'note': 'U type1, A3.00 solder tail,B6.00 mating length,C6.07 abovePCB. Do not subtractAfromC.',
    },
    'SW_TE_1825027_2_Side': {
        'mpn': 'TE1825027-2 / FSMRA1JH04', 'refs': ['SW1', 'SW2'], 'article': 199312,
        'pads': [('1', -2.25, 0, 0.99, 'THT'), ('2', 2.25, 0, 0.99, 'THT'),
                 ('', -3.505, 2.49, 1.30, 'NPTH'), ('', 3.505, 2.49, 1.30, 'NPTH')],
        'bbox': [-3.555, -2.49, 3.555, 1.19], 'courtyard_bbox': [-4.455, -3.30, 4.455, 4.26],
        'height': 7.01, 'tail': 3.51, 'mating': [0, -1], 'actuator_projection': 0.56,
        'bracket_width': 8.41,
        'source': 'https://www.te.com/en/product-1825027-2.html',
        'drawing_mirror': 'https://www.danomsk.ru/upload/iblock/51a/199312_5a706f693299daa97f0862bd57db70e9.pdf',
        'note': 'Electrical hole pitch4.50mm; bracket pitch7.01mm, not7.11bodywidth. Row separation2.49mm. Bracket width8.41mm and rearreach4.01 from electrical row included in courtyard. Bracket holes are non-electrical.',
    },
}

# Same documented40positionstrip, cut tofour positions for side UART/I2C.
four = copy.deepcopy(DEFINITIONS['Connfly_DS1022_1x02RUF11_B_Horizontal'])
four.update(mpn='Connfly DS1022-1x40RUF11-B cut to4pins', refs=['J3', 'J5'],
            pads=[(str(i+1),0,2.54*i,1.02,'THT') for i in range(4)],
            bbox=[-1.25,-1.27,1.25,8.89])
DEFINITIONS['Connfly_DS1022_1x04RUF11_B_Horizontal'] = four

# Cable-side female pieces for J3/J5. The DS1071 manufacturer drawing explicitly
# identifies DS1021/DS1022 as its matching male headers; this is not a pitch-only
# cross-brand substitution. These accessories do not alter any PCB footprint.
J3_J5_MATES = [
    {'refs':['J3_J5_HOUSINGS'], 'mpn':'Connfly I-DS1071-SCB01x4',
     'article':208362, 'quantity':2, 'unit':'pc',
     'dan_url':'https://www.danomsk.ru/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/208362-bls-1x04-i-ds1071-scb01x4-rozetka-obzh-bez-kontaktov-kontakty-178228-201995-shag-2-54mm-maks-dopust-/',
     'stock':170, 'stock_checked':'2026-10-12',
     'source':'https://en.connfly.com/static/upload/file/pdf/DS1071.pdf',
     'pitch_mm':2.54, 'housing_nominal_mm':[10.16,2.54,14.00],
     'housing_max_mm':[10.41,2.79,14.25],
     'mate_headers':['J3','J5'], 'mate_mpn':'Connfly DS1022-1x40RUF11-B cut to4pins',
     'note':'Два кабельных корпуса 1x4 без контактов. По одному для J3/I2C и J5/UART; требуется всего 8 T-DS1071-SC600. Разъёмы без ключа: первый контакт пометить вручную и проверить всю распиновку до включения. Габариты корпуса по Connfly: 10,16 x 2,54 x 14,00 мм; общий допуск ±0,25 мм.'},
    {'refs':['J3_J5_CONTACTS'], 'mpn':'Connfly T-DS1071-SC600',
     'article':201995, 'quantity':8, 'unit':'pc',
     'dan_url':'https://www.danomsk.ru/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/201995-kontakty-dlya-rozetok-bls-bld-t-ds1071-sc600-2-54mm-connfly/',
     'stock':6746, 'stock_checked':'2026-10-12',
     'source':'https://en.connfly.com/static/upload/file/pdf/DS1071.pdf',
     'wire_awg':[28,22], 'wire_area_mm2':[0.09,0.30], 'wire_insulation_od_mm':[1.2,1.6],
     'note':'Восемь гнездовых обжимных контактов: по четыре для J3 и J5. Медь AWG28..22, 0,09..0,30 мм²; диаметр изоляции 1,2..1,6 мм. Обжимать подходящей матрицей, затем проверить фиксацию и электрическую распиновку. Для пяти сборок: 10 корпусов и 40 контактов без запаса.'},
]


def write_contract():
    if (ROOT / 'design' / 'feature_ina219_vertical.json').exists():
        raise RuntimeError(
            'Legacy IDC generator: refusing to overwrite the current vertical '
            'mechanical_selection.json or DAN_NEW_PARTS.csv. Use the current '
            'docs/vertical_interconnect_selection.json and '
            'tools/cad/update_v2_vertical_interconnect.py for Ali parts. '
            '--models --only-model remains available for an unrelated narrow model update.'
        )
    cards = json.loads((ROOT / 'docs/dan_cards_checked.json').read_text(encoding='utf-8'))
    indexed = {str(c['url'].rstrip('/').split('/')[-1].split('-')[0]): c for c in cards}
    parts = []
    for name, d in DEFINITIONS.items():
        c = indexed.get(str(d['article']), {})
        stock = int(c['stock_fragment'].split(':')[1].strip()) if c else 127
        url = c.get('url', 'https://www.danomsk.ru/shop/7-kommutatsiya/120-pereklyuchateli/587-mikroknopki/199312-mikroknopka-1825027-2-fsmra1jh04-kan0631n-0431b010-42-uglovaya-bez-fiksatsii-7-11-7-01-3-68mm-off-on/')
        parts.append({**d, 'footprint': 'Meshcore:'+name, 'dan_url': url, 'stock': stock, 'stock_checked': '2026-10-11'})
    parts.extend([
        {'refs': ['W1_END_POWER', 'W1_END_LOGIC'], 'mpn': 'Connfly DS1016-12MA2BB', 'article': 195394,
         'dan_url': indexed['195394']['url'], 'stock': 230, 'stock_checked': '2026-10-11',
         'body_length': 19.9, 'body_width': 6.0, 'top_cover_dimension': 13.3,
         'assembled_axial_size':None,'mated_axial_extension':None,
         'dimension_note':'13.3 mm is the separate Top cover dimension in DS1016, not a dimensioned final mated assembly. Validate the final socket size and mating depth on an actual pair.',
         'source': 'https://en.connfly.com/static/upload/file/pdf/DS1016.pdf',
         'note': 'Female key/strain relief,12positions2.54mm. Cable conductor pitch1.27mm.'},
        {'refs': ['STAND_POWER_SCREEN_X4'], 'mpn': 'RUICHI PCHSN-18', 'article': 206757,
         'dan_url': 'https://www.danomsk.ru/shop/8-ustanovochnye/109-krepezh-aksessuary/291-stoyki-pribornye/206757-stoyka-pchsn-18-shestigrannaya-18-mm-m3-latun-ruichi/',
         'stock': 52, 'stock_checked': '2026-10-11', 'body_length': 18, 'thread': 'M3',
         'across_flats': 5.5, 'male_stud': 5.0, 'female_hole_depth': 6.0,
         'source': indexed['110251']['pdfs'][0],
         'note': 'Family drawing explicitly listsPCHSN-18. Acrossflats/stud/femalehole areapproximate; incoming inspectionrequired. Male5mm faces lower retainingnut; upperConnfly6mmstud entersRUICHI femalehole.'},
        {'refs': ['STAND_SCREEN_LOGIC_X4'], 'mpn': 'Connfly H-L1500-2100-5-03-1N1W / PCHSN-15', 'article': 188548,
         'dan_url': indexed['188548']['url'], 'stock': 168, 'stock_checked': '2026-10-11',
         'body_length': 15, 'thread': 'M3', 'across_flats': 5.5, 'male_stud': 6.0,
         'source': indexed['188548']['pdfs'][0],
         'note': '6.0±0.2mm male; usable female thread depth unspecified. Measure before tightening top6mm screw.'},
    ])
    accessory_base='https://www.danomsk.ru/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/'
    accessories=[
        {'refs':['W1_CABLE'],'mpn':'Connfly DS1057-16A282R-30.5','article':200351,'quantity':0.12,'unit':'m',
         'dan_url':'https://www.danomsk.ru/shop/425-kabeli-provoda-shnury/427-kabeli-provoda/789-shleyfy/200351-shleyf-16-zhil-1-27mm-ds1057-16a282r-30-5-connfly/',
         'stock':72,'stock_checked':'2026-10-11','source':'https://en.connfly.com/static/upload/file/pdf/DS1057.pdf',
         'note':'Buy required sale length; separate12conductors retaining red pin1 stripe. AWG28,7x0.127mm, conductor resistance<=0.237ohm/m20C, PVC thickness0.9±0.15mm, ratedambient-20..70C. A120mmlengthisslacktarget, confirmonassembly.'},
        {'refs':['J12_HARNESS'],'mpn':'KLS L-KLS1-2.50-04-H','article':205451,'quantity':1,'unit':'pc',
         'dan_url':accessory_base+'205451-chu-4-xh-04f-l-kls1-2-50-04-h-rozetka-kabelnaya-bez-kontaktov-kontakty-203549-203367-2-5mm-kls/',
         'stock':413,'stock_checked':'2026-10-11','source':'https://img.klsele.com/admin/product_upload/20250303165321L-KLS1-2.50.pdf#page=2','note':'Same KLS family as J12. Populate only pins1..3; leave pin4 empty.'},
        {'refs':['J12_CONTACTS'],'mpn':'KLS KLS1-2.50-T','article':203367,'quantity':3,'unit':'pc',
         'dan_url':accessory_base+'203367-kontakty-dlya-rozetok-chu-xh-cwf-kls1-2-50-t-kls/',
         'stock':5490,'stock_checked':'2026-10-11','source':'https://img.klsele.com/admin/product_upload/20250303165321L-KLS1-2.50.pdf#page=1','note':'Crimp with matched wire size and tool; verify retention.'},
        {'refs':['J7_J8_CONTACTS'],'mpn':'JST SXH-001T-P0.6','article':204874,'quantity':4,'unit':'pc',
         'dan_url':accessory_base+'204874-kontakty-dlya-rozetok-xhp-sxh-001t-p0-6-jst/',
         'stock':150,'stock_checked':'2026-10-11','source':indexed['167075']['pdfs'][0]+'#page=2','note':'Matching original JST terminal for XHP-2; AWG28..22.'},
        {'refs':['J11_SHUNT'],'mpn':'Connfly DS1027-2BBN1','article':128935,'quantity':1,'unit':'pc',
         'dan_url':accessory_base+'128935-dzhamper-mj-c-6-5-ds1027-2bbn1-connfly/',
         'stock':724,'stock_checked':'2026-10-11','source':'https://en.connfly.com/static/upload/file/pdf/DS1027.pdf','note':'Closed6.5mm shunt,2.54pitch. Remove forUSBservice; provide finger/pinceraccess.'},
        {'refs':['J7_J8_HOUSINGS'],'mpn':'JST XHP-2','quantity':2,'unit':'pc','supplier':'TMElectronics/LCSC',
         'supplier_url':'https://tmelectronics.ru/product/XHP-2/',
         'alternate_url':'https://lcsc.com/product-detail/Rectangular-Connectors-Housings_JST-Sales-America_XHP-2_JST-Sales-America-XHP-2_C144401.html',
         'stock':None,'stock_checked':'searchindex only; directcard403','source':indexed['167075']['pdfs'][0]+'#page=2',
         'note':'Original JST matching housing. Dan has Connfly2pole alternatives; crossbrandmateisnotmanufacturer-qualified. LCSClistedstock42050/MOQ50 insearchindex; recheck beforepurchase.'},
        {'refs':['WASHERS_ALL'],'mpn':'metal DIN433 M3 3.2x6x0.5mm','quantity':20,'unit':'pc','supplier':'Завод Купцова',
         'supplier_url':'https://www.kuptsov-zavod.ru/catalog/shayby-umenshennye/shayba-umenshennaya-otsinkovannaya-m3-din-433/',
         'stock':'In stock oncard','stock_checked':'2026-10-11','source':'https://www.kuptsov-zavod.ru/catalog/shayby-umenshennye/shayba-umenshennaya-otsinkovannaya-m3-din-433/',
         'note':'Metal DIN433 washers: OD 6 mm, ID 3.2 mm, thickness 0.5 mm. Keep the selected dimensions for the documented thread stack.'},
        {'refs':['NUTS_POWER_X4'],'mpn':'metal M3 DIN934 A2','quantity':4,'unit':'pc','supplier':'Darxton',
         'supplier_url':'https://darxton.ru/catalog_item/gayka-m3-a2-din-934/',
         'stock':'Available; sellerupdate2026-08-05','stock_checked':'2026-10-11','source':'https://darxton.ru/catalog_item/gayka-m3-a2-din-934/',
         'note':'Acrossflats5.5, nominalheight2.4. Retains lowerRUICHIstud.'},
        {'refs':['SCREWS_LOGIC_X4'],'mpn':'metal M3x6 DIN7985','quantity':4,'unit':'pc','supplier':'Все инструменты/Стройметиз',
         'supplier_url':'https://www.vseinstrumenti.ru/product/vint-strojmetiz-m3h6-din-7985-polukruglaya-golovka-tsink-up-40-sht-3100821-1527042/',
         'stock':'Ordering available insearchresult; pack40','stock_checked':'2026-10-11','source':'https://purelogic.ru/docs/mekhanika/vinty_din_7985_chernye_draw.pdf',
         'note':'Nominal6mm underhead. Headmodel uses conservative6mmOD/2.52mmhigh; exactorderedheadmayvary. Prove usablefemale depth beforetightening. Do not substitute25mm screw fromDan.'},
    ]
    accessories.extend(copy.deepcopy(J3_J5_MATES))
    contract = {
        'date': '2026-10-11', 'units': 'mm', 'project': 'Mesh Repeater ver2.0',
        'status': 'dimensioned library; actual hardware fit and electrical current qualification pending',
        'board': {'width': 90, 'height': 60, 'thickness_nominal': 1.5, 'native_thickness': 1.52, 'layers': 2},
        'shield': {'width': 90, 'height': 60, 'thickness': 1.52, 'copper_face': 'DOWN', 'continuous_foil': True, 'no_copper_letter_cuts': True,
                   'manufacturing_copper_layers':1,'native_cad_copper_layer_container':2,'unused_native_layer':'B.Cu',
                   'stackup_mm':{'F.Mask':0.010,'F.Cu':0.035,'FR4_core':1.475,'B.Cu':0.0,'B.Mask':0.0},
                   'expected_step_core_plus_foil_mm':1.510,
                   'cad_note':'KiCad uses a two-copper-layer container. B.Cu is empty and has zero stackup thickness. The manufactured shield has copper on one side only. The native nominal total is 1.52 mm; STEP omits the 0.01 mm front mask.'},
        'mounting': {'centres': [[3.5,3.5],[86.5,3.5],[3.5,56.5],[86.5,56.5]], 'drill': 3.2, 'gnd_contact_od': 6.0, 'mechanical_keepout_od': 6.5,
                     'frame': {'reference':'SH1','fitted':False,'status':'Removed by final frame/mount review; the continuous middle shield is retained.'},
                     'hex_note': 'M3 standoffs have 5.5 mm across flats and a 6.35 mm circumscribed circle. The lower SH1 frame is removed.'},
        'parts': parts,
        'accessories': accessories,
        'interboard': {'headers': ['J101','J201'], 'pin_map': {str(i): ('FILTER_OUT' if i in [1,3,5,7] else 'BAT' if i==9 else 'MODE' if i==11 else 'GND') for i in range(1,13)},
                      'connection': '1:1; test every pin before power.', 'forbidden_crossnet': 'SYS_3V3',
                      'cable': 'Connfly DS1057-16A282R-30.5: separate 12 conductors, retain the red stripe; provisional length 120 mm including slack.',
                      'assembly_current_limit': 'Dan specifies 1 A/contact. Board continuous current 0.5 A is an unmeasured design assumption. Qualify the cable, peak current and voltage drop; parallel contacts do not prove a multiplied assembly rating.',
                      'cable_temperature_limit_C':[-20,70],
                      'cable_resistance_max_ohm_per_m20C':0.237,
                      'ideal_wire_only_drop_at0_5A_120mm_V':0.005925,
                      'route': 'Around the north screen edge; planned external cable loop physical Y <= -23 mm, design bend radius >= 5 mm. These provisional dimensions require assembly validation.',
                      'header_power': {'first_pin': [64.15,11.0], 'rotation_kicad': 90},
                      'header_logic': {'first_pin': [76.85,49.0], 'rotation_kicad': 270},
                      'header_physical_body_xy': [59.08,-2.8,81.92,6.0],
                      'header_mount_clearance_note':'The headers were shifted left to preserve clearance to the north-east washers and arbitrarily rotated M3 hex standoffs. Physical center X is 70.5 mm.',
                      'orientation_warning': 'After LOGIC rotates about X, both keyed headers face north but pin 1 is at opposite physical X. A correctly oriented half-twist of the ribbon or a custom 1:1 wire harness is necessary. The key alone does not prove 1:1 wiring.'},
        'assembly': {'lower_components': 'F up', 'upper_components': 'F down via 180 degrees about X', 'visible_upper_silk': 'B', 'isp': 'Baseline native location; service after disassembly.'},
        'stack': {'pcb_thickness':1.52,'washer_thickness':0.5,'lower_stand_body':18.0,'upper_stand_body':15.0,
                  'washer_count_per_corner':5,'washer_od':6.0,'washer_id':3.2,
                  'sequence_bottom_to_top':['M3 DIN934 nut','Metal DIN433 washer 0.5 mm','POWER PCB 1.52 mm','RUICHI PCHSN-18 body directly on the POWER GND land','Metal DIN433 washer 0.5 mm','SHIELD PCB 1.52 mm, foil down','Metal DIN433 washer 0.5 mm','Connfly PCHSN-15 body','Metal DIN433 washer 0.5 mm','LOGIC PCB 1.52 mm, components down','Metal DIN433 washer 0.5 mm','M3x6 screw head'],
                  'power_pcb_bottom_z':0.0,'power_pcb_top_z':1.52,'lower_stand_bottom_z':1.52,'lower_stand_top_z':19.52,
                  'shield_bottom_z':20.02,'shield_top_z':21.54,'upper_stand_bottom_z':22.04,'upper_stand_top_z':37.04,
                  'logic_component_face_z':37.54,'logic_outside_face_z':39.06,
                  'lower_face_clearance':18.5,'upper_face_clearance':16.0,'outer_pcb_surface_height':39.06,
                  'nominal_nut_to_screw_head_height':44.98,
                  'nominal_upper_stud_engagement':3.48,'nominal_top_screw_engagement':3.48,'nominal_lower_nut_available_thread':2.98,
                  'qualification':'Nominal dimension chain only. Measure the usable female thread depth and actual PCB, washer and stud dimensions. Confirm at least 3.0 mm engagement in upper joints, no bottoming and full lower nut engagement. Both metal washer faces must contact GND only.'},
        'unresolved': ['Measure the NiceNano clone and actual Type-C plug.', 'Incoming inspection: usable female thread depth and approximate RUICHI stud dimensions.', 'Check all connector footprints against the actual ordered MPNs before fabrication.', 'Validate the cable, thread stack and connector access on an assembly.', 'Selected IDC cable is specified for -20 to +70 C. Lower ambient temperatures require another qualified cable.', 'Original JST XHP-2 direct stock is not verified; supplier alternatives have qualified availability notes.'],
    }
    assembly_report=ROOT/'docs/mechanics/assembly_geometry_report.json'
    if assembly_report.is_file():
        measured=json.loads(assembly_report.read_text(encoding='utf-8'))['artifacts']['MeshRepeater2_assembly']['bbox_mm']
        contract['assembly_cad_dimensions']={
            'uncabled_bbox_mm':measured,
            'uncabled_dimensions_mm':[round(measured[i+3]-measured[i],5) for i in range(3)],
            'source':'docs/mechanics/assembly_geometry_report.json',
            'note':'The complete CAD envelope includes projecting connector bodies and the lower M3 stud. The 44.98 mm nut-to-head chain is not the complete height. Cable outside the screen and actual connector mating remain provisional; with the native southern connector at physical Y=67.21 mm, a planned northern cable loop Y <= -23 mm makes the complete Y envelope at least about 90.21 mm before actual mating and slack allowances.'}
    (ROOT/'docs/mechanical_selection.json').write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding='utf-8')
    rows=[]
    readable_notes={
        167075:'Оригинальный JST. Угловая вилка, 2 контакта, шаг 2,50 мм. Для кабеля XHP-2 и SXH-001T-P0.6.',
        38160:'J12: заменить 3-контактный корпус на 4-контактный. Пины 1..3 прежние PACK+, MID, GND; пин 4 NC.',
        134861:'Два угловых IDC 2x6. Распиновка кабеля строго 1:1, проверить каждую жилу после полуоборота шлейфа.',
        195394:'Две ответные розетки, 12 контактов, с ключом и фиксацией шлейфа.',
        202688:'Один ряд 40 контактов разрезать на 2+4+4 для J11, J3, J5; остаётся 30 контактов. Серия U, контакт 6 мм.',
        199312:'Заказывать именно TE 1825027-2. Аналоги KAN из названия карточки проверяются отдельно по размерам.',
        206757:'Четыре нижние стойки 18 мм. Чертёж семейства M3 содержит строку PCHSN-18; длина шпильки ≈5 мм и глубина ≈6 мм требуют входного контроля.',
        188548:'Четыре верхние стойки 15 мм, медный сплав/никель. Шпилька 6 мм. Полезная глубина внутренней резьбы не указана.',
        200351:'Отделить 12 жил с сохранением красной полосы. Длина 120 мм предварительная; уточнить по сборке. AWG28, −20..+70°C.',
        205451:'Родной корпус KLS для J12; заполняются только позиции 1..3.',
        203367:'Три родных обжимных контакта KLS для J12. Подобрать провод и инструмент по чертежу KLS.',
        204874:'Четыре родных контакта JST для кабельных корпусов XHP-2, AWG28..22.',
        128935:'Съёмная перемычка 6,5 мм, шаг 2,54 мм. Снимается для USB; обеспечить доступ пальцами/пинцетом.',
    }
    accessory_notes={
        'J7_J8_HOUSINGS':'Оригинальные JST XHP-2. Живой остаток TMElectronics не проверен (403); у LCSC карточка C144401, минимальный заказ 50. Проверить перед закупкой.',
        'WASHERS_ALL':'20 металлических уменьшенных шайб DIN433, 3.2x6x0.5 мм. Для замены шайбами DIN125 OD7 из ДАН требуется новая проверка зазоров и резьбовой цепочки.',
        'NUTS_POWER_X4':'Четыре металлические гайки M3 DIN934. Удерживают нижние шпильки; номинальная высота 2,4 мм.',
        'SCREWS_LOGIC_X4':'Четыре металлических винта M3x6; магазин продаёт упаковку 40 шт. Перед затяжкой проверить глубину резьбы; M3x25 не подходит.',
    }
    for p in parts+accessories:
        refs=','.join(p['refs'])
        qty=p.get('quantity',4 if refs.startswith('STAND') else len(p['refs']))
        mpn=p['mpn'];footprint_name=p.get('footprint','')
        if p.get('article')==202688:
            if p['refs']==['J3','J5']:continue
            refs='J11,J3,J5';qty=1
            mpn='Connfly DS1022-1x40RUF11-B, cut 2+4+4 pins'
            footprint_name='Meshcore:Connfly_DS1022_1x02RUF11_B_Horizontal; Meshcore:Connfly_DS1022_1x04RUF11_B_Horizontal'
            note='One40positionstrip cut2+4+4;30positionsremain. '+p.get('note','')
        else:note=p.get('note','')
        note=readable_notes.get(p.get('article'),accessory_notes.get(refs,note))
        applies='LTO 2S only'if refs.startswith('J12')else'Na-ion 1S and LTO 2S; cold option unchanged'
        rows.append({'Refs':refs,'MPN':mpn,'Quantity_per_assembly':qty,'Unit':p.get('unit','pc'),'Applicability':applies,
                     'Supplier':'ДАН'if'dan_url'in p else p.get('supplier',''),
                     'Article':p.get('article',''),'Purchase_URL':p.get('dan_url',p.get('supplier_url','')),
                     'Stock_observed':p.get('stock',''),'Checked':p.get('stock_checked',''),
                     'Drawing_URL':p.get('source',''),'Footprint':footprint_name,'Notes':note})
    bom=ROOT/'bom';bom.mkdir(exist_ok=True)
    with (bom/'DAN_NEW_PARTS.csv').open('w',encoding='utf-8-sig',newline='')as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return contract


def rectangle(x0, y0, x1, y1, layer, width):
    return f'(fp_rect (start {x0:g} {y0:g}) (end {x1:g} {y1:g}) (stroke (width {width}) (type solid)) (fill no) (layer "{layer}"))'


def footprint(name, d):
    x0,y0,x1,y1=d['bbox']
    cb=d.get('courtyard_bbox',[min(x0,-1.15)-.25,min(y0,-1.15)-.25,max(x1,2.54+1.15)+.25,max(y1,1.15)+.25])
    if 'DS1022' in name: cb=[-1.5,-1.52,7.5,y1+.25]
    pads=[]
    for num,x,y,drill,kind in d['pads']:
        style='np_thru_hole'if kind=='NPTH'else'thru_hole'
        shape='rect'if num=='1'else'circle'
        size=drill if kind=='NPTH' else 1.8
        pads.append(f'(pad "{num}" {style} {shape} (at {x} {y}) (size {size} {size}) (drill {drill}) (layers "*.Cu" "*.Mask") (remove_unused_layers no))')
    text=f'''(footprint "{name}" (version 20260206) (generator "mesh_repeater_dimensioned_library") (layer "F.Cu")
(descr "{d['mpn']}. Drawing: {d['source']}. Simplified envelope STEP model.")
(property "Reference" "REF**" (at {(x0+x1)/2:g} {y0-1.0:g}) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.12))))
(property "Value" "{d['mpn']}" (at {(x0+x1)/2:g} {y1+1:g}) (layer "F.Fab") (effects (font (size 0.8 0.8) (thickness 0.12))))
(attr through_hole)
{rectangle(x0,y0,x1,y1,'F.Fab',.1)}
{rectangle(x0-.1,y0-.1,x1+.1,y1+.1,'F.SilkS',.12)}
{rectangle(*cb,'F.CrtYd',.05)}
{' '.join(pads)}
(model "${{KIPRJMOD}}/3dmodels/{name}.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
(embedded_fonts no))'''
    return text


def write_footprints():
    for target in DESIGNS:
        library=target/'Meshcore.pretty'
        if not library.is_dir(): raise SystemExit(f'Missing v2library: {library}')
        for name,d in DEFINITIONS.items():
            (library/(name+'.kicad_mod')).write_text(footprint(name,d),encoding='utf-8')
    print(f'Wrote {len(DEFINITIONS)} dimensioned footprints into each v2 library')


def write_models(only=None):
    import FreeCAD as App
    import Part
    outdir=DESIGNS[0]/'3dmodels'
    selected = DEFINITIONS if only is None else {only: DEFINITIONS[only]}
    for name,d in selected.items():
        doc=App.newDocument('Model')
        x0,y0,x1,y1=d['bbox']
        # KiCad XY is reflected alongY intheSTEP localcoordinate convention.
        def feature(label,shape,color):
            obj=doc.addObject('Part::Feature',label);obj.Shape=shape
            try:obj.ViewObject.ShapeColor=color
            except Exception:pass
            return obj
        body=Part.makeBox(x1-x0,y1-y0,d['height'],App.Vector(x0,-y1,0))
        if 'DS1013' in name:
            cavity=Part.makeBox(8.0,y1-y0-2.2,d['height']-2.0,App.Vector(x0+1.0,-y1+1.1,1.0))
            body=body.cut(cavity)
        elif 'XH_' in name:
            cavity=Part.makeBox(x1-x0-1.8,7.5,d['height']-1.6,App.Vector(x0+.9,-y0-7.5,.8))
            body=body.cut(cavity)
        feature('Body',body,(.90,.90,.85)if'XH_'in name else(.10,.10,.12))
        for num,x,y,drill,kind in d['pads']:
            pin=Part.makeBox(.64,.64,d['tail']+2.0,App.Vector(x-.32,-y-.32,-d['tail']))
            feature('Lead'+(num or'Mount'),pin,(.74,.67,.42))
        if 'DS1022' in name:
            for num,x,y,drill,kind in d['pads']:
                feature('MatingPin'+num,Part.makeBox(7.57,.64,.64,App.Vector(-.32,-y-.32,d['overall_height']-.64)),(.74,.67,.42))
                feature('Riser'+num,Part.makeBox(.64,.64,d['overall_height']-.32,App.Vector(-.32,-y-.32,0)),(.74,.67,.42))
        if name.startswith('SW_'):
            feature('Actuator',Part.makeCylinder(1.755,d['actuator_projection'],App.Vector(0,-y0,4.01),App.Vector(0,1,0)),(.95,.95,.85))
            # TE specifies an 8.41 mm overall bracket, wider than the 7.01 mm
            # centre pitch of its mounting legs. Preserve the full outer envelope.
            bracket_section_width=d['bracket_width']-7.01
            for sx in(-1,1):
                feature('Bracket'+str(sx),Part.makeBox(bracket_section_width,3.0,3.0,
                    App.Vector(sx*3.505-bracket_section_width/2,-4.01,0)),(.75,.75,.78))
        doc.recompute()
        dest=outdir/(name+'.step');Part.export(doc.Objects,str(dest));App.closeDocument(doc.Name)
        for target in DESIGNS[1:]:
            (target/'3dmodels'/dest.name).write_bytes(dest.read_bytes())
    print(f'Wrote {len(selected)} simplified envelope STEP models into each v2 project')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--footprints',action='store_true');ap.add_argument('--models',action='store_true')
    ap.add_argument('--only-model',choices=tuple(DEFINITIONS));args=ap.parse_args()
    if args.only_model and (not args.models or args.footprints):
        ap.error('--only-model requires --models and cannot change footprints')
    if not args.only_model:write_contract()
    if args.footprints:write_footprints()
    if args.models:write_models(args.only_model)


if __name__=='__main__':main()
