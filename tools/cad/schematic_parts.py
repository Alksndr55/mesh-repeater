"""Readable reference/MPN/package schedules embedded on each circuit sheet.

Package names are based on the reviewed local footprints. An unknown ordering
number remains explicitly unselected; the table is not a stock availability claim.
"""
from pathlib import Path
import collections,json,math,re
from schematic_core import PARTS, DEFS

CATALOG=json.loads(Path(__file__).with_name('schematic_parts_catalog.json').read_text(encoding='utf-8'))
CATPARTS={p['ref']:p for p in CATALOG['parts']}

def compact_refs(refs):
    groups=collections.defaultdict(list)
    for ref in refs:
        m=re.fullmatch(r'([A-Z]+)(\d+)',ref)
        groups[m[1]].append(int(m[2]))
    result=[]
    for prefix,nums in groups.items():
        nums=sorted(nums);start=last=nums[0]
        for n in nums[1:]+[None]:
            if n is not None and n==last+1:
                last=n;continue
            result.append(prefix+str(start)+(('–'+prefix+str(last)) if last!=start else ''))
            start=last=n
    return ', '.join(result)

def add_parts_table(sheet):
    groups=collections.OrderedDict()
    for ref in sheet.refs:
        p=PARTS[ref]
        if p['kind'] in ('TestPoint','MountingHole','NetTie'):continue
        local_fp='Meshcore:'+p.get('source_footprint_before_v2_graphic_variant',p['footprint']).split(':',1)[-1]
        package=CATALOG['footprint_to_package'][local_fp]
        item=CATPARTS.get(ref,{})
        mpn=p.get('mpn','')
        if ref in ('C52','C53','C54','C55') and p.get('assembly_default_dnp',p.get('dnp')):
            display='DNP; MPN не выбран'
        elif item.get('mpn_status')=='assigned_in_model':
            display=mpn
        else:
            display=item.get('display_mpn') or mpn or 'MPN не выбран'
        display=display.replace('MPN TBD','MPN не выбран').replace('band TBD','диапазон выбрать')
        groups.setdefault((display,package),[]).append(ref)
    rows=[dict(refs=refs,display_refs=compact_refs(refs),mpn=mpn,package=pkg)
          for (mpn,pkg),refs in groups.items()]
    sheet.parts_table=rows
    y={'Charger':213.36,'Converter':229.87}.get(sheet.name,205.74)
    sheet.text('Комплектующие этого листа: MPN и корпус (EIA / метрический)',15.24,y,1.27)
    columns=2;per=math.ceil(len(rows)/columns)
    # The schedule stays left of the A3 drawing title block.
    for i in range(columns):
        x=15.24+i*137.16;header=y+5.08;subset=rows[i*per:(i+1)*per]
        for name,off in [('Поз.',1.27),('MPN / заказной номер',29.21),('Корпус',80.01)]:
            sheet.text(name,x+off,header,1.27)
        sheet.graphic([(x,header+2.54),(x+134.62,header+2.54)],.18)
        for j,row in enumerate(subset):
            yy=header+7.62+j*5.08
            sheet.text(row['display_refs'],x+1.27,yy,1.15)
            sheet.text(row['mpn'],x+29.21,yy,1.15)
            sheet.text(row['package'],x+80.01,yy,1.15)

