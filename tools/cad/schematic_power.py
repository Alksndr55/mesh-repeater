"""Compact, explicitly wired power sheet for the editable S3 schematic.

Symbols retain their normal size. Coordinates use the 1.27 mm pin grid;
all visible reference/value properties retain the same upright two-line order.
"""
from schematic_core import Sheet,MODEL,PARTS


def _g(x, y):
    return round(x * 1.27, 5), round(y * 1.27, 5)


def _side_label(x, y):
    xx, yy = _g(x, y)
    return xx + 3.81, yy - 1.27, xx + 3.81, yy + 1.27


def _sym(sheet, ref, x, y, style=None, label=None):
    sheet.sym(ref, *_g(x, y), style=style, label=label)


def _ground(sheet, point):
    sheet.ground(point, length=2.54)


def _converter():
    s = Sheet('Converter', 'TPS63802 — питание и двухкаскадный LC-фильтр', 2)
    _sym(s, 'U2', 69, 66,
         label=(*_g(69, 44), *_g(69, 46)))
    _sym(s, 'L2', 69, 31, 'L_H')
    _sym(s, 'C12', 22, 60, 'C_V', _side_label(22, 60))
    _sym(s, 'C13', 39, 60, 'C_V', _side_label(39, 60))
    _sym(s, 'R15', 16, 76, 'R_V', _side_label(16, 76))
    _sym(s, 'R16', 16, 90, 'R_V', _side_label(16, 90))
    _sym(s, 'R17', 31, 90, 'R_V', _side_label(31, 90))
    _sym(s, 'C14', 94, 64, 'C_V', _side_label(94, 64))
    _sym(s, 'R13', 107, 64, 'R_V', _side_label(107, 64))
    _sym(s, 'R14', 107, 82, 'R_V', _side_label(107, 82))
    if 'R18' in PARTS:_sym(s, 'R18', 129, 82, 'R_V', _side_label(129, 82))
    _sym(s, 'TP3', 118, 52)
    if 'TP5' in PARTS:_sym(s, 'TP5', 140, 90)
    if 'TP7' in PARTS:_sym(s, 'TP7', 80, 87)

    # S4.5 reserve sites are wired directly to the same local input/output
    # rails as C12/C14. DNP denotes an empty site, not a chosen capacitance.
    for ref,x in [('C52',22),('C53',39),('C54',94),('C55',112)]:
        _sym(s,ref,x,34,'C_V',_side_label(x,34))
        _ground(s,(ref,2))
    s.wire(_g(16,52),_g(16,26),_g(39,26))
    for ref,x in [('C52',22),('C53',39)]:
        s.wire((ref,1),_g(x,26));s.dot(_g(x,26))
    s.wire(_g(94,26),_g(120,26),_g(120,56));s.dot(_g(120,56))
    for ref,x in [('C54',94),('C55',112)]:
        s.wire((ref,1),_g(x,26));s.dot(_g(x,26))

    # Both local input capacitors are normal vertical shunts below BAT.
    s.wire(_g(16, 52), _g(50, 52), _g(50, 56), ('U2', 10))
    s.global_stub('BAT_SYS' if MODEL.get('battery_monitor') else 'BAT',_g(39,26),_g(47,26),angle=180)
    for ref, x in [('C12', 22), ('C13', 39)]:
        s.wire((ref, 1), _g(x, 52)); s.dot(_g(x, 52))
        _ground(s, (ref, 2))

    # EN divider: BAT -> R15 -> EN_UV -> R16 -> GND.
    if MODEL.get('battery_monitor'):
        s.net('R15',1,7.62)
    else:
        s.wire(('R15', 1), _g(16, 52)); s.dot(_g(16, 52))
    s.wire(('R15', 2), _g(16, 82), ('R16', 1))
    s.wire(('U2', 1), _g(47, 66), _g(47, 82), _g(16, 82))
    s.dot(_g(16, 82)); s.label('EN_UV', _g(33, 82))
    _ground(s, ('R16', 2))

    s.wire(('U2', 9), _g(63, 31), ('L2', 1))
    s.wire(('U2', 7), _g(75, 31), ('L2', 2))
    s.label('LX1', _g(63, 43)); s.label('LX2', _g(75, 43))

    # C14 hangs below VOUT immediately before the additional LC network.
    if 'R55' in PARTS:
        _sym(s,'R55',125,56,'R_H',(*_g(125,48),*_g(125,50)))
        s.wire(('U2',6),('R55',1))
    else:s.wire(('U2', 6), _g(130, 56))
    s.label('SYS_PRE', _g(88, 56))
    s.wire(('C14', 1), _g(94, 56)); s.dot(_g(94, 56))
    _ground(s, ('C14', 2))
    s.wire(('TP3', 1), _g(118, 56)); s.dot(_g(118, 56))

    s.wire(('R13', 1), _g(107, 56)); s.dot(_g(107, 56))
    s.wire(('R13', 2), _g(107, 74), ('R14', 1))
    s.wire(('U2', 4), _g(88, 66), _g(88, 74), _g(107, 74))
    s.dot(_g(107, 74)); s.label('FB_SYS', _g(101, 74))
    _ground(s, ('R14', 2))

    s.wire(('U2', 3), _g(65, 90))
    s.wire(('U2', 8), _g(73, 90)); s.dot(_g(73, 90))
    s.wire(_g(65, 90), _g(80 if 'TP7' in PARTS else 73, 90))
    if 'TP7' in PARTS:s.wire(('TP7', 1), _g(80, 90))
    s.dot(_g(69, 90)); _ground(s, _g(69, 90))

    if 'R18' in PARTS:
        s.wire(('R18', 1), _g(129, 56)); s.dot(_g(129, 56))
        s.wire(('U2', 5), _g(88, 76), _g(88, 93), _g(140, 93))
        s.wire(('R18', 2), _g(129, 93))
        s.wire(('TP5', 1), _g(140, 93))
        s.dot(_g(129, 93));s.label('PG_SYS', _g(100, 93))
    else:s.nc('U2',5)

    # Actual parallel MLCC banks, one22mOhm resistor before each entire bank.
    _sym(s,'L3',138,56,'L_H')
    _sym(s,'L4',220,56,'L_H')
    if 'TP4' in PARTS:_sym(s,'TP4',292,52)
    _sym(s,'TP6',121,113)
    _sym(s,'TP1',39,48)
    if MODEL.get('battery_monitor'):
        tx,ty=s.pin('TP1',1)
        s.global_stub('BAT',(tx,ty),(tx-7.62,ty))
    else:
        s.wire(('TP1',1),_g(39,52));s.dot(_g(39,52))
    if 'R55' in PARTS:
        s.wire(('R55',2),('L3',1))
        s.wire(_g(130,56),_g(130,42));s.dot(_g(130,56))
        s.wire(_g(130,42),_g(135,42))
        s.label('SYS_LC_IN',_g(135,42))
    else:s.wire(_g(130,56),('L3',1))
    s.wire(('L3',2),('L4',1))
    s.label('FILTER_MID',_g(158,56))
    if 'TP8' in PARTS:
        s.sym('TP8',228.6,63.5)
        s.wire(('TP8',1),(228.6,71.12));s.dot((228.6,71.12))
        s.text('FILTER_MID',228.6,60.96,1.05,'')
    if 'J11' in PARTS:
        _sym(s,'J11',265,56,'JUMPER_H')
        s.wire(('L4',2),('J11',1))
        s.label('FILTER_OUT',_g(241,56))
        s.wire(('J11',2),_g(303,56))
        s.label('SYS_3V3',_g(303,56),angle=180,global_=True)
        if 'TP4' in PARTS:s.wire(('TP4',1),_g(292,56));s.dot(_g(292,56))
    else:
        s.global_stub('FILTER_OUT',('L4',2),_g(251,56),angle=180)
        s.text('FILTER_OUT → межплатные штыри → J11.1 (LOGIC).',309.88,83.82,1.05)
    _ground(s,('TP6',1))
    for stage,(rref,xbase) in enumerate([('R40',185.42),('R41',299.72)]):
        s.sym(rref,xbase,88.9,'R_V')
        s.wire((xbase,71.12),(rref,1));s.dot((xbase,71.12))
        refs=MODEL['filter_bank']['refs'][stage]
        previous=s.pin(rref,2)
        for offset in range(0,len(refs),5):
            row=refs[offset:offset+5]; y=116.84+33.02*(offset//5)
            top=y-10.16;bottom=y+10.16
            xs=[xbase+7.62+16.51*i for i in range(len(row))]
            s.wire(previous,(xbase,top),(xs[-1],top))
            if offset:s.dot(previous)
            previous=(xbase,top)
            for ref,x in zip(row,xs):
                s.sym(ref,x,y,'C_V')
                s.wire((x,top),(ref,1));s.dot((x,top))
                s.wire((ref,2),(x,bottom))
            if len(xs)>1:s.wire((xs[0],bottom),(xs[-1],bottom))
            for x in xs[1:-1]:s.dot((x,bottom))
            s.wire((xs[-1],bottom),(xs[-1]+7.62,bottom))
            s.ground((xs[-1]+7.62,bottom),2.54)
        s.text('Каскад '+str(stage+1)+': Cэфф ≥ 330 мкФ при 3,3 В',xbase,177.8,1.05)

    # TXEN directly controls MODE through R21. RF_QUIET and diode OR removed.
    if 'R21' in PARTS:
        _sym(s, 'R21', 38, 110, 'R_H')
        s.wire(_g(24,110),('R21',1)); s.label('RADIO_TXEN',_g(24,110),global_=True)
        s.wire(('R21',2),_g(48,110),_g(48,76),('U2',2))
    else:
        s.wire(_g(48,110),_g(48,76),('U2',2))
        s.global_stub('MODE',_g(48,110),_g(40,110))
    if 'R21' in PARTS:s.label('MODE',_g(48,104))
    s.wire(('R17',1),_g(31,84),_g(48,84));s.dot(_g(48,84))
    _ground(s,('R17',2))
    s.flag('FILTER_OUT' if 'J11' not in PARTS else 'SYS_3V3',360.68,180.34,5)
    s.text('SYS_PRE: 3,300 В; FB до L3. C14 — локальная ёмкость TPS63802.',15.24,160.02,1.15)
    if 'R55' in PARTS:
        s.text('R55: 47 мОм последовательно перед L3; падение 47 мВ/А. FB и C14 до R55.',185.42,185.42,1.05)
    s.text('TXEN=0: PFM; TXEN=1: forced PWM.',15.24,167.64,1.15)
    if MODEL.get('en_assembly_variants'):
        s.text('EN / Na: R15=40,2 кОм; R16=49,9 кОм; выкл.≈1,806 В; вкл.≈1,986 В.',15.24,173.99,1.05)
        s.text('EN / LTO: R15=130 кОм; R16=49,9 кОм; выкл.≈3,605 В; вкл.≈3,966 В (тип.).',15.24,178.435,1.05)
    else:s.text('EN: выкл. ≈1,806 В; вкл. ≈1,986 В.',15.24,175.26,1.15)
    s.text('J11 соединяет выход LC с SYS_3V3 всех нагрузок. Снять ДО USB; вернуть после отключения USB.',15.24,182.88,1.15)
    s.text('L3, L4: CDRH127/LDNP-2R4NC, 2,4 мкГн каждый. R40/R41: 22 мОм только в ветвях C.',15.24,193.04,1.15)
    s.text(MODEL['filter_bank']['schematic_note'],15.24,200.66,1.15)
    s.text('Cэфф ≥330 мкФ — требование приёмки; типовые кривые не дают гарантии. Проверить банк и запуск.',15.24,208.28,1.15)
    s.text('Проверить минимумы/максимумы 3V3 при подключении USB, PFM/PWM и скачке нагрузки.',15.24,215.9,1.15)
    s.text('C12 + C52: два локальных 10 мкФ / 16 В / 0805. C53, C54, C55: резерв 1206 / DNP.',15.24,222.25,1.15)
    return s

def build():
    return [_converter()]
