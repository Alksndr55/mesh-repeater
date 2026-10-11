"""Render the actual FreeCAD tessellation, with an orthographic depth buffer.

This script reads only v2 mesh outputs. It does not draw guessed components,
modify an image, or replace the source CAD. Colors are illustrative.
Run with the bundled Python runtime (NumPy and Pillow).
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import json
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]


def render(source, destination, elevation, caption):
    with gzip.open(source, 'rt', encoding='utf-8') as stream:
        data = json.load(stream)
    if hashlib.sha256((ROOT/'docs/mechanical_selection.json').read_bytes()).hexdigest()!=data['mechanical_contract_sha256']:
        raise ValueError('Mechanical stack changed after CAD tessellation; rebuild the assembly first.')
    for name,record in data['verified_native_inputs'].items():
        if hashlib.sha256((ROOT/record['path']).read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError(f'{name}: STEP changed after CAD tessellation; rebuild the assembly first.')
        pcb=record['verified_pcb_source']
        if hashlib.sha256((ROOT/pcb['path']).read_bytes()).hexdigest()!=pcb['sha256']:
            raise ValueError(f'{name}: native PCB changed after CAD tessellation; export and rebuild first.')
    objects = data['objects']
    azimuth = -50 * math.pi / 180
    elev = elevation * math.pi / 180
    view = np.array([math.cos(elev) * math.cos(azimuth), math.cos(elev) * math.sin(azimuth), math.sin(elev)])
    axis_u = np.array([-math.sin(azimuth), math.cos(azimuth), 0])
    axis_v = np.cross(view, axis_u)
    basis = np.stack((axis_u, -axis_v, view), axis=1)
    projected = []
    for obj in objects:
        xyz = np.asarray(obj['vertices'], dtype=np.float64)
        projected.append(xyz @ basis)
    all_vertices = np.concatenate(projected)
    x0, y0 = all_vertices[:, :2].min(axis=0)
    x1, y1 = all_vertices[:, :2].max(axis=0)
    width, height = 1600, 1300
    available_width, available_height = width - 110, height - 220
    scale = min(available_width / (x1 - x0), available_height / (y1 - y0))
    origin = np.array([(width - (x1 - x0) * scale) / 2 - x0 * scale,
                       110 + (available_height - (y1 - y0) * scale) / 2 - y0 * scale])
    canvas = np.full((height, width, 3), 249, dtype=np.uint8)
    depth = np.full((height, width), -np.inf, dtype=np.float32)
    light = np.array([.25, -.35, .90]); light /= np.linalg.norm(light)
    triangle_count = 0
    for obj, projection in zip(objects, projected):
        xyz = np.asarray(obj['vertices'], dtype=np.float64)
        pp = projection.copy(); pp[:, :2] = pp[:, :2] * scale + origin
        for face in obj['triangles']:
            a, b, c = pp[list(face)]
            left = max(0, int(math.floor(min(a[0], b[0], c[0]))))
            right = min(width - 1, int(math.ceil(max(a[0], b[0], c[0]))))
            top = max(0, int(math.floor(min(a[1], b[1], c[1]))))
            bottom = min(height - 1, int(math.ceil(max(a[1], b[1], c[1]))))
            if right < left or bottom < top:
                continue
            denom = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(denom) < 1e-8:
                continue
            xx = np.arange(left, right + 1, dtype=np.float64)[None, :] + .5
            yy = np.arange(top, bottom + 1, dtype=np.float64)[:, None] + .5
            wa = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / denom
            wb = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / denom
            wc = 1 - wa - wb
            zz = wa * a[2] + wb * b[2] + wc * c[2]
            old_depth = depth[top:bottom + 1, left:right + 1]
            visible = (wa >= -1e-7) & (wb >= -1e-7) & (wc >= -1e-7) & (zz > old_depth)
            if not visible.any():
                continue
            va, vb, vc = xyz[list(face)]
            normal = np.cross(vb - va, vc - va)
            norm = np.linalg.norm(normal)
            illumination = .55 + .45 * abs(np.dot(normal / norm, light)) if norm > 1e-12 else .7
            color = np.clip(np.asarray(obj['color']) * 255 * illumination, 0, 255).astype(np.uint8)
            old_depth[visible] = zz[visible]
            canvas[top:bottom + 1, left:right + 1][visible] = color
            triangle_count += 1
    occupied = np.isfinite(depth)
    outline = occupied & (~np.roll(occupied, 1, 0) | ~np.roll(occupied, -1, 0) | ~np.roll(occupied, 1, 1) | ~np.roll(occupied, -1, 1))
    canvas[outline] = (50, 58, 66)
    image = Image.fromarray(canvas)
    draw = ImageDraw.Draw(image)
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    title_font = ImageFont.truetype(str(font_path), 32)
    small_font = ImageFont.truetype(str(font_path), 21)
    draw.text((45, 25), caption, font=title_font, fill=(25, 35, 47))
    for x,color,label in [(45,(20,97,61),'POWER · компоненты вверх'),
                          (580,(168,102,41),'SHIELD · медь вниз'),
                          (1080,(23,71,133),'LOGIC · компоненты вниз')]:
        draw.rectangle((x,76,x+22,94),fill=color)
        draw.text((x+32,72),label,font=small_font,fill=(55,65,75))
    draw.text((45, height - 78), 'Геометрия: native STEP плат и габариты крепежа. Цвета условные; кабель и ответные части не показаны.', font=small_font, fill=(55, 65, 75))
    draw.text((45, height - 43), 'Резьба, действительные модули и сопряжение кабеля требуют проверки на образце.', font=small_font, fill=(55, 65, 75))
    image.save(destination)
    return {'source':str(source.relative_to(ROOT)), 'image':str(destination.relative_to(ROOT)), 'triangles_drawn':triangle_count,
            'image_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'verified_native_inputs':data['verified_native_inputs'],
            'view_elevation_deg':elevation,'geometry':'Native CAD tessellation, not an invented component rendering.'}


def stack_drawing(directory):
    contract = json.loads((ROOT / 'docs/mechanical_selection.json').read_text(encoding='utf-8'))
    st = contract['stack']
    x0, x1 = 130, 1030
    ybase, scale = 680, 12
    yy = lambda z: ybase - z * scale
    elements = []
    preview=Image.new('RGB',(1450,920),'white')
    drawing=ImageDraw.Draw(preview)
    fonts={size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size) for size in (17,18,19,27)}
    def text(x, y, value, size=18, anchor='start', color='#263746'):
        elements.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{color}">{value}</text>')
        px=x-drawing.textlength(value,font=fonts[size])/2 if anchor=='middle' else x
        drawing.text((px,y-size),value,font=fonts[size],fill=color)
    def rect(x, z, w, thickness, fill):
        elements.append(f'<rect x="{x}" y="{yy(z+thickness)}" width="{w}" height="{thickness*scale}" fill="{fill}" stroke="#1f2b33" stroke-width="1"/>')
        drawing.rectangle((x,yy(z+thickness),x+w,yy(z)),fill=fill,outline='#1f2b33')
    def dimension(x, z1, z2, label):
        elements.append(f'<path d="M{x},{yy(z1)} H{x+18} M{x},{yy(z2)} H{x+18} M{x+9},{yy(z1)} V{yy(z2)}" fill="none" stroke="#536373"/>')
        drawing.line((x,yy(z1),x+18,yy(z1)),fill='#536373')
        drawing.line((x,yy(z2),x+18,yy(z2)),fill='#536373')
        drawing.line((x+9,yy(z1),x+9,yy(z2)),fill='#536373')
        text(x+23,(yy(z1)+yy(z2))/2+6,label,17)
    for x in (x0+35,x1-35):
        rect(x-27.5,st['power_pcb_top_z'],55,st['lower_stand_body'],'#cbbd79')
        rect(x-27.5,22.04,55,st['upper_stand_body'],'#c7c9cb')
        for z in(-.5,19.52,21.54,37.04,39.06):rect(x-30,z,60,.5,'#dedfe0')
        rect(x-27.5,-2.9,55,2.4,'#b6b8ba')
        rect(x-15,-3.48,30,.58,'#b6b8ba')
        rect(x-30,39.56,60,2.52,'#b6b8ba')
    rect(x0,0,x1-x0,1.52,'#3e8766')
    rect(x0,st['shield_bottom_z'],x1-x0,1.52,'#a59a6c')
    rect(x0,st['shield_bottom_z'],x1-x0,.035,'#b46e35')
    rect(x0,st['logic_component_face_z'],x1-x0,1.52,'#4476a5')
    text(45,45,'Mesh Repeater 2.0 — номинальная размерная цепь',27)
    text(45,77,'Платы 90×60 мм; толщина CAD 1,52 мм; экран медью вниз.',18)
    text(x0+115,yy(5),'POWER: компоненты вверх; нижняя сторона снаружи',18)
    text(x0+115,yy(23.5),'SHIELD: сплошная медь на нижней стороне',18)
    text(x0+115,yy(40.7),'LOGIC: компоненты вниз; B.SilkS снаружи',18)
    text(x0+115,yy(11.5),'Стойки RUICHI PCHSN-18, M3, тело 18 мм',18)
    text(x0+115,yy(31.5),'Стойки Connfly H-L1500…, M3, тело 15 мм',18)
    dimension(1080,1.52,20.02,'18,50 мм')
    dimension(1080,21.54,37.54,'16,00 мм')
    dimension(1230,0,39.06,'39,06 мм')
    elements.append(f'<path d="M{x0},735 V755 M{x1},735 V755 M{x0},745 H{x1}" fill="none" stroke="#536373"/>')
    drawing.line((x0,735,x0,755),fill='#536373');drawing.line((x1,735,x1,755),fill='#536373');drawing.line((x0,745,x1,745),fill='#536373')
    text((x0+x1)/2,773,'90,00 мм',19,'middle')
    text(45,815,'Крепёж: 4 стойки 18 мм + 4 стойки 15 мм; 20 шайб DIN433 3,2×6×0,5 мм; 4 гайки M3; 4 винта M3×6.',18)
    text(45,848,'От гайки до головки: 44,98 мм. Полный габарит STEP с выступающей нижней шпилькой: 45,56 мм.',18)
    text(45,881,'Рамка SH1 удалена. Основной возврат тока идёт через межплатный GND, крепёж служит для экранирования.',18)
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1450" height="920" viewBox="0 0 1450 920"><rect width="1450" height="920" fill="white"/><g font-family="Arial, sans-serif">'+''.join(elements)+'</g></svg>'
    path=directory/'MeshRepeater2_stack_dimensions.svg'
    path.write_text(svg,encoding='utf-8')
    preview.save(directory/'MeshRepeater2_stack_dimensions.png')
    return path


def harness_drawing(directory):
    """A dimensioned route proposal, deliberately separate from exact native 3D."""
    width,height=1500,1000
    canvas=Image.new('RGB',(width,height),'white');draw=ImageDraw.Draw(canvas)
    fonts={size:ImageFont.truetype('C:/Windows/Fonts/arial.ttf',size) for size in(17,18,22,27)}
    elements=[]
    xx=lambda y:100+(y+30)*10
    yy=lambda z:760-z*12
    def text(x,y,value,size=18,color='#263746'):
        draw.text((x,y-size),value,font=fonts[size],fill=color)
        elements.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}">{value}</text>')
    def rect(y0,z0,y1,z1,color,outline='#52606b'):
        a,b,c,d=xx(y0),yy(z1),xx(y1),yy(z0)
        draw.rectangle((a,b,c,d),fill=color,outline=outline,width=1)
        elements.append(f'<rect x="{a}" y="{b}" width="{c-a}" height="{d-b}" fill="{color}" stroke="{outline}"/>')
    def line(points,color='#536373',stroke=2,dashed=False):
        xy=[(xx(y),yy(z)) for y,z in points]
        draw.line(xy,fill=color,width=stroke)
        path=' '.join(('M'if i==0 else'L')+f'{x},{y}'for i,(x,y)in enumerate(xy))
        dash=' stroke-dasharray="6 5"'if dashed else''
        elements.append(f'<path d="{path}" fill="none" stroke="{color}" stroke-width="{stroke}"{dash}/>')
    text(45,45,'Mesh Repeater 2.0 — проектный маршрут межплатного кабеля',27)
    text(45,77,'Боковое сечение около X=70,5 мм; северная кромка всех плат — физическая Y=0.',18)
    text(45,107,'Положение кабеля условное: размер ответной сборки и глубина вставки подтверждаются образцом.',18)
    rect(0,0,60,1.52,'#3e8766');rect(0,20.02,60,21.54,'#a59a6c');rect(0,37.54,60,39.06,'#4476a5')
    rect(-2.8,1.52,6,10.62,'#8b949e');rect(-2.8,28.44,6,37.54,'#8b949e')
    text(xx(9),yy(5),'J101 POWER: native (64,15;11), 90°',18)
    text(xx(9),yy(31),'J201 LOGIC: native (76,85;49), 270°',18)
    text(xx(20),yy(22.5),'SHIELD без вырезов',18)
    text(xx(7),yy(39.8),'LOGIC — компоненты вниз',18)
    text(xx(7),yy(-2.8),'POWER — компоненты вверх',18)
    route=[(-2.8,6.07),(-18,6.07)]
    route += [(-18-5*math.sin(i*math.pi/2/20),11.07-5*math.cos(i*math.pi/2/20))for i in range(1,21)]
    route += [(-23,27.99)]
    route += [(-18-5*math.cos(i*math.pi/2/20),27.99+5*math.sin(i*math.pi/2/20))for i in range(1,21)]
    route += [(-2.8,32.99)]
    line(route,'#2573ae',5)
    line([(0,-1.5),(0,41.5)],'#b5bec5',1,True)
    text(200,yy(22),'Петля кабеля',18,'#2573ae')
    text(200,yy(19),'Y ≤ −23 мм',18,'#2573ae')
    text(200,yy(16),'изгиб ≥5 мм',18,'#2573ae')
    text(1040,195,'Кабель строго 1:1',22)
    for y,value in[(230,'1/3/5/7: FILTER_OUT'),(258,'2/4/6/8/10/12: GND'),(286,'9: BAT (sense)'),(314,'11: MODE'),(360,'SYS_3V3 отсутствует'),(410,'Полуоборот шлейфа'),(438,'или 1:1 жгут проводов'),(480,'Длина 120 мм'),(508,'предварительная')]:text(1040,y,value,18)
    text(45,865,'Контроль на образце: посадка обеих IDC, глубина контакта, strain-relief, отсутствие натяжения и прозвонка всех 12 жил.',18)
    text(45,898,'13,3 мм в DS1016 — размер отдельной Top cover, а не подтверждённая длина окончательной ответной сборки.',18)
    text(45,931,'Выбранный шлейф Connfly DS1057 имеет паспорт −20…+70°C. Более низкая температура требует другого кабеля.',18)
    svg='<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1000" viewBox="0 0 1500 1000"><rect width="1500" height="1000" fill="white"/><g font-family="Arial, sans-serif">'+''.join(elements)+'</g></svg>'
    path=directory/'MeshRepeater2_harness_routing_plan.svg';path.write_text(svg,encoding='utf-8')
    canvas.save(directory/'MeshRepeater2_harness_routing_plan.png')
    return path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,default=ROOT/'docs/mechanics')
    args=parser.parse_args()
    directory=args.directory.resolve()
    if not directory.is_relative_to(ROOT):raise ValueError('All outputs must stay inside v2.')
    directory.mkdir(parents=True,exist_ok=True)
    outputs=[]
    for stem,elevation,caption in [('assembly',18,'Mesh Repeater 2.0 — сборка'),('exploded',30,'Mesh Repeater 2.0 — разнесённый вид'),('exploded',-28,'Mesh Repeater 2.0 — разнесённый вид снизу')]:
        mesh=directory/f'MeshRepeater2_{stem}_native_mesh.json.gz'
        if mesh.is_file():
            suffix='_below' if elevation<0 else''
            outputs.append(render(mesh,directory/f'MeshRepeater2_{stem}{suffix}_native_3D.png',elevation,caption))
    dimensions=stack_drawing(directory)
    harness=harness_drawing(directory)
    report={'renders':outputs,'dimensions':str(dimensions.relative_to(ROOT)), 'harness_plan':str(harness.relative_to(ROOT)), 'colors':'Illustrative. Source STEP geometry is retained.'}
    (directory/'native_render_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