def _label_details(ref):
    p=PARTS[ref]
    # Per-instance silk/Fab variants are hidden library identifiers; the
    # visible purchasing caption describes the selected physical package.
    fp=p.get('source_footprint_before_v2_graphic_variant',p['footprint']).split(':')[-1]
    package_overrides={
        'D_SMB':'SMB / DO-214AA','TI_DCT0008A':'SSOP-8 / DCT / 0.65 mm','SOIC-8_3.9x4.9mm_P1.27mm':'SOIC-8 / 3.9 mm',
        'L_Sumida_CDRH127_LDNP_101MC':'12.3 x 12.3 x 8 mm',
        'L_Sumida_CDRH127_LD':'12.3 x 12.3 x 8 mm',
        'SW_Push_KLS7_TS6604_4_3_180':'SMD / 6 x 6 x 4.3 mm',
        'CP_Elec_Panasonic_FK_D_6.3x5.8':'SMD / D6.3 x 5.8 mm'}
    package_overrides['TO-92_Inline']='TO-92 / шаг 1.27 mm'
    package_overrides['NTC_Remote_SolderPads_P2.54mm']='PTH / шаг 2.54 mm'
    package_overrides['NTC_TDK_B57861S_Onboard_or_Remote_P2.54mm']='NTC ø2.41 / P2.54'
    package_overrides['Ferrite_Murata_BLM21PG']='0805 / 2 x 1.25 mm'
    if re.match(r'[CR]_(0603|0805|1206|1812)_',fp):package=fp.split('_')[1]
    else:package=package_overrides.get(fp,CATALOG['footprint_to_package'].get('Meshcore:'+fp,fp))
    mpn=p.get('mpn') or 'MPN не выбран'
    if p.get('assembly_default_dnp',p.get('dnp')):mpn=(mpn+' / LTO only') if p.get('group')=='lto_balancer' else 'DNP; MPN не выбран'
    if ref=='M1':mpn='Nice!Nano / клон';package='ProMicro / доработка'
    if ref=='M2':mpn='HT-RA62 / диапазон выбрать'
    if ref=='BT1' and mpn=='1060':mpn='Keystone 1060 / держатель'
    if ref=='J4':package='1 x 8 / 1.25 mm / SMD'
    if p.get('package_short'):package=p['package_short']
    elif p.get('package'):package=p['package']
    if ref in ('J7','J8','J12','J101','J201'):mpn=mpn.removeprefix('Connfly ').removeprefix('JST ').removeprefix('KLS ')
    if ref in ('J11','J3','J5'):mpn=mpn.removeprefix('Connfly ').split(' cut to')[0]
    if ref in ('SW1','SW2'):mpn='1825027-2 / FSMRA1JH04'
    if ref=='J13':mpn=p.get('mpn','L-KLS1-SMA002-B');package='SMA / угловой / PTH'
    if ref=='FL1':mpn='S869M000S003 / опция';package='DCC6C / 3 x 3 x 1.3 mm'
    if ref.startswith('J') and mpn.startswith('DS1021-'):
        # Ordered strip length is not the fitted number of contacts.
        package=('2 x 3 / 2.54 mm' if ref=='J10' else '1 x '+str(len(p['nets']))+' / 2.54 mm')
    return mpn,package

