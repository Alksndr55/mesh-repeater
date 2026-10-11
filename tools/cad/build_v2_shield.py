"""Native single-copper v2 middle screen; no circuit and no cut-out lettering.

Only MeshRepeater2_Shield is written. The foil is native F.Cu and faces down
after the X180 assembly flip. The GND label assigns only the foil/contact
assembly; power and signal return use the separate interboard cable.
"""
from pathlib import Path
import argparse, csv, hashlib, json, subprocess
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/'design/MeshRepeater2_Shield'
NAME='MeshRepeater2_Shield'
HOLES=[(3.5,3.5),(86.5,3.5),(3.5,56.5),(86.5,56.5)]
def vec(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def mm(v):return k.ToMM(v)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def local_libraries():
    lib=DIR/'Shield.pretty';lib.mkdir(parents=True,exist_ok=True)
    hole='Shield_NPTH_D3_2_ContactOD6'
    (lib/(hole+'.kicad_mod')).write_text(f'''(footprint "{hole}" (version 20260206) (generator "pcbnew")
 (layer "F.Cu") (descr "M3 NPTH; F-mask OD6 metal-contact opening; drill-to-foil gap 0.30")
 (attr board_only exclude_from_pos_files exclude_from_bom)
 (fp_text reference "H?" (at 0 -4) (layer "F.Fab") hide (effects (font (size 1 1) (thickness 0.1))))
 (fp_text value "{hole}" (at 0 4) (layer "F.Fab") hide (effects (font (size 1 1) (thickness 0.1))))
 (fp_circle (center 0 0) (end 3 0) (stroke (width 0) (type default)) (fill solid) (layer "F.Mask"))
 (fp_circle (center 0 0) (end 3 0) (stroke (width 0.1) (type default)) (fill none) (layer "F.Fab"))
 (fp_circle (center 0 0) (end 3.25 0) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
 (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") (clearance 0.3))
)\n''',encoding='utf8')
    anchor='Shield_Foil_GND_Anchor'
    (lib/(anchor+'.kicad_mod')).write_text(f'''(footprint "{anchor}" (version 20260206) (generator "pcbnew")
 (layer "F.Cu") (descr "Hidden copper-only GND anchor; not an electronic part; no mask or paste aperture")
 (attr board_only exclude_from_pos_files exclude_from_bom)
 (fp_text reference "GF1" (at 0 0) (layer "F.Fab") hide (effects (font (size 1 1) (thickness 0.1))))
 (fp_text value "{anchor}" (at 0 0) (layer "F.Fab") hide (effects (font (size 1 1) (thickness 0.1))))
 (fp_rect (start -0.2 -0.2) (end 0.2 0.2) (stroke (width 0.05) (type default)) (fill none) (layer "F.CrtYd"))
 (pad "1" smd rect (at 0 0) (size 0.2 0.2) (layers "F.Cu") (zone_connect 2))
)\n''',encoding='utf8')
    (DIR/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "Shield")(type "KiCad")(uri "${KIPRJMOD}/Shield.pretty")(options "")(descr "Local mechanical shield library")))\n',encoding='utf8')
    (DIR/'sym-lib-table').write_text('(sym_lib_table (version 7))\n',encoding='utf8')
    return lib,hole,anchor

def text(b,s,x,y,layer,font=.95,bold=False):
    # Guide positions are laid out in their own readable physical face view.
    # For B the assembly X180 mirrors nativeY; mirror the guide's layout too.
    native_y=60-y if layer==k.B_SilkS else y
    t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(vec(x,native_y));t.SetLayer(layer);t.SetMirrored(layer==k.B_SilkS)
    t.SetTextSize(vec(font,font));t.SetTextThickness(k.FromMM(.16 if bold else .12));t.SetBold(bold)
    # Native B is the visible assembly-top face after the X180 flip.
    t.SetTextAngle(k.EDA_ANGLE(180 if layer==k.B_SilkS else 0,k.DEGREES_T));t.SetHorizJustify(k.GR_TEXT_H_ALIGN_CENTER);t.SetVertJustify(k.GR_TEXT_V_ALIGN_CENTER)
    b.Add(t);return t

def short(row,variant):
    value=row['Value_'+variant].split()[0]
    if row['Reference'].startswith('R') and value.replace('.','',1).isdigit():value+='R'
    return value

