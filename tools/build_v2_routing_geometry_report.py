"""Publish native before/after views only after the independent geometry audit."""
from pathlib import Path
import hashlib, html, json

ROOT=Path(__file__).resolve().parents[1]
AUDIT='audit/routing_geometry_2026_10_12'

def main():
    review=json.loads((ROOT/AUDIT/'independent_final.json').read_text(encoding='utf-8'))
    acceptance=json.loads((ROOT/'audit/V2_FINAL_ACCEPTANCE.json').read_text(encoding='utf-8'))
    assert review['ok'] and review['routing_geometry_review_complete']
    assert acceptance['ok']
    for path,digest in review['inputs'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
    closure_html=''
    closure_path=ROOT/AUDIT/'closure_review.json'
    if closure_path.is_file():
        closure=json.loads(closure_path.read_text(encoding='utf-8'))
        assert not closure['genuine_unapplied_safe_actions'] and closure['independent_saved_native_gate_pass']
        closure_rows=[]
        for item in closure['issues']:
            status='Исправлено' if item['status'].startswith('APPLIED') else 'Сохранено с обоснованием' if item['status'].startswith('RETAINED') else item['status']
            closure_rows.append('<tr>'+''.join('<td>'+html.escape(str(value))+'</td>' for value in (item['board'],item['subject'],status,item['result_ru']))+'</tr>')
        closure_html='<h2>Применение исходного аудита</h2><p>Сверены все 18 пунктов. Пропущенное объединение GPS_3V3 исправлено; неприменённых безопасных правок нет. Обязательные обходы и защищённые возвраты указаны отдельно.</p><p><a href="../'+AUDIT+'/closure_review.md">Подробная сверка замечаний</a></p><table><tr><th>Плата</th><th>Участок</th><th>Статус</th><th>Результат</th></tr>'+''.join(closure_rows)+'</table><h2>Измерения до и после</h2>'
    columns=[('segments','Сегменты'),('turns','Повороты'),
             ('micro_segments_under_0_25_mm','Сегменты короче 0,25 мм'),
             ('length_mm','Длина всех дорожек, мм'),('gnd_vias','Переходы GND')]
    rows=[]
    for name,board in review['boards'].items():
        for key,label in columns:
            old,new=board['before'][key],board['after'][key]
            if key=='length_mm':old,new=f'{old:.2f}',f'{new:.2f}'
            rows.append(f'<tr><td>{name}</td><td>{label}</td><td>{old}</td><td>{new}</td></tr>')
        rows.append(f'<tr><td>{name}</td><td>Перенесено переходов GND</td><td>—</td><td>{board["gnd_vias_moved"]}</td></tr>')
    links=[('Независимый аудит','../'+AUDIT+'/independent_final_RU.md'),
           ('Все измерения','../'+AUDIT+'/independent_final.json'),
           ('Итоговая проверка файлов','../audit/V2_FINAL_ACCEPTANCE.json'),
           ('Схема POWER','pdf/MeshRepeater2_Power_V2_A2_INA219_schematic.pdf'),
           ('Схема LOGIC','pdf/MeshRepeater2_Logic_V2_A2_schematic.pdf')]
    for name in ('Power','Logic'):
        links.append(('Проект '+name.upper(),f'../design/MeshRepeater2_{name}/MeshRepeater2_{name}.kicad_pro'))
    nav=''.join(f'<a href="{html.escape(path,quote=True)}">{html.escape(label)}</a>' for label,path in links)
    cards=[]
    for name in ('POWER','LOGIC'):
        for side,label in (('front','лицевая сторона'),('back','обратная сторона')):
            before=f'../{AUDIT}/before/images/{name}_{side}.png'
            after=f'{name}/MeshRepeater2_{name.title()}_{side}.png'
            assert (ROOT/'output'/before).is_file() and (ROOT/'output'/after).is_file()
            cards.append(f'<figure><figcaption>{name}: {label}</figcaption><a class="image-link" href="{after}"><img src="{after}" data-before="{before}" data-after="{after}" alt="{name}: {label}"></a></figure>')
    document='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mesh Repeater 2.0 — геометрия трассировки</title>
<style>body{margin:0;background:#edf2f5;color:#193349;font:16px/1.55 system-ui}main{max-width:1240px;margin:auto;padding:28px}nav{display:flex;gap:10px;flex-wrap:wrap}nav a,button{padding:9px 14px;background:white;border:1px solid #cddae3;border-radius:6px;color:#174f75}table{width:100%;border-collapse:collapse;background:white;margin:24px 0}td,th{text-align:left;padding:8px 12px;border-bottom:1px solid #dce4eb}.good{background:#e5f5e9;border-left:4px solid #268449;padding:15px}.controls{position:sticky;top:0;background:#edf2f5;padding:12px 0;z-index:2;display:flex;align-items:center;gap:12px}button{cursor:pointer}button[aria-pressed=true]{background:#174f75;color:white}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:20px}figure{margin:0;padding:14px;background:white}figcaption{font-weight:600;margin-bottom:12px}img{display:block;width:100%;height:auto}@media(max-width:500px){main{padding:16px}.grid{grid-template-columns:1fr}}</style>
<main><h1>Mesh Repeater 2.0: геометрия дорожек и земляных переходов</h1><p>Независимый аудит и исправления сохранённых плат POWER и LOGIC. Схемы, GPIO, номиналы, посадочные места и положение ISP сохранены.</p>
<p class="good">Все направления дорожек — 0°, 45° и 90°. Свежий строгий DRC: 0 нарушений, 0 неподключённых цепей. Связанность GND, точки ответвления, силовые и RF-узлы проверены по сохранённой меди.</p><nav>'''+nav+'</nav>'+closure_html+'''<table><tr><th>Плата</th><th>Показатель</th><th>До</th><th>После</th></tr>'''+''.join(rows)+'''</table>
<p>Убраны проверенные возвратные петли и мелкие ступеньки. Свободные переходы вынесены из коридоров дорожек и привязаны к существующим рядам. Сетка 3 мм, локальная ограда POWER с шагом 2 мм и переходы возвратных токов сохранены. Повороты, необходимые для обхода площадок, переходов и ответвлений, остаются. Проверка CAD не заменяет измерения EMI и переходных процессов на образце.</p>
<div class="controls"><strong>Сравнение:</strong><button data-state="before" aria-pressed="false">До правок</button><button data-state="after" aria-pressed="true">После правок</button><span>Нажмите на изображение для полного размера.</span></div><div class="grid">'''+''.join(cards)+'''</div></main>
<script>document.querySelectorAll('button[data-state]').forEach(button=>button.addEventListener('click',()=>{const state=button.dataset.state;document.querySelectorAll('img[data-before]').forEach(img=>{img.src=img.dataset[state];img.parentElement.href=img.src;});document.querySelectorAll('button[data-state]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));}));</script></html>'''
    target=ROOT/'output/V2_ROUTING_GEOMETRY_RU.html'
    target.write_text(document,encoding='utf-8')
    print(target)

if __name__=='__main__':main()
