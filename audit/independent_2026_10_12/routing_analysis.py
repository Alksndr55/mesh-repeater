"""Analyze the independent native snapshot and draw copper for visual review."""
from pathlib import Path
import json,math,heapq,itertools
from collections import defaultdict,Counter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Rectangle,Circle
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
D=json.loads((OUT/'routing_native.json').read_text(encoding='utf8'))
COL={'BAT':'#e06b00','SOLAR':'#8f298f','SYS_PRE':'#dd7a2f','SYS_LC_IN':'#ff4500','FILTER_MID':'#b08000','FILTER_OUT':'#d82636','SYS_3V3':'#cc1425','RADIO_3V3':'#ec4d84','SW_CHG':'#e23830','LX1':'#e23830','LX2':'#6a40d7','ANT_RF':'#135dce','ANT_SMA':'#d71fb1','BAT_ADC':'#28a99a','FB_SYS':'#28a99a'}
def draw(name,layer,bounds,refs,filename,nets=None):
    b=D['boards'][name];fig,ax=plt.subplots(figsize=(15,10));ax.set_aspect('equal')
    for poly in b['GND_full_copper'].get(layer,[]):
        ax.add_patch(Polygon(poly['shell'],color='#bdcfb8',zorder=0))
        for hole in poly['holes']:ax.add_patch(Polygon(hole,color='white',zorder=1))
    for t in b['items'].values():
        net=t['logical_net'];color=COL.get(net,'#627587')
        if t['kind']=='track' and t['layer']==layer:
            if net=='GND':color='#306f30'
            highlighted=nets is None or net in nets
            a,e=t['start'],t['end'];ax.plot([a[0],e[0]],[a[1],e[1]],color=color if highlighted else '#999999',lw=t['width_mm']*8,alpha=1 if highlighted else .4,solid_capstyle='round',zorder=2)
        if t['kind']=='via' and layer in t['layers']:
            ax.add_patch(Circle(t['at'],t['diameter_mm']/2,color='#306f30' if net=='GND' else color,zorder=3));ax.add_patch(Circle(t['at'],t['drill_mm']/2,color='white',zorder=4))
        if t['kind']=='pad' and layer in t['layers']:
            x,y=t['at'];w,h=t['size'];ang=math.radians(t['angle']);corners=[]
            for dx,dy in [(-w/2,-h/2),(w/2,-h/2),(w/2,h/2),(-w/2,h/2)]:corners.append([x+dx*math.cos(ang)+dy*math.sin(ang),y-dx*math.sin(ang)+dy*math.cos(ang)])
            ax.add_patch(Polygon(corners,color='#306f30' if net=='GND' else color,zorder=3,alpha=.85))
            if t['drill'][0]:ax.add_patch(Circle(t['at'],t['drill'][0]/2,color='white',zorder=4))
            if t['ref'] in refs:ax.text(x,y,t['pin'],fontsize=6,color='black',ha='center',va='center',zorder=5)
    for r in refs:
        if r in b['footprints']:
            f=b['footprints'][r];x,y=f['at'];ax.text(x,y-1.8,r,ha='center',fontsize=8,bbox=dict(fc='white',alpha=.8,ec='none'),zorder=6)
    ax.set_xlim(bounds[0],bounds[1]);ax.set_ylim(bounds[3],bounds[2]);ax.grid(alpha=.2);ax.set_title(f'{name} {layer}: saved native GND fill + copper, mm; pads shown by size/orientation')
    fig.tight_layout();fig.savefig(OUT/filename,dpi=200);plt.close(fig)
def paths(b,start,end):
    items=b['items'];edges=b['edges'];src=[u for u,o in items.items() if o['kind']=='pad' and [o['ref'],o['pin']]==list(start)];dst={u for u,o in items.items() if o['kind']=='pad' and [o['ref'],o['pin']]==list(end)}
    def w(u):
        t=items[u]
        if t['kind']=='track':return 1.724e-8*(t['length_mm']/1000)/(t['width_mm']/1000*35e-6)
        if t['kind']=='via':return 1.724e-8*(b['thickness_mm']/1000)/(math.pi*t['drill_mm']/1000*20e-6)
        return 0
    q=[(0,u) for u in src];dist={u:0 for u in src};prev={};end_u=None
    while q:
        cost,u=heapq.heappop(q)
        if cost!=dist[u]:continue
        if u in dst:end_u=u;break
        for v in edges.get(u,[]):
            candidate=cost+(w(u)+w(v))/2
            if candidate<dist.get(v,math.inf):dist[v]=candidate;prev[v]=u;heapq.heappush(q,(candidate,v))
    if end_u is None:return {'start':start,'end':end,'found_track_only':False}
    nodes=[end_u]
    while nodes[-1] in prev:nodes.append(prev[nodes[-1]])
    nodes.reverse();ts=[items[u] for u in nodes if items[u]['kind']=='track'];vs=[items[u] for u in nodes if items[u]['kind']=='via'];a=items[src[0]]['at'];z=items[end_u]['at']
    return {'start':start,'end':end,'found_track_only':True,'length_mm':sum(t['length_mm'] for t in ts),'min_width_mm':min([t['width_mm'] for t in ts],default=None),'width_length_mm':{str(wd):sum(t['length_mm'] for t in ts if t['width_mm']==wd) for wd in sorted({t['width_mm'] for t in ts})},'vias':vs,'one_route_R20_mohm':1000*sum(w(u) for u in nodes),'direct_distance_mm':math.dist(a,z),'detour_factor':sum(t['length_mm'] for t in ts)/math.dist(a,z) if math.dist(a,z) else 0,'items':[items[u] for u in nodes]}
