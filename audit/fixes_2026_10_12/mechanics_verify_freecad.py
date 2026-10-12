"""Fresh model/mate-envelope proof for M-01/M-02; no native board writes."""
from pathlib import Path
import hashlib
import json
import math
import shutil

import FreeCAD as App
import Part

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def bounds(shape):
    b=shape.BoundBox
    return [round(v,6) for v in (b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax)]
checks=[]
for project in ('MeshRepeater2_Power','MeshRepeater2_Logic'):
    folder=ROOT/'design'/project/'3dmodels'
    for name in ('JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal',
                 'KLS_XH_L_KLS1_2_50_04_R_Horizontal',
                 'Connfly_DS1013_12RSIB_B_0_Horizontal',
                 'Connfly_DS1022_1x02RUF11_B_Horizontal',
                 'SW_TE_1825027_2_Side',
                 'Connfly_DS1022_1x04RUF11_B_Horizontal'):
        path=folder/(name+'.step');shape=Part.Shape();shape.read(str(path))
        assert shape.isValid() and not shape.isNull(),path
        item={'model':name,'project':project,'valid':True,'bbox':bounds(shape),
              'path':str(path.relative_to(ROOT)).replace('\\','/'),
              'sha256':sha(path),'checked':'2026-10-12',
              'qualification':'simplified dimension envelope; not mechanical mating proof'}
        if name=='SW_TE_1825027_2_Side':
            assert abs(shape.BoundBox.XLength-8.41)<1e-6
            assert abs(shape.BoundBox.ZLength-(7.01+3.51))<1e-6
            item['bracket_width_mm']=8.41
            item['fix']='M-02: expands the nominal bracket outer envelope by 0.375 mm on each side.'
        checks.append(item)
modelchecks=ROOT/'docs/mechanical_model_checks.json'
before=OUT/'mechanical_model_checks.before.json'
assert not before.exists();shutil.copyfile(modelchecks,before)
modelchecks.write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Maximum nominal+general-tolerance housing dimensions from Connfly DS1071:
# B=10.16±0.25; width=2.54±0.25; axial length=14.00±0.25 mm.
# Local X follows the DS1022 pin direction; Y is the STEP reflection of PCB Y.
# Seating front x=1.50 is an explicit proposed position, not a manufacturer's
# unstated mated stop. This solid is deliberately a conservative outer envelope.
mate=Part.makeBox(14.25,10.41,2.79,App.Vector(1.50,-9.015,4.355))
assert mate.isValid()
dest=ROOT/'docs/mechanics/Connfly_DS1071_SCB01x4_Mated_Envelope.step'
doc=App.newDocument('Connfly_DS1071_SCB01x4_Mate_Envelope')
obj=doc.addObject('Part::Feature','MaxToleranceHousingEnvelope');obj.Shape=mate
try:obj.ViewObject.ShapeColor=(.12,.12,.14)
except Exception:pass
doc.recompute();Part.export([obj],str(dest));App.closeDocument(doc.Name)
selection=json.loads((ROOT/'docs/mechanical_selection.json').read_text(encoding='utf-8'))
st=selection['stack'];placements=selection['mechanical_fixes']['mate_placements_native']
fit=[]
for ref,entry in placements.items():
    s=mate.copy()
    x,y=entry['origin_mm']
    s.rotate(App.Vector(),App.Vector(0,0,1),entry['rotation_kicad_degrees'])
    s.translate(App.Vector(x,-y,0))
    s.rotate(App.Vector(),App.Vector(1,0,0),180)
    s.translate(App.Vector(0,-60,st['logic_component_face_z']))
    # Arbitrary rotated M3 stand conservatively bounded by its circumscribed
    # cylinder. The whole top stand, not just a washer, is checked.
    distances=[]
    for hx,hy in selection['mounting']['centres']:
        stand=Part.makeCylinder(5.5/math.sqrt(3),15,
            App.Vector(hx,-hy,st['upper_stand_bottom_z']))
        distances.append({'mount':[hx,hy],'clearance_mm':round(s.distToShape(stand)[0],6)})
        assert s.common(stand).Volume<1e-8,(ref,hx,hy)
    screen_clearance=s.BoundBox.ZMin-st['shield_top_z']
    board_face_clearance=st['logic_component_face_z']-s.BoundBox.ZMax
    assert screen_clearance>8 and board_face_clearance>4
    motion=s.copy()
    sign=1 if ref=='J3'else-1
    motion.translate(App.Vector(sign*7,0,0))
    fit.append({'reference':ref,'native_origin_mm':[x,y],
                'native_angle_degrees':entry['rotation_kicad_degrees'],
                'installed_max_envelope_world_CAD_bbox_mm':bounds(s),
                'screen_nominal_plane_clearance_mm':round(screen_clearance,6),
                'logic_component_face_clearance_mm':round(board_face_clearance,6),
                'stand_cylinder_clearances':distances,
                'minimum_stand_clearance_mm':min(d['clearance_mm']for d in distances),
                'withdrawal_target_mm':7,
                'withdrawn_world_CAD_bbox_mm':bounds(motion),
                'notes':'Envelope lies outside the two PCB/shield planes and clears all upper M3 stands. Actual header engagement and contacts intentionally are not qualified by this outer envelope. Wires and housing stop require hardware qualification.'})
result={'date':'2026-10-12','model_checks':checks,
        'mate_model':{'path':str(dest.relative_to(ROOT)).replace('\\','/'),
                      'sha256':sha(dest),'local_STEP_bbox_mm':bounds(mate),
                      'source':'https://en.connfly.com/static/upload/file/pdf/DS1071.pdf',
                      'dimensions_max_mm':[10.41,2.79,14.25]},
        'mate_fit_nominal_stack':fit,
        'hardware_mating_proven':False,
        'unchanged_footprints_proof':'mechanics.footprint_checks.json'}
(OUT/'mechanics.models.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'switch_width_mm':8.41,
                  'switch_local_model_sha256':[c['sha256']for c in checks if c['model']=='SW_TE_1825027_2_Side'],
                  'mate_model':result['mate_model'],
                  'mate_min_stand_clearance':{c['reference']:c['minimum_stand_clearance_mm']for c in fit}},ensure_ascii=False))
