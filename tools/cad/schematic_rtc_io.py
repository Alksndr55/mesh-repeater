"""Compact RTC, expansion headers and shield connections."""
from schematic_core import Sheet, define, box, line, chip, PARTS

def build():
    s=Sheet('RTC_IO','DS3231M / CR2032, разъёмы и экран',4)
    define('RTC_J2_LEFT',[('1','1',-10.16,-2.54,'L','passive'),('2','2',-10.16,2.54,'L','passive')],box(-5.08,-5.08,5.08,5.08),-8.89)
    s.sym('U4',78.74,83.82)
    s.sym('BT1',30.48,91.44,label=(30.48,110.49,30.48,113.03))
    s.sym('C27',38.1,60.96,'C_V')
    for ref,x in [('R29',114.3),('R30',139.7)]:s.sym(ref,x,55.88,'R_V')
    rail_y=50.8
    s.wire((25.4,rail_y),(139.7,rail_y));s.label('SYS_3V3',(25.4,rail_y),global_=True)
    for ref in ['C27','R29','R30']:
        x,_=s.pin(ref,1);s.wire((ref,1),(x,rail_y));s.dot((x,rail_y))
    s.wire(('U4',2),(53.34,68.58),(53.34,rail_y));s.dot((53.34,rail_y))
    s.ground(('C27',2),2.54)
    s.wire(('BT1',1),(30.48,81.28),('U4',6));s.label('RTC_BAT',(38.1,81.28))
    s.ground(('BT1',2),2.54)
    for pin,ref,x,net in [(7,'R29',114.3,'SDA'),(8,'R30',139.7,'SCL')]:
        _,y=s.pin('U4',pin)
        s.wire(('U4',pin),(177.8,y));s.wire((ref,2),(x,y));s.dot((x,y))
        s.label(net,(177.8,y),180,True)
    s.nc('U4',1);s.nc('U4',3);s.nc('U4',4)
    s.wire(('U4',5),(53.34,104.14),(53.34,118.11))
    s.ground((53.34,118.11),2.54)
    s.text('CR2032: без зарядки. Установить после пайки.',15.24,132.08,1.27)
    s.text('DS3231M: SO-8; точность ±5 ppm; SQW только 1 Гц.',15.24,138.43,1.27)
    s.text('I²C: 0x68. INT/SQW не используется.',15.24,144.78,1.27)
    s.text('EOSC=0; BBSQW=0; INTCN=1; EN32kHz=0.',15.24,151.13,1.27)
    s.text('Проверять OSF; снять после установки времени.',15.24,157.48,1.27)
    for ref,x,y in [('J3',205.74,60.96),('J5',205.74,103.0)]:
        s.sym(ref,x,y)
        for pin in range(1,5):s.net(ref,pin,5.08)
    build_gps(s)
    if 'SH1' in PARTS:
        s.sym('SH1',210.82,151.13,label=(210.82,133.35,210.82,135.89))
        pts=[]
        for pin in range(1,5):
            _,y=s.pin('SH1',pin);p=(228.6,y);pts.append(p);s.wire(('SH1',pin),p)
        s.wire(*pts)
        for p in pts[1:-1]:s.dot(p)
        s.ground(pts[-1],2.54)
    for ref,x,y in [('H1',251.46,146.05),('H2',278.13,146.05),('H3',251.46,170.18),('H4',278.13,170.18)]:
        if ref in PARTS:
            s.sym(ref,x,y)
            if PARTS[ref]['nets']:s.net(ref,'1',2.54)
    s.text('Средний экран: отдельная плата 90×60; GND через стойки.',195.58,186.69,1.27)
    return s

def build_gps(s):
    # Exact P3 numbering, names always describe the GPS module direction.
    chip('GPS_J8',[(str(i),name,-12.7,(i-4.5)*5.08,'L','passive') for i,name in enumerate(['RESET_N','PPS','WAKE_UP','RXD GPS','TXD GPS','V_BCKP','VCC','GND'],1)]+[('MP','Mounts',0,30.48,'B','passive')],20.32,45.72)
    define('GPS_NMOS',[('1','G',-10.16,0,'L','input',5.08),('3','D',0,-7.62,'T','passive',2.54),('2','S',0,7.62,'B','passive',2.54)],
        line([(-5.08,0),(-2.54,0),(-2.54,-2.54),(-2.54,2.54)])+line([(-1.27,-2.54),(-1.27,2.54)])+line([(0,-5.08),(0,-1.27),(-1.27,-1.27)])+line([(0,5.08),(0,1.27),(-1.27,1.27)])+line([(0,1.27),(1.27,0),(1.27,2.54),(0,1.27)]),-12.7)
    chip('GPS_BUF',[('8','VCC GPS',-17.78,-17.78,'L','power_in'),('2','1A / MCU TX',-17.78,-7.62,'L','input'),('6','1Y / GPS RX',17.78,-7.62,'R','output'),('5','2A / GPS TX',-17.78,2.54,'L','input'),('3','2Y / MCU RX',17.78,2.54,'R','output'),('1','~{OE1}',-7.62,25.4,'B','input'),('7','~{OE2}',0,25.4,'B','input'),('4','GND',7.62,25.4,'B','power_in')],25.4,40.64)
    s.sym('J4',385,55,'GPS_J8')
    for pin in (1,2,3):s.nc('J4',pin)
    for pin in (4,5,6,7,8):s.net('J4',pin,5.08)
    s.ground(('J4','MP'),2.54)
    s.sym('Q2',270,55,'PMOS')
    s.net('Q2',2);s.net('Q2',3)
    s.sym('R42',245,77,'R_V');s.net('R42',1)
    s.sym('Q3',270,100,'GPS_NMOS',label=(280.16,98.73,280.16,101.27));s.ground(('Q3',2),2.54)
    s.wire(('Q2',1),(270,85),('Q3',3));s.wire(('R42',2),(245,85),(270,85));s.dot((270,85));s.label('GPS_GATE',(255.16,85))
    s.sym('R44',246,100,'R_H')
    s.global_stub('GPS_EN',('R44',1),(234.95,100),(234.95,132.08),(229.87,132.08))
    s.wire(('R44',2),('Q3',1))
    s.sym('R43',255.27,117,'R_V');s.wire(('R43',1),(255.27,100));s.dot((255.27,100));s.ground(('R43',2),2.54);s.label('GPS_EN_GATE',(252,100))
    s.sym('U7',330,140,'GPS_BUF')
    for pin in (8,2,6,5,3):s.net('U7',pin,5.08)
    for pin in (1,7,4):s.ground(('U7',pin),3.81)
    s.sym('R45',300,93,'R_V');s.net('R45',1);s.net('R45',2)
    s.sym('R46',300,60,'R_V');s.net('R46',1);s.net('R46',2)
    s.sym('C56',391.16,153.67,'C_V',label=(387.35,152.4,387.35,154.94));s.net('C56',1);s.ground(('C56',2),2.54)
    s.sym('C57',330,65,'C_V');s.net('C57',1);s.ground(('C57',2),2.54)
    s.flag('GPS_3V3',285.75,30.48,407)
    s.text('GPS_EN = P0.24: HIGH включено; LOW / Hi-Z выключено.',240,199,1.05)
    s.text('J4.6: резерв 3,3 В постоянно; J4.7: питание через Q2.',240,205,1.05)
    s.text('U7: Ioff; UART не подпитывает выключенный GPS.',240,211,1.05)
    s.text('J4.1 / .3: внутренние подтяжки L76K; .2 PPS не используется.',240,217,1.05)
    s.text('T114 V2.1 P3: порядок контактов; корпус кабеля проверить.',240,223,1.05)
