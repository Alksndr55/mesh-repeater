import json, hashlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root=Path(__file__).resolve().parents[2]
out=Path(__file__).resolve().parent
data={
 'checked_date':'2026-10-12', 'timezone':'Asia/Omsk',
 'status':'PURCHASABLE_DOCUMENTED_PAIR_PROPOSED; INPUT_DIMENSIONAL_INSPECTION_REQUIRED; CAD_UNCHANGED',
 'male': {'mpn':'TSW-106-21-L-D','vendor':'ChipDip', 'url':'https://www.chipdip.ru/product/tsw-106-21-l-d-samtec-8068996880','rub_each':390,'stock_displayed':70,'stock_kind':'supplier stock; not local Moscow stock','lead_time_displayed':'4 weeks','minimum_order':25,'buy_button_visible':True},
 'female': {'mpn':'BCS-106-L-D-TE','vendor':'ChipDip','url':'https://www.chipdip.ru/product/bcs-106-l-d-te-samtec-8048163390','rub_each':150,'stock_displayed':7,'stock_kind':'Moscow warehouse','lead_time_displayed':'2 weeks','minimum_order':1,'buy_button_visible':True},
 'cost': {'consumed_pair_rub':540,'assemblies_needed':5,'male_order_qty':25,'female_order_qty':5,'order_total_excluding_shipping_rub':10500,'unused_males':20},
 'mechanics': json.loads((out/'dan_local_samtec_mating.json').read_text(encoding='utf-8-sig')),
 'independent_review': {'result':'Nominal mating, current requirement, quoted stock and cost checked against primary sources', 'preferred_assembly_acceptance_insertion_mm':[4.50,7.00], 'reason':'The computed worst-case under separate ±0.10 inspection gates has only 0.0274 mm margin above the absolute minimum. Use direct insertion-depth acceptance with margin for all pins. This is an assembly inspection requirement, not a claim that all vendor tolerance combinations fit automatically.'},
 'shield': {'crossed_by_pins':True,'male_body_above_POWER_mm':2.54,'shield_near_face_above_POWER_mm':18.50,'shield_far_face_above_POWER_mm':20.02,'female_bottom_above_POWER_mm':28.654,'female_to_SHIELD_clearance_mm':8.634,'holes_are_proposed_not_implemented':True,'condition':'Isolated NPTH apertures and foil clearance; hole size must include pin straightness and board registration. No fixed final drill size certified in this proposal.'},
 'source_documents': {'male':'https://suddendocs.samtec.com/prints/tsw-xxx-xx-xxx-x-xx-xxx-mkt.pdf','female':'https://suddendocs.samtec.com/prints/bcs-1xx-xxx-x-xx-xxx-mkt.pdf','mating_window':'https://suddendocs.samtec.com/catalog_english/bcs.pdf'},
 'cheaper_candidate': {'male':json.loads((out/'ali_local_candidate.json').read_text(encoding='utf-8-sig')),'female':'SSW-106-01-G-D','female_url':'https://www.chipdip.ru/product/ssw-106-01-g-d-2.54mm-double-row-4.7a-gold-12p-samtec-8044793842','female_price_rub':570,'female_stock_displayed':17,'female_lead_time':'5-6 weeks','nominal_insertion_mm':4.489,'cost_for5_excluding_shipping_rub':4299,'not_selected_reason':'Exact Ali SKU pin width and tolerance absent; cross-section compatibility not documented. Do not claim a fully confirmed pair.'},
 'native_sha256': {}
}
expected={'Power':'c4efced02420f48fea993d166091e3ba3ec7be7cf9bc30feec164d067077cc3b','Logic':'6cbd7850caa14163ebe4d40aba4435ac8fe17f327d68419dfb94e0a1bc361bc8','Shield':'4ba1d2a7b47dd392b2ac79fa9a7e10fbf8e98be6b8a3423c813d8530ddb25147'}
for board,wanted in expected.items():
 p=root/'design'/f'MeshRepeater2_{board}'/f'MeshRepeater2_{board}.kicad_pcb'
 got=hashlib.sha256(p.read_bytes()).hexdigest()
 data['native_sha256'][board]={'sha256':got,'unchanged_from_previous_turn':got==wanted}
 assert got==wanted, f'Native {board} changed; do not claim unchanged'
