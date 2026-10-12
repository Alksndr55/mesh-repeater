"""Compose exact exported PCB STEP geometry into the proposed v2 stack.

Run with FreeCAD/bin/python.exe. No PCB or schematic edits.
Hardware models are outer envelopes, not thread/mating qualification.
External cable/female plugs are deliberately not fabricated as a false fit proof.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import gzip
from datetime import date

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--power',type=Path,required=True)
    p.add_argument('--logic',type=Path,required=True)
    p.add_argument('--shield',type=Path,required=True)
    p.add_argument('--out',type=Path,default=ROOT/'docs/mechanics')
    p.add_argument('--mesh',action='store_true',help='Write exact CAD tessellation for the separate PNG renderer.')
    p.add_argument('--edge-svg',action='store_true',help='Also run the more expensive native CAD edge projection.')
    a=p.parse_args()
    for name in ('power','logic','shield','out'):
        setattr(a,name,getattr(a,name).resolve())
    for x in (a.power,a.logic,a.shield):
        if not x.resolve().is_relative_to(ROOT)or not x.is_file():raise ValueError(f'Missing v2 STEP: {x}')
    if not a.out.resolve().is_relative_to(ROOT):raise ValueError('Output must stay inside v2')
    a.out.mkdir(exist_ok=True,parents=True)
    import FreeCAD as App
    import Part
    import TechDraw
    contract=json.loads((ROOT/'docs/mechanical_selection.json').read_text(encoding='utf-8'))
    st=contract['stack'];holes=contract['mounting']['centres']
    inputs={};native={}
    for name,path in [('POWER',a.power),('SHIELD',a.shield),('LOGIC',a.logic)]:
        s=Part.Shape();s.read(str(path));assert not s.isNull(),name
        boards=[b for b in s.Solids if abs(b.BoundBox.XLength-90)<.05 and abs(b.BoundBox.YLength-60)<.05 and 1.0<b.BoundBox.ZLength<2.0]
        if not boards:raise ValueError(f'No 90×60 mm FR4 solid in {name}; refusing a baseline board or an incorrect origin.')
        board=max(boards,key=lambda b:b.Volume);bb=board.BoundBox
        # KiCad exports CADY=-nativePCB-Y. Normalize by the boardbody, not components.
        if name=='SHIELD':
            # Physical one-sided foil: its F.Cu outer face is the lower contact plane.
            foil=[solid for solid in s.Solids if .015<solid.BoundBox.ZLength<.06 and solid.BoundBox.ZMin>=bb.ZMax-.001]
            if not foil:raise ValueError('SHIELD STEP has no front foil solid.')
            f_outer=max(solid.BoundBox.ZMax for solid in foil)
            physical_thickness=f_outer-bb.ZMin
            if abs(physical_thickness-st['pcb_thickness'])>.03:
                raise ValueError(f'SHIELD: exported one-sided physical thickness {physical_thickness:.4f} mm does not match nominal {st["pcb_thickness"]:.4f}. Set an explicit single-copper stackup before assembly export.')
            z_anchor=f_outer
            anchoring_note='Front foil outer face anchored to the lower screen contact plane. Body plus single foil thickness measured from STEP.'
        else:
            # Full nominal PCB thickness includes mask and outer copper that STEP may omit.
            z_anchor=(bb.ZMin+bb.ZMax)/2+st['pcb_thickness']/2
            physical_thickness=None
            anchoring_note='Dielectric center plus half nominal PCB thickness defines the F outer plane. Native STEP component offset above copper is preserved; mask is not a STEP solid.'
        s.translate(App.Vector(-bb.XMin,-bb.YMax,-z_anchor))
        native[name]=s
        inputs[name]={'path':str(path.resolve().relative_to(ROOT)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'board_bbox':[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax],
                      'normalization':[-bb.XMin,-bb.YMax,-z_anchor],
                      'measured_dielectric_thickness':bb.ZLength,'nominal_total_pcb_thickness':st['pcb_thickness'],
                      'physical_screen_core_plus_foil_thickness':physical_thickness,'anchoring_note':anchoring_note}
        manifest_path=path.with_name(path.stem+'_exports.json')
        if manifest_path.is_file():
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            pcb_path=ROOT/manifest['pcb']
            pcb_digest=hashlib.sha256(pcb_path.read_bytes()).hexdigest()
            if pcb_digest!=manifest['sha256']:raise ValueError(f'{name}: native PCB changed after this STEP export.')
            record=next((r for r in manifest['artifacts']if Path(r['path']).name==path.name),None)
            if not record or record['sha256']!=inputs[name]['sha256']:raise ValueError(f'{name}: STEP hash does not match the export manifest.')
            inputs[name]['verified_pcb_source']={'path':manifest['pcb'],'sha256':pcb_digest,'export_manifest':str(manifest_path.relative_to(ROOT))}
        else:
            raise ValueError(f'{name}: export manifest is required to verify this STEP against the current native PCB.')

    def placed(name,extra):
        s=native[name].copy()
        if name=='POWER':s.translate(App.Vector(0,0,st['power_pcb_top_z']))
        else:
            s.rotate(App.Vector(0,0,0),App.Vector(1,0,0),180)
            z=st['shield_bottom_z']if name=='SHIELD'else st['logic_component_face_z']
            s.translate(App.Vector(0,-60,z+extra))
        return s

    def hex_body(x,y,z,length,flats=5.5):
        radius=flats/math.sqrt(3)
        # θ30 gives the assembly a consistent orientation of all hexagonal hardware.
        pts=[App.Vector(x+radius*math.cos(math.radians(30+60*i)),y+radius*math.sin(math.radians(30+60*i)),z)for i in range(6)]
        pts.append(pts[0]);return Part.Face(Part.makePolygon(pts)).extrude(App.Vector(0,0,length))

    def washer(x,y,z):
        return Part.makeCylinder(3,.5,App.Vector(x,y,z)).cut(Part.makeCylinder(1.6,.5,App.Vector(x,y,z)))

    reports={};assembled_shapes=None
    for exploded in (False,True):
        doc=App.newDocument('MeshRepeater2_'+('Exploded'if exploded else'Assembled'))
        pieces=[];piece_colors={}
        def add(label,shape,color):
            obj=doc.addObject('Part::Feature',label);obj.Label=label;obj.Shape=shape
            try:obj.ViewObject.ShapeColor=color
            except Exception:pass
            pieces.append(obj);piece_colors[label]=color;return obj
        extras={'POWER':0,'SHIELD':25 if exploded else 0,'LOGIC':50 if exploded else 0}
        boards={name:placed(name,extras[name])for name in ('POWER','SHIELD','LOGIC')}
        colors={'POWER':(.08,.38,.24),'SHIELD':(.66,.40,.16),'LOGIC':(.09,.28,.52)}
        for name,s in boards.items():add(name+'_native_PCB_export',s,colors[name])
        hardware=[]
        for idx,(x,ky)in enumerate(holes):
            y=-ky
            e1=extras['SHIELD'];e2=extras['LOGIC']
            low=hex_body(x,y,1.52,18).fuse(Part.makeCylinder(1.5,5,App.Vector(x,y,-3.48)))
            high=hex_body(x,y,22.04+e1,15).fuse(Part.makeCylinder(1.5,6,App.Vector(x,y,16.04+e1)))
            hardware.append(add(f'Lower18mm_standoff_{idx+1}_outer_envelope',low,(.70,.65,.38)))
            hardware.append(add(f'Upper15mm_standoff_{idx+1}_outer_envelope',high,(.72,.73,.76)))
            for n,z in enumerate([-.5,19.52+e1,21.54+e1,37.04+e2,39.06+e2]):
                hardware.append(add(f'Metal_DIN433_washer_{idx+1}_{n+1}',washer(x,y,z),(.73,.74,.77)))
            nut=hex_body(x,y,-2.9,2.4).cut(Part.makeCylinder(1.5,2.4,App.Vector(x,y,-2.9)))
            screw=Part.makeCylinder(1.5,6,App.Vector(x,y,33.56+e2)).fuse(Part.makeCylinder(3,2.52,App.Vector(x,y,39.56+e2)))
            hardware.append(add(f'M3_lower_nut_{idx+1}',nut,(.73,.74,.77)))
            hardware.append(add(f'M3x6_top_screw_{idx+1}_envelope',screw,(.73,.74,.77)))
        if not exploded:
            assembled_shapes=boards
            direct_vertical=(ROOT/'design/feature_ina219_vertical.json').is_file()
            # The declared long header intentionally crosses the middle board.
            # Its narrow XY envelope is excluded only from the conservative
            # vertical-gap summary; every solid remains in Boolean collisions.
            pass_window=(61.5,-13.2,79.6,-6.3)
            nonpassing=[];passing=[]
            for solid in boards['POWER'].Solids:
                sb=solid.BoundBox
                in_window=(pass_window[0]<=sb.XMin and sb.XMax<=pass_window[2] and pass_window[1]<=sb.YMin and sb.YMax<=pass_window[3])
                if direct_vertical and in_window and sb.ZMax>st['shield_bottom_z']:
                    passing.append(solid)
                else:nonpassing.append(solid)
            nonpassing_z=max(s.BoundBox.ZMax for s in nonpassing)
            vertical_clearances={
                'power_max_native_component_height_mm':boards['POWER'].BoundBox.ZMax-st['power_pcb_top_z'],
                'power_envelope_to_screen_mm':boards['SHIELD'].BoundBox.ZMin-boards['POWER'].BoundBox.ZMax,
                'logic_max_native_component_height_mm':st['logic_component_face_z']-boards['LOGIC'].BoundBox.ZMin,
                'logic_envelope_to_screen_mm':boards['LOGIC'].BoundBox.ZMin-boards['SHIELD'].BoundBox.ZMax,
                'power_nonpassing_envelope_to_screen_mm':boards['SHIELD'].BoundBox.ZMin-nonpassing_z,
                'intentional_header_passage':{'active':direct_vertical,'excluded_solids_from_gap_only':len(passing),'window_xy_mm':list(pass_window),'Boolean_collision_check_includes_all_solids':True},
                'note':'Long header pins cross the screen through declared NPTH holes; a negative whole-export gap is expected. Ordinary component clearance and full BRep intersections are checked separately. Undocumented NiceNano, SMA and modem models remain approximate.'}
            collisions=[]
            for na,nb in [('POWER','SHIELD'),('SHIELD','LOGIC'),('POWER','LOGIC')]:
                ba,bb=boards[na].BoundBox,boards[nb].BoundBox
                separated=(ba.XMax<=bb.XMin or bb.XMax<=ba.XMin or ba.YMax<=bb.YMin or bb.YMax<=ba.YMin or ba.ZMax<=bb.ZMin or bb.ZMax<=ba.ZMin)
                if separated:
                    volume=0.0
                    method='Disjoint axis-aligned bounding boxes prove no intersection.'
                else:
                    # The new long posts overlap the other exports' broad
                    # envelopes. Check every potentially touching solid pair,
                    # rather than Boolean thousands of distant copper solids.
                    left=[(solid,solid.BoundBox)for solid in boards[na].Solids]
                    right=[(solid,solid.BoundBox)for solid in boards[nb].Solids]
                    volume=0.;candidate_count=0
                    for sa,aa in left:
                        for sb,bb in right:
                            if aa.XMax<=bb.XMin or bb.XMax<=aa.XMin or aa.YMax<=bb.YMin or bb.YMax<=aa.YMin or aa.ZMax<=bb.ZMin or bb.ZMax<=aa.ZMin:continue
                            candidate_count+=1;common=sa.common(sb)
                            volume+=common.Volume if not common.isNull() else 0.
                    method=f'Native BRep Boolean of every overlapping solid pair ({candidate_count}); disjoint pairs rejected by bounding boxes. Volume sum is conservative if solids overlap internally.'
                collisions.append({'a':na,'b':nb,'intersecting_volume_mm3':volume,'pass':volume<1e-6,'method':method})
            hardware_clearances=[]
            for name in ('POWER','LOGIC'):
                plane=st['power_pcb_top_z'] if name=='POWER' else st['logic_component_face_z']
                component_solids=[(n,s)for n,s in enumerate(boards[name].Solids)if (s.BoundBox.ZMax>plane+.15 if name=='POWER' else s.BoundBox.ZMin<plane-.15)]
                for idx,(x,ky)in enumerate(holes):
                    y=-ky
                    # Rotating a circular circumscribed envelope bounds every hex angle.
                    start,height=(st['lower_stand_bottom_z'],18)if name=='POWER' else(st['upper_stand_bottom_z'],15)
                    hw=Part.makeCylinder(5.5/math.sqrt(3),height,App.Vector(x,y,start))
                    distances=[]
                    hb=hw.BoundBox
                    for n,solid in component_solids:
                        cb=solid.BoundBox
                        gaps=[max(hb.XMin-cb.XMax,cb.XMin-hb.XMax,0),max(hb.YMin-cb.YMax,cb.YMin-hb.YMax,0),max(hb.ZMin-cb.ZMax,cb.ZMin-hb.ZMax,0)]
                        lower_bound=math.sqrt(sum(v*v for v in gaps))
                        if lower_bound<2.0:
                            distance=hw.distToShape(solid)[0]
                            distances.append({'component_solid':n,'distance_mm':distance,'component_bbox_mm':[cb.XMin,cb.YMin,cb.ZMin,cb.XMax,cb.YMax,cb.ZMax]})
                    nearest=min(distances,key=lambda d:d['distance_mm'])if distances else None
                    hardware_clearances.append({'pcb':name,'corner':idx+1,'hardware_envelope':'Circumscribed M3 hex cylinder: valid for arbitrary angle. Ground contact planes and thread mating excluded.',
                                                'minimum_component_distance_mm':nearest['distance_mm']if nearest else None,'proven_minimum_mm':nearest['distance_mm']if nearest else 2.0,
                                                'nearest':nearest,'pass':not nearest or nearest['distance_mm']>.001})
        else:collisions=[];hardware_clearances=[];vertical_clearances=None
        doc.recompute()
        stem='MeshRepeater2_'+('exploded'if exploded else'assembly')
        doc.saveAs(str(a.out/(stem+'.FCStd')))
        Part.export(pieces,str(a.out/(stem+'.step')))
        compound=Part.makeCompound([o.Shape for o in pieces]);bb=compound.BoundBox
        if a.mesh:
            meshes=[]
            for obj in pieces:
                label=obj.Label
                solids=obj.Shape.Solids if '_native_'in label else[obj.Shape]
                for number,solid in enumerate(solids):
                    vertices,triangles=solid.tessellate(0.18)
                    color=piece_colors[label]
                    if '_native_'in label:
                        sb=solid.BoundBox
                        if abs(sb.XLength-90)<.05 and abs(sb.YLength-60)<.05 and 1.0<sb.ZLength<2.0:
                            pass
                        elif sb.ZLength<.2:
                            color=(.68,.45,.20)
                        elif 1.0<sb.ZLength<1.6 and min(sb.XLength,sb.YLength)>10:
                            color=(.14,.44,.29)
                        else:
                            color=(.25,.28,.31)
                    meshes.append({'label':label+f'_solid_{number}','color':color,'vertices':[[v.x,v.y,v.z] for v in vertices],'triangles':triangles})
            with gzip.open(a.out/(stem+'_native_mesh.json.gz'),'wt',encoding='utf-8') as stream:
                json.dump({'geometry_source':'Native PCB STEP tessellation with dimensional hardware envelopes. Colors are illustrative.','scene':stem,'verified_native_inputs':inputs,'mechanical_contract_sha256':hashlib.sha256((ROOT/'docs/mechanical_selection.json').read_bytes()).hexdigest(),'objects':meshes},stream,separators=(',',':'))
        svg_error=None
        if a.edge_svg:
            try:
                svg=TechDraw.projectToSVG(compound,App.Vector(1,-1,1))
                # Native CAD edge projection, not an invented illustration.
                corners=[(x,y,z) for x in (bb.XMin,bb.XMax) for y in (bb.YMin,bb.YMax) for z in (bb.ZMin,bb.ZMax)]
                projected=[((x-z)/math.sqrt(2),-(x+2*y+z)/math.sqrt(6)) for x,y,z in corners]
                vx=min(x for x,y in projected)-5;vy=min(y for x,y in projected)-5
                vw=max(x for x,y in projected)-vx+5;vh=max(y for x,y in projected)-vy+5
                svg=svg.replace('stroke-width="1.0"','stroke-width="0.15"')
                standalone=f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1000" viewBox="{vx} {vy} {vw} {vh}"><title>{stem}: native CAD edge projection</title><rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="white"/>{svg}</svg>'
                (a.out/(stem+'_native_isometric.svg')).write_text(standalone,encoding='utf-8')
            except Exception as e:svg_error=str(e)
        reports[stem]={'bbox_mm':[bb.XMin,bb.YMin,bb.ZMin,bb.XMax,bb.YMax,bb.ZMax],
                       'pcb_intersections':collisions,'vertical_envelope_clearances':vertical_clearances,'hardware_to_component_clearances':hardware_clearances,'edge_svg_requested':a.edge_svg,'edge_svg_error':svg_error,'includes':['Native PCB STEP components','Standoff, washer, screw and nut outer envelopes'],
                       'excludes':['External harness','Thread profiles and unmeasured usable female thread depth','Actual spring-contact engagement and connector manufacturing tolerances'],
                       'qualification':'Native PCB geometry including nominal vertical male/female envelopes and a nominal mechanical stack. Actual modules, threaded fasteners and Ali connector mating require a physical sample.'}
        App.closeDocument(doc.Name)
    result={'date':date.today().isoformat(),'inputs':inputs,'coordinate_convention':'CAD X = native PCB X; CAD Y = −physical PCB Y; CAD Z points up. LOGIC and SHIELD rotate 180° about X.',
            'stack_source':'docs/mechanical_selection.json','stack_contract_sha256':hashlib.sha256((ROOT/'docs/mechanical_selection.json').read_bytes()).hexdigest(),'artifacts':reports}
    (a.out/'assembly_geometry_report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
