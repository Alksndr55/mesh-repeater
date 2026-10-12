"""Build the two v2 native schematics without changing S4.16 circuit values.

Each --project must contain the exact partitioned model.json and chosen local
footprints. No provisional connector is selected by this script. All output
paths are checked against the v2 workspace before importing the primitives.
"""
from pathlib import Path
import argparse, collections, hashlib, json, os, shutil, subprocess, sys

V2_ROOT = Path(__file__).resolve().parents[2]

def safe(path):
    p = Path(path).resolve()
    if not p.is_relative_to(V2_ROOT):
        raise ValueError(f'Output must stay inside {V2_ROOT}: {p}')
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--board', choices=('POWER','LOGIC'), required=True)
    ap.add_argument('--revision', default='V2.0-A1')
    ap.add_argument('--date', default=None)
    ap.add_argument('--pdf-out',type=Path,default=None,help='Alternate v2 PDF path when a prior PDF is open/locked')
    ap.add_argument('--preserve-model',action='store_true',help='Keep an already synchronized model unchanged during routing-owned pose updates')
    ap.add_argument('--cli', type=Path, default=Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe'))
    ap.add_argument('--export', action='store_true')
    ap.add_argument('--netlist-erc', action='store_true',help='Native XML/ERC only; no PDF export')
    args = ap.parse_args()
    project = safe(args.project)
    model = json.loads((project/'model.json').read_text(encoding='utf-8'))
    contract = json.loads((V2_ROOT/'design/v2_electrical_contract.json').read_text(encoding='utf-8'))
    source_parts = {p['reference']:p for p in contract['parts']}
    packages={'J7':'XH 1x2 / 2.50 / 90deg','J8':'XH 1x2 / 2.50 / 90deg','J12':'XH 1x4 / 2.50 / 90deg',
              'J101':'THT 2x6 / 2.54 / vertical','J201':'THT 2x6 / 2.54 / vertical',
              'J11':'1x2 / 2.54 / 90deg','J3':'1x4 / 2.54 / 90deg','J5':'1x4 / 2.54 / 90deg',
              'J10':'ISP 2x3 / 2.54 / THT','SW1':'THT 7.11x7.01 / side','SW2':'THT 7.11x7.01 / side'}
    for part in model['parts']:
        if part['ref'] in packages:
            part['package_short']=packages[part['ref']]
        source = source_parts.get(part['ref'])
        if not source:continue
        row=source['assembly_variant_row']
        part['fit_naion']=row['Fit_NaIon']=='yes'
        part['fit_lto2s']=row['Fit_LTO_2S']=='yes'
        part['value_lto2s']=row['Value_LTO_2S']
        part['fit_naion_no_cold']=row['Fit_NaIon_NoCold']=='yes'
        part['value_naion_no_cold']=row['Value_NaIon_NoCold']
        if part['kind'] == 'MountingHole':
            # V2 uses plated GND contact lands in every battery variant.
            part['value_lto2s'] = part['value']
            part['value_naion_no_cold'] = part['value']
        # A mechanical replacement is the same chosen part in all variants;
        # retain real alternate electrical parts, such as R56's zero-ohm link.
        part['mpn_lto2s']=part.get('mpn','') if row['MPN_LTO_2S']==row['MPN_NaIon'] else row['MPN_LTO_2S']
        part['mpn_naion_no_cold']=part.get('mpn','') if row['MPN_NaIon_NoCold']==row['MPN_NaIon'] else row['MPN_NaIon_NoCold']
    assert model.get('partition_board') == args.board, 'model.partition_board must match --board'
    assert model.get('baseline_pcb_sha256') == '742ae27bb1d13893f6dc368e5c67f5c41b35a3e6765331fc7e9871297d23dec6', 'Exact S4.16 provenance is required'
    model['schematic_revision'] = args.revision
    model['schematic_date'] = args.date or model.get('schematic_date','2026-10-12')
    model['root_sheet'] = 'Charger' if args.board == 'POWER' else 'Modules'
    ordered = ['Charger','Converter','LTO_Balancer','Thermal',*(['BatteryMonitor'] if model.get('battery_monitor') else []),'Interconnect'] if args.board == 'POWER' else ['Modules','RTC_IO','Watchdog','Interconnect']
    model['sheet_pages'] = {name: index+1 for index,name in enumerate(ordered)}
    if not args.preserve_model:
        (project/'model.json').write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')
    pro=project/(model['project']+'.kicad_pro')
    if not pro.exists():
        settings=json.loads((V2_ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pro').read_text(encoding='utf-8'))
        settings['meta']['filename']=pro.name
        settings['boards']=[];settings['sheets']=[]
        # Do not replace concurrent caller-written PCB settings.
        try:
            with pro.open('x',encoding='utf-8') as handle:json.dump(settings,handle,ensure_ascii=False,indent=2)
        except FileExistsError:pass
    # Keep the complete reviewed S4.16 ERC coverage even if a caller recreated
    # PCB settings and omitted its ERC section. No default ignored checks.
    settings=json.loads(pro.read_text(encoding='utf-8'))
    settings['erc']=json.loads((V2_ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pro').read_text(encoding='utf-8'))['erc']
    pro.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')
    os.environ['MESHCORE_PROJECT_DIR'] = str(project)
    import schematic_core as core
    from schematic_parts import add_component_annotations
    if args.board == 'POWER':
        import schematic_charger, schematic_power, schematic_lto, schematic_thermal
        sheets = [schematic_charger.build(), *schematic_power.build(), schematic_lto.build(), schematic_thermal.build()]
        if model.get('battery_monitor'):
            import schematic_battery_monitor
            sheets.append(schematic_battery_monitor.build())
    else:
        import schematic_modules, schematic_rtc_io, schematic_watchdog
        sheets = [schematic_modules.build(), schematic_rtc_io.build(), schematic_watchdog.build()]

    s = core.Sheet('Interconnect', 'Mesh Repeater 2.0 — '+args.board+' / межплатные соединения', len(sheets)+1)
    if args.board == 'LOGIC':
        s.sym('J11',76.2,50.8,'JUMPER_H')
        s.net('J11',1,7.62); s.net('J11',2,7.62)
        s.sym('TP4',111.76,50.8); s.net('TP4',1,7.62)
        if 'TP7' in core.PARTS:s.sym('TP7',111.76,76.2);s.net('TP7',1,7.62)
        s.sym('R21',76.2,93.98,'R_H')
        s.net('R21',1,7.62); s.net('R21',2,7.62)
        s.flag('SYS_3V3',111.76,116.84,505)
        s.flag('GND',134.62,116.84,506)
        s.text('J11: шунт установлен для АКБ/солнца.',25.4,140.97,1.27)
        s.text('До USB снять J11; вернуть только после отключения USB.',25.4,148.59,1.27)
        s.text('R21 оставлен 1 кОм: RADIO_TXEN → R21 → MODE через штыри.',25.4,160.02,1.15)
    else:
        s.text('Основные токи FILTER_OUT и GND идут через вертикальные штыри.',25.4,45.72,1.27)
        s.text('BAT: отдельный отвод измерения прямо от разъёма батареи.',25.4,53.34,1.27)
        s.text('MODE: R21 на LOGIC у источника; R17 pull-down на POWER.',25.4,60.96,1.15)
        s.text('D3 CHARGE / D4 DONE находятся только на POWER.',25.4,68.58,1.15)
        s.text('SYS_3V3 возвращается с LOGIC только для питания INA219.',25.4,76.2,1.15)
    already = {r for sheet in sheets+[s] for r in sheet.refs}
    pending = [p for p in core.MODEL['parts'] if p['ref'] not in already]
    # Interboard connector and purely mechanical contacts are the only extra
    # positions permitted. Reject accidental omissions of functional parts.
    allowed_groups = {'interboard','mechanical','mounting','shield'}
    mount_index=0
    for index,p in enumerate(pending):
        if p.get('group') not in allowed_groups and p['ref'] != 'SH1' and p['kind'] != 'MountingHole':
            raise AssertionError(('Functional part missing from its retained sheet',p['ref'],p.get('group')))
        if p['kind']=='MountingHole':
            x,y=177.8+30.48*mount_index,170.18
            mount_index+=1
        elif p.get('group')=='interboard':x,y=220.98,80.01
        elif p['ref']=='SH1':x,y=330.2,160.02
        else:x,y=330.2,101.6+25.4*index
        pins = [(n,net or 'NC',12.7,(i-(len(p['nets'])-1)/2)*5.08,'R','passive') for i,(n,net) in enumerate(p['nets'].items())]
        style = 'V2_' + p['ref']
        core.chip(style,pins,15.24,max(10.16,len(pins)*5.08))
        s.sym(p['ref'],x,y,style)
        for n,net in p['nets'].items():
            if net is None:s.nc(p['ref'],n)
            else:s.net(p['ref'],n,7.62)
    s.text('Экран/стойки: только GND/EMI; не обязательный силовой возврат.',25.4,205.74,1.15)
    s.text('Распиновка прямого соединения — interboard_connections.csv.',25.4,213.36,1.15)
    sheets.append(s)
    counts = collections.Counter(ref for sheet in sheets for ref in sheet.refs)
    assert set(counts) == set(core.PARTS), ('Missing',set(core.PARTS)-set(counts),'Extra',set(counts)-set(core.PARTS))
    assert all(n == 1 for n in counts.values()), counts
    root = sheets[0]
    assert root.root
    for i,child in enumerate(sheets[1:]):
        pitch=76.2 if len(sheets)>5 else 83.82
        width=71.12 if len(sheets)>5 else 78.74
        x,y = 15.24+i*pitch,239.776
        sid = core.stable('sheet:'+child.name)
        root.items.append(f'(sheet (at {x} {y}) (size {width} 12.7) (stroke (width .254) (type default)) (fill (color 0 0 0 0)) (uuid {core.q(sid)}) (property "Sheetname" {core.q(str(child.page)+". "+child.name)} (at {x} {y-1.27} 0) {core.fx(1.27,"left bottom")}) (property "Sheetfile" {core.q(child.name+".kicad_sch")} (at {x} {y+8.89} 0) {core.fx(1.15,"left top")}) (instances (project {core.q(core.PROJECT)} (path {core.q("/"+core.ROOT_ID)} (page {core.q(str(child.page))})))))')
    core.library()
    for sheet in sheets:
        add_component_annotations(sheet)
        sheet.write()
    if not args.preserve_model:
        (project/'model.json').write_text(json.dumps(core.MODEL,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest = dict(board=args.board,revision=args.revision,project=core.PROJECT,parts=len(core.PARTS),baseline_pcb_sha256=model['baseline_pcb_sha256'],sheets=[dict(name=t.name,page=t.page,refs=t.refs,annotations=t.component_annotations,global_labels=t.global_labels,wire_segments=t.wires) for t in sheets])
    (project/'schematic_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for sheet in sheets:
        dest = project/((core.PROJECT if sheet.root else sheet.name)+'.kicad_sch')
        subprocess.run([str(args.cli),'sch','upgrade','--force',str(dest)],check=True)
    subprocess.run([str(args.cli),'sym','upgrade','--force',str(project/'Meshcore.kicad_sym')],check=True)
    if args.export or args.netlist_erc:
        export = safe(V2_ROOT/'audit'/'schematic'/args.board)
        export.mkdir(parents=True,exist_ok=True)
        sch = project/(core.PROJECT+'.kicad_sch')
        commands=[ ['sch','export','netlist','--format','kicadxml','-o',str(export/'netlist.xml'),str(sch)], ['sch','erc','--format','json','--severity-all','-o',str(export/'erc.json'),str(sch)] ]
        if args.export:
            pdf_dir=safe(V2_ROOT/'output/pdf');pdf_dir.mkdir(parents=True,exist_ok=True)
            pdf_path=safe(args.pdf_out) if args.pdf_out else pdf_dir/(core.PROJECT+'_schematic.pdf')
            commands.append(['sch','export','pdf','-o',str(pdf_path),str(sch)])
        for cmd in commands:
            subprocess.run([str(args.cli),*cmd],check=True)
    print(json.dumps({'board':args.board,'project':core.PROJECT,'components':len(core.PARTS),'sheets':len(sheets),'schematic_manifest':str((project/'schematic_manifest.json').relative_to(V2_ROOT))},ensure_ascii=True))

if __name__ == '__main__':main()