(out/'local_selection.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

# Read-only offer screenshots; title, price, stock and minimum order remain visible.
shots=[]
for name in ('chip_tsw10621_offer.jpg','chip_bcs106_offer.jpg'):
 im=Image.open(out/'sources'/name).convert('RGB')
 crop=im.crop((0,260,im.width,im.height))
 crop.thumbnail((950,600))
 shots.append(crop)
canvas=Image.new('RGB',(950,sum(i.height for i in shots)+70),'white')
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
draw.text((18,12),'ChipDip — предложения проверены 12.10.2026',font=font,fill='#123')
y=50
for im in shots:
 canvas.paste(im,(0,y)); y+=im.height+10
canvas.save(out/'sources'/'selected_pair_offers.jpg',quality=92)

html='''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Разъёмы Mesh Repeater 2.0 — подбор</title>
<style>body{font:17px/1.55 Arial,sans-serif;max-width:1050px;margin:32px auto;padding:0 24px;color:#182334}h1{font-size:28px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd5df;padding:10px;text-align:left}img{max-width:100%}.note{padding:14px;background:#fff3db}a{color:#125ca0}</style>
<h1>Межплатные разъёмы Mesh Repeater 2.0</h1><p>Проверено 12 октября 2026. Подбор для согласования. Схема, платы, стойки и BOM не изменены.</p>
<table><tr><th>Деталь</th><th>Цена</th><th>Наличие и срок на карточке</th><th>Минимум</th></tr>
<tr><td><a href="https://www.chipdip.ru/product/tsw-106-21-l-d-samtec-8068996880">Samtec TSW-106-21-L-D</a> — длинная вилка 2×6</td><td>390 ₽/шт.</td><td>70 шт. у поставщика, 4 недели</td><td>25 шт.</td></tr>
<tr><td><a href="https://www.chipdip.ru/product/bcs-106-l-d-te-samtec-8048163390">Samtec BCS-106-L-D-TE</a> — розетка 2×6</td><td>150 ₽/шт.</td><td>7 шт. со склада Москвы, 2 недели</td><td>1 шт.</td></tr></table>
<p>Стоимость использованных деталей: <b>540 ₽ на сборку</b>. Для пяти устройств требуется заказать 25 вилок и 5 розеток: <b>10 500 ₽ без доставки</b>, 20 вилок останется.</p>
<p>Обе детали — выводные, шаг 2,54 мм, квадратный штырь 0,635 мм. Samtec документирует сопряжение BCS с TSW. Ток соединения достаточен для проектного требования 0,5 А на контакт; паспортные токи не складываются между параллельными контактами.</p>
<table><tr><th>Геометрия</th><th>Размер</th></tr><tr><td>Расстояние между рабочими поверхностями POWER и LOGIC</td><td>36,020 мм</td></tr><tr><td>Высота кончика вилки от POWER</td><td>2,540 + 30,988 = 33,528 мм</td></tr><tr><td>Высота розетки</td><td>7,366 мм</td></tr><tr><td>Номинальная глубина ввода</td><td><b>4,874 мм</b></td></tr><tr><td>Паспортный диапазон BCS</td><td>4,3434–7,239 мм</td></tr><tr><td>Зазор корпуса розетки до верхней поверхности экрана</td><td>8,634 мм</td></tr></table>
<p>Штыри пересекают экран; оба пластиковых корпуса находятся вне его плоскости. После согласования потребуются изолированные проходные отверстия и удаление меди вокруг них. Сигнальные штыри не соединяются с экраном.</p>
<p class="note"><b>Ограничение размерной проверки:</b> высоты пластиковых корпусов указаны изготовителем как REF. Их измерение обязательно. При приёмке корпуса вилки 2,540±0,100 мм, корпуса розетки 7,366±0,100 мм и собранного зазора 36,020±0,100 мм, с паспортным допуском поста ±0,2032 мм, ввод получается 4,3708–5,3772 мм — внутри допустимого окна, но запас до нижнего предела всего 0,0274 мм. Поэтому независимый обзор рекомендует непосредственно проверять ввод каждого штыря в диапазоне <b>4,50–7,00 мм</b>. Это наши требования к приёмке, а не обещанные допуски стоек. Наклон длинных контактов и совмещение отверстий экрана проверяются отдельно; окончательная сверловка пока не утверждена.</p>
<p>Документы изготовителя: <a href="https://suddendocs.samtec.com/prints/tsw-xxx-xx-xxx-x-xx-xxx-mkt.pdf">TSW</a>, <a href="https://suddendocs.samtec.com/prints/bcs-1xx-xxx-x-xx-xxx-mkt.pdf">BCS</a>, <a href="https://suddendocs.samtec.com/catalog_english/bcs.pdf">сопряжение и глубина ввода BCS</a>.</p>
<p>Более дешёвый запасной вариант: <a href="https://aliexpress.ru/item/1005011978353933.html?sku_id=12000057202232448">AliExpress E-SIMPO L35mm A3C6, 2×6P</a> (1449 ₽ за 50 шт., остаток 99+, доставка почтой 363 ₽) + <a href="https://www.chipdip.ru/product/ssw-106-01-g-d-2.54mm-double-row-4.7a-gold-12p-samtec-8044793842">SSW-106-01-G-D</a> (570 ₽, 17 шт., 5–6 недель). Закупка для пяти устройств 4299 ₽ без доставки. Номинально высота подходит (ввод 4,489 мм), <b>но сечение контакта точного SKU Ali не документировано</b>, поэтому эта пара не признана полностью подтверждённой.</p>
<p>DAN имеет обычные короткие вилки и розетки; подтверждённая длинная вилка на текущую высоту сборки не найдена. На Ozon просмотренные предложения оказались короткими.</p>
<img src="../audit/vertical_interconnect_2026_10_12/sources/selected_pair_offers.jpg" alt="Цена, остаток и минимальная партия выбранных разъёмов">
</html>'''
(root/'output'/'V2_LOCAL_CONNECTOR_SELECTION_RU.html').write_text(html,encoding='utf-8')
print(json.dumps({'order_total':10500,'native_unchanged':True,'report':str(root/'output'/'V2_LOCAL_CONNECTOR_SELECTION_RU.html')},ensure_ascii=False))
