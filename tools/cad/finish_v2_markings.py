"""Finish v2 silk from the actual native board, without moving copper or parts.

Native F components of LOGIC face down after the assembly X180 flip. Its
native B text is therefore the exterior operator surface; 180 degree reading
orientation is used there. A primary ref + bare nominal block projects below
the real body. If that projection is crowded, a uniformly enlarged spatial
group preserves relative locations and component axes. No BOM table replaces
the spatial association. All paths must remain within the v2 workspace.

The one non-text operation permitted by the parent is transfer of footprint
silk graphics outside the PCB, or across a mask opening, to the same-side Fab.
The true body in Fab and 3D, pads, copper, placement and electrical fields are
invariant. Existing board option outlines remain untouched.

Run only after routing/placement is ready:
  KiCad/bin/python.exe finish_v2_markings.py --pcb ... --out ...
Use --dry-run to plan and verify without writing any board.
"""
from pathlib import Path
import argparse, collections, hashlib, json, math
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from component_nominal import nominal

ROOT=Path(__file__).resolve().parents[2]
SILKS=(k.F_SilkS,k.B_SilkS)

def safe(p):
    p=Path(p).resolve()
    if not p.is_relative_to(ROOT):raise ValueError('Path outside Mesh_Repeater_2_0: '+str(p))
    return p
def mm(n):return k.ToMM(n)
def v(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def xy(p):return [mm(p.x),mm(p.y)]
def rect(b,m=0):return (mm(b.GetLeft())-m,mm(b.GetTop())-m,mm(b.GetRight())+m,mm(b.GetBottom())+m)
def grow(a,m):return (a[0]-m,a[1]-m,a[2]+m,a[3]+m)
def overlap(a,b):return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]
def union(a):return (min(x[0] for x in a),min(x[1] for x in a),max(x[2] for x in a),max(x[3] for x in a))
def center(a):return [(a[0]+a[2])/2,(a[1]+a[3])/2]
def dist(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])
def within(a,b):return a[0]>=b[0] and a[1]>=b[1] and a[2]<=b[2] and a[3]<=b[3]
def seg_rect(a,z,box):
    lo,hi=0.,1.;dx=z[0]-a[0];dy=z[1]-a[1]
    for p,q in ((-dx,a[0]-box[0]),(dx,box[2]-a[0]),(-dy,a[1]-box[1]),(dy,box[3]-a[1])):
        if abs(p)<1e-10:
            if q<0:return False
        else:
            t=q/p
            if p<0:lo=max(lo,t)
            else:hi=min(hi,t)
            if lo>hi:return False
    return True

def interval_in_rect(a,z,box):
    """Parametric part of a segment within a clearance rectangle."""
    lo,hi=0.,1.;dx=z[0]-a[0];dy=z[1]-a[1]
    for p,q in ((-dx,a[0]-box[0]),(dx,box[2]-a[0]),(-dy,a[1]-box[1]),(dy,box[3]-a[1])):
        if abs(p)<1e-10:
            if q<0:return None
        else:
            t=q/p
            if p<0:lo=max(lo,t)
            else:hi=min(hi,t)
            if lo>hi:return None
    return lo,hi

