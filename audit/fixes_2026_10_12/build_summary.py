"""Publish the completed fix evidence as a local human-readable report."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, html, json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
load = lambda p:json.loads((ROOT/p).read_text(encoding='utf-8'))
sha = lambda p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
gate = load('audit/V2_FINAL_ACCEPTANCE.json')
proof = load('audit/fixes_2026_10_12/reviewer_routing.json')
fresh = load('audit/fixes_2026_10_12/root_fresh_checks.json')
equiv = load('audit/fixes_2026_10_12/root_equivalence.json')
assert gate['ok'] and equiv['pass']
assert all(c['exit_code'] == 0 for c in fresh['checks'])
assert not fresh['tracked_changes']
assert proof['sha256'] == sha(proof['input'])
assert proof['native_unchanged_by_review']
decision=load('audit/fixes_2026_10_12/user_decision.json')
assert decision['status']=='PRESERVE_EXISTING_LTO_AND_ACCEPT_NOTED_LIMITATIONS'
baseline = load('audit/independent_2026_10_12/SUMMARY.json')
paths = proof['selected_paths']
numbers = {n:{'mm':round(paths[n]['whole_selected_segments_sum_mm'],2),'vias':paths[n]['via_count']} for n in ('MOSI','MISO','RESET')}
body = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mesh Repeater 2.0 — исправления аудита, 12 октября 2026</title>
<style>body{{font:16px/1.55 system-ui,sans-serif;background:#edf1f5;color:#173042;margin:0}}main{{max-width:1120px;margin:auto;padding:28px}}article,section{{background:white;padding:20px;margin:18px 0;border-radius:7px}}h1{{font-size:29px}}h2{{font-size:21px}}a{{color:#165784}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:9px;border-bottom:1px solid #dce3e8}}img{{width:100%;height:auto}}.ok{{color:#186543;font-weight:650}}.pending{{border-left:5px solid #b17620;background:#fff7e8}}code{{overflow-wrap:anywhere}}nav{{display:flex;gap:14px;flex-wrap:wrap}}</style>
<main><h1>Mesh Repeater 2.0 — исправления аудита</h1>
<p class="ok">Пять новых замечаний устранены. Проверены актуальные сохранённые CAD-файлы.</p>
<p>Исходный аудит относится к опубликованному коммиту <code>547740fee937f891568f18485c7a6a3733c234c9</code>. Этот отчёт относится к локальным исправлениям; он не подтверждает их публикацию на GitHub. Версия 1.0 и замороженная S4.16 сохранены.</p>
<nav><a href="../../output/V2_OVERVIEW_RU.html">Виды и документы</a><a href="../../design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pro">Проект LOGIC</a><a href="../../design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pro">Проект POWER</a><a href="../../bom/DAN_NEW_PARTS.csv">Закупка в ДАН</a><a href="../independent_2026_10_12/SUMMARY_RU.html">Исходный аудит</a></nav>
<article><h2>R1 — короткие линии SPI и RESET</h2>
<table><tr><th>Путь</th><th>До: целые выбранные сегменты</th><th>После</th><th>Переходы после</th></tr>
<tr><td>MOSI</td><td>171,09 мм</td><td>{numbers['MOSI']['mm']:.2f} мм</td><td>{numbers['MOSI']['vias']}</td></tr>
<tr><td>MISO</td><td>94,64 мм</td><td>{numbers['MISO']['mm']:.2f} мм</td><td>{numbers['MISO']['vias']}</td></tr>
<tr><td>RESET</td><td>102,42 мм</td><td>{numbers['RESET']['mm']:.2f} мм</td><td>{numbers['RESET']['vias']}</td></tr></table>
<p>Устранены длинные обходы; добавлены локальные переходы GND возле смены слоя и участков сигнальных трасс. Значения — суммы целых нативных сегментов из графа соединений; это не расчёт электрической длины внутри широких площадок. Фактическое качество фронтов проверяется на образце.</p>
<p><a href="reviewer_routing.json">Независимый замер меди и опорной земли</a></p>
<img src="../../output/LOGIC/MeshRepeater2_Logic_front.png" alt="Текущая лицевая сторона LOGIC"></article>
<article><h2>R2 — земля под ANT_RF</h2><p>RXEN выведен из проекции ANT_RF. Прежний пробел B.Cu GND около 0,90 мм устранён. Добавлено правило RF_GROUND_GUARD, запрещающее цифровые дорожки и переходы на обратном слое этого участка при сохранении GND-заливки. Правило проверено отрицательной контрольной пробой в отдельной копии платы.</p>
<p>Исходная неоднородность возле SMA launch отмечена отдельно; непрерывность ANT_RF не объявляется гарантией одинакового импеданса всего антенного тракта.</p>
<img src="../../output/LOGIC/MeshRepeater2_Logic_back.png" alt="Текущая обратная сторона LOGIC"></article>
<article><h2>M-01 — полный комплект кабельных частей</h2><p>Для J3/J5 добавлены два корпуса Connfly I-DS1071-SCB01x4 и восемь контактов T-DS1071-SC600 на комплект устройства. ДАН: артикулы 208362 и 201995; на дату проверки было 170 и 6746 шт. Официальный DS1071 подтверждает совместимую серию DS1022. Распиновки, размеры и ограничение по реальному обжиму приведены в инструкции.</p><p><a href="mechanics.json">Изменения механики и закупки</a> · <a href="reviewer_mechanics.json">Независимая проверка</a></p></article>
<article><h2>M-02 — модель кнопок</h2><p>Ширина скобы STEP кнопок SW1/SW2 исправлена с 7,66 на 8,41 мм. Геометрия площадок и courtyard сохранена. Обновлены модели POWER/LOGIC, экспорты плат, сборка и размерный чертёж.</p><p><a href="../../docs/mechanics/assembly_geometry_report.json">Зазоры актуальной сборки</a> · <a href="../../output/pdf/MeshRepeater2_assembly_dimensions.pdf">Размерный PDF</a></p><p>У экспорта LOGIC осталось прежнее предупреждение о двух мелких контурах меди. Доставленные тела STEP геометрически корректны, но точное воспроизведение всей меди не заявляется; <a href="step_diagnosis_RU.md">диагностика экспорта</a>.</p></article>
<article><h2>DOC-01 — правильное описание крепёжных отверстий</h2><p>H1–H4 во всех вариантах BOM, скрытых полях схемы/платы и локальных вариантах посадочных мест обозначены M3 GND contact. Отверстия Ø3,2 мм металлизированы, контактные кольца Ø6 мм связаны с GND. Исправлены генераторы; электрические связи, сверловка и медь POWER сохранены.</p><p><a href="root_hole_metadata.json">Проверка точечной замены метаданных</a></p></article>
<section><h2>Проверки</h2><p>Свежие ERC обеих схем и DRC трёх плат — 0 нарушений, 0 неразведённых цепей и 0 расхождений со схемой. DRC выполнен и на сохранённой меди, и после отдельного пересчёта полигонов. Отключённых проверок нет. Сохранены 435 исходных функциональных/контактных выводов и 102 группы связности; J11 остаётся единственной связью FILTER_OUT→SYS_3V3. J10 ISP не перемещён. Ветви питания MCU и модема раздельные; отвод BATsense сохранён.</p>
<p><a href="root_fresh_checks.json">ERC/DRC</a> · <a href="root_equivalence.json">Эквивалентность свежих схем</a> · <a href="../../audit/V2_FINAL_ACCEPTANCE.json">Проверка файлов и контрольных сумм</a></p>
<p>Это проверка проекта, а не протокол электрических, тепловых или EMI-испытаний. Остаточные требования к образцу перечислены в <a href="../../docs/V2_LIMITATIONS_RU.md">ограничениях</a>.</p></section>
<article class="pending"><h2>E-I1 — сохранённое ограничение LTO-балансира</h2><p>12 октября 2026 года пользователь выбрал «Сохранить прежнюю схему LTO и отмеченные ограничения». Резисторы 2 Ом и прямое включение LMV431 сохранены; усилитель не добавляется. Риск превышения допустимого тока катода остаётся. Принятие ограничения не считается его устранением.</p><p><a href="user_decision.json">Зафиксированный выбор пользователя</a></p></article>
<article class="pending"><h2>E-I2 — сохранённое ограничение при отключении LTO</h2><p>По выбору пользователя прежний делитель CN3722 без независимой отсечки сохранён. При отсутствии аккумулятора внутренняя OVP может превышать рабочие 5,5 В TPS63802. Смена делителя не гарантирует предел при переходном процессе. Этот риск остаётся принятым ограничением; изменений электрической схемы по этому пункту нет.</p><p><a href="lto_options_RU.html">Рассмотренные варианты и расчёты — не применены</a></p></article>
<p>Дата: 12 октября 2026. Нативный LOGIC SHA256: <code>{sha(proof['input'])}</code>.</p></main></html>'''
(OUT/'SUMMARY_RU.html').write_text(body,encoding='utf-8')
report = {
    'date_UTC': datetime.now(timezone.utc).isoformat(), 'scope':'Five new V2 findings corrected; previous LTO constraints not silently changed',
    'new_findings_closed':['R1','R2','M-01','M-02','DOC-01'], 'routing_paths_after':numbers,
    'inherited_LTO_findings':['E-I1','E-I2'], 'inherited_LTO_status':'User selected preservation of existing circuitry and noted limitations; risks unchanged',
    'publication_asserted':False, 'hardware_tests_performed':False,
    'inputs_sha256':{p:sha(p) for p in ['audit/V2_FINAL_ACCEPTANCE.json','audit/fixes_2026_10_12/user_decision.json','audit/fixes_2026_10_12/root_fresh_checks.json','audit/fixes_2026_10_12/root_equivalence.json','audit/fixes_2026_10_12/reviewer_routing.json','audit/fixes_2026_10_12/reviewer_mechanics.json','audit/fixes_2026_10_12/root_hole_metadata.json','audit/fixes_2026_10_12/lto_options.json']},
}
(OUT/'SUMMARY.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'new_findings_closed':report['new_findings_closed'],'path':str(OUT/'SUMMARY_RU.html')}))
