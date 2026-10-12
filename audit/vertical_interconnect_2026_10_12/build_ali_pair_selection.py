import json, hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
p=Path(__file__).resolve().parent
root=p.parents[1]
male=json.loads((p/'ali_local_candidate.json').read_text(encoding='utf-8-sig'))
geometry=json.loads((p/'ali_pair_geometry.json').read_text(encoding='utf-8-sig'))
record={
 'date':'2026-10-12', 'project':'Mesh Repeater 2.0',
 'status':'ALI_MALE_ACCEPTED_BY_USER; ALI_FEMALE_SELECTED_AND_DIMENSIONED; CAD_BOM_NOT_UPDATED',
 'user_direction':'AliExpress option accepted; select female there and define final pin height.',
 'male':{'brand':'E-SIMPO','product_id':'1005011978353933','sku_id':'12000057202232448','options':['L35mm A3C6','2x6P'],'url':male['url'],'lot_quantity':50,'lot_price_rub':1449,'stock_displayed':'99+','tail_PC_mm':3,'free_tip_PA_mm':6,'PB_mm':26,'overall_metal_length_mm':35,'tip_above_POWER_mm':32,'upper_plastic_above_POWER_mm':[23.5,26.0],'postal_shipping_shown_rub':363},
 'female':{'listed_brand':'MTJ','drawing_mark':'JinSheng','product_id':'1005008954873458','sku_id':'12000047353417475','option':'2X6P 10PCS','url':'https://aliexpress.ru/item/1005008954873458.html?sku_id=12000047353417475','price_rub_for_selected_option':106,'pack_quantity_in_option_and_title':10,'platform_generic_unit_label':'Цена за 1 штуку / Количество 1; refers to one selected sale unit, do not infer a one-connector price from it. Confirm packing against 2X6P 10PCS when ordering.','stock_displayed':'99+','cart_button_visible':True,'body_height_mm':8.5,'body_height_tolerance':'Not given','body_length_mm':15.64,'body_length_tolerance_mm':0.30,'body_width_mm':5.00,'tail_length_mm':3.15,'tail_tolerance_mm':0.25,'tail_section_mm':[0.60,0.40],'tail_section_not_male_acceptance':True,'nominal_current_rating_A':3,'contact_resistance_max_mOhm':20,'delivery_price_shown_rub':192,'delivery_shown':'24–27 October pickup; 31 October–5 November post','minimum_mating_depth':'Not specified in drawing','accepted_male_pin_section':'Not specified in drawing'},
 'decision':{'male_total_length_mm':35,'female_height_mm':8.5,'pin_grid_mm':2.54,'configuration':'2x6','POWER_LOGIC_working_face_gap_mm':36.02,'nominal_insertion_mm':4.48,'upper_plastic_to_socket_mm':1.52,'screen_to_upper_plastic_mm':3.48,'standoffs_changed':False,'washer_chain_changed':False,'nominal_outer_PCB_height_mm':39.06,'complete_existing_assembly_envelope_height_mm':45.56,'equation':'L = working gap + PCB solder tail - female body height + target insertion = 36.02 + 3 - 8.5 + 4.5 = 35.02 mm; choose sale variant 35 mm, actual nominal insertion 4.48 mm.'},
 'limits':'Nominal geometry only. Male contact section and mating-depth window of this exact generic pair remain undocumented. Fit/contact qualification uses actual samples; no Samtec mating-depth window is attributed to this pair. Measure the assembled working gap and pin straightness before production. Shield apertures are still to be designed; this selection does not claim final drill qualification.',
 'purchase_for_five':{'male_lots':1,'female_packs':1,'goods_rub':1555,'shipping_shown_sum_rub':555,'total_with_two_shown_delivery_charges_rub':2110,'unused_males':45,'unused_females':5,'consumed_pair_cost_rub':39.58,'shipping_not_checkout_quote':True},
 'independent_geometry_report':'audit/vertical_interconnect_2026_10_12/ali_pair_geometry.json',
 'native_unchanged':{}
}
expected={'Power':'c4efced02420f48fea993d166091e3ba3ec7be7cf9bc30feec164d067077cc3b','Logic':'6cbd7850caa14163ebe4d40aba4435ac8fe17f327d68419dfb94e0a1bc361bc8','Shield':'4ba1d2a7b47dd392b2ac79fa9a7e10fbf8e98be6b8a3423c813d8530ddb25147'}
for name,want in expected.items():
 f=root/'design'/f'MeshRepeater2_{name}'/f'MeshRepeater2_{name}.kicad_pcb'
 got=hashlib.sha256(f.read_bytes()).hexdigest();assert got==want,(name,got)
 record['native_unchanged'][name]=got
