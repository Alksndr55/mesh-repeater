from schematic_core import Sheet, MODEL


def build():
    s = Sheet('Charger', '01. Солнечная зарядка CN3722 / аккумулятор Na-ion 1S',
              1, root=True)

    cold = bool(MODEL.get('cold_charge'))
    right = lambda x: x + (50.8 if cold else 0)

    # The force path runs left to right. Sense wires span the base shunt and,
    # when fitted, the optional 1.8-ohm series element independently.
    rail_y = 45.72
    s.sym('J7', 25.40, 43.18,
          label=(25.40, 35.56, 44.45, 38.10))
    s.sym('Q1', 119.38, rail_y)
    s.sym('D1', 148.59, rail_y, 'D_H')
    s.sym('L1', 177.80, rail_y, 'L_H')
    if cold:
        s.sym('R56', 207.01, rail_y, 'R_H')
    s.sym('R1', right(207.01), rail_y, 'R_H')
    s.sym('C1', 43.18, 64.77, 'C_V')
    s.sym('C2', 68.58, 64.77, 'C_V')
    s.sym('C8', 91.44, 64.77, 'CP_V')
    s.sym('D2', 163.83, 64.77, 'D_UP')
    s.sym('C4', right(276.86), 59.69, 'C_V')
    if not MODEL.get('battery_monitor'):
        s.sym('J8', right(278.13), 93.98)

    s.wire(('J7', 1), (38.10, 40.64), (38.10, rail_y), ('Q1', 2))
    s.global_stub('SOLAR',(86.36,rail_y),(86.36,33.02),(76.20,33.02));s.dot((86.36,rail_y))
    s.ground(('J7', 2))
    for ref in ('C1', 'C2', 'C8'):
        x, y = s.pin(ref, 1)
        s.wire((x, rail_y), (x, y))
        s.dot((x, rail_y))
        s.ground((ref, 2))
    from schematic_core import PARTS
    if 'TP9' in PARTS:
        s.sym('TP9',55.88,38.1)
        s.wire(('TP9',1),(55.88,rail_y));s.dot((55.88,rail_y))
        s.text('SOLAR',55.88,35.56,1.05,'')
    s.wire(('Q1', 3), ('D1', 2))
    s.wire(('D1', 1), ('L1', 1))
    if cold:
        s.wire(('L1', 2), ('R56', 1))
        s.wire(('R56', 2), ('R1', 1))
        s.global_stub('CHG_CS_M', (238.76, rail_y), (238.76, 33.02), (228.60, 33.02))
        s.dot((238.76, rail_y))
    else:
        s.wire(('L1', 2), ('R1', 1))
    if MODEL.get('battery_monitor'):
        s.wire(('R1',2),(right(276.86),rail_y))
    else:
        s.wire(('R1', 2), (right(295.91), rail_y), (right(295.91), 91.44), ('J8', 1))
        s.ground(('J8', 2))
    battery_rail='BAT_SYS' if MODEL.get('battery_monitor') else 'BAT'
    s.global_stub(battery_rail,(right(262.89),rail_y),(right(262.89),33.02),(right(252.73),33.02));s.dot((right(262.89),rail_y))
    s.wire((163.83, rail_y), ('D2', 1))
    s.dot((163.83, rail_y))
    s.ground(('D2', 2))
    s.wire((right(276.86), rail_y), ('C4', 1))
    s.dot((right(276.86), rail_y))
    s.ground(('C4', 2))

    s.sym('U1', 139.70, 101.60)
    s.net('U1', 15, 7.62)
    s.wire(('U1', 16), (104.14, 96.52), (104.14, 76.20),
           (119.38, 76.20), ('Q1', 1))
    s.label('GATE', (106.68, 76.20))
    # VG's capacitor returns to VCC, as specified by CN3722.
    s.sym('C3', 92.71, 101.60, 'C_H')
    s.net('C3', 1, 8.89)
    s.wire(('C3', 2), (107.95, 101.60), (107.95, 106.68), ('U1', 1))

    sense_ref = 'R56' if cold else 'R1'
    s.wire((sense_ref, 1), (201.93, 71.12), (171.45, 71.12),
           (171.45, 86.36), ('U1', 13))
    s.dot((sense_ref, 1))
    if cold:
        s.global_stub('CS_P', (201.93, 66.04), (189.23, 66.04))
        s.dot((201.93, 66.04))
    else:
        s.label('CS_P', (184.15, 71.12))
    s.wire(('R1', 2), (right(212.09), 76.20), (179.07, 76.20),
           (179.07, 93.98), ('U1', 14))
    s.dot(('R1', 2))
    s.text('BAT sense',185.42,74.93,1.05)
    s.text('Kelvin:\nCSP до R56;\nBAT после R1' if cold else 'Kelvin от R1', 173.99, 59.69, 1.05)

    # The feed-forward capacitor is parallel to the upper CV resistor.
    s.sym('R3', right(224.79), 99.06, 'R_V')
    s.sym('R4', right(224.79), 121.92, 'R_V')
    s.sym('C30', right(247.65), 104.14, 'C_V')
    s.wire((right(224.79), rail_y), ('R3', 1))
    s.dot((right(224.79), rail_y))
    s.wire(('R3', 2), (right(224.79), 110.49), ('R4', 1))
    s.dot((right(224.79), 110.49))
    s.wire((right(247.65), rail_y), ('C30', 1))
    s.dot((right(247.65), rail_y))
    s.wire(('C30', 2), (right(247.65), 110.49), (right(224.79), 110.49))
    # Two adjacent T-junctions retain the exact FB graph without the inherited
    # four-way crossing: the controller connects slightly above C30/R4.
    s.wire(('U1', 10), (right(215.90), 101.60), (right(215.90), 107.95),
           (right(224.79), 107.95))
    s.dot((right(224.79), 107.95))
    s.ground(('R4', 2))
    if MODEL.get('battery_dividers'):
        cv_note = ('Na-ion: R3 61,9k / R4 100k; C30 12pF; CV ≈ 3,915 В\n'
                   'LTO 2S: R3 121k / R4 100k; C30 6,8pF; CV ≈ 5,345 В\n'
                   'Делитель: 0,1%; ТКС ≤25 ppm/°C. LTO: запаять балансир.')
    else:
        cv_note = ('Na-ion: R3 6,34k / R4 10k; C30 12pF; CV ≈ 3,948 В\n'
                   'LTO 2S: R3 13k / R4 10,5k; C30 6,8pF; CV ≈ 5,408 В\n'
                   'Делитель: 0,1%; LTO ТКС ≤25 ppm/°C. Запаять балансир.')
    s.text(cv_note, 305.0 if cold else 294.64 if MODEL.get('battery_dividers') else 234.95,
           119.38 if MODEL.get('battery_dividers') else 129.54, 1.05)

    # MPPT enters from the left; its divider shares the input supply net.
    s.sym('R7', 45.72, 106.68, 'R_V')
    s.sym('R8', 45.72, 127.00, 'R_V')
    s.net('R7', 1, 7.62)
    s.wire(('R7', 2), (45.72, 116.84), ('R8', 1))
    s.dot((45.72, 116.84))
    s.wire(('U1', 7), (45.72, 116.84))
    s.ground(('R8', 2))
    s.text('MPPT: Vmp ≈ 11,96 В.\nR7/R8 = 105/10 кОм.\n'
           'Vmp ≈ 18 В: изменить R7.', 20.32, 148.59, 1.05)
    s.text('Панель 12 В.\nХолодный Voc ≤ 24 В.', 20.32, 163.83, 1.05)

    # Compensation networks remain directly beneath their controller pins.
    s.sym('R5', 95.25, 152.40, 'R_V',
          label=(85.09, 151.13, 85.09, 153.67))
    s.sym('C5', 123.19, 152.40, 'C_V',
          label=(110.49, 151.13, 110.49, 153.67))
    s.wire(('U1', 8), (95.25, 142.24), ('R5', 1))
    s.wire((123.19, 142.24), ('C5', 1))
    s.dot((123.19, 142.24))
    s.ground(('R5', 2))
    s.ground(('C5', 2))
    s.sym('R6', 139.70, 152.40, 'R_V')
    s.sym('C6', 139.70, 165.10, 'C_V')
    s.wire(('U1', 9), ('R6', 1))
    s.wire(('R6', 2), ('C6', 1))
    s.ground(('C6', 2))
    s.sym('C7', 171.45, 152.40, 'C_V')
    s.wire(('U1', 11), (171.45, 142.24), ('C7', 1))
    s.ground(('C7', 2))
    s.ground(('U1', 2))
    s.ground(('U1', 3))
    s.nc('U1', 12)

    s.sym('R9', 190.50, 123.19, 'R_V')
    s.wire(('U1', 6), (190.50, 109.22), ('R9', 1))
    s.ground(('R9', 2))
    s.text('TEMP: защита\nотключена по заданию.', 181.61, 144.78, 1.05)

    # Open-collector status nets are labelled at both the IC and the LEDs.
    s.sym('R10', right(228.60), 147.32, 'R_V')
    s.sym('R11', right(256.54), 147.32, 'R_V')
    s.sym('D3', right(228.60), 167.64, 'LED_V')
    s.sym('D4', right(256.54), 167.64, 'LED_V')
    s.wire(('R10', 1), (right(228.60), 137.16), (right(256.54), 137.16), ('R11', 1))
    s.global_stub('SOLAR',(right(256.54),137.16),(right(276.86),137.16),angle=180)
    s.wire(('R10', 2), ('D3', 2))
    s.wire(('R11', 2), ('D4', 2))
    s.net('U1', 4, 7.62)
    s.net('U1', 5, 7.62)
    s.net('D3', 1, 6.35)
    s.net('D4', 1, 6.35)

    if cold:
        s.text('Na-ion / опция: R56 = 1,8 Ом; холод ≈ 96 мА; тепло ≈ 665 мА. Управление: лист '+str(MODEL['sheet_pages']['Thermal'])+'.\n'
               'LTO / без опции: R56 = 0 Ом; узел Thermal не ставить. R1 = 0,28 Ом: ток ≈ 714 мА, максимум ≈ 784 мА.',
               101.60, 181.61, 1.05)
    else:
        s.text('R1 = 0,28 Ом / 1%: Iзар ≈ 714 мА; расчётный максимум ≈ 784 мА.',
               101.60, 184.15, 1.05)
    s.flag('SOLAR', 30.48, 179.07, 1)
    s.flag('BAT_SYS' if MODEL.get('battery_monitor') else 'BAT', 58.42, 179.07, 2)
    s.flag('GND', 86.36, 179.07, 3)
    return s
