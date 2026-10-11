"""Optional T2 low-current control, copied pin-for-pin from CN3722 Cold Current."""
from schematic_core import Sheet, PARTS

def build():
    t=Sheet('Thermal','Снижение тока на холоде / Na-ion / опция POWER',7)
    # One continuous drawing: supply reference across the top, NTC on the left,
    # threshold and hysteresis immediately beside comparator A, short detection
    # below, and the gate driver to the right. Only intersheet supplies/control use
    # global labels. Local labels name a visible wire, never replace a connection.
    t.sym('R57',38.10,44.45,'R_V');t.net('R57',1,7.62)
    t.sym('U11',38.10,88.90,'LM285Z',label=(60.96,87.63,60.96,90.17))
    t.wire(('R57',2),('U11',2));t.dot((38.10,57.15));t.nc('U11',1)
    t.ground(('U11',3));t.wire((38.10,57.15),(300.99,57.15));t.label('CHG_VREF',(45.72,57.15))

    t.sym('R59',95.25,88.90,'R_V')
    t.wire((95.25,57.15),('R59',1));t.dot((95.25,57.15))
    t.sym('TH1',95.25,158.75,'NTC_V',label=(111.76,154.94,111.76,157.48))
    t.sym('C61',128.27,158.75,'C_V')
    t.wire(('R59',2),(95.25,115.57),('TH1',1));t.dot((95.25,115.57));t.dot((95.25,133.35))
    t.ground(('TH1',2));t.ground(('C61',2));t.text('-t°',87.63,161.29,1.0)

    t.sym('R60',190.50,77.47,'R_V');t.sym('R69',190.50,90.17,'R_V')
    t.sym('R61',171.45,101.60,'R_V',label=(166.37,100.33,166.37,102.87))
    t.wire((190.50,57.15),('R60',1));t.dot((190.50,57.15))
    t.wire(('R60',2),('R69',1));t.label('CHG_VTH_UP',(190.50,83.82));t.wire(('R69',2),(171.45,95.25),('R61',1));t.dot(('R69',2));t.ground(('R61',2),2.54)

    t.sym('U10',245.11,120.65,'LM393Dual',label=(260.35,83.82,260.35,86.36))
    t.wire(('R69',2),(190.50,107.95),('U10',3));t.label('CHG_VTH',(194.31,107.95))
    t.wire((95.25,115.57),('U10',2));t.label('CHG_TSENSE',(151.13,115.57))
    t.wire((95.25,133.35),('U10',5));t.wire((128.27,133.35),('C61',1));t.dot((128.27,133.35))

    t.sym('R64',76.20,154.94,'R_V',label=(72.39,153.67,72.39,156.21))
    t.sym('R65',76.20,179.07,'R_V',label=(72.39,177.8,72.39,180.34))
    t.wire((76.20,57.15),('R64',1));t.dot((76.20,57.15))
    t.wire(('R64',2),(76.20,167.64),('R65',1));t.dot((76.20,167.64));t.ground(('R65',2))
    t.wire((76.20,167.64),(200.66,167.64),(200.66,140.97),('U10',6));t.label('CHG_VSHORT',(151.13,167.64))

    t.sym('R70',232.41,69.85,'R_H_REV');t.sym('R62',265.43,69.85,'R_H_REV')
    t.wire((218.44,107.95),(218.44,69.85),('R70',2));t.dot((218.44,107.95))
    t.wire(('R70',1),('R62',2));t.label('CHG_HYST_MID',(241.3,69.85));t.wire(('R62',1),(285.75,69.85),(285.75,111.76));t.dot((285.75,111.76))
    t.wire(('U10',1),(300.99,111.76),(300.99,137.16),('U10',7));t.dot((300.99,111.76))
    t.label('CHG_WARM',(274.32,111.76))
    t.sym('R63',300.99,88.90,'R_V');t.wire((300.99,57.15),('R63',1));t.wire(('R63',2),(300.99,101.6),(293.37,101.6),(293.37,111.76));t.dot((293.37,111.76))
    t.sym('C62',300.99,158.75,'C_V');t.wire((300.99,137.16),('C62',1));t.dot((300.99,137.16));t.ground(('C62',2))

    t.sym('C60',321.31,83.82,'C_V')
    t.wire(('U10',8),(245.11,74.93),(321.31,74.93),('C60',1));t.dot((321.31,74.93))
    t.global_stub('SOLAR',(321.31,74.93),(340.36,74.93),angle=180);t.ground(('C60',2));t.ground(('U10',4))
    t.sym('R66',328.93,111.76,'R_H');t.wire((300.99,111.76),('R66',1))
    t.sym('Q5',359.41,111.76,'NMOS',label=(375.92,110.49,375.92,113.03))
    t.wire(('R66',2),('Q5',1));t.label('CHG_G_ENABLE',(336.55,111.76));t.dot((342.90,111.76))
    t.sym('R67',342.90,146.05,'R_V');t.wire((342.90,111.76),('R67',1));t.ground(('R67',2));t.ground(('Q5',2))
    t.sym('R68',361.95,88.90,'R_V');t.wire(('R68',2),('Q5',3));t.label('CHG_PULLDOWN',(361.95,101.60));t.net('R68',1,5.08)
    # The bypass devices are drawn together on this option sheet. CSP remains
    # upstream of R56 on sheet 1; R1 stays in series for every assembly variant.
    for ref,x in [('Q4',40.64),('Q6',82.55),('Q7',124.46)]:
        t.sym(ref,x,215.9,'PMOS')
        t.wire((ref,2),(x-10.16,198.12));t.dot((x-10.16,198.12))
        t.wire((ref,3),(x+10.16,219.71));t.dot((x+10.16,219.71))
        t.wire((ref,1),(x,232.41));t.dot((x,232.41))
    t.global_stub('CS_P',(114.3,198.12),(17.78,198.12))
    t.global_stub('CHG_CS_M',(50.8,219.71),(147.32,219.71),angle=180)
    t.global_stub('CHG_G_SHUNT',(40.64,232.41),(147.32,232.41),angle=180)
    t.sym('R58',175.26,246.38,'R_V');t.net('R58',1,3.81);t.net('R58',2,3.81)
    t.text('Q4 / Q6 / Q7: S = до R56; D = после R56.\nR58 закрывает ключи при выключенном управлении.',20.32,260.35,1.05)
    t.text('TH1: B57861S0103F040; 10k, B25/100 = 3988 K, R/T 8016.\nОдин NTC: на плате либо на проводах у аккумулятора.\nНа плате измеряется температура под экраном.\nОбрыв или КЗ NTC → холодный ток.',203.20,191.77,1.05)
    t.text('R60 + R69 = 130k; R62 + R70 = 1,15M.\nНоминальные пороги: холод −17,4 °C; тепло −14,5 °C.\nOUT A и OUT B — соединённые открытые коллекторы.\nCHG_WARM высокий: Q5 включён, R56 обойдён.\nCHG_WARM низкий: Q5 выключен, R58 закрывает Q4/Q6/Q7.',203.20,218.44,1.05)
    t.text('Na-ion с опцией: установить весь узел, R56 = 1,8 Ом.\nLTO / без опции: R56 = 0 Ом, остальные 24 позиции не ставить.\nОсновной R1 = 0,28 Ом остаётся во всех вариантах.\nХолод ≈ 96 мА; тепло ≈ 665 мА (зависит от RDS(on)).',203.20,245.11,1.05)
    return t