(p/'ali_pair_selection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
(root/'docs'/'vertical_interconnect_selection.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
top=Image.open(p/'sources'/'ali_socket_offer_header.jpg').convert('RGB').crop((0,140,700,635))
price=Image.open(p/'sources'/'ali_socket_offer_price.jpg').convert('RGB').crop((0,80,700,385))
sheet=Image.new('RGB',(700,top.height+price.height+48),'white');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
draw.text((12,12),'AliExpress — 2X6P 10PCS, H8.5 — 12.10.2026',font=font,fill='#123')
sheet.paste(top,(0,48));sheet.paste(price,(0,48+top.height))
sheet.save(p/'sources'/'ali_socket_selected_proof.jpg',quality=92)
html='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Mesh Repeater 2.0 — пара AliExpress</title><style>body{font:17px/1.5 Arial,sans-serif;color:#182334;max-width:1050px;margin:30px auto;padding:0 24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5df;padding:10px;text-align:left}img{max-width:100%}a{color:#125ca0}.note{background:#fff1d6;padding:14px}</style>
<h1>Пара AliExpress: штыри 35 мм + розетка 8,5 мм</h1><p>Подбор проверен 12 октября 2026. Вариант вилки принят пользователем. Новая розетка и размерная проверка представлены для финальной проверки; посадочные места, трассировка и BOM пока не изменены.</p>
<table><tr><th>Деталь и выбранный вариант</th><th>Цена</th><th>Наличие</th></tr>
<tr><td><a href="https://aliexpress.ru/item/1005011978353933.html?sku_id=12000057202232448">E-SIMPO — L35mm A3C6, 2x6P</a></td><td>1449 ₽ за лот 50 шт.</td><td>99+, покупка доступна</td></tr>
<tr><td><a href="https://aliexpress.ru/item/1005008954873458.html?sku_id=12000047353417475">MTJ — 2X6P 10PCS, корпус H8.5</a></td><td>106 ₽ за выбранный набор 10 шт.</td><td>99+, покупка доступна</td></tr></table>
<p>Для пяти устройств: один лот вилок и один набор розеток — <b>1555 ₽ за товары</b>. Показанная доставка двумя заказами: 363+192=555 ₽; ориентир с доставкой <b>2110 ₽</b>. Цена окончательного оформления заказа не проверялась. Вариант розетки и заголовок прямо задают 10PCS/10 шт.; общая подпись платформы «Цена за 1 штуку» относится к выбранной продажной единице.</p>
<h2>Итоговые размеры</h2><table><tr><th>Величина</th><th>Размер, мм</th></tr><tr><td>Полная длина металлического штыря</td><td><b>35</b></td></tr><tr><td>Хвост под POWER</td><td>3</td></tr><tr><td>Кончики над POWER</td><td>32</td></tr><tr><td>Свободный конец над верхней пластиковой планкой</td><td>6</td></tr><tr><td>Высота розетки</td><td><b>8,5</b></td></tr><tr><td>Расстояние POWER F → LOGIC F</td><td>36,02</td></tr><tr><td>Номинальный ввод</td><td><b>32+8,5−36,02=4,48</b></td></tr><tr><td>Верхняя пластмассовая планка → вход розетки</td><td>1,52</td></tr><tr><td>Экран → верхняя пластмассовая планка</td><td>3,48</td></tr></table>
<p>Экран находится на высоте 18,50–20,02 мм от POWER, верхняя пластиковая планка — 23,50–26,00 мм. Через экран проходят только штыри. Корпус розетки начинается на высоте 27,52 мм от POWER. Стойки 18/15 мм и шайбы сохраняются. Наружные поверхности крайних плат: 39,06 мм; полная текущая огибающая с крепежом: 45,56 мм.</p>
<p>Расчёт длины: L=36,02+3−8,5+4,50=35,02 мм. Выбираем продаваемый <b>L35mm A3C6</b>, без подрезки штырей и без изменения высоты стоек.</p>
<table><tr><th>Вилка</th><th>Положение верхней пластиковой планки</th><th>Результат</th></tr><tr><td>L30</td><td>18,50–21,00 мм</td><td>Пересекает экран, не достигает розетки</td></tr><tr><td><b>L35</b></td><td>23,50–26,00 мм</td><td><b>Номинальная геометрия подходит</b></td></tr><tr><td>L40</td><td>28,50–31,00 мм</td><td>Планка сталкивается с розеткой</td></tr></table>
<h2>Розетка по собственному чертежу продавца</h2><p>Корпус 15,64±0,30 × 5,00 × 8,50 мм; межцентровое расстояние крайних контактов в ряду 12,70±0,20 мм; шаг 2,54 мм. Хвосты 3,15±0,25 мм, сечение паяемого хвоста 0,60×0,40 мм. Ток 3 А, сопротивление контакта максимум 20 мОм, рабочая температура −40…+105 °C.</p>
<p class="note">Подтверждена номинальная геометрия пары. Точный диапазон допустимого ввода и сечение ответного штыря продавцы не задают; у высоты корпуса розетки 8,50 мм отсутствует собственный допуск. Размер 0,60×0,40 относится к паяемому хвосту розетки. Перед выпуском платы нужны проверка сопряжения образцов, фактического межплатного расстояния и прямолинейности штырей. Данные Samtec не приписываются этой паре. Проходные отверстия экрана пока не внесены в CAD.</p>
<img src="../audit/vertical_interconnect_2026_10_12/sources/ali_socket_selected_proof.jpg" alt="Выбранная розетка 2X6P 10PCS и цена 106 рублей"><p><a href="../audit/vertical_interconnect_2026_10_12/sources/ali_socket_2x6_drawing.png">Полный чертёж продавца розетки</a></p></html>'''
(root/'output'/'V2_ALI_INTERCONNECT_RU.html').write_text(html,encoding='utf-8')
print(json.dumps({'selected_metal_length_mm':35,'female_body_height_mm':8.5,'nominal_insertion_mm':4.48,'goods_cost_rub':1555,'native_boards_unchanged':True},ensure_ascii=False))
