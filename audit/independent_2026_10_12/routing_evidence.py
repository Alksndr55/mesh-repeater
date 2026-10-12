from pathlib import Path
import json,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon,Circle
OUT=Path(__file__).parent
D=json.loads((OUT/'routing_native.json').read_text(encoding='utf8'));F=json.loads((OUT/'routing_focus.json').read_text(encoding='utf8'));B=D['boards']['LOGIC']
def copper(ax,layer):
    for p in B['GND_full_copper'][layer]:
        ax.add_patch(Polygon(p['shell'],color='#c6d5c0',zorder=0))
        for h in p['holes']:ax.add_patch(Polygon(h,color='white',zorder=1))
def trace(ax,a,z,w,color,zorder=3):
    dx,dy=z[0]-a[0],z[1]-a[1];length=math.hypot(dx,dy)
    if length:
        px,py=-dy/length*w/2,dx/length*w/2
        ax.add_patch(Polygon([[a[0]+px,a[1]+py],[z[0]+px,z[1]+py],[z[0]-px,z[1]-py],[a[0]-px,a[1]-py]],color=color,zorder=zorder))
    ax.add_patch(Circle(a,w/2,color=color,zorder=zorder));ax.add_patch(Circle(z,w/2,color=color,zorder=zorder))
fig,axes=plt.subplots(2,2,figsize=(18,13));samples={s['uuid']:s for s in B['opposite_ground_samples']}
for row,(net,label) in enumerate([('MOSI_RF','MOSI'),('MISO_MCU','MISO')]):
    route=F['signal_paths']['LOGIC'][label];total=sum(t['length_mm'] for t in B['items'].values() if t['kind']=='track' and t['logical_net']==net)
    for col,layer in enumerate(['F.Cu','B.Cu']):
        ax=axes[row,col];ref='B.Cu' if layer=='F.Cu' else 'F.Cu';copper(ax,ref)
        for t in B['items'].values():
            if t['logical_net']!=net:continue
            if t['kind']=='track' and t['layer']==layer:
                trace(ax,t['start'],t['end'],t['width_mm'],'#215fb4')
                for s in samples[t['uuid']]['missing_spans']:trace(ax,s['start'],s['end'],t['width_mm']+.05,'#ee782d',4)
            if t['kind']=='via':ax.add_patch(Circle(t['at'],.36,ec='#215fb4',fc='white',lw=.8,zorder=5))
        for t in B['items'].values():
            if t['kind']=='via' and t['logical_net']=='GND':ax.add_patch(Circle(t['at'],.16,color='#526d48',zorder=2))
        for t in B['items'].values():
            if t['kind']=='pad' and t['logical_net']==net:ax.scatter(*t['at'],marker='s',s=42,c='#123869',zorder=6);ax.annotate(t['ref']+'.'+t['pin'],t['at'],xytext=(6,8),textcoords='offset points',fontsize=8,bbox=dict(fc='white',alpha=.85,ec='none'),zorder=7)
        if label=='MOSI' and layer=='F.Cu':
            ax.annotate('9.1 mm without B.Cu GND\n(10.1,47.2)-(19.2,47.2)',(14.5,47.2),xytext=(31,55),fontsize=9,arrowprops=dict(arrowstyle='->'),bbox=dict(fc='white',alpha=.9))
        if label=='MISO' and layer=='B.Cu':
            ax.annotate('6.9 mm without F.Cu GND\n(49.0,6.1)-(55.9,6.1)',(52,6.1),xytext=(33,3.5),fontsize=9,arrowprops=dict(arrowstyle='->'),bbox=dict(fc='white',alpha=.9))
        if label=='MOSI':
            ax.plot([53,57.5],[21,25],'k--',lw=.8,zorder=6);ax.annotate('nearest GND barrel: 6.021 mm\nsignal via (53,21)',(53,21),xytext=(59,33),fontsize=8,arrowprops=dict(arrowstyle='->'),bbox=dict(fc='white',alpha=.9),zorder=7)
        ax.set_xlim(0,90);ax.set_ylim(60,0);ax.set_aspect('equal');ax.grid(alpha=.2);ax.set_title(f'{net}, {layer} trace over {ref} reference\nall segments {total:.3f} mm; selected whole-segment path {route["copper_segment_length_mm"]:.3f} mm',fontsize=11)
fig.suptitle('Saved native copper: blue = signal; orange = no GND directly on opposite layer; green = reference GND\nSegment sums are geometric estimates; pad/track overlap is not a transmission-line solve.',fontsize=13);fig.subplots_adjust(hspace=.27,wspace=.10,top=.88,bottom=.05,left=.04,right=.99);fig.savefig(OUT/'routing_spi_evidence.png',dpi=180);plt.close(fig)
fig,ax=plt.subplots(figsize=(12,8));copper(ax,'B.Cu')
for t in B['items'].values():
    if t['kind']=='track' and t['layer']=='B.Cu' and t['logical_net']=='RADIO_RXEN':trace(ax,t['start'],t['end'],t['width_mm'],'#c74938')
for t in B['items'].values():
    if t['kind']=='track' and t['layer']=='F.Cu' and t['logical_net']=='ANT_RF':trace(ax,t['start'],t['end'],t['width_mm'],'#215fb4')
gap=next(s for s in B['opposite_ground_samples'] if s['uuid']=='0a10c8ed-006d-451e-8ec3-774664bdfb11')['missing_spans'][0]
ax.plot([gap['start'][0],gap['end'][0]],[gap['start'][1],gap['end'][1]],color='#ffd750',lw=4,zorder=7)
ax.annotate('New break in B.Cu reference under ANT_RF\n~0.900 mm: (42.722,8.278)-(42.086,8.914)',(42.4,8.6),xytext=(38,6.2),fontsize=10,arrowprops=dict(arrowstyle='->'),bbox=dict(fc='white',alpha=.94),zorder=8)
ax.annotate('B.Cu RADIO_RXEN, width 0.25 mm\n(37.4,8.6)-(49.2,8.6)',(46.7,8.6),xytext=(43.9,10.6),fontsize=10,arrowprops=dict(arrowstyle='->'),bbox=dict(fc='white',alpha=.94),zorder=8)
ax.text(38,12.2,'Green: saved B.Cu GND. Blue: ANT_RF on F.Cu. Red: RXEN on B.Cu.\nS4.16 has continuous B.Cu GND under this ANT_RF segment.',fontsize=10,bbox=dict(fc='white',alpha=.94),zorder=8)
ax.set_xlim(37.5,49);ax.set_ylim(13,5);ax.set_aspect('equal');ax.grid(alpha=.3);ax.set_title('New RF reference gap in LOGIC; native coordinates in mm');fig.tight_layout();fig.savefig(OUT/'routing_rf_reference_gap.png',dpi=200);plt.close(fig)
print('routing_spi_evidence.png and routing_rf_reference_gap.png saved')