def invariant(b):
    """Exclude silk/text only; every electrical/placement object is included."""
    tracks=[];pads=[];placements=[];zones=[];graphics=[]
    for t in b.GetTracks():
        width=t.GetWidth(k.F_Cu) if isinstance(t,k.PCB_VIA) else t.GetWidth()
        row=[t.m_Uuid.AsString(),t.GetNetname(),t.GetLayer(),width,xy(t.GetStart()),xy(t.GetEnd())]
        if isinstance(t,k.PCB_VIA):row += [t.GetDrill(),t.TopLayer(),t.BottomLayer()]
        tracks.append(row)
    for f in b.GetFootprints():
        models=[]
        for m in f.Models():
            vector=lambda q:[q.x,q.y,q.z]
            models.append([str(m.m_Filename),vector(m.m_Offset),vector(m.m_Rotation),vector(m.m_Scale),m.m_Show,m.m_Opacity])
        placements.append([f.GetReference(),xy(f.GetPosition()),f.GetOrientationDegrees(),f.GetLayer(),f.GetValue(),f.IsDNP(),str(f.GetFPID().GetLibItemName()),str(f.GetPath().AsString()),sorted((t.GetName(),t.GetText()) for t in f.GetFields()),models])
        for p in f.Pads():
            pads.append([f.GetReference(),p.m_Uuid.AsString(),p.GetNumber(),p.GetNetname(),xy(p.GetPosition()),xy(p.GetSize()),xy(p.GetDrillSize()),p.GetOrientationDegrees(),int(p.GetShape()),str(p.GetLayerSet().FmtBin())])
    for z in b.Zones():
        outline=z.Outline();polys=[]
        for i in range(outline.OutlineCount()):
            line=outline.COutline(i);polys.append([xy(line.CPoint(j)) for j in range(line.PointCount())])
        zones.append([z.m_Uuid.AsString(),z.GetNetname(),z.GetLayer(),z.GetAssignedPriority(),polys])
    for g in b.GetDrawings():
        if isinstance(g,k.PCB_TEXT) or g.GetLayer() in SILKS:continue
        if isinstance(g,k.PCB_SHAPE):graphics.append([g.m_Uuid.AsString(),g.GetLayer(),int(g.GetShape()),xy(g.GetStart()),xy(g.GetEnd()),g.GetWidth()])
    data=dict(tracks=sorted(tracks),pads=sorted(pads),placement=sorted(placements),zones=sorted(zones),non_silk_board_graphics=sorted(graphics))
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()

NAMES={'J3':'I2C','J4':'GPS','J5':'UART','J7':'SOLAR','J8':'BAT','J10':'ISP','J11':'LC / SYS','J12':'LTO','J13':'SMA','J101':'POWER / LOGIC','J201':'POWER / LOGIC','TH1':'NTC'}
PIN_NAMES={
 'J3':{'1':'VIN','2':'GND','3':'SCL','4':'SDA'},
 'J4':{'1':'NC/RST','2':'NC/PPS','3':'NC/WAKE','4':'RX','5':'TX','6':'BACKUP','7':'POWER','8':'GND'},
 'J5':{'1':'GND','2':'VIN','3':'TX','4':'RX'},
 'J7':{'1':'SOLAR+','2':'GND'},'J8':{'1':'BAT+','2':'GND'},
 'J10':{'1':'MISO','2':'VIN','3':'SCK','4':'MOSI','5':'RESET','6':'GND'},
 'J11':{'1':'LC_OUT','2':'SYS_3V3'},'J12':{'1':'BAT+','2':'MID','3':'GND','4':'NC'},
 'J13':{'1':'RF','2':'GND'},'TH1':{'1':'NTC','2':'GND'},
 'J101':{str(i):'GND' if i%2==0 else '3V3' if i<9 else 'BAT' if i==9 else 'MODE' for i in range(1,13)},
 'J201':{str(i):'GND' if i%2==0 else '3V3' if i<9 else 'BAT' if i==9 else 'MODE' for i in range(1,13)},
}

