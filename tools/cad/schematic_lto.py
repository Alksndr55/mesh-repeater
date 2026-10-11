from schematic_core import Sheet,define,chip,box,line,P,MODEL,PARTS
def build():
    define('LMV431',[('3','K',0,-10.16,'T',P),('4','REF',-12.7,0,'L','input'),('5','A',0,10.16,'B',P),('2','A',7.62,10.16,'B',P),('1','NC',12.7,0,'R','no_connect')],box(-7.62,-5.08,7.62,5.08),-15.24)
    labels=['PACK+','MID','PACK-'] + (['NC'] if '4' in PARTS['J12']['nets'] else [])
    chip('J3_LTO',[(str(i+1),label,10.16,(i-(len(labels)-1)/2)*5.08,'R',P) for i,label in enumerate(labels)],10.16,len(labels)*5.08)
    s=Sheet('LTO_Balancer','Балансир 2S LTO / опциональная сборка POWER',6)
    for ch,dx,pos,neg in [(1,0,'BAT','LTO_MID'),(2,162.56,'LTO_MID','GND')]:
        x=96.52+dx;y=96.52;r=47+4*(ch-1);u='U'+str(ch+7);c='C'+str(ch+57)
        s.text('Верхняя ячейка' if ch==1 else 'Нижняя ячейка',x-45.72,38.1,1.5)
        s.sym(u,x,y,'LMV431',label=(x+11.43,y-8.89,x+11.43,y-6.35));s.nc(u,1)
        s.sym('R'+str(r),x,60.96,'R_V');s.net('R'+str(r),1,name=pos)
        s.wire(('R'+str(r),2),(x,73.66),(x,86.36), (u,3))
        s.sym('R'+str(r+1),x-43.18,78.74,'R_V')
        s.sym('R'+str(r+2),x-43.18,96.52,'R_V')
        s.sym('R'+str(r+3),x-43.18,120.65,'R_V')
        s.wire((x,73.66),(x-43.18,73.66),('R'+str(r+1),1));s.dot((x,73.66))
        s.wire(('R'+str(r+1),2),('R'+str(r+2),1))
        s.wire(('R'+str(r+2),2),(x-43.18,110.49),('R'+str(r+3),1));s.dot((x-43.18,110.49))
        s.wire((x-43.18,110.49),(x-25.4,110.49),(x-25.4,96.52),(u,4))
        s.sym(c,x+35.56,96.52,'C_V');s.wire((x,81.28),(x+35.56,81.28),(c,1));s.dot((x,81.28))
        bottom=y+43.18
        for pin in [(u,5),(u,2),(c,2),('R'+str(r+3),2)]:
            px,py=s.point(pin);s.wire(pin,(px,bottom))
        s.wire((x-43.18,bottom),(x,bottom),(x+7.62,bottom),(x+35.56,bottom))
        s.dot((x,bottom));s.dot((x+7.62,bottom))
        if neg=='GND':s.ground((x+35.56,bottom),2.54)
        else:s.global_stub(neg,(x+35.56,bottom),(x+35.56,bottom+7.62),(x+30.48,bottom+7.62))
    s.sym('J12',30.48,175.26,'J3_LTO')
    for n in range(1,4):s.net('J12',n)
    if '4' in PARTS['J12']['nets']:s.nc('J12',4)
    s.text('Na-ion: этот лист не запаивать. LTO 2S: запаять все компоненты этого листа.',86.36,171.45,1.3)
    if MODEL.get('battery_dividers'):
        s.text('Na-ion: R3=61,9k / R4=100k / C30=12pF. LTO: 121k / 100k / 6,8pF. Допуск R: 0,1%.',86.36,180.34,1.3)
        s.text('LTO: номинал 5,345 В; максимум 5,445 В при ТКС ≤25 ppm/°C, -40…85°C. Выбросы не учтены.',86.36,189.23,1.2)
    else:
        s.text('Na-ion: R3=6,34k / R4=10k / C30=12pF. LTO: 13k / 10,5k / 6,8pF. Допуск R: 0,1%.',86.36,180.34,1.3)
        s.text('LTO: номинал 5,408 В; угол до 5,481 В при ТКС ≤25 ppm/°C, -40…85°C. Выбросы не учтены.',86.36,189.23,1.2)
    s.text('Балансир: 2R, 120k+2,49k / 100k (0,1%), LMV431A, 47nF.',86.36,198.12,1.2)
    s.text('Балласт R47/R51 = 2R по выбору пользователя; ток LMV431 на углах допусков не ограничен до 15 мА.',86.36,216,1.2)
    s.text(MODEL.get('schematic_revision','S4.9')+': отдельной защиты ячеек и защиты от перенапряжения нет.',86.36,207.01,1.2)
    if MODEL.get('balancer_layout'):
        s.text('POWER: балансир под средним экраном. J12: 1 PACK+ / 2 MID / 3 PACK-.',86.36,224.89,1.2)
    return s
