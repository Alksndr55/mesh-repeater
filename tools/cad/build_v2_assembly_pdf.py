"""Publish a dimensioned review PDF from verified native STEP assembly outputs."""
from pathlib import Path
from datetime import date
import hashlib
import json

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/mechanics'
OUTPUT = ROOT / 'output/pdf/MeshRepeater2_assembly_dimensions.pdf'


def main():
    report = json.loads((DOCS / 'assembly_geometry_report.json').read_text(encoding='utf-8'))
    images = json.loads((DOCS / 'native_render_report.json').read_text(encoding='utf-8'))
    contract = json.loads((ROOT / 'docs/mechanical_selection.json').read_text(encoding='utf-8'))
    for record in report['inputs'].values():
        assert hashlib.sha256((ROOT / record['path']).read_bytes()).hexdigest() == record['sha256']
        pcb = record['verified_pcb_source']
        assert hashlib.sha256((ROOT / pcb['path']).read_bytes()).hexdigest() == pcb['sha256']
    for record in images['renders']:
        assert hashlib.sha256((ROOT / record['image']).read_bytes()).hexdigest() == record['image_sha256']
        assert record['verified_native_inputs'] == report['inputs']
    assert len(images['renders']) == 3, 'Three native CAD views are required.'
    pdfmetrics.registerFont(TTFont('Arial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('ArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    width, height = landscape(A3)
    c = canvas.Canvas(str(OUTPUT), pagesize=(width, height))
    c.setTitle('Mesh Repeater 2.0 - сборка и размеры по native STEP')
    c.setAuthor('Mesh Repeater 2.0 engineering project')

    def text(x, y, value, size=12, bold=False, color='#243444'):
        c.setFillColor(HexColor(color))
        c.setFont('ArialBold' if bold else 'Arial', size)
        c.drawString(x, y, value.replace('—', '-').replace('–', '-'))

    def title(value, number):
        text(35, height-39, value, 23, True)
        c.setStrokeColor(HexColor('#d4dce3'))
        c.line(35, height-51, width-35, height-51)
        text(35, 19, 'Mesh Repeater 2.0 | native STEP + номинальная цепочка крепежа | '+date.today().strftime('%d.%m.%Y'), 10, color='#526273')
        text(width-80, 19, f'{number}/4', 10, color='#526273')

    def picture(name, x, y, w, h):
        image = ImageReader(str(DOCS/name))
        iw, ih = image.getSize()
        scale = min(w/iw, h/ih)
        c.drawImage(image, x+(w-iw*scale)/2, y+(h-ih*scale)/2,
                    width=iw*scale, height=ih*scale, mask='auto')

    def lines(x, y, values, size=12, leading=19):
        for line in values:
            text(x, y, line, size)
            y -= leading
        return y

    def metric(x, y, name, value):
        text(x, y, name, 12)
        text(x+246, y, f'{value:.3f} мм', 12, True)
        return y-26

    assembled = report['artifacts']['MeshRepeater2_assembly']
    gaps = assembled['vertical_envelope_clearances']
    clearances = assembled['hardware_to_component_clearances']
    minimum = min(row['proven_minimum_mm'] for row in clearances)
    bbox = assembled['bbox_mm']
    stack = contract['stack']

    title('Сборка - настоящая геометрия экспортов KiCad', 1)
    picture('MeshRepeater2_assembly_native_3D.png', 35, 128, 735, 640)
    x, y = 801, 742
    text(x, y, 'Габариты и зазоры модели', 16, True); y -= 35
    y = metric(x, y, 'POWER над платой', gaps['power_max_native_component_height_mm'])
    y = metric(x, y, 'POWER до экрана', gaps['power_envelope_to_screen_mm'])
    y = metric(x, y, 'LOGIC под платой', gaps['logic_max_native_component_height_mm'])
    y = metric(x, y, 'LOGIC до экрана', gaps['logic_envelope_to_screen_mm'])
    y = metric(x, y, 'Стойка до компонентов, ≥', minimum)
    y = metric(x, y, 'Полная высота модели', bbox[5]-bbox[2])
    y -= 15
    text(x, y, 'Номинальная размерная цепь', 16, True); y -= 33
    y = metric(x, y, 'Зазор POWER - экран', stack['lower_face_clearance'])
    y = metric(x, y, 'Зазор экран - LOGIC', stack['upper_face_clearance'])
    y = metric(x, y, 'Внешние поверхности PCB', stack['outer_pcb_surface_height'])
    y -= 17
    y = lines(x, y, [
        'Все три PCB: 90 × 60 мм.',
        ('Полный CAD: '+' × '.join(f'{bbox[i+3]-bbox[i]:.2f}'.replace('.',',') for i in range(3))+' мм.'),
        'Размеры выше не включают внешний кабель.',
        'С петлёй Y≤−23: по Y ориентировочно',
        'не менее 90,21 мм; проверить на образце.',
        'Стойки M3: 18 мм снизу, 15 мм сверху.',
        'Отверстия Ø3,2; контакты GND Ø6 мм.',
        'Центры: (3,5;3,5), (86,5;3,5),',
        '(3,5;56,5), (86,5;56,5) мм.',
        'Маска отсутствует в STEP.',
        'Экран: 1,475 FR4 + 0,035 Cu = 1,510 мм.',
    ], 12)
    lines(45, 102, [
        'Зазоры вычислены из native STEP. Модели Nice!Nano, модема и SMA остаются приближенными.',
        'Нулевые пересечения плат подтверждены геометрией моделей; реальные модули и сопряжения требуют образца.',
        'В STEP LOGIC возможен пропуск двух мелких контуров меди; нативная плата проходит DRC. См. отчёт экспорта.',
    ], 12, 20)
    c.showPage()

    title('Размерная цепь крепежа - номинальные значения', 2)
    picture('MeshRepeater2_stack_dimensions.png', 35, 55, width-70, height-115)
    c.showPage()

    title('Разнесённая сборка - вид со стороны компонентов LOGIC', 3)
    picture('MeshRepeater2_exploded_below_native_3D.png', 35, 99, 735, 675)
    x, y = 801, 745
    text(x, y, 'Состояние проверки', 16, True); y -= 34
    y = lines(x, y, [
        'POWER, SHIELD, LOGIC: объём',
        'взаимных пересечений равен нулю.',
        'Стойки проверены окружностью',
        'описанного шестигранника 5,5 мм.',
        'Это исключает зависимость от угла',
        'его поворота около оси винта.',
        'Сопряжение резьбы не моделируется.',
        'Кабель и ответные IDC не показаны.',
        'J10 / ISP обслуживается при разборке.',
    ], 12)
    y -= 16
    text(x, y, 'Исходные STEP, SHA-256', 14, True); y -= 29
    for name in ('POWER','SHIELD','LOGIC'):
        text(x, y, name, 12, True); y -= 18
        digest = report['inputs'][name]['sha256']
        c.setFont('Arial', 8.6); c.setFillColor(HexColor('#243444'))
        c.drawString(x, y, digest); y -= 30
    y -= 6
    lines(x, y, [
        'Полные native PCB SHA и результаты',
        'зазоров: assembly_geometry_report.json.',
        'PDF и PNG связаны с теми же исходниками.',
        'Замена этих исходников требует',
        'повторного экспорта и пересборки.',
    ], 12)
    lines(45, 69, ['Физический контроль: размеры Type-C/модулей, глубина резьбы, зацепление,',
                   'зажим металлических шайб, посадка IDC и свободная прокладка кабеля.'], 12)
    c.showPage()

    title('Межплатный кабель - размерное предложение', 4)
    picture('MeshRepeater2_harness_routing_plan.png', 35, 40, width-70, height-97)
    c.showPage()
    c.save()
    reader = PdfReader(str(OUTPUT))
    assert len(reader.pages) == 4
    assert all('Mesh Repeater 2.0' in page.extract_text() for page in reader.pages)
    audit = {'pdf':str(OUTPUT.relative_to(ROOT)), 'pdf_sha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
             'pages':len(reader.pages), 'native_step_inputs':report['inputs'],
             'assembly_report_sha256':hashlib.sha256((DOCS/'assembly_geometry_report.json').read_bytes()).hexdigest(),
             'qualification':'A native CAD review and nominal mechanical drawing; actual hardware fit is not qualified.'}
    (DOCS/'assembly_pdf_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__ == '__main__':
    main()
