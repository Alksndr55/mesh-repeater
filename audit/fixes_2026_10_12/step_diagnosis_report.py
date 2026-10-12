"""Record bounded STEP-export diagnosis from independent control exports."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def log_info(path):
 text=path.read_text(encoding='utf-8-sig')
 if '\x00' in text:text=path.read_text(encoding='utf-16')
 boxes=re.findall(r'z:\s*([\d.]+); bounding box: x0:\s*([\d.]+); y0:\s*([\d.]+); x1:\s*([\d.]+); y1:\s*([\d.]+)',text)
 return {'path':str(path.relative_to(ROOT)),'sha256':sha(path),'wire_warning_count':text.count('Wire self-interference check failed'),'boxes_z_xy_mm':[list(map(float,b)) for b in boxes],'missing_model_count':text.count('Could not add 3D model'),'step_created':'STEP file' in text and 'created.' in text}
native=json.loads((OUT/'step_diagnosis_native.json').read_text(encoding='utf-8'))
brep=json.loads((OUT/'step_diagnosis_brep.json').read_text(encoding='utf-8'))
inputs={'current':log_info(ROOT/'output/LOGIC/MeshRepeater2_Logic_step_export.log'),'before':log_info(OUT/'step_diagnosis_before.log'),'without_zones':log_info(OUT/'step_diagnosis_nozones.log'),'zones_only':log_info(OUT/'step_diagnosis_zones_only.log')}
assert inputs['current']['wire_warning_count']==inputs['before']['wire_warning_count']==inputs['zones_only']['wire_warning_count']==4
assert inputs['without_zones']['wire_warning_count']==0
assert all(max(abs(a-b) for a,b in zip(now,old))<.01 for now,old in zip(inputs['current']['boxes_z_xy_mm'],inputs['before']['boxes_z_xy_mm']))
assert native['native_unchanged'] and brep['source_unchanged'] and brep['valid_compound'] and not brep['invalid_solid_indices']
assert sha(ROOT/native['input'])==native['sha256'] and sha(ROOT/brep['input'])==brep['sha256']
assert all(not r['polygon_self_intersecting'] and all(p['outline']['closed'] for p in r['regions']) for r in native['clipped_native_filled_area_at_warning_boxes'])
result={'status':'PASS_WITH_BOUNDED_STEP_COPPER_FIDELITY_LIMITATION','native_pcb_sha256':native['sha256'],'step_sha256':brep['sha256'],'controls':inputs,'native_local_geometry_report':{'path':str((OUT/'step_diagnosis_native.json').relative_to(ROOT)),'sha256':sha(OUT/'step_diagnosis_native.json')},'STEP_BRep_report':{'path':str((OUT/'step_diagnosis_brep.json').relative_to(ROOT)),'sha256':sha(OUT/'step_diagnosis_brep.json')},'diagnosis':'Four warnings represent two unique small copper-contour regions. Warnings predate current routing corrections and depend on exporting zones. Independent local Boolean-clipped native F.Cu GND regions are closed and non-self-intersecting. The delivered STEP compound and all 964 solids are BRep-valid. This does not prove faithful export of those two source copper contours.','likely_cause':'The warning boxes coincide with adjacent GND_TOP / RF_CPW_GND_1 boundaries whose points differ by approximately one 1nm native grid unit. An OCC contour tolerance/rounding issue is consistent with these observations; the exact internal skipped contour was not recovered.','limitation':'Full STEP is a mechanical/visual derivative, not an exact manufacturing-copper source. Preserve exporter warnings; use saved native board/verified native plots for copper. Re-export without --include-zones is warning-free if a clean mechanical-only STEP is required, explicitly recording omitted zones. Do not alter valid native routing solely to hide this export limitation.','primary_source':'https://gitlab.com/kicad/code/kicad/-/raw/10.0.6/pcbnew/exporters/step/step_pcb_model.cpp','source_interpretation':'MakeShapes checks OCC wire validity, nullifies an invalid wire and may skip an outline or a hole. Success exit does not guarantee that every source contour was exported.','scope':'No native boards, models, canonical exports or root scripts changed by this diagnosis. Before-control model lookup fails because its scratch KIPRJMOD differs; that control is used only for copper-warning comparison.'}
(OUT/'step_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
md=f'''# Проверка предупреждений STEP, 12 октября 2026

Результат: ограничение точности отображения меди в STEP. В нативную плату изменений не внесено.

Текущая LOGIC PCB: `{native['sha256']}`. Текущий STEP: `{brep['sha256']}`.

- Полный текущий экспорт: 4 предупреждения, 2 уникальные области около C22/C23. Их размеры приблизительно 0,149×0,083 и 0,201×0,115 мм, z=1,43 мм.
- Экспорт прежней `routing_before.kicad_pcb` воспроизводит те же 2 области. Поэтому предупреждения не являются регрессией новых исправлений трассировки. У этой временной копии не найдены локальные модели компонентов; сравнение относится только к предупреждениям меди.
- Текущая плата, дорожки без полигонов: 0 предупреждений. Текущая плата, полигоны без компонентов: те же 4 предупреждения. Ранее изменение допуска 0,01→0,001 мм предупреждения не устранило.
- Нативная сохранённая заливка в обеих областях отдельно для GND_TOP и RF_CPW_GND_1 проверена пересечением с локальным прямоугольником, с запасом 0,01 мм. Все 4 полученных плоских области замкнуты, без самопересечения и отверстий. Это локальная проверка; общие DRC/связность подтверждены отдельными итоговыми проверками платы.
- FreeCAD/OCC: весь текущий STEP валиден; из {brep['exported_solid_count']} экспортированных тел невалидных 0. Проверка валидности уже созданных тел не доказывает полноту экспорта исходной меди.

Области предупреждений совпадают с границей двух земляных полигонов, где некоторые координаты отличаются на 0,000001 мм — один шаг нативной сетки. Это согласуется с ограничением OCC при построении контура с почти совпадающими границами. Точный внутренний пропущенный контур экспортера отдельно не восстановлен.

В [исходнике KiCad 10.0.6](https://gitlab.com/kicad/code/kicad/-/raw/10.0.6/pcbnew/exporters/step/step_pcb_model.cpp) `MakeShapes` аннулирует невалидный OCC-контур и затем может пропустить контур или отверстие. Поэтому успешное создание STEP не означает абсолютного совпадения меди с платой.

Сохранить полный STEP вместе с предупреждениями и указать ограничение: он пригоден для компоновки и вида компонентов, но не является источником производственной геометрии меди. Для дорожек и полигонов использовать нативную KiCad PCB и проверенные нативные изображения. Если нужен STEP без предупреждений, подтверждённый обход — механический экспорт без `--include-zones`, с явной отметкой об отсутствии полигонов. Изменять корректную нативную разводку ради сокрытия предупреждений не требуется.

Доказательства: [машинный итог](step_diagnosis.json), [локальная геометрия](step_diagnosis_native.json), [BRep](step_diagnosis_brep.json), [прежний экспорт](step_diagnosis_before.log), [без полигонов](step_diagnosis_nozones.log), [только полигоны](step_diagnosis_zones_only.log).
'''
(OUT/'step_diagnosis_RU.md').write_text(md,encoding='utf-8')
print(json.dumps({'status':result['status'],'native':native['sha256'],'STEP':brep['sha256'],'valid_solids':brep['exported_solid_count']}))