class Markings:
    def __init__(self,b,model):
        self.b=b;self.model=model;self.which=model['partition_board'];self.base=180 if self.which=='LOGIC' else 0
        self.parts={p['ref']:p for p in model['parts']};self.fps={f.GetReference():f for f in b.GetFootprints()}
        if set(self.parts)!=set(self.fps):raise ValueError('Native PCB and model ref inventories differ')
        self.bounds=grow(rect(b.GetBoardEdgesBoundingBox()),-.40)
        self.obs={l:[] for l in SILKS};self.lines={l:[] for l in SILKS};self.bodies={};self.generated=[];self.associations=[];self.groups=[];self.pinouts=[];self.transferred=[];self.unplaced_front=[];self.clipped_boundaries=[];self.held=[]
    def angle(self,ref,layer=k.B_SilkS):return (round(self.fps[ref].GetOrientationDegrees())%180+(self.base if layer==k.B_SilkS else 0))%360
    def prepare(self):
        for g in list(self.b.GetDrawings()):
            if isinstance(g,k.PCB_TEXT) and g.GetLayer() in SILKS:self.b.Delete(g)
        # Fields retain their original content and electrical metadata.
        for f in self.fps.values():
            for t in f.GetFields():t.SetVisible(False)
        mask={l:[] for l in SILKS}
        for ref,f in self.fps.items():
            for p in f.Pads():
                for l,m in ((k.F_SilkS,k.F_Mask),(k.B_SilkS,k.B_Mask)):
                    if p.GetLayerSet().Contains(m) or p.GetDrillSize().x:
                        margin=p.GetLocalSolderMaskMargin()
                        expansion=max(0,mm(margin))+.16 if margin is not None else .16
                        mask[l].append((rect(p.GetBoundingBox(),expansion),ref))
            for t in f.GraphicalItems():
                if isinstance(t,k.PCB_TEXT) and t.GetLayer() in SILKS:t.SetVisible(False)
        for ref,f in self.fps.items():
            fab=[];pads=[rect(p.GetBoundingBox()) for p in f.Pads()]
            for g in f.GraphicalItems():
                if isinstance(g,k.PCB_TEXT):continue
                layer=g.GetLayer()
                if layer==k.F_Fab:fab.append(rect(g.GetBoundingBox()))
                if layer not in SILKS:continue
                box=rect(g.GetBoundingBox())
                outside=not within(box,self.bounds)
                if g.GetShape()==k.SHAPE_T_SEGMENT:
                    a,z=xy(g.GetStart()),xy(g.GetEnd())
                    masked=any(seg_rect(a,z,grow(q,mm(g.GetWidth())/2)) for q,_ in mask[layer])
                else:masked=any(overlap(box,q) for q,_ in mask[layer])
                if outside or masked:
                    g.SetLayer(k.F_Fab if layer==k.F_SilkS else k.B_Fab)
                    self.transferred.append(dict(ref=ref,uuid=g.m_Uuid.AsString(),from_layer=k.LayerName(layer),reason='outside_board' if outside else 'mask_overlap'))
            self.bodies[ref]=union(fab or pads or [rect(f.GetBoundingBox())])
            if ref!='SH1':self.obs[k.F_SilkS].append((grow(self.bodies[ref],.12),'body',ref))
        for l in SILKS:self.obs[l].extend((q,'mask',r) for q,r in mask[l])
        self.clip_option_boundaries(mask)
        for g in list(self.b.GetDrawings())+[g for f in self.fps.values() for g in f.GraphicalItems()]:
            layer=g.GetLayer()
            if layer not in SILKS or isinstance(g,k.PCB_TEXT):continue
            if not isinstance(g,k.PCB_SHAPE):continue
            if g.GetShape()==k.SHAPE_T_SEGMENT:self.lines[layer].append((xy(g.GetStart()),xy(g.GetEnd()),mm(g.GetWidth())))
            elif g.GetShape()==k.SHAPE_T_RECT:
                a,z=xy(g.GetStart()),xy(g.GetEnd());x0,x1=sorted((a[0],z[0]));y0,y1=sorted((a[1],z[1]));w=mm(g.GetWidth())
                self.lines[layer].extend((a,z,w) for a,z in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))])
            else:self.obs[layer].append((rect(g.GetBoundingBox(),.16),'graphic','board'))
        # A tented via has no silk-clipping mask aperture. Honour the native
        # per-via/default tenting rather than blanking the complete stitch grid.
        for g in self.b.GetTracks():
            if not isinstance(g,k.PCB_VIA):continue
            r=mm(g.GetWidth(k.F_Cu))/2+max(0,mm(g.GetSolderMaskExpansion()))+.16;x,y=xy(g.GetPosition())
            for l,cu in ((k.F_SilkS,k.F_Cu),(k.B_SilkS,k.B_Cu)):
                if not g.IsTented(cu):self.obs[l].append(((x-r,y-r,x+r,y+r),'via','via'))
    def clip_option_boundaries(self,mask):
        """Keep option outlines, with local gaps around pads/body silk.

        These are BOARD_SHAPEs only. Fab geometry, component graphics,
        copper, connector pad outlines and the approved group path remain.
        """
        if self.which!='POWER':return
        for g in list(self.b.GetDrawings()):
            if not isinstance(g,k.PCB_SHAPE) or g.GetLayer()!=k.F_SilkS or g.GetShape()!=k.SHAPE_T_SEGMENT:continue
            a,z=xy(g.GetStart()),xy(g.GetEnd());width=mm(g.GetWidth());cuts=[]
            obstacles=[grow(q,.10+width/2) for q,_ in mask[k.F_SilkS]]
            for f in self.fps.values():
                for q in f.GraphicalItems():
                    if isinstance(q,k.PCB_TEXT) or q.GetLayer()!=k.F_SilkS:continue
                    obstacles.append(rect(q.GetBoundingBox(),.12+width/2))
            for box in obstacles:
                part=interval_in_rect(a,z,box)
                if part:cuts.append(part)
            if not cuts:continue
            merged=[]
            for lo,hi in sorted(cuts):
                if merged and lo<=merged[-1][1]+1e-9:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
                else:merged.append((lo,hi))
            keep=[];cursor=0.
            for lo,hi in merged:
                if lo>cursor:keep.append((cursor,lo))
                cursor=max(cursor,hi)
            if cursor<1.:keep.append((cursor,1.))
            row={'source_uuid':g.m_Uuid.AsString(),'source_from_mm':a,'source_to_mm':z,'retained_segments_mm':[],'reason':'solder_mask_and_component_silk_clearance'}
            self.b.Remove(g);self.held.append(g)
            for lo,hi in keep:
                p=[a[0]+lo*(z[0]-a[0]),a[1]+lo*(z[1]-a[1])];q=[a[0]+hi*(z[0]-a[0]),a[1]+hi*(z[1]-a[1])]
                if dist(p,q)<.4:continue
                line=k.PCB_SHAPE(self.b);line.SetShape(k.SHAPE_T_SEGMENT);line.SetLayer(k.F_SilkS);line.SetWidth(k.FromMM(width));line.SetStart(v(*p));line.SetEnd(v(*q));self.b.Add(line);row['retained_segments_mm'].append([p,q])
            self.clipped_boundaries.append(row)
    def free(self,box,layer,owner=''):
        if not within(box,self.bounds):return False
        if any(overlap(box,q) for q,_,_ in self.obs[layer]):return False
        return not any(seg_rect(a,z,grow(box,.1+w/2)) for a,z,w in self.lines[layer])
    def text(self,caption,layer,font,angle,bold=False):
        t=k.PCB_TEXT(self.b);t.SetText(caption);t.SetLayer(layer);t.SetMirrored(layer==k.B_SilkS)
        t.SetTextSize(v(font,font));t.SetTextThickness(k.FromMM(.16 if bold else .12 if font>=1 else .1));t.SetBold(bold)
        t.SetTextAngle(k.EDA_ANGLE(angle,k.DEGREES_T));t.SetHorizJustify(k.GR_TEXT_H_ALIGN_CENTER);t.SetVertJustify(k.GR_TEXT_V_ALIGN_CENTER)
        return t
    def at(self,t,pos):
        t.SetPosition(v(0,0));box=rect(t.GetBoundingBox());cx,cy=center(box)
        t.SetPosition(v(pos[0]-cx,pos[1]-cy));return rect(t.GetBoundingBox(),.16 if self.which=='LOGIC' else .10)
    def save(self,t,box,owner,kind):
        self.b.Add(t);self.obs[t.GetLayer()].append((box,'text',owner))
        row=dict(owner=owner,kind=kind,text=t.GetText(),at_mm=xy(t.GetPosition()),box_mm=box,angle_deg=t.GetTextAngle().AsDegrees(),layer=k.LayerName(t.GetLayer()),font_mm=mm(t.GetTextHeight()),uuid=t.m_Uuid.AsString())
        self.generated.append(row);return row
    def near_sites(self,origin,maxdistance=12,step=.5):
        # Uniform candidates, ordered by true distance; useful for headings only.
        choices=[]
        for iy in range(math.ceil((self.bounds[1]-origin[1])/step),math.floor((self.bounds[3]-origin[1])/step)+1):
            for ix in range(math.ceil((self.bounds[0]-origin[0])/step),math.floor((self.bounds[2]-origin[0])/step)+1):
                if ix*ix+iy*iy>(maxdistance/step)**2:continue
                choices.append((ix*ix+iy*iy,origin[0]+ix*step,origin[1]+iy*step))
        for _,x,y in sorted(choices):yield [x,y]
    def find_caption(self,s,layer,font,origin,owner,maxdistance=8,angle=None,bold=False,required=True):
        t=self.text(s,layer,font,self.base if angle is None and layer==k.B_SilkS else 0 if angle is None else angle,bold)
        for pos in self.near_sites(origin,maxdistance):
            box=self.at(t,pos)
            if self.free(box,layer,owner):return self.save(t,box,owner,'function')
        if required:raise RuntimeError('No clear local marking for '+owner+': '+s)
        return None
    def functional(self):
        # Reserve operator and option captions before component labels.
        if self.which=='LOGIC':
            self.find_caption('Mesh Repeater ver 2.0',k.B_SilkS,1.4,[48,50],'PRODUCT',12,bold=True)
            self.find_caption('Designed by @Alksndritm',k.B_SilkS,1.,[48,46.5],'DESIGNER',12)
            p=center(self.bodies['J11'])
            self.find_caption('REMOVE J11 BEFORE USB',k.B_SilkS,.9,[p[0]-11,p[1]],'USB_SHUNT',9)
            self.find_caption('D3 CHARGE    D4 DONE',k.B_SilkS,.9,[53.5,56],'LED_NAMES',12)
        else:
            self.find_caption('POWER 2.0',k.F_SilkS,1.0,[45,58.5],'PRODUCT',8,bold=True)
            self.find_caption('BAL1',k.F_SilkS,1.,[26,20.3],'BAL1_OPTION',8,bold=True)
            self.find_caption('BAL2',k.F_SilkS,1.,[16.5,56.2],'BAL2_OPTION',4,bold=True)
            self.find_caption('A',k.F_SilkS,1.,[33,28.75],'COLD_A_OPTION',3,bold=True)
            self.find_caption('B',k.F_SilkS,1.,[25.5,53.5],'COLD_B_OPTION',3,bold=True)
            self.find_caption('COLD A+B',k.F_SilkS,1.,[39.5,56.7],'COLD_OPTION',6,bold=True)
            for ref,name in [('D3','CHARGE'),('D4','DONE')]:
                p=xy(self.fps[ref].GetPosition());self.find_caption(name,k.F_SilkS,.8,[p[0],p[1]+2.3],ref,4,bold=True)
    def connector_pinouts(self):
        for ref in sorted(set(self.fps)&set(PIN_NAMES)):
            f=self.fps[ref];names=PIN_NAMES[ref]
            pads={}
            for p in f.Pads():
                pin=p.GetNumber()
                if pin in names and pin not in pads:pads[pin]=p
            if set(pads)!=set(names):raise ValueError(ref+' pin inventory does not match reviewed marking map')
            mp={str(pin):net for pin,net in self.parts[ref].get('nets',{}).items()}
            for pin,p in pads.items():
                logical=mp.get(pin)
                if logical is not None and p.GetNetname().split('/')[-1]!=logical:raise ValueError(ref+'.'+pin+' model/native pin disagreement')
            xs=sorted(set(round(xy(p.GetPosition())[0],5) for p in pads.values()));ys=sorted(set(round(xy(p.GetPosition())[1],5) for p in pads.values()))
            row=dict(ref=ref,pins=[],source='actual native numbered pads',view='native B exterior, assembly X180' if self.which=='LOGIC' else 'native B',name=NAMES[ref])
            # Rows at 1.25 mm use projected numbers and a local named list.
            if ref=='J4':
                for pin,p in sorted(pads.items(),key=lambda z:int(z[0])):
                    t=self.text(pin,k.B_SilkS,.8,self.base);box=self.at(t,xy(p.GetPosition()))
                    if not self.free(box,k.B_SilkS,ref):raise RuntimeError('GPS projected pin number collision '+pin)
                    lab=self.save(t,box,ref,'pin_number');row['pins'].append(dict(pin=pin,net=p.GetNetname(),label=lab))
                legend='J4 GPS\n'+'\n'.join('  '.join(pin+' '+names[pin] for pin in pair) for pair in [('1','2'),('3','4'),('5','6'),('7','8')])
                row['legend']=self.find_caption(legend,k.B_SilkS,.8,[center(self.bodies[ref])[0],center(self.bodies[ref])[1]+8],ref,11)
                self.pinouts.append(row);continue
            # Put pin names in actual rows/columns at the matching pad coordinate.
            vertical=len(xs)<=2 and len(ys)>1
            horizontal=len(ys)<=2 and len(xs)>1
            done=False
            for gap in (.65,.9,1.2,1.6,2.,2.5,3.,4.):
                for side in (1,-1):
                    trial=[];good=True
                    for pin,p in sorted(pads.items(),key=lambda z:int(z[0])):
                        px,py=xy(p.GetPosition());text=pin+' '+names[pin]
                        ang=self.base if vertical or not horizontal else (90+self.base)%360
                        t=self.text(text,k.B_SilkS,.8,ang);q=self.at(t,[0,0]);w=q[2]-q[0];h=q[3]-q[1]
                        if vertical:
                            choose=-1 if len(xs)==2 and px==xs[0] else 1 if len(xs)==2 else side
                            x=px+choose*(mm(p.GetSize().x)/2+gap+w/2);y=py
                        elif horizontal:
                            choose=-1 if len(ys)==2 and py==ys[0] else 1 if len(ys)==2 else side
                            x=px;y=py+choose*(mm(p.GetSize().y)/2+gap+h/2)
                        else:
                            x=px;y=py+side*(mm(p.GetSize().y)/2+gap+h/2)
                        box=self.at(t,[x,y])
                        if not self.free(box,k.B_SilkS,ref) or any(overlap(box,a[3]) for a in trial):good=False;break
                        trial.append((pin,p,t,box))
                    if not good:continue
                    for pin,p,t,box in trial:row['pins'].append(dict(pin=pin,net=p.GetNetname(),pad_at_mm=xy(p.GetPosition()),label=self.save(t,box,ref,'pin_aligned')))
                    done=True;break
                if done:break
            if not done:
                # SMA and very crowded headers: explicitly numbered local map.
                legend=ref+' '+NAMES[ref]+'\n'+'\n'.join(pin+' '+names[pin] for pin in sorted(names,key=int))
                row['legend']=self.find_caption(legend,k.B_SilkS,.8,center(self.bodies[ref]),ref,14)
                row['pins']=[dict(pin=pin,net=p.GetNetname(),pad_at_mm=xy(p.GetPosition())) for pin,p in sorted(pads.items(),key=lambda z:int(z[0]))]
            self.pinouts.append(row)
    def caption(self,ref):
        p=self.parts[ref];n=nominal(p)
        if ref in ('J101','J201'):n='IDC 12P'
        if ref.startswith('H') and self.which=='LOGIC':return ref+' M3'
        if ref.startswith('H'):n='GND M3'
        # Field content is preserved; only the printed caption is shortened.
        return ref+('\n'+n if n else '')
    def front_sites(self,ref,t):
        body=self.bodies[ref];cx,cy=center(body);q=self.at(t,[0,0]);w=q[2]-q[0];h=q[3]-q[1]
        for gap in (.25,.4,.65,.9,1.3,1.8,2.5):
            for offset in (0,-.5,.5,-1.,1.):
                yield [cx+offset,body[1]-h/2-gap]
                yield [cx+offset,body[3]+h/2+gap]
                yield [body[0]-w/2-gap,cy+offset]
                yield [body[2]+w/2+gap,cy+offset]
    def labels(self):
        remaining=set(self.fps)
        for ref in sorted(remaining,key=lambda r:(-len(self.caption(r)),r)):
            pos=center(self.bodies[ref])
            for font in (1.,.9,.8):
                t=self.text(self.caption(ref),k.B_SilkS,font,self.angle(ref));box=self.at(t,pos)
                if self.free(box,k.B_SilkS,ref):
                    label=self.save(t,box,ref,'projected_body');self.associations.append(dict(ref=ref,mode='projected_body',real_body_center_mm=pos,label=label));remaining.remove(ref);break
        # A primary front block stays directly adjacent to its true component.
        for ref in sorted(remaining,key=lambda r:(-len(self.caption(r)),r)):
            for font in (.9,.8):
                t=self.text(self.caption(ref),k.F_SilkS,font,self.angle(ref,k.F_SilkS))
                for pos in self.front_sites(ref,t):
                    box=self.at(t,pos)
                    if self.free(box,k.F_SilkS,ref):
                        label=self.save(t,box,ref,'adjacent_front');self.associations.append(dict(ref=ref,mode='adjacent_front',real_body_center_mm=center(self.bodies[ref]),label=label));remaining.remove(ref);break
                if ref not in remaining:break
        # Remaining blocks are always a real spatial zoom, never individual
        # labels pushed around independently. Fixed uniform s and translation.
        clusters=[]
        while remaining:
            seed=min(remaining);remaining.remove(seed);refs=[seed]
            for ref in sorted(remaining,key=lambda r:dist(center(self.bodies[r]),center(self.bodies[seed]))):
                if len(refs)>=4:break
                if self.parts[ref].get('group')==self.parts[seed].get('group') and dist(center(self.bodies[ref]),center(self.bodies[seed]))<8:
                    refs.append(ref);remaining.remove(ref)
            clusters.append(refs)
        used={r for refs in clusters for r in refs}
        for refs in clusters:
            if len(refs)>1:continue
            seed=refs[0];origin=center(self.bodies[seed])
            choices=[a for a in self.associations if a['ref'] not in used and dist(center(self.bodies[a['ref']]),origin)>1.2]
            if not choices:raise RuntimeError('No neighboring part for spatial group '+seed)
            # Prefer a physical neighbor before a distant member of a broad
            # category such as mounting holes. Opposite corners cannot form
            # a larger spatial fragment inside this board.
            local=[a for a in choices if dist(center(self.bodies[a['ref']]),origin)<=20]
            if local:choices=local
            a=min(choices,key=lambda a:(self.parts[a['ref']].get('group')!=self.parts[seed].get('group'),dist(center(self.bodies[a['ref']]),origin)))
            ref=a['ref'];refs.append(ref);used.add(ref)
            uuid=a['label']['uuid']
            for g in list(self.b.GetDrawings()):
                if g.m_Uuid.AsString()==uuid:self.b.Delete(g)
            self.generated=[g for g in self.generated if g['uuid']!=uuid]
            # Relocating a primary caption must retain the same connector's
            # pin-name reservations and operator captions.
            old_box=tuple(a['label']['box_mm'])
            for l in SILKS:self.obs[l]=[g for g in self.obs[l] if not(g[1]=='text' and g[2]==ref and tuple(g[0])==old_box)]
            self.associations.remove(a)
        for index,refs in enumerate(sorted(clusters,key=lambda z:-sum(len(self.caption(r)) for r in z)),1):
            gid='G'+str(index);poses={r:center(self.bodies[r]) for r in refs};origin=center(union([(p[0],p[1],p[0],p[1]) for p in poses.values()]));done=False
            for font in (1.,.9,.8):
                ts={r:self.text(self.caption(r),k.B_SilkS,font,self.angle(r)) for r in refs}
                for scale in (1.5,2.,2.5,3.,4.,5.):
                    trial={r:self.at(t,[(poses[r][0]-origin[0])*scale,(poses[r][1]-origin[1])*scale]) for r,t in ts.items()}
                    if any(overlap(trial[r],trial[z]) for i,r in enumerate(refs) for z in refs[i+1:]):continue
                    env=union(list(trial.values()));head=self.text(gid+' x'+format(scale,'g'),k.B_SilkS,.8,self.base)
                    headingbox=self.at(head,[(env[0]+env[2])/2,env[1]-1.2]);env=union([env,headingbox])
                    for site in self.near_sites(origin,100,.5):
                        moved={r:(q[0]+site[0],q[1]+site[1],q[2]+site[0],q[3]+site[1]) for r,q in trial.items()}
                        h=(headingbox[0]+site[0],headingbox[1]+site[1],headingbox[2]+site[0],headingbox[3]+site[1])
                        if not self.free(h,k.B_SilkS,gid) or any(not self.free(q,k.B_SilkS,gid) for q in moved.values()):continue
                        for r,t in ts.items():
                            pos=[site[0]+scale*(poses[r][0]-origin[0]),site[1]+scale*(poses[r][1]-origin[1])];box=self.at(t,pos)
                            label=self.save(t,box,r,'spatial_group');self.associations.append(dict(ref=r,mode='spatial_group',group=gid,real_body_center_mm=poses[r],label=label))
                        hp=[site[0]+(headingbox[0]+headingbox[2])/2,site[1]+(headingbox[1]+headingbox[3])/2];self.save(head,self.at(head,hp),gid,'group_heading')
                        self.groups.append(dict(id=gid,refs=refs,scale=scale,origin_mm=origin,translation_mm=[site[0]-scale*origin[0],site[1]-scale*origin[1]],preserves_orientation=True))
                        done=True;break
                    if done:break
                if done:break
            if not done:raise RuntimeError('No readable uniform spatial group space for '+str(refs))
        primary_front={a['ref'] for a in self.associations if a['mode']=='adjacent_front'}
        for ref in sorted(set(self.fps)-primary_front):
            t=self.text(ref,k.F_SilkS,.8,self.angle(ref,k.F_SilkS));done=False
            for pos in self.front_sites(ref,t):
                box=self.at(t,pos)
                if self.free(box,k.F_SilkS,ref):self.save(t,box,ref,'front_reference');done=True;break
            if not done:self.unplaced_front.append(ref)
        if set(a['ref'] for a in self.associations)!=set(self.fps):raise AssertionError('Missing primary component marking')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--out',type=Path);ap.add_argument('--model',type=Path);ap.add_argument('--report',type=Path);ap.add_argument('--dry-run',action='store_true');args=ap.parse_args()
    source=safe(args.pcb);dest=safe(args.out or source);modelpath=safe(args.model or source.parent/'model.json');report=safe(args.report or ROOT/'audit'/(source.stem+'_markings.json'))
    input_sha=hashlib.sha256(source.read_bytes()).hexdigest();model_sha=hashlib.sha256(modelpath.read_bytes()).hexdigest()
    model=json.loads(modelpath.read_text(encoding='utf8'));b=k.LoadBoard(str(source));before=invariant(b)
    lab=Markings(b,model);lab.prepare();lab.functional();lab.connector_pinouts();lab.labels()
    after=invariant(b)
    if before!=after:raise AssertionError('Copper, net, placement, Value, field content, pad or engineering graphics changed')
    rows=lab.generated
    proof=dict(source=str(source.relative_to(ROOT)),destination=str(dest.relative_to(ROOT)),source_pcb_sha256=input_sha,model_sha256=model_sha,board=model['partition_board'],dry_run=args.dry_run,invariant_before=before,invariant_after=after,unchanged_electrical_and_placement=True,primary_count=len(lab.associations),expected_count=len(lab.fps),minimum_font_mm=min(x['font_mm'] for x in rows),label_edge_gap_mm=.4,reserved_mask_gap_mm=.16,assembly_flip='X180' if lab.which=='LOGIC' else 'none',associations=lab.associations,spatial_groups=lab.groups,pinouts=lab.pinouts,all_text=rows,footprint_silk_transferred_to_fab=lab.transferred,option_boundaries_clipped=lab.clipped_boundaries,unplaced_secondary_front_refs=lab.unplaced_front)
    report.parent.mkdir(parents=True,exist_ok=True)
    if not args.dry_run:
        if hashlib.sha256(source.read_bytes()).hexdigest()!=input_sha or hashlib.sha256(modelpath.read_bytes()).hexdigest()!=model_sha:
            raise RuntimeError('Input board or model changed concurrently; stop instead of overwriting another agent')
        dest.parent.mkdir(parents=True,exist_ok=True);k.SaveBoard(str(dest),b)
        reloaded=k.LoadBoard(str(dest))
        if invariant(reloaded)!=before:raise AssertionError('Saved/reloaded board invariant differs')
        proof['pcb_sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
    report.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({name:proof[name] for name in ('board','dry_run','primary_count','expected_count','minimum_font_mm','unchanged_electrical_and_placement')},ensure_ascii=True))

if __name__=='__main__':main()
