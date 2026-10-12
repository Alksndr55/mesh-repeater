"""Apply only M-01, M-02 mechanical metadata and DOC-01 to existing V2 docs."""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
generator=ROOT/'tools/cad/build_v2_mechanical_library.py'
spec=importlib.util.spec_from_file_location('v2_mechanical_library',generator)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
contract_path=ROOT/'docs/mechanical_selection.json'
contract=json.loads(contract_path.read_text(encoding='utf-8'))
for part in contract['parts']:
    if part.get('footprint')=='Meshcore:SW_TE_1825027_2_Side':
        part['bracket_width']=8.41
        part['model_width_before_fix_mm']=7.66
        part['model_width_after_fix_mm']=8.41
        part['model_fix']='M-02: full nominal TE bracket outer envelope; pads and courtyard unchanged.'
        part['model_fix_checked']='2026-10-12'
assert not any(a['refs'][0].startswith('J3_J5_') for a in contract['accessories'])
contract['accessories'].extend(module.copy.deepcopy(module.J3_J5_MATES))
contract['mechanical_fixes']={
    'date':'2026-10-12','findings':['M-01','M-02','DOC-01'],
    'report':'audit/fixes_2026_10_12/mechanics.json',
    'mate_envelope':'docs/mechanics/Connfly_DS1071_SCB01x4_Mated_Envelope.step',
    'mate_qualification':'Manufacturer family compatibility and dimensioned conservative envelope. The fully assembled mating depth and cable retention require hardware qualification.',
    'mate_model_local_bbox_step_mm':[1.50,-9.015,4.355,15.75,1.395,7.145],
    'mate_placements_native':{
        'J3':{'origin_mm':[86,12],'rotation_kicad_degrees':0,'pins':{'1':'SYS_3V3','2':'GND','3':'SCL','4':'SDA'}},
        'J5':{'origin_mm':[2.5,18.12],'rotation_kicad_degrees':180,'pins':{'1':'GND','2':'SYS_3V3','3':'UART_TX','4':'UART_RX'}},
    },
    'mate_removal_space_target_mm':7,
    'mate_insertion_depth_note':'Envelope assumes housing front x=1.50 mm, 0.25 mm after nominal male insulator edge. Actual seating stop and mating depth are not specified in the drawing; do not infer an exact tolerance fit from this model.',
}
contract_path.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

path=ROOT/'bom/DAN_NEW_PARTS.csv'
with path.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
assert not any(r['Refs'].startswith('J3_J5_') for r in rows)
for a in module.J3_J5_MATES:
    rows.append({'Refs':','.join(a['refs']),'MPN':a['mpn'],
       'Quantity_per_assembly':a['quantity'],'Unit':a['unit'],
       'Applicability':'Na-ion 1S and LTO 2S; cold option unchanged','Supplier':'ДАН',
       'Article':a['article'],'Purchase_URL':a['dan_url'],'Stock_observed':a['stock'],
       'Checked':a['stock_checked'],'Drawing_URL':a['source'],'Footprint':'','Notes':a['note']})
with path.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

path=ROOT/'bom/V2_COMPONENT_BOM.csv'
with path.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
model_values={p['ref']:p['value'] for board in ['Power','Logic']
    for p in json.loads((ROOT/f'design/MeshRepeater2_{board}/model.json').read_text(encoding='utf-8'))['parts']
    if p['kind']=='MountingHole'}
for row in rows:
    if row['Reference'] in model_values:
        for field in ('Value_NaIon_COLD','Value_NaIon_NoCOLD','Value_LTO_2S'):
            row[field]=model_values[row['Reference']]
    if row['Reference'] in ('J3','J5'):
        row['Note']+=' Cable mate: Connfly I-DS1071-SCB01x4; 4x Connfly T-DS1071-SC600 per connector; quantities and purchase links in bom/DAN_NEW_PARTS.csv.'
with path.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

path=ROOT/'docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md'
text=path.read_text(encoding='utf-8')
marker='## Проверка перед механической сборкой'
assert text.count(marker)==1 and '## Кабельные части J3' not in text
section='''## Кабельные части J3 / I²C и J5 / UART

Для полного комплекта внешних кабелей закупите в ДАН **два корпуса Connfly I-DS1071-SCB01x4** (артикул 208362) и **восемь гнездовых контактов T-DS1071-SC600** (артикул 201995). На каждый разъём нужен один корпус и четыре контакта. Комплект применяется ко всем трём вариантам аккумулятора. Для пяти полных сборок нужны 10 корпусов и 40 контактов без технологического запаса. Кабельные детали перечислены отдельно в `bom/DAN_NEW_PARTS.csv`.

Официальный чертёж [Connfly DS1071](https://en.connfly.com/static/upload/file/pdf/DS1071.pdf) указывает DS1021/DS1022 как ответные вилки: это одна совместимая серия со штырём 0,64 мм и шагом 2,54 мм. Корпус 1×4 имеет номинальные размеры **10,16×2,54×14,00 мм**, с общим допуском ±0,25 мм. Провода для T-DS1071-SC600: медь AWG28–22 / 0,09–0,30 мм², диаметр изоляции 1,2–1,6 мм. Матрицу обжима подбирают для этих контактов; проверяют удержание каждого контакта в корпусе.

| Контакт платы и кабельного корпуса | J3 / I²C | J5 / UART |
|---|---|---|
| 1 | SYS_3V3 | GND |
| 2 | GND | SYS_3V3 |
| 3 | SCL | UART_TX, выход MCU |
| 4 | SDA | UART_RX, вход MCU |

Розетки без ключа: пометьте первый контакт обоих корпусов и проверьте нумерацию мультиметром относительно контактов платы до первого включения. J3 и J5 имеют различный порядок питания; одинаковый корпус не делает кабели взаимозаменяемыми. UART_TX платы подключают к RX внешнего устройства, UART_RX платы — к его TX.

Разъёмы входят горизонтально с внешних боковых краёв собранного LOGIC. Размерная модель `docs/mechanics/Connfly_DS1071_SCB01x4_Mated_Envelope.step` учитывает максимальный наружный габарит корпуса **10,41×2,79×14,25 мм** по допускам. Для прямого снятия предусмотрите по внешней стороне минимум **7 мм** свободного хода сверх установленного корпуса. Модель является оценкой наружного контура: точный упор, глубина посадки, инструмент обжима и удержание реального кабеля проверяются на образце.

'''
path.write_text(text.replace(marker,section+marker),encoding='utf-8')
print('Updated mechanical selection, cable accessory BOM, mounting values and assembly instructions.')
