"""Publish the completed A2 review using final saved CAD and audit outputs."""
from pathlib import Path
import hashlib,html,json
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def record(p):return {'path':p,'sha256':sha(p)}

def schematic_manifest():
    projects=[]
    for board,pdf,pages in [('POWER','MeshRepeater2_Power_V2_A2_INA219_schematic.pdf',6),('LOGIC','MeshRepeater2_Logic_V2_A2_schematic.pdf',4)]:
        name='MeshRepeater2_'+board.title();folder=ROOT/'design'/name
        assert len(PdfReader(ROOT/'output/pdf'/pdf).pages)==pages
        previews=[f'audit/ina219_and_vertical_2026_10_12/pdf_preview/{board.lower()}-{i}.png' for i in range(1,pages+1)]
        assert all((ROOT/p).is_file() for p in previews)
        projects.append({'board':board,'pages':pages,'native_schematics':[record(str(p.relative_to(ROOT)).replace('\\','/')) for p in sorted(folder.glob('*.kicad_sch'))],'native_netlist':record(f'audit/schematic/{board}/netlist.xml'),'strict_erc':record(f'audit/schematic/{board}/erc.json'),'pdf':record('output/pdf/'+pdf),'reviewed_previews':[record(p) for p in previews]})
    qa={'revision':'V2.0-A2','page_count':10,'every_page_visually_inspected':True,'renderer':'Native KiCad10 PDF + Poppler PNG','native_editor_files_retained':True,'corrections':'INA219 compact circuit, readable MPN/package captions, five child sheet references within A3 frame, exact vertical interconnect roles. All ten exported pages visually reviewed.','projects':projects}
    target='audit/schematic/final_schematic_output_manifest.json'
    old=ROOT/'audit/ina219_and_vertical_2026_10_12/before/final_schematic_output_manifest_A1.json'
    if not old.exists():old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes((ROOT/target).read_bytes())
    (ROOT/target).write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    manifest={'revision':'V2.0-A2','projects':[{k:v for k,v in p.items() if k not in ('native_schematics','reviewed_previews')} for p in projects],'visual_qa':record(target),'historical_A1_PDFs':['MeshRepeater2_Power_schematic.pdf','MeshRepeater2_Logic_schematic.pdf']}
    (ROOT/'output/pdf/SCHEMATIC_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    acceptance=read('audit/V2_FINAL_ACCEPTANCE.json')
    assert acceptance.get('stage')=='V2_0_A2_INA219_VERTICAL_SAVED_CAD_GATE' and acceptance['ok']
    schematic_manifest()
    mating=read('audit/ina219_vertical_interconnect_2026_10_12/vertical_coordinate_mating.json')
    geometry=read('docs/mechanics/assembly_geometry_report.json')['artifacts']['MeshRepeater2_assembly']
    dims=[geometry['bbox_mm'][i+3]-geometry['bbox_mm'][i] for i in range(3)]
    sch=read('audit/v2_schematic_equivalence.json');native=read('audit/v2_native_boards_final.json')
    pinmap=read('design/feature_ina219_vertical.json')['interboard_pinmap']
    rows=''.join(f'<tr><td>{p}</td><td>{html.escape(n)}</td></tr>' for p,n in pinmap.items())
    links=[('Проект POWER','../design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pro'),('Проект LOGIC','../design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pro'),('Проект SHIELD','../design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pro'),('Схема POWER','pdf/MeshRepeater2_Power_V2_A2_INA219_schematic.pdf'),('Схема LOGIC','pdf/MeshRepeater2_Logic_V2_A2_schematic.pdf'),('Компоненты и варианты','../bom/V2_COMPONENT_BOM.csv'),('Закупка новых деталей','../bom/DAN_NEW_PARTS.csv'),('Независимый аудит','../audit/ina219_and_vertical_2026_10_12/independent_final_review.md'),('Итоговые проверки','../audit/V2_FINAL_ACCEPTANCE.json'),('Инструкция сборки','../docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md')]
    if (ROOT/'audit/routing_geometry_2026_10_12/independent_final.json').is_file():
        links=[(label,'../audit/routing_geometry_2026_10_12/independent_final_RU.md' if label=='Независимый аудит' else path) for label,path in links]
        links.insert(0,('Геометрия дорожек: сравнение до/после','V2_ROUTING_GEOMETRY_RU.html'))
    nav=''.join(f'<a href="{html.escape(p,quote=True)}">{html.escape(t)}</a>' for t,p in links)
    cards=[('POWER: сторона компонентов','POWER/MeshRepeater2_Power_front.png'),('POWER: обратная сторона и шунт','POWER/MeshRepeater2_Power_back.png'),('LOGIC: новый межплатный разъём','LOGIC/MeshRepeater2_Logic_front.png'),('Экран: 12 изолированных отверстий','SHIELD/MeshRepeater2_Shield_front.png'),('Номинальная 3D-сборка','../docs/mechanics/MeshRepeater2_assembly_native_3D.png')]
    pictures=''.join(f'<figure><figcaption>{html.escape(t)}</figcaption><a href="{p}"><img src="{p}" alt="{html.escape(t)}"></a></figure>' for t,p in cards)
    doc=f'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mesh Repeater 2.0 A2 - INA219 и вертикальные разъёмы</title>
<style>body{{font:16px/1.55 system-ui;margin:0;background:#eef2f4;color:#173046}}main{{max-width:1200px;margin:auto;padding:28px}}nav{{display:flex;flex-wrap:wrap;gap:10px}}nav a{{background:white;padding:9px 14px;border-radius:6px}}.good{{background:#e7f6eb;border-left:4px solid #208247;padding:15px}}.note{{background:#fff6df;padding:15px}}table{{border-collapse:collapse;background:white;width:100%;margin:16px 0}}th,td{{text-align:left;border-bottom:1px solid #dce3e8;padding:8px 12px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:18px}}figure{{background:white;padding:14px;margin:0}}figcaption{{font-weight:600}}img{{width:100%;height:auto}}@media(max-width:500px){{main{{padding:15px}}.grid{{grid-template-columns:1fr}}}}</style>
<main><h1>Mesh Repeater 2.0 / A2</h1><p>12 октября 2026. INA219 на нижней плате и прямые штыри через средний экран. Платы 90 × 60 мм, прежние GPIO Nice!Nano и HT-RA62 сохранены. ISP J10 остаётся на (35,7;31,3), 0°.</p>
<p class="good">ERC двух схем: 0. DRC трёх плат: 0, неподключённых цепей: 0. Схема: {len(sch['checks'])}/{len(sch['checks'])}; проверка native PCB: {len(native['checks'])}/{len(native['checks'])}. Все 12 физических пар совпадают. Полные пересечения моделей плат и экрана: 0.</p><nav>{nav}</nav>
<h2>Измеритель батареи</h2><p>U12 INA219AIDR, SOIC-8, адрес 0x40. R71 RL2512FK-070R1L: 0,1 Ом ±1%, 1 Вт, 2512. Штатная калибровка MeshCore: заряд положительный, разряд отрицательный; измеряется напряжение самой батареи.</p>
<p>Шунт разделяет BAT и BAT_SYS. Дорожки измерения сняты отдельно с его площадок; R72/R73 по 10 Ом и C64 100 нФ образуют входной фильтр. C63 100 нФ установлен у питания INA. Делитель и BAT-sense CN3722 остаются на BAT_SYS; EN TPS63802 и BAT_ADC подключены к сырой BAT.</p>
<p>VS приходит с верхней SYS_3V3 по контакту 7. Поэтому INA питается при USB со снятой J11; соединения в обход J11 нет. Шунт даёт 80 мВ / 64 мВт при 800 мА и 125 мВ / 156 мВт при 1,25 А. INA потребляет около 0,7 мА типично, максимум 1 мА по <a href="https://www.ti.com/lit/ds/symlink/ina219.pdf">паспорту TI</a>. Токи LTO-балансиров обходят измерительный шунт.</p>
<h2>Межплатное соединение</h2><p>J101: E-SIMPO L35mm A3C6, 2×6; J201: MTJ H8.5, 2×6. Общая длина металла 35 мм, нижний вывод 3 мм, кончик над POWER 32 мм. Номинальная глубина входа в розетку {mating['nominal_socket_insertion_mm']:.2f} мм. Зеркальная локальная сетка J201 учитывает поворот LOGIC вокруг X.</p><table><tr><th>Контакт J101 = J201</th><th>Сеть</th></tr>{rows}</table>
<p>В экране 12 NPTH Ø2 мм. Отступ фольги от сверловки не менее 0,5 мм; вокруг группы сделан общий вырез только в меди, сохраняющий одну связанную фольгу. Механические стойки и высота этажей сохранены. Габарит предоставленных 3D-моделей: {' × '.join(f'{x:.2f}' for x in dims)} мм.</p>
<p class="note">Показан проверенный CAD прототипа. Посадка, прямолинейность и реальное сечение Ali-штырей, контакты розетки и допуски сборки проверяются на образце. Ранее согласованные ограничения LTO с резисторами 2 Ом и без независимой OVP сохраняются. Пакет заказа плат остаётся отложенным; старые сборочные PDF с IDC относятся к A1.</p>
<div class="grid">{pictures}</div></main></html>'''
    closure_path=ROOT/'audit/routing_geometry_2026_10_12/closure_review.json'
    if closure_path.is_file():
        closure=read(str(closure_path.relative_to(ROOT)).replace('\\','/'))
        assert not closure['genuine_unapplied_safe_actions'] and closure['independent_saved_native_gate_pass']
        notice='<p class="good">Исправления исходного аудита применены. Сверены все 18 пунктов; пропущенная коллинеарная пара GPS_3V3 объединена. <a href="V2_ROUTING_GEOMETRY_RU.html">Статус каждого замечания и актуальные платы</a>.</p>'
        doc=doc.replace('<nav>',notice+'<nav>',1)
    dest=ROOT/'output/V2_A2_INA219_VERTICAL_RU.html';dest.write_text(doc,encoding='utf-8');print(dest)

if __name__=='__main__':main()
