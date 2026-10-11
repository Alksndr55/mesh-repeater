"""Build a local gallery using final CAD exports; contains no fabricated views."""
from pathlib import Path
import html
ROOT=Path(__file__).resolve().parents[1]

def main():
 cards=[
  ('Сборка, реальные STEP-модели','../docs/mechanics/MeshRepeater2_assembly_native_3D.png'),
  ('Разнесённая сборка','../docs/mechanics/MeshRepeater2_exploded_native_3D.png'),
  ('Размеры и ориентация этажей','../docs/mechanics/MeshRepeater2_stack_dimensions.png'),
  ('Кабель: размерное предложение, проверить по образцу','../docs/mechanics/MeshRepeater2_harness_routing_plan.png'),
  ('POWER — лицевая медь','POWER/MeshRepeater2_Power_front.png'),
  ('POWER — обратная сторона','POWER/MeshRepeater2_Power_back.png'),
  ('LOGIC — сторона компонентов','LOGIC/MeshRepeater2_Logic_front.png'),
  ('LOGIC — наружный вид после поворота X на 180°','LOGIC/MeshRepeater2_Logic_operator_top.png'),
  ('SHIELD — лицевая сторона','SHIELD/MeshRepeater2_Shield_front.png'),
  ('SHIELD — обратная сторона','SHIELD/MeshRepeater2_Shield_back.png'),
 ]
 links=[
  ('Схема POWER, PDF','pdf/MeshRepeater2_Power_schematic.pdf'),
  ('Схема LOGIC, PDF','pdf/MeshRepeater2_Logic_schematic.pdf'),
  ('Сборка и обслуживание, PDF','pdf/MeshRepeater2_assembly_manual_RU.pdf'),
  ('Размерный сборочный чертёж, PDF','pdf/MeshRepeater2_assembly_dimensions.pdf'),
  ('BOM: компоненты и варианты','../bom/V2_COMPONENT_BOM.csv'),
  ('Закупка новых деталей в ДАН','../bom/DAN_NEW_PARTS.csv'),
  ('Отчёт итоговых проверок','../audit/V2_FINAL_ACCEPTANCE.json'),
  ('Ограничения и предстоящие испытания','../docs/V2_LIMITATIONS_RU.md'),
  ('Проект POWER','../design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pro'),
  ('Проект LOGIC','../design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pro'),
  ('Проект SHIELD','../design/MeshRepeater2_Shield/MeshRepeater2_Shield.kicad_pro'),
 ]
 body=''.join('<a href="'+html.escape(p,quote=True)+'">'+html.escape(t)+'</a>' for t,p in links)
 figures=''.join('<figure><figcaption>'+html.escape(t)+'</figcaption><a href="'+html.escape(p,quote=True)+'"><img loading="lazy" src="'+html.escape(p,quote=True)+'" alt="'+html.escape(t,quote=True)+'"></a></figure>' for t,p in cards)
 document='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mesh Repeater 2.0 — окончательные виды</title>
<style>body{font:16px/1.55 system-ui,sans-serif;margin:0;background:#eef1f4;color:#172c3e}main{max-width:1240px;margin:auto;padding:30px}h1{font-size:30px}nav{display:flex;flex-wrap:wrap;gap:10px}nav a{background:white;padding:9px 14px;border-radius:6px;color:#175179}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px;margin-top:25px}figure{margin:0;background:white;border-radius:8px;padding:16px}img{width:100%;height:auto}figcaption{font-weight:600;margin-bottom:10px}.note{padding:15px;border-left:4px solid #ba842b;background:#fff8e9}@media(max-width:500px){.grid{grid-template-columns:1fr}main{padding:16px}}</style>
<main><h1>Mesh Repeater 2.0</h1><p>POWER + сплошной экран + LOGIC: каждый элемент 90×60 мм. Верхняя плата обращена компонентами вниз. ISP J10 сохранён; обслуживание после разборки.</p>
<p class="note">Это проверенные CAD-файлы прототипа. Электрические режимы, EMI, реальное сопряжение кабеля и крепежа требуют проверки образца. Цвета 3D условные, геометрия взята из экспортов плат. Размерная цепь 44,98 мм; полный текущий 3D-габарит с выступающей шпилькой 98,00×70,01×45,56 мм. Внешний кабель требует дополнительного места.</p><nav>'''+body+'</nav><div class="grid">'+figures+'</div></main></html>'
 dest=ROOT/'output/V2_OVERVIEW_RU.html';dest.write_text(document,encoding='utf8');print(dest)

if __name__=='__main__':main()
