"""Compact module interconnect, controls and battery measurement."""
from schematic_core import Sheet

def build():
    s=Sheet('Modules','Nice!Nano, HT-RA62, управление и измерение батареи',3)
    s.sym('M1',88.9,80.01).sym('M2',215.9,80.01)
    for a,b in [(1,4),(2,6),(7,10),(21,11)]:s.wire(('M1',a),('M2',b))
    for ref,a,b,x in [('R23',3,12,153.67),('R24',5,14,153.67),('R25',4,15,153.67),('R26',6,13,175.26)]:
        y=s.pin('M1',a)[1]
        s.sym(ref,x,y,'R_H_REV' if ref=='R26' else 'R_H',label=(x-3.81,y-1.905,x+5.08,y-1.905))
        if ref=='R26':s.wire(('M1',a),(ref,2));s.wire((ref,1),('M2',b))
        else:s.wire(('M1',a),(ref,1));s.wire((ref,2),('M2',b))
    for a,n in [(1,'RADIO_RST'),(2,'RADIO_DIO1'),(7,'RADIO_BUSY'),(21,'RADIO_RXEN')]:s.label(n,(142.24,s.pin('M1',a)[1]))
    for pin in [12,13]:s.nc('M1',pin)
    from schematic_core import MODEL
    for pin in ([8] if MODEL.get('rf_connector') else [1,8]):s.nc('M2',pin)
    if MODEL.get('rf_connector'):
        rf_y=116.84 if MODEL.get('rf_filter_option') else 101.6
        s.sym('J13',317.5,rf_y,'COAX')
        ant=s.pin('M2',1)
        if MODEL.get('rf_filter_option'):
            s.sym('FL1',279.4,rf_y,'SAW')
            s.sym('NT1',279.4,104.14,'NETTIE')
            s.wire(ant,(246.38,ant[1]),(246.38,rf_y),('FL1',2))
            s.wire(('FL1',5),('J13',1))
            s.wire(('NT1',1),(259.08,104.14),(259.08,rf_y));s.dot((259.08,rf_y))
            s.wire(('NT1',2),(299.72,104.14),(299.72,rf_y));s.dot((299.72,rf_y))
            s.wire((254.0,rf_y),(254.0,119.38),(248.92,119.38));s.dot((254.0,rf_y))
            s.label('ANT_RF',(248.92,119.38),angle=180)
            s.wire((304.8,rf_y),(304.8,121.92),(299.72,121.92));s.dot((304.8,rf_y))
            s.label('ANT_SMA',(299.72,121.92),angle=180)
            for pin in (1,3,4,6):s.wire(('FL1',pin),(s.pin('FL1',pin)[0],132.08))
            s.wire((271.78,132.08),(287.02,132.08))
            s.dot((276.86,132.08));s.dot((281.94,132.08));s.ground((287.02,132.08),2.54)
            s.text('FL1 — опция 868–870 МГц, TX ≤ +13 dBm.\nДо установки разрезать медь NT1 под FL1.\nБез FL1 оставить NT1 целой.',266.7,151.13,1.05,'left')
        else:
            s.wire(ant,(246.38,ant[1]),(246.38,rf_y),('J13',1))
            s.label('ANT_RF',(269.24,rf_y))
        s.ground(('J13',2),2.54)
    for pin in [8,10,17,18,19,20,24,25,15,16]:s.net('M1',pin,5.08)
    s.nc('M1',14)
    # TXEN is DIO2: only a high-impedance sense is taken.
    tx=s.pin('M2',5);dio=s.pin('M2',7);x=182.88
    s.wire(tx,(x,tx[1]),(x,dio[1]),dio)
    s.wire((x,dio[1]),(x,114.3));s.dot((x,dio[1]))
    s.global_stub('RADIO_TXEN',(x,114.3),(187.96,114.3),angle=180)
    s.sym('R35',162.56,121.92,'R_H');s.net('R35',1,5.08)
    cs_y=s.pin('M2',15)[1]
    s.wire(('R35',2),(177.8,121.92),(177.8,cs_y));s.dot((177.8,cs_y))
    for ref,pins in [('M1',[11,22,23,26]),('M2',[2,9,16])]:
        coords=[s.pin(ref,n) for n in pins];y=max(p[1] for p in coords)+3.81
        for x,a in coords:s.wire((x,a),(x,y))
        s.wire((coords[0][0],y),(coords[-1][0],y))
        for x,a in coords[1:-1]:s.dot((x,y))
        s.ground((coords[1][0],y),2.54)
    # User-requested direct feed to the module3V3 pin.
    y=s.pin('M1',9)[1]
    s.wire(('M1',9),(30.48,y),(30.48,39.37))
    s.global_stub('SYS_3V3',(30.48,39.37),(25.4,39.37))
    s.sym('C23',251.46,73.66,'C_V').sym('C24',274.32,73.66,'C_V')
    y=s.pin('M2',3)[1]
    s.wire(('M2',3),(284.48,y));s.label('RADIO_3V3',(274.32,y))
    s.sym('FB1',251.46,38.1,'L_H')
    s.global_stub('SYS_3V3',('FB1',1),(238.76,38.1))
    s.wire(('FB1',2),(284.48,38.1),(284.48,y))
    for ref in ['C23','C24']:
        x,_=s.pin(ref,1);s.wire((x,y),(ref,1));s.dot((x,y));s.ground((ref,2),2.54)
    s.sym('C21',218.44,167.64,'C_V').sym('C22',243.84,167.64,'C_V')
    s.wire((218.44,157.48),(243.84,157.48));s.global_stub('SYS_3V3',(218.44,157.48),(210.82,157.48))
    for ref in ['C21','C22']:
        x,_=s.pin(ref,1);s.wire((x,157.48),(ref,1));s.ground((ref,2),2.54)
    s.sym('R27',30.48,119.38,'R_V').sym('R28',30.48,139.7,'R_V').sym('C25',55.88,139.7,'C_V')
    s.net('R27',1,5.08)
    s.wire(('R27',2),(30.48,129.54),('R28',1));s.dot((30.48,129.54))
    s.wire((30.48,129.54),(55.88,129.54),('C25',1));s.global_stub('BAT_ADC',(55.88,129.54),(63.5,129.54),angle=180)
    s.ground(('R28',2),2.54);s.ground(('C25',2),2.54)
    s.sym('SW2',38.1,177.8,'SW_H').sym('SW1',91.44,177.8,'SW_H')
    for ref in ['SW2','SW1']:s.net(ref,1,5.08);s.ground((ref,2),2.54)
    s.sym('R31',104.14,149.86,'R_V').sym('C26',130.81,172.72,'C_V')
    s.net('R31',1,5.08)
    s.wire(('R31',2),(104.14,160.02),(130.81,160.02),('C26',1))
    s.global_stub('USER_BTN',(130.81,160.02),(140.97,160.02),angle=180);s.ground(('C26',2),2.54)
    adc_note=('ADC: BAT/2; τ ≈ 110 мс. Калибровка ADC.'
              if MODEL.get('battery_dividers') else 'ADC: BAT/2; установление ≈ 50 мс.')
    s.text(adc_note,15.24,157.48,1.27)
    s.text('SPI: 33 Ом у драйверов.\n'+('ANT: J13 / SMA, 50 Ом.\n' if MODEL.get('rf_connector') else 'ANT: штатный IPEX.\n')+'TXEN → MODE и watchdog.\nP1.06 свободен.\nBUSY=P0.29; GPS_EN=P0.24.\nGPS_EN=HIGH: питание GPS включено.',228.6,124.46,1.05)
    if MODEL.get('rf_connector'):
        s.text(MODEL['rf_connector']['module_configuration_ru'],317.5,152.4 if MODEL.get('rf_filter_option') else 137.16,1.05,'left')
    s.text('3V3 через J11; RAW/BAT: NC. USB-зарядник отключить.\nСнять шунт J11 ДО подключения USB.\nВернуть J11 только после отключения USB.',142.24,188,1.27)
    s.text('Модем: отдельная ветвь J11 → FB1 → RADIO_3V3. GPS/RTC питаются до FB1.',142.24,210.82,1.15)
    s.text('FB1: DCR ≤20 мОм; около 3 мВ при 150 мА. Проверить броски питания при TX осциллографом.',142.24,218.44,1.15)
    return s