def add_component_annotations(sheet):
    """Place native editable MPN/package text below each purchasing symbol.

    A vertical symbol's lower-right quadrant avoids its real lower pin/wire.
    Tight SPI resistor rows use one compact line between neighbouring wires.
    """
    for ref in sheet.refs:
        p=PARTS[ref]
        if p['kind'] in ('TestPoint','MountingHole','NetTie'):continue
        mpn,package=_label_details(ref)
        x,y=sheet.placed[ref];style=sheet.styles[ref]
        vertical=style in ('R_V','C_V','CP_V','D_V','D_UP','LED_V')
        if vertical:
            ax,ay=x+3.81,y+5.08;justify='left';size=.95
            lines=[mpn,package]
        elif ref in ('R23','R24','R25','R26'):
            ax,ay=x,y+1.778;justify='';size=.9;lines=[mpn+' / '+package]
        elif style in ('R_H','R_H_REV','C_H','L_H','D_H','SW_H','JUMPER_H'):
            ax,ay=x,y+5.08;justify='';size=.95;lines=[mpn,package]
        elif ref=='Q1':
            ax,ay=x+6.35,y+8.89;justify='left';size=.95;lines=[mpn,package]
        elif p['kind'] in ('CN3722','TPS63802','ATtiny13A','DS3231M'):
            ax,ay=x+6.35,y+max(z[3] for z in DEFS[style]['pins'])+8.89
            justify='left';size=1.05;lines=[mpn,package]
        else:
            ax,ay=x,y+max(z[3] for z in DEFS[style]['pins'])+11.43
            justify='';size=1.05;lines=[mpn,package]
        # Small measured exceptions keep annotations beneath the symbol and
        # clear of surrounding compensation wires or battery properties.
        overrides={
            'U1':(154.94,132.08,'left'), 'U2':(91.44,121.92,'left'),
            'U4':(78.74,114.3,''), 'U6':(109.22,114.3,'left'),
            'BT1':(30.48,119.38,''), 'M1':(78.74,147.32,''),
            'M2':(213.36,121.92,''), 'SH1':(208.28,180.34,''),
            'R6':(143.51,158.75,'left')}
        if ref in overrides and sheet.name!='Interconnect':ax,ay,justify=overrides[ref]
        if sheet.name=='BatteryMonitor':
            if ref=='R72':ax,ay,justify=x,y+3.81,''
            if ref=='R73':ax,ay,justify=x,y+13.97,''
            if ref=='C64':ax,ay,justify=x+3.81,y+15.24,'left';size=.85;lines=[mpn,package]
        if sheet.name=='LTO_Balancer' and ref in ('U8','U9'):
            # Below/right of the device, between its A return and capacitor.
            # The sheet already declares LTO-only assembly; repeating that
            # suffix here would cross the vertical return conductors.
            ax,ay,justify=x+11.43,y+26.67,'left';lines=[p.get('mpn',''),package]
        if sheet.name=='RTC_IO' and ref=='Q2':ax,ay,justify=x+6.35,y+20.32,'left'
        if sheet.name=='RTC_IO' and ref=='Q3':ax,ay,justify=x+6.35,y+12.7,'left'
        if sheet.name=='Thermal':
            if ref=='R60':ax,ay,justify=x-3.81,y+5.08,'right'
            if ref=='R62':ax,ay,justify=x,y+8.89,''
            if ref=='R61':ax,ay,justify=x-5.08,y+5.08,'right'
            if ref=='R69':ax,ay,justify=x+3.81,y+6.35,'left'
            if ref=='R64':ax,ay,justify=x-3.81,y+5.08,'right'
            if ref=='TH1':ax,ay,justify=x+3.81,y+10.16,'left';lines=[mpn,package]
            if ref=='U10':ax,ay,justify=x+6.35,y+45.72,'left'
            if ref=='U11':ax,ay,justify=x,y+20.32,''
            if ref in ('Q4','Q6','Q7'):ax,ay,justify=x,y+26.67,''
        if ref=='C56':ax,ay,justify=x-3.81,y+12.7,'right'
        if p['group']=='filter' and ref.startswith('C'):
            ax,ay,justify=x,y+13.97,''
            lines=['C4532X5R','1A107M280KC','1812']
        if ref=='R1':lines=['PT1206FR-','7W0R28L','1206']
        if ref=='R55':lines=['WSL1206','R0470FEA','1206 / 0.25 W']
        if ref=='C5':lines=['CC0805JRNPO9','BN471','0805']
        if ref=='R18':lines=['RC0805FR-','07100KL','0805']
        if ref in ('R29','R30','R32'):ay=y+5.08
        if ref in ('C2','C14'):ay=y+7.62
        if ref=='C14':ay=y+6.35;lines=['CL21A226','MAQNNNE','0805']
        if ref=='L2':lines=[mpn,'4 x 4 mm','H max 2.1 mm']
        if ref=='D2':ax=x-3.81;justify='right'
        if ref in ('SW1','SW2'):ay=y+10.16
        for i,text in enumerate(lines):sheet.text(text,ax,ay+i*2.54,size,justify)
        sheet.component_annotations.append({'ref':ref,'mpn':mpn,'package':package,'at':[ax,ay],'font_mm':size,'lines':lines,'placement':'below symbol; lower-right for vertical passive'})