def artwork(b,rows):
    f=k.F_SilkS;back=k.B_SilkS
    # Every value is read from the accepted CSV, rather than stale model metadata.
    vals=lambda variant:'   '.join(r+' '+short(rows[r],variant) for r in ('R3','R4','C30'))
    ens=lambda variant:'   '.join(r+' '+short(rows[r],variant) for r in ('R15','R16'))
    texts=[]
    def add(s,y,layer,font=.95,bold=False):texts.append(text(b,s,45,y,layer,font,bold))
    add('Mesh Repeater 2.0 / SHIELD / V2.0-A1',8,f,1.2,True)
    add('COPPER SIDE DOWN / GND CONTACT OD6',11.2,f,1.,True)
    add('POWER below: CN3722 + TPS63802 + 2-stage LC',15.5,f)
    add('LOGIC above: NiceNano + HT-RA62 + RTC + watchdog',18.2,f)
    add('J7 SOLAR: 1 + / 2 GND. Panel 12V; Voc <=24V.',22.2,f)
    add('J8 BAT: 1 + / 2 GND. J12 LTO: 1 BAT / 2 MID / 3 GND / 4 NC.',24.9,f,.88)
    add('J101 <-> J201: cable pins 1:1; route around screen edge.',29.1,f)
    add('1/3/5/7 FILTER_OUT   all even GND   9 BAT   11 MODE',31.8,f)
    add('Cable supplies power/GND; metal stands are for shield contact.',34.5,f,.9)
    add('Before USB: REMOVE J11. Refit only after USB is disconnected.',38.7,f,.9,True)
    add('Keep all four foil contacts clean. Use metal DIN433 M3 washers.',42.7,f,.9)
    add('No SH1 frame/lid. Continuous foil: no slots or cut-out letters.',45.4,f,.9)
    add('M3 holes 3.2mm / washer OD6 / PCB 1.52mm / foil one face',49.6,f,.9)
    add('Disconnect solar + battery + USB before disassembly.',52.3,f,.9,True)

    add('Mesh Repeater 2.0 / SHIELD / V2.0-A1',8,back,1.2,True)
    add('UPPER FACE / ASSEMBLY QUICK GUIDE',11.2,back,1.,True)
    add('Na-ion 1S: fit COLD; omit BAL1/BAL2. R56 '+short(rows['R56'],'NaIon'),15.5,back)
    add(vals('NaIon'),18.2,back)
    add(ens('NaIon'),20.9,back)
    add('Na-ion without COLD: omit cold parts; R56 '+short(rows['R56'],'NaIon_NoCold'),25.1,back)
    add('LTO 2S: fit BAL1/BAL2; omit COLD. R56 '+short(rows['R56'],'LTO_2S'),29.3,back)
    add(vals('LTO_2S'),32.0,back)
    add(ens('LTO_2S'),34.7,back)
    add('USB / firmware: REMOVE J11. ISP J10 is on LOGIC.',38.9,back,.9,True)
    add('GPS: J4 Heltec T114 pinout; power enable nRF P0.24.',41.6,back,.9)
    add('RTC: CR2032 primary cell. D3 CHARGE / D4 DONE on POWER.',44.3,back,.9)
    add('Below: stand 18mm + washer. Above: washer + stand 15mm.',48.5,back,.9)
    add('Metal washers DIN433 3.2 x 6 x 0.5mm; 5 per corner.',51.2,back,.9)
    add('Full assembly instructions / cable / variants: project docs.',53.9,back,.9)
    return texts

