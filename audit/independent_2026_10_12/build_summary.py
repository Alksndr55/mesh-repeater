"""Render the independent audit only. Never writes project/CAD files."""
from pathlib import Path
import hashlib, html, json, os, subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
def load(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def esc(value):
    return html.escape(str(value))
def link(path, label):
    return '<a href="'+esc(path)+'">'+esc(label)+'</a>'

routing_path = OUT/'routing.json'
if not routing_path.exists():
    routing_path = OUT/'routing_report.json'
if not routing_path.exists():
    raise SystemExit('Waiting for the completed routing report; no summary written.')
routing = json.loads(routing_path.read_text(encoding='utf-8'))
electrical = load('electrical.json')
mechanics = load('mechanics.json')
documents = load('root_document_checks.json')
checks = load('root_fresh_checks.json')
equivalence = load('root_equivalence.json')
before = load('root_tracked_before.json')
changed = [{'path':p,'before':sha,'after':digest(ROOT/p)} for p,sha in before.items() if digest(ROOT/p)!=sha]
if changed:
    raise SystemExit('Tracked files changed; investigate before issuing the audit: '+str(changed))
v1 = Path(r'C:\Users\Alksndr\Desktop\codex\Meshcore\design\Meshcore_NaIon\Meshcore_NaIon.kicad_pcb')
original_board_hash = digest(v1)
frozen_board_hash = digest(ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pcb')
rules = {}
for name in ('Power','Logic','Shield'):
    pro = json.loads((ROOT/'design'/('MeshRepeater2_'+name)/('MeshRepeater2_'+name+'.kicad_pro')).read_text(encoding='utf-8'))
    board_rules = pro.get('board',{}).get('design_settings',{}).get('rule_severities',{})
    erc_rules = pro.get('erc',{}).get('rule_severities',{})
    rules[name] = {'DRC_severity_ignore':[k for k,v in board_rules.items() if v=='ignore'], 'ERC_severity_ignore':[k for k,v in erc_rules.items() if v=='ignore']}
new_findings = routing.get('findings',routing.get('findings_new_V2',[])) + mechanics['findings'] + documents['findings']
new_findings = [dict(f) for f in new_findings]
for f in new_findings:
    if f['id'] == 'R1':
        f['title'] = 'Избыточные обходы MOSI/MISO и RESET, разрывы местной опорной земли'
        f['detail'] = 'При тех же конечных площадках, что в S4.16, MOSI/MISO получили длинные обходы. Суммы целых выбранных сегментов около 171,1 / 94,6 мм против 33,7 / 35,6 мм в S4.16; это оценка графа, не точная длина пути внутри широких площадок. Вся медь соответствующих сетей — 185,3 / 121,7 мм, по 11 виа. Выбранный RESET вырос примерно с 53,0 до 102,4 мм. Под частями SPI нет земли противоположного слоя; у MOSI via (53; 21) ближайшая GND via находится в 6,02 мм. Функциональный отказ не установлен, но геометрическая регрессия подтверждена.'
        f['fix'] = 'Освободить центральный коридор MCU ↔ модем, сократить обходы и переходы, оставить согласующие резисторы у источников, обеспечить непрерывную местную опору и соседние GND via. GPIO и функции сохранить. Проверить SPI/reset осциллографом после переразводки.'
        f['evidence'] = ['routing.md:15; routing_spi_evidence.png', 'LOGIC PCB:31401, UUID 55ba81aa-501c-4eb4-92b4-31b9ec08ed3e — 9,1 мм MOSI без B.Cu GND', 'LOGIC PCB:36008, UUID 0b63f05f-ccd6-4c91-8e44-5a6e65296761 — 6,9 мм MISO без F.Cu GND', 'LOGIC PCB:31878 — сигнальная via (53; 21)']
    elif f['id'] == 'R2':
        f['title'] = 'RADIO_RXEN разрывает B.Cu GND непосредственно под ANT_RF'
        f['detail'] = 'Новая дорожка RXEN от (37,4; 8,6) до (49,2; 8,6) и её зазор прорезают нижнюю опорную медь под RF. Пробел по оси ANT_RF составляет около 0,900 мм; в S4.16 его не было. Боковая F.Cu земля остаётся, поэтому RF-возврат полностью не оборван. Изменение структуры и близкое цифровое пересечение подтверждены; величина RF/EMI-последствий не измерена.'
        f['fix'] = 'Перенести RXEN вне проекции ANT_RF/ANT_SMA, восстановить сплошную B.Cu GND под RF и добавить правило, запрещающее цифровые трассы в этом коридоре без запрета GND-заливки. Повторить проверку сохранённой меди и RF-тракта.'
        f['evidence'] = ['routing.md:44; routing_rf_reference_gap.png', 'LOGIC PCB:35441, UUID e0e0ec38-fa6a-448a-a9bd-716f6f9b20c8 — RXEN', 'LOGIC PCB:33187, UUID 0a10c8ed-006d-451e-8ec3-774664bdfb11 — ANT_RF']
    elif f['id'] == 'DOC-01':
        f['severity'] = 'P3'
        f['title'] = 'BOM H1–H4: подпись NPTH против фактических отверстий PTH GND'
        f['detail'] = 'Во всех трёх колонках номиналов H1–H4 осталось M3 NPTH, тогда как физические посадки, MPN и пояснения задают металлизированные отверстия с контактом GND. Нативная сверловка корректна; неоднозначность находится в тексте ведомости.'
        f['recommended_fix'] = 'Переименовать значения H1–H4 во всех вариантах в M3 PTH GND, сохранив геометрию и признак «не закупать как компонент».'
        f['evidence'] = ['bom/V2_COMPONENT_BOM.csv:71–74', 'Physical_Package_Footprint = Meshcore:GND_M3_D3.2_OD6; native pad type = thru_hole']
summary = {'date':'2026-10-12','scope':'Independent read-only audit of published Mesh Repeater 2.0; three fresh reviewers plus separate root proof checks','commit':checks['commit'],'baseline_commit':'cf54f9970e716272d477afdb252b4e195d595cb6','new_findings':new_findings,'inherited_accepted_risks':electrical['inherited_accepted_risks'],'formal_checks':{'kicad_version':checks['kicad_version'],'ERC_runs':2,'DRC_runs':6,'all_exit_codes_zero':all(c['exit_code']==0 for c in checks['checks']),'rules':rules},'equivalence':{'pass':equivalence['pass'],'retained_pins':equivalence['source_pins_retained'],'source_groups':equivalence['source_groups'],'v2_groups':equivalence['v2_groups'],'J11_removed_FILTER_SYS_separate':equivalence['J11_removed_FILTER_SYS_separate']},'local_document_links':{'checked':documents['checked_local_links'],'broken':documents['broken_local_links']},'preservation':{'tracked_file_count':len(before),'tracked_changes':changed,'original_V1_board_sha256':original_board_hash,'frozen_V1_board_sha256':frozen_board_hash,'V1_board_unchanged':original_board_hash==frozen_board_hash},'review_reports':{'routing':routing_path.name,'electrical':'electrical.json','mechanics':'mechanics.json','documents':'root_document_checks.json'},'product_modifications':False,'manufacturing_or_EMC_qualification':False}
(OUT/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

def finding_block(f, inherited=False):
    title = f.get('title',f.get('problem',f.get('evidence','Замечание')))
    priority = f.get('severity',f.get('priority',''))
    detail = f.get('detail',f.get('problem',f.get('description','')))
    if not detail and isinstance(f.get('evidence'),str):
        detail = f['evidence']
    fix = f.get('suggestion',f.get('recommended_fix',f.get('fix','')))
    ev = f.get('evidence',[])
    if isinstance(ev,list):
        # Preserve exact native references; individual reviewer reports contain
        # their sources, coordinates, screenshots and calculation assumptions.
        ev = '; '.join(str(x) for x in ev[:8])
    elif not isinstance(ev,str):
        ev = json.dumps(ev,ensure_ascii=False)
    coords = f.get('coordinates_native_mm',f.get('coordinates',None))
    extra = '<p class="source">'+esc(ev)+'</p>' if ev else ''
    if coords:
        extra += '<p class="source">Координаты native, мм: '+esc(json.dumps(coords,ensure_ascii=False))+'</p>'
    return '<article><p class="tag">'+esc(f.get('id',''))+' · '+esc(priority)+'</p><h3>'+esc(title)+'</h3><p>'+esc(detail)+'</p><p><b>Предлагаемая правка:</b> '+esc(fix)+'</p>'+extra+'</article>'

blocks = ''.join(finding_block(f) for f in new_findings)
images = ''
for name,caption in [('routing_spi_evidence.png','SPI: фактическая медь сохранённой LOGIC, маршруты MOSI/MISO и отсутствие местной опорной земли'),('routing_rf_reference_gap.png','RF: разрыв B.Cu GND под ANT_RF, образованный RADIO_RXEN')]:
    if (OUT/name).exists():
        images += '<figure>'+link(name,'<image>')+'<img src="'+esc(name)+'" alt="'+esc(caption)+'"><figcaption>'+esc(caption)+'</figcaption></figure>'
images = images.replace('&lt;image&gt;','Открыть изображение')
inherited = '''<article><p class="tag">E-I1 · высокий электрический риск · принято в S4.16</p><h3>Балансир LTO, R47/R51 = 2 Ом</h3><p>Согласованный номинал не ограничивает ток катода LMV431A паспортным пределом. При низком расчётном пороге около 2,700 В идеализированная модель при ячейке 2,8 В требует около 50,4 мА. Это демонстрирует отсутствие гарантированного ограничения; фактический ток за пределами спецификации так не предсказывается.</p><p>Рекомендованный предел — 15 мА, абсолютный — 30 мА: <a href="https://www.ti.com/lit/ds/symlink/lmv431.pdf">даташит TI</a>. Сохранение 2 Ом принято пользователем. Для будущего изменения нужны ограничение тока либо подходящий балансир; до этого — проверка тока и температуры на образце.</p></article>
<article><p class="tag">E-I2 · высокий электрический риск · унаследовано из S4.16</p><h3>LTO при отсутствии или отключении батареи</h3><p>Расчёт режима CN3722 без батареи даёт примерно 5,773 В типично и 5,978 В для верхнего угла при 25 °C. Рабочий предел TPS63802 — 5,5 В, абсолютный — 6 В. Запас делителя в обычном заряде не подтверждает этот отдельный режим.</p><p>Источники: <a href="https://consonance-elec.com/static/upload/file/20231218/1702867485736775.pdf">CN3722 Rev1.2</a> и <a href="https://www.ti.com/lit/ds/symlink/tps63802.pdf">TPS63802</a>. Пользователь выбрал делитель без отдельной защиты. Работа без батареи и её отключение остаются неквалифицированными; последующая схемная защита — отдельное изменение исходного решения.</p></article>'''
proof = [
('ERC обеих схем','0 ошибок и предупреждений. Все уровни включены; отключённых проверок нет.'),
('DRC POWER, LOGIC, SHIELD','6 свежих прогонов: сохранённая заливка и перезаливка в памяти. Нарушений, неразведённых цепей и расхождений схемы/платы нет; платы не сохранялись.'),
('Эквивалентность S4.16 → 2.0','435 сохранённых ref/pin, 102 группы в обоих вариантах графа; функциональных расхождений нет. Три варианта Value/Fit/MPN сохранены с документированными исключениями механики. SH1 удалена по принятому решению.'),
('GPIO и прошивка','Физические pad→GPIO сопоставлены с официальными Nice!Nano/HT-RA62 и MeshCore commit a366955… . SDA P1.04, кнопка P1.00, GPS RX/TX P0.22/P0.20 — корректны для проверенного варианта.'),
('J11 и межплатное соединение','1/3/5/7 FILTER_OUT; 6 чётных GND; 9 BAT sense; 11 MODE. SYS_3V3 в кабеле отсутствует. Снятый J11 разделяет FILTER_OUT и SYS_3V3.'),
('Физическая связность GND','Сохранённая медь, реальные площадки и переходы образуют один компонент GND на каждом этаже. Это проверка связности; она не отменяет обнаруженные разрывы опорной земли под отдельными сигналами.'),
('Механика','Каждый элемент 90 × 60 мм, четыре крепления совпадают. J10 сохранён (35,7; 31,3), 0°. Зазоры к экрану 5,960 / 5,270 мм; минимум до стойки 1,4046 мм. Текущая приближённая CAD-сборка без кабеля 98 × 70,01 × 45,56 мм.'),
('Документы и сохранность','68 локальных ссылок существуют. Все 837 ранее отслеживаемых файлов побайтно неизменны. Исходная плата 1.0 совпадает с замороженной S4.16.')]
rows = ''.join('<tr><th>'+esc(a)+'</th><td>'+esc(b)+'</td></tr>' for a,b in proof)
pending = [
'Полные размеры вставленных ответных частей, IDC-шлейфа и шунта J11; доступ руками/инструментом, полуповорот и прозвонка всех 12 жил 1:1, окончательная длина кабеля.',
'Полезная глубина резьбы и отсутствие упора крепежа; фактический прижим и сопротивление контакта GND через стойки и шайбы.',
'Питание конкретного Nice!Nano-клона от USB: аппаратное отключение зарядки, обратные токи, ток и нагрев штатного LDO.',
'Минимальная эффективная ёмкость LC при 3,3 В, пуск и скачки нагрузки; одновременные осциллограммы MCU/модема, минимальный BAT и GPS.',
'EMI/EMC, RF-тракт, SPI на выбранной частоте, RSSI/дальность. Средняя пластина после удаления SH1 не образует замкнутую металлическую клетку.',
'Паспорта ячеек и панели, холодный Voc, индивидуальные пределы LTO, температура NTC относительно батареи, реальные пороги COLD, калибровка BAT_ADC и восстановление watchdog.'
]
pending_html = ''.join('<li>'+esc(t)+'</li>' for t in pending)
links = ' · '.join(link(name,label) for name,label in [('routing.md','Полный аудит разводки'),('electrical.md','Расчёты и первичные даташиты'),('mechanics.md','Механика и комплектность'),('root_fresh_checks.json','Свежие ERC/DRC'),('root_equivalence.json','Независимое сравнение схем'),('SUMMARY.json','Сводные данные JSON')])
document = '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Независимый аудит Mesh Repeater 2.0</title><style>body{margin:0;background:#f4f6f8;color:#19232c;font:16px/1.6 Segoe UI,Arial,sans-serif}main{max-width:1120px;margin:auto;padding:32px 24px 64px}h1{font-size:29px;line-height:1.25}h2{font-size:23px;margin-top:36px}h3{font-size:19px;margin:4px 0}article{background:white;border:1px solid #d6dfe7;border-left:4px solid #d2942d;padding:18px 22px;margin:16px 0;border-radius:6px}p{margin:10px 0}.tag{font-weight:700;color:#77521e;font-size:14px}.source{font:13px/1.6 Consolas,monospace;overflow-wrap:anywhere;color:#52616e}a{color:#005db4}table{width:100%;border-collapse:collapse;background:white}th,td{padding:12px 15px;border:1px solid #d6dfe7;text-align:left;vertical-align:top}th{width:26%}figure{margin:24px 0;background:white;padding:10px;border:1px solid #d6dfe7}img{width:100%;height:auto;display:block}figcaption{padding:10px;color:#465968}code{overflow-wrap:anywhere}.lead{font-size:18px;padding:16px 20px;background:#fff3d9;border-left:4px solid #d2942d}.small{font-size:14px;color:#52616e}li{margin:9px 0}</style><main>'''
document += '<h1>Независимый аудит Mesh Repeater 2.0</h1><p>12 октября 2026 года · KiCad 10.0.6 · опубликованный коммит <code>'+esc(checks['commit'])+'</code></p><p class="lead">Формальная связность схем и плат подтверждена. Обнаружены новые недостатки трассировки верхней платы и комплектности документации. Их следует исправить до выпуска; согласованные электрические риски 1.0 остаются отдельными вопросами квалификации.</p><p>Три проверяющих не участвовали в проектировании и работали с сохранёнными native CAD, первичными источниками и собственными расчётами. Отдельно выполнены свежие ERC/DRC и сравнение с новым экспортом исходной S4.16. Старые PASS не служили самостоятельным доказательством. CAD, библиотеки, настройки и GitHub не изменены.</p><p>'+links+'</p>'
document += '<h2>Новые замечания: '+str(len(new_findings))+'</h2><p class="small">Высокий приоритет означает необходимость переработки или проверки, а не установленный стендовый отказ. Подробные предположения измерений и точные native ссылки находятся в профильных отчётах.</p>'+blocks+images
document += '<h2>Что подтверждено</h2><table>'+rows+'</table>'
document += '<h2>Согласованные исходные риски</h2>'+inherited
document += '<h2>Что требует собранного образца</h2><ul>'+pending_html+'</ul><p>Сертификация EMC, фактический нагрев и устойчивость питания не установлены CAD-аудитом. Отсутствие ошибок DRC подтверждает геометрические правила проекта и не является доказательством этих характеристик.</p>'
document += '<h2>Порядок последующей правки</h2><p>Сначала освободить короткий коридор SPI MCU ↔ модем и вынести RXEN из-под RF-тракта, сохраняя GPIO и функции. Затем упростить избыточные участки, дополнить кабельные позиции J3/J5, исправить оболочку модели кнопок и неоднозначные обозначения крепёжных отверстий. После фактических изменений повторить затронутые проверки и пересоздать виды/экспорты с новыми хешами.</p><p>Пакет изготовления и публикация исправлений в рамках этого аудита не выполнялись. Исходная ветка 1.0, её тег v1.0 и отложенный заказ остаются в прежнем состоянии.</p><p class="small">Исходная S4.16: <code>cf54f9970e716272d477afdb252b4e195d595cb6</code>. Все машинные данные и скрипты находятся рядом с отчётом. Проверка снимка: 837 файлов, изменений 0; SHA платы 1.0 <code>'+esc(original_board_hash)+'</code>.</p></main></html>'
(OUT/'SUMMARY_RU.html').write_text(document,encoding='utf-8')
print(json.dumps({'report':str(OUT/'SUMMARY_RU.html'),'new_findings':len(new_findings),'tracked_changes':changed,'V1_board_unchanged':summary['preservation']['V1_board_unchanged'],'html_sha256':digest(OUT/'SUMMARY_RU.html')},ensure_ascii=False))