P={'POWER':{'C8_Q1':(('C8','1'),('Q1','2')),'C8_U1_VCC':(('C8','1'),('U1','14')),'Q1_D2':(('Q1','3'),('D2','1')),'D2_L1':(('D2','1'),('L1','1')),'L1_R1':(('L1','2'),('R1','1')),'R1_BAT':(('R1','2'),('J8','1')),'BAT_TPS':(('J8','1'),('U2','10')),'BAT_sense':(('J8','1'),('J101','9')),'C12_VIN':(('C12','1'),('U2','10')),'C14_VOUT':(('C14','1'),('U2','6')),'U2_R55':(('U2','6'),('R55','1')),'R55_L3':(('R55','2'),('L3','1')),'L3_L4':(('L3','2'),('L4','1')),'L4_J101':(('L4','2'),('J101','1')),'L2_LX1':(('L2','1'),('U2','9')),'L2_LX2':(('L2','2'),('U2','7')),'FB_R8':(('U2','4'),('R8','2'))},'LOGIC':{'J201_J11':(('J201','1'),('J11','1')),'J11_MCU':(('J11','2'),('M1','9')),'J11_FB1':(('J11','2'),('FB1','1')),'FB1_M2':(('FB1','2'),('M2','3')),'M2_C23':(('M2','3'),('C23','1')),'M2_C24':(('M2','3'),('C24','1')),'ADC_MCU':(('R27','2'),('M1','8')),'BAT_R27':(('J201','9'),('R27','1')),'RF_M2_FL1':(('M2','1'),('FL1','2')),'SMA_FL1':(('J13','1'),('FL1','5'))}}
R={'assumptions':{'Cu_um':35,'rho20':1.724e-8,'via_plating_um':20,'path_excludes_planes_parallel_routes':True},'boards':{}}
for name,b in D['boards'].items():
    if name=='SHIELD':continue
    namepairs=P.get(name,{}) if name!='BASELINE' else P['POWER']|P['LOGIC']
    # Exclude interboard pairs absent on baseline.
    namepairs={label:pair for label,pair in namepairs.items() if pair[0][0] in b['footprints'] and pair[1][0] in b['footprints']}
    rd={'paths':{label:paths(b,*pair) for label,pair in namepairs.items()}}
    refs=defaultdict(lambda:{'length_mm':0,'missing_weighted_length_mm':0,'max_missing_span_mm':0,'worst_span':None})
    for t in b['opposite_ground_samples']:
        x=refs[t['logical_net']];x['length_mm']+=t['length_mm'];x['missing_weighted_length_mm']+=t['length_mm']*t['uncovered_fraction']
        for span in t['missing_spans']:
            if span['length_mm']>x['max_missing_span_mm']:x['max_missing_span_mm']=span['length_mm'];x['worst_span']={'track_uuid':t['uuid'],'reference_layer':t['reference_layer'],**span}
    rd['opposite_GND']=dict(refs)
    angle_counts=Counter();angle_positions=[];endpoints=defaultdict(list)
    for u,t in b['items'].items():
        if t['kind']!='track':continue
        for x,y in [(t['start'],t['end']),(t['end'],t['start'])]:endpoints[(t['logical_net'],t['layer'],tuple(x))].append((u,y))
    for (net,layer,at),adj in endpoints.items():
        if len(adj)!=2:continue
        v=[(e[0]-at[0],e[1]-at[1]) for _,e in adj];m=math.hypot(*v[0])*math.hypot(*v[1])
        if not m:continue
        turn=180-math.degrees(math.acos(max(-1,min(1,(v[0][0]*v[1][0]+v[0][1]*v[1][1])/m))))
        if turn<1e-3:continue
        label=str(round(turn,2));angle_counts[label]+=1
        if 89<turn<91 or turn>90:angle_positions.append({'net':net,'layer':layer,'at':at,'turn_degrees':turn,'uuids':[u for u,_ in adj]})
    rd['angle_counts']=dict(angle_counts);rd['turns_atleast90']=angle_positions
    R['boards'][name]=rd
(OUT/'routing_metrics.json').write_text(json.dumps(R,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
for name in ['POWER','LOGIC']:
    draw(name,'F.Cu',[-2,92,-3,64],list(D['boards'][name]['footprints']),f'routing_{name.lower()}_front.png')
    draw(name,'B.Cu',[-2,92,-3,64],[],f'routing_{name.lower()}_back.png')
draw('POWER','F.Cu',[6,53,13,42],['U1','U2','Q1','D1','D2','L1','L2','C8','C12','C14','R1','R55','C10'], 'routing_power_loops.png')
draw('LOGIC','F.Cu',[29,53,0,22],['M2','FL1','J13','FB1','C23','C24','C25','R27','R28','NT1'], 'routing_rf_front.png')
draw('LOGIC','B.Cu',[18,65,0,32],[], 'routing_spi_back.png')
print(json.dumps({n:{'paths':{p:{f:x.get(f) for f in ['found_track_only','length_mm','min_width_mm','one_route_R20_mohm','detour_factor']} for p,x in r['paths'].items()},'angles':r['angle_counts'],'SPI':{net:x for net,x in r['opposite_GND'].items() if net.startswith(('SCK','MISO','MOSI','CS_'))}} for n,r in R['boards'].items()},indent=2))