def write_settings():
    settings=json.loads((ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pro').read_text(encoding='utf8'))
    settings['meta']['filename']=NAME+'.kicad_pro';settings['boards']=[];settings['sheets']=[]
    ds=settings['board']['design_settings'];ds['drc_exclusions']=[]
    # The standalone mechanical screen has no inherited suppressed DRC rule.
    for rule,severity in ds['rule_severities'].items():
        if severity=='ignore':ds['rule_severities'][rule]='warning'
    ds['rules']['min_copper_edge_clearance']=.3;ds['rules']['min_hole_clearance']=.3
    ds['rules']['min_silk_clearance']=.1;ds['rules']['min_text_height']=.8
    ds['rules']['min_text_thickness']=.1
    (DIR/(NAME+'.kicad_pro')).write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf8')
    (DIR/(NAME+'.kicad_dru')).write_text('(version 1)\n',encoding='utf8')

def audit(b,texts,path,csvpath):
    zones=list(b.Zones());assert len(zones)==1
    z=zones[0];filled=k.SHAPE_POLY_SET(z.GetFilledPolysList(k.F_Cu));filled.Unfracture()
    counts={'native_container_copper_layers':b.GetCopperLayerCount(),'manufacturing_copper_layers':1,'filled_outline_count':filled.OutlineCount(),'filled_holes':sum(filled.HoleCount(i) for i in range(filled.OutlineCount()))}
    assert counts['filled_outline_count']==1,'Foil must be a single connected region'
    assert counts['filled_holes']==4,'Only the four mounting drill clearances may remove foil'
    assert z.GetIslandRemovalMode()==k.ISLAND_REMOVAL_MODE_NEVER
    assert len(list(b.GetTracks()))==0 and len(list(b.GetFootprints()))==5
    assert not any(g.GetLayer() in (k.F_Cu,k.B_Cu) for g in b.GetDrawings()),'Text/graphics must not cut or add copper'
    edge=b.GetBoardEdgesBoundingBox();size=[mm(edge.GetWidth()),mm(edge.GetHeight())]
    # Edge.Cuts line widths expand bounding box; pad coordinate outline is exact.
    outline=[tuple(round(mm(t),4) for t in [g.GetStart().x,g.GetStart().y,g.GetEnd().x,g.GetEnd().y]) for g in b.GetDrawings() if isinstance(g,k.PCB_SHAPE) and g.GetLayer()==k.Edge_Cuts]
    footprints={f.GetReference():f for f in b.GetFootprints()};contact=[]
    for i,pos in enumerate(HOLES,301):
        f=footprints['H'+str(i)];p=next(iter(f.Pads()));assert p.GetAttribute()==k.PAD_ATTRIB_NPTH
        assert abs(mm(p.GetDrillSize().x)-3.2)<1e-6
        assert [mm(f.GetPosition().x),mm(f.GetPosition().y)]==list(pos)
        ring_points=[]
        for n in range(72):
            a=n*2*3.141592653589793/72;import math
            pt=vec(pos[0]+2.5*math.cos(a),pos[1]+2.5*math.sin(a));ring_points.append(filled.Contains(pt))
        assert all(ring_points),'All 360deg of exposed contact annulus must connect to foil'
        contact.append({'ref':f.GetReference(),'xy_mm':pos,'drill_mm':3.2,'open_mask_od_mm':6,'foil_gap_to_drill_mm':.3,'metal_contact_annulus_id_mm':3.8,'ring_360deg_connected':True})
    bounds=(.3,.3,89.7,59.7);textrows=[]
    for t in texts:
        r=t.GetBoundingBox();box=[mm(r.GetLeft()),mm(r.GetTop()),mm(r.GetRight()),mm(r.GetBottom())]
        assert box[0]>=bounds[0] and box[1]>=bounds[1] and box[2]<=bounds[2] and box[3]<=bounds[3],'Text outside physical screen'
        textrows.append(dict(text=t.GetText(),layer=k.LayerName(t.GetLayer()),font_mm=mm(t.GetTextHeight()),box_mm=box))
    assert not any(p.IsOnLayer(k.B_Cu) and p.GetAttribute()!=k.PAD_ATTRIB_NPTH for f in b.GetFootprints() for p in f.Pads()),'Back must have no copper pad'
    return {'project':NAME,'pcb_sha256':digest(path),'variants_csv_sha256':digest(csvpath),'checks':counts,'native_one_layer_limitation':'KiCad10 SetCopperLayerCount(1) reports1 only in memory; SaveBoard/reload restores2 and an F-only layers stanza is rejected. Valid native project uses minimum2-layer container, but all manufacturing copper is F.Cu; B.Cu has no features and must not be manufactured.','outline_segments_mm':outline,'nominal_size_mm':[90,60],'board_thickness_mm':mm(b.GetDesignSettings().GetBoardThickness()),'assembly_flip':'X180','assembled_copper_face':'DOWN','continuous_foil':True,'four_contact_rings':contact,'island_removal':'NEVER','copper_anchor':'GF1: hidden 0.2mm copper-only pad, no electronic BOM/assembly part','no_copper_text_or_slots':True,'all_markings':textrows,'minimum_font_mm':min(t['font_mm'] for t in textrows)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cli',type=Path,default=Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'));args=ap.parse_args()
    DIR.mkdir(parents=True,exist_ok=True);lib,hole,anchor=local_libraries()
    csvpath=ROOT/'baseline/S4_16/assembly_variants_S4_16.csv'
    rows={r['Reference']:r for r in csv.DictReader(csvpath.open(encoding='utf-8-sig',newline=''))}
    # Native KiCad10 storage/parser requires its minimum 2-Cu-layer container.
    # Only F.Cu contains any manufacturing copper; B.Cu is deliberately blank.
    b=k.BOARD();b.SetCopperLayerCount(2);s=b.GetDesignSettings();s.SetBoardThickness(k.FromMM(1.52));s.m_CopperEdgeClearance=k.FromMM(.3);s.m_HoleClearance=k.FromMM(.3);s.m_MinClearance=k.FromMM(.2);s.m_SilkClearance=k.FromMM(.1)
    b.GetTitleBlock().SetTitle('Mesh Repeater 2.0 / middle shield');b.GetTitleBlock().SetRevision('V2.0-A1');b.GetTitleBlock().SetDate('2026-10-11');b.GetTitleBlock().SetCompany('Designed by @Alksndritm')
    net=k.NETINFO_ITEM(b,'GND',1);b.Add(net)
    for i,(x,y) in enumerate(HOLES,301):
        f=k.FootprintLoad(str(lib),hole);f.SetReference('H'+str(i));f.SetFPID(k.LIB_ID('Shield',hole));f.SetPosition(vec(x,y));f.Reference().SetVisible(False);f.Value().SetVisible(False);b.Add(f)
    f=k.FootprintLoad(str(lib),anchor);f.SetReference('GF1');f.SetFPID(k.LIB_ID('Shield',anchor));f.SetPosition(vec(45,30));next(iter(f.Pads())).SetNet(net);f.Reference().SetVisible(False);f.Value().SetVisible(False);b.Add(f)
    for a,c in [((0,0),(90,0)),((90,0),(90,60)),((90,60),(0,60)),((0,60),(0,0))]:
        g=k.PCB_SHAPE(b);g.SetShape(k.SHAPE_T_SEGMENT);g.SetLayer(k.Edge_Cuts);g.SetStart(vec(*a));g.SetEnd(vec(*c));g.SetWidth(k.FromMM(.05));b.Add(g)
    z=k.ZONE(b);z.SetLayer(k.F_Cu);z.SetNet(net);z.SetZoneName('CONTINUOUS_GND_FOIL');z.SetLocalClearance(k.FromMM(.3));z.SetMinThickness(k.FromMM(.1));z.SetPadConnection(k.ZONE_CONNECTION_FULL);z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_NEVER);z.Outline().NewOutline()
    for x,y in [(0.3,0.3),(89.7,0.3),(89.7,59.7),(.3,59.7)]:z.Outline().Append(*vec(x,y))
    b.Add(z);texts=artwork(b,rows);k.ZONE_FILLER(b).Fill(b.Zones());path=DIR/(NAME+'.kicad_pcb');k.SaveBoard(str(path),b)
    # SaveBoard may serialise default project settings from pcbnew's in-memory
    # context. Restore the explicit strict settings after it, before native DRC.
    write_settings()
    from set_v2_shield_stackup import ensure
    ensure(path);b=k.LoadBoard(str(path));k.SaveBoard(str(path),b);write_settings()
    proof=audit(b,texts,path,csvpath);report=ROOT/'audit/v2_shield_foil_audit.json';report.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    out=ROOT/'output/SHIELD'
    subprocess.run([str(Path(__import__('sys').executable)),str(Path(__file__).parent/'export_v2_board.py'),'--pcb',str(path),'--out',str(out),'--drc','--mechanical','--step','--cli',str(args.cli)],check=True)
    drc=json.loads((out/(NAME+'_drc.json')).read_text(encoding='utf8'));proof['drc_counts']={n:len(drc.get(n,[])) for n in ('violations','unconnected_items','schematic_parity')};proof['drc_ignored_checks']=drc.get('ignored_checks',[])
    proof['project_sha256']=digest(DIR/(NAME+'.kicad_pro'))
    assert not proof['drc_ignored_checks'],'No suppressed DRC check is permitted'
    assert not any(proof['drc_counts'].values()),'Shield native DRC must be empty'
    report.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'pcb':str(path.relative_to(ROOT)),'foil_connected':True,**counts(proof)},ensure_ascii=True))
def counts(proof):return {'manufacturing_copper_layers':proof['checks']['manufacturing_copper_layers'],'drc':proof['drc_counts'],'minimum_font_mm':proof['minimum_font_mm']}

if __name__=='__main__':main()
