"""Narrow V2 interconnect update on the current reviewed native boards.

Does not rebuild either board from S4.16 and does not write model.json.
POWER mutation must be coordinated with the INA219 owner before --board POWER.
The Ali generic parts are dimensioned envelopes, not contact qualification.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, shutil, subprocess, types

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'audit' / 'ina219_vertical_interconnect_2026_10_12'
MALE = 'Ali_PinHeader_2x06_P2.54_L35_A3C6'
FEMALE = 'Ali_PinSocket_2x06_P2.54_H8.5_v2_mirror'
SHIELD_HOLES = 'Shield_Interconnect_2x06_NPTH_D2_CuVoid3'
PINMAP = {'1':'FILTER_OUT','2':'GND','3':'FILTER_OUT','4':'GND',
          '5':'FILTER_OUT','6':'GND','7':'SYS_3V3','8':'GND',
          '9':'BAT','10':'SDA','11':'MODE','12':'SCL'}
URLS = {
 MALE:'https://aliexpress.ru/item/1005011978353933.html?sku_id=12000057202232448',
 FEMALE:'https://aliexpress.ru/item/1005008954873458.html?sku_id=12000047353417475',
}
KEEP=[]

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def rect(x0,y0,x1,y1,layer,width):
 return f'(fp_rect (start {x0} {y0}) (end {x1} {y1}) (stroke (width {width}) (type default)) (fill none) (layer "{layer}"))'

def connector_footprint(name):
 female=name==FEMALE
 sign=-1 if female else 1
 centre=sign*1.27
 x0,x1=centre-2.5,centre+2.5
 y0,y1=6.35-7.82,6.35+7.82
 description=(
  'Ali MTJ/JinSheng 2X6P 10PCS. H8.5mm, length15.64+/-0.30, width5mm; solder tail3.15+/-0.25mm, section0.6x0.4. '
  'Female top-view pad rows mirror male: even row localX=-2.54, both footprints rotate90deg. '
  'Actual contact mating depth and accepted male cross-section require sample qualification.'
  if female else
  'Ali E-SIMPO 2x6P L35mm A3C6. Full metal35mm; solder tail3mm; tip32mm above board; '
  'lower plastic0..2.5mm, upper plastic23.5..26mm; free tip6mm. Male pin section0.64mm is nominal envelope only, not documented acceptance.'
 )
 pads=[]
 for col in range(6):
  for row in range(2):
   number=str(col*2+row+1);x=sign*2.54*row;y=2.54*col
   pads.append(f'(pad "{number}" thru_hole {"rect" if number=="1" else "circle"} (at {x:g} {y:g}) (size 1.8 1.8) (drill 1.02) (layers "*.Cu" "*.Mask") (remove_unused_layers no))')
 return f'''(footprint "{name}" (version 20260206) (generator "pcbnew") (layer "F.Cu")
 (descr "{description}")
 (property "Reference" "REF**" (at {centre:g} -2.8) (layer "F.SilkS") (hide yes) (effects (font (size 0.9 0.9) (thickness 0.14))))
 (property "Value" "{name}" (at {centre:g} 15.5) (layer "F.Fab") (hide yes) (effects (font (size 0.9 0.9) (thickness 0.12))))
 (attr through_hole)
 {rect(x0,y0,x1,y1,'F.Fab',.1)}
 {rect(x0-.1,y0-.1,x1+.1,y1+.1,'F.SilkS',.12)}
 {rect(x0-.25,y0-.25,x1+.25,y1+.25,'F.CrtYd',.05)}
 (fp_line (start {x0} {y0+1.0}) (end {x0+1.0} {y0}) (stroke (width 0.15) (type default)) (layer "F.Fab"))
 (fp_text user "1" (at {x0-.9} 0) (layer "F.SilkS") (effects (font (size 0.8 0.8) (thickness 0.13))))
 {' '.join(pads)}
 (model "${{KIPRJMOD}}/3dmodels/{name}.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))
 (embedded_fonts no))
'''

def shield_footprint():
 pads=[]
 # Native screen flips about X180 in the stack; even nativeY is +2.54.
 for col in range(6):
  for row in range(2):
   pads.append(f'(pad "" np_thru_hole circle (at {col*2.54:g} {row*2.54:g}) (size 2 2) (drill 2) (layers "*.Cu" "*.Mask") (clearance 0.5))')
 return f'''(footprint "{SHIELD_HOLES}" (version 20260206) (generator "pcbnew") (layer "F.Cu")
 (descr "12 separate NPTH2.0mm, pitch2.54. Drill-to-foil clearance0.50mm; Cuvoid3.0mm overlaps adjacent copper clearances while FR4 drill web0.54mm remains. Generic pin fit subject to incoming dimensional control.")
 (property "Reference" "HS1" (at 6.35 5) (layer "F.Fab") (hide yes) (effects (font (size 0.8 0.8))))
 (property "Value" "INTERCONNECT PASS-THROUGH" (at 6.35 5) (layer "F.Fab") (hide yes) (effects (font (size 0.8 0.8))))
 (attr board_only exclude_from_pos_files exclude_from_bom)
 {rect(-1.25,-1.25,13.95,3.79,'F.CrtYd',.05)}
 {' '.join(pads)}
 (embedded_fonts no))
'''

def write_footprints():
 for which in ['Power','Logic']:
  project=ROOT/'design'/('MeshRepeater2_'+which)
  for name in [MALE,FEMALE]:
   (project/'Meshcore.pretty'/(name+'.kicad_mod')).write_text(connector_footprint(name),encoding='utf-8')
 project=ROOT/'design/MeshRepeater2_Shield'
 (project/'Shield.pretty'/(SHIELD_HOLES+'.kicad_mod')).write_text(shield_footprint(),encoding='utf-8')

def write_models():
 import FreeCAD as App
 import Part
 for name in [MALE,FEMALE]:
  doc=App.newDocument('Ali_interconnect')
  female=name==FEMALE;sign=-1 if female else 1;centre=sign*1.27
  def feature(label,shape):
   item=doc.addObject('Part::Feature',label);item.Shape=shape;return item
  body=Part.makeBox(5.,15.64,8.5 if female else 2.5,App.Vector(centre-2.5,-14.17,0))
  if female:
   # Open socket cavities only illustrate the mating envelope; unspecified
   # internal spring contacts are deliberately not fabricated as fit evidence.
   for col in range(6):
    for row in range(2):
     x=sign*row*2.54;y=-col*2.54
     body=body.cut(Part.makeBox(1.05,1.05,8.5,App.Vector(x-.525,y-.525,0)))
  feature('Socket_body_H8p5' if female else 'Base_insulator_H2p5',body)
  if not female:
   feature('Upper_insulator_Z23p5_to26',Part.makeBox(5.,15.64,2.5,App.Vector(centre-2.5,-14.17,23.5)))
  for col in range(6):
   for row in range(2):
    number=str(col*2+row+1);x=sign*row*2.54;y=-col*2.54
    if female:
     feature('Tail'+number,Part.makeBox(.6,.4,3.15,App.Vector(x-.3,y-.2,-3.15)))
    else:
     feature('Pin'+number+'_nominal_0p64',Part.makeBox(.64,.64,35.,App.Vector(x-.32,y-.32,-3.)))
  doc.recompute()
  out=ROOT/'design/MeshRepeater2_Power/3dmodels'/(name+'.step')
  Part.export(doc.Objects,str(out));App.closeDocument(doc.Name)
  target=ROOT/'design/MeshRepeater2_Logic/3dmodels'/out.name
  target.write_bytes(out.read_bytes())

def load_kicad():
 from kicad_headless import configure_headless
 configure_headless()
 import pcbnew
 configure_headless()
 return pcbnew

def vec(k,x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def xy(k,p):return k.ToMM(p.x),k.ToMM(p.y)

def text(k,b,s,x,y,layer,size=.85,angle=0):
 t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(vec(k,x,y));t.SetLayer(layer)
 t.SetTextSize(vec(k,size,size));t.SetTextThickness(k.FromMM(.13));t.SetMirrored(layer==k.B_SilkS)
 t.SetTextAngle(k.EDA_ANGLE(angle,k.DEGREES_T));b.Add(t);return t

def replace_connector(k,b,which):
 ref='J101' if which=='POWER' else 'J201';name=MALE if which=='POWER' else FEMALE
 project=ROOT/'design'/('MeshRepeater2_'+which.title())
 old=next(f for f in b.GetFootprints() if f.GetReference()==ref)
 f=k.FootprintLoad(str(project/'Meshcore.pretty'),name)
 selected_description=f.GetLibDescription()
 f.SetUuid(old.m_Uuid);f.SetPath(old.GetPath());f.SetFPID(k.LIB_ID('Meshcore',name))
 f.SetReference(ref);f.SetValue('INTERBOARD 12P')
 for field in old.GetFields():
  if field.GetName() not in ['Reference','Value','Footprint']:f.SetField(field.GetName(),field.GetText())
 f.SetField('MPN','E-SIMPO 2x6P L35mm A3C6' if which=='POWER' else 'MTJ/JinSheng 2x6P H8.5')
 f.SetField('Vendor','AliExpress');f.SetField('Vendor URL',URLS[name])
 f.SetField('Description',selected_description)
 f.SetField('Package','2x6 / 2.54 / L35 / vertical' if which=='POWER' else '2x6 / 2.54 / H8.5 / vertical')
 for field in f.GetFields():field.SetVisible(False)
 f.SetPosition(vec(k,64.15,11 if which=='POWER' else 49));f.SetOrientationDegrees(90)
 ni={n.GetNetname():n for n in b.GetNetInfo().NetsByNetcode().values()}
 for name in set(PINMAP.values()):
  if name not in ni:
   net=k.NETINFO_ITEM(b,name,max(ni0.GetNetCode() for ni0 in ni.values())+1);b.Add(net);ni[name]=net
 for p in f.Pads():p.SetNet(ni[PINMAP[p.GetNumber()]])
 b.Remove(old);KEEP.append(old);b.Add(f)
 return f

def run_drc(k,path,label,parity=False):
 output=AUDIT/(path.stem+'_'+label+'_drc.json')
 command=['C:/Program Files/KiCad/10.0/bin/kicad-cli.exe','pcb','drc','--format','json','--severity-all','--refill-zones','--save-board']
 if parity:command.append('--schematic-parity')
 subprocess.run(command+['-o',str(output),str(path)],check=True,stdout=subprocess.PIPE)
 return json.loads(output.read_text(encoding='utf-8'))

def trim_connector_leaves(k,b):
 """Remove obsolete single-ended branches on changed nets in memory."""
 removed=[]
 def pdist(p,a,z):
  dx,dy=z[0]-a[0],z[1]-a[1];d=dx*dx+dy*dy
  q=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/d))if d else 0
  return math.dist(p,(a[0]+q*dx,a[1]+q*dy))
 for iteration in range(400):
  tracks=[t for t in b.GetTracks()if t.GetNetname() in PINMAP.values() and t.GetNetname()!='GND']
  pads=[p for f in b.GetFootprints()for p in f.Pads()if p.GetNetname() in PINMAP.values()]
  geometries={str(t.m_Uuid.AsString()):(xy(k,t.GetStart()),xy(k,t.GetEnd()))for t in tracks}
  drop=[]
  for t in tracks:
   if isinstance(t,k.PCB_VIA):continue
   tid=str(t.m_Uuid.AsString());net=t.GetNetCode();layer=t.GetLayer()
   for at in geometries[tid]:
    if any(p.GetNetCode()==net and p.IsOnLayer(layer)and p.HitTest(vec(k,*at),0)for p in pads):continue
    attached=False
    for u in tracks:
     uid=str(u.m_Uuid.AsString())
     if uid==tid or u.GetNetCode()!=net or not u.IsOnLayer(layer):continue
     if pdist(at,*geometries[uid])<.001:attached=True;break
    if not attached:drop.append(t);break
  if not drop:break
  for t in drop:
   tid=str(t.m_Uuid.AsString());a,z=geometries[tid]
   removed.append({'uuid':tid,'net':t.GetNetname(),'start':a,'end':z,'reason':'obsolete connector leaf'})
   b.Remove(t);KEEP.append(t)
 for t in list(b.GetTracks()):
  if isinstance(t,k.PCB_VIA) and t.GetNetname() in PINMAP.values() and t.GetNetname()!='GND':
   at=xy(k,t.GetPosition())
   if not any(u!=t and u.GetNetCode()==t.GetNetCode()and pdist(at,xy(k,u.GetStart()),xy(k,u.GetEnd()))<.001 for u in b.GetTracks()):
    removed.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname(),'start':at,'end':at,'reason':'obsolete connector via'});b.Remove(t);KEEP.append(t)
 return removed

def update_board(which):
 k=load_kicad();import complete_v2_routes as base
 AUDIT.mkdir(parents=True,exist_ok=True)
 path=ROOT/'design'/('MeshRepeater2_'+which.title())/('MeshRepeater2_'+which.title()+'.kicad_pcb')
 before=AUDIT/(path.stem+'_before.kicad_pcb')
 if not before.exists():shutil.copy2(path,before)
 b=k.LoadBoard(str(path));KEEP.append(b)
 chosen=MALE if which=='POWER' else FEMALE
 if any(f.GetFPID().GetLibItemName()==chosen for f in b.GetFootprints()):
  check=run_drc(k,path,'existing_check')
  if not check['violations']and not check['unconnected_items']:
   print('Existing vertical interconnect is already DRC clean: '+which,flush=True);return
 j10=next((f for f in b.GetFootprints() if f.GetReference()=='J10'),None)
 isp=None if j10 is None else {'xy':xy(k,j10.GetPosition()),'angle':j10.GetOrientationDegrees(),'uuid':str(j10.m_Uuid.AsString())}
 f=replace_connector(k,b,which);removed=[]
 # Remove only local old connector branches; retain the rest of reviewed routes.
 y0,y1=(46.6,52.7) if which=='LOGIC' else (6.2,14.2)
 for t in list(b.GetTracks()):
  a,z=xy(k,t.GetStart()),xy(k,t.GetEnd())
  endpoint_inside=any(62.3<=p[0]<=79.8 and y0<=p[1]<=y1 for p in [a,z])
  if endpoint_inside and t.GetNetname() in ['FILTER_OUT','MODE','BAT','GND'] and not isinstance(t,k.PCB_VIA):
   removed.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname(),'start':a,'end':z})
   b.Remove(t);KEEP.append(t)
 # Delete obsolete connector label only; functional/operator labels stay.
 for t in list(b.GetDrawings()):
  if isinstance(t,k.PCB_TEXT):
   at=xy(k,t.GetPosition())
   if ('J201' if which=='LOGIC' else 'J101') in t.GetText() or (61<=at[0]<=80 and (40<=at[1]<=59 if which=='LOGIC' else 0<=at[1]<=17) and re.match(r'^\d+\s',t.GetText())):
    b.Remove(t);KEEP.append(t)
 if which=='LOGIC':
  text(k,b,'J201 2x6 H8.5',70.5,54.0,k.F_SilkS,.8)
  text(k,b,'J201 2x6 H8.5',70.5,58.2,k.B_SilkS,.8,180)
  # GND fence is preserved except one via moved away from the new SDA land.
  for t in b.GetTracks():
   if isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND' and math.dist(xy(k,t.GetPosition()),(73.5,52.5))<.01:t.SetPosition(vec(k,73.5,53.5))
 else:
  text(k,b,'J101 2x6 L35',70.5,4.9,k.F_SilkS,.8)
  text(k,b,'J101 2x6 L35',70.5,4.9,k.B_SilkS,.8)
 # Collapse obsolete leaf chains in memory before asking native DRC. The old
 # reviewed router split one battery-sense branch into many short octilinear
 # segments; removing one leaf per DRC subprocess is needlessly slow.
 removed.extend(trim_connector_leaves(k,b))
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(path),b)
 # Use the existing octilinear router with an explicit RF reference reservation.
 router=types.ModuleType('interconnect_router');router.__file__=base.__file__
 code=Path(base.__file__).read_text(encoding='utf-8').replace('CLEAR=.225','CLEAR=.275').replace('edge=.3+','edge=.55+')
 code=code.replace('if logic:rect(arr,(12,30.5,24,45.5),.31)','if logic:\n   rect(arr,(12,30.5,24,45.5),.31)\n   rect(arr,(31,.5,45,12),.31)')
 exec(code,router.__dict__)
 routes=[]
 for iteration in range(50):
  d=run_drc(k,path,'round'+str(iteration))
  b=k.LoadBoard(str(path));KEEP.append(b)
  lookup={str(t.m_Uuid.AsString()):t for t in b.GetTracks()}
  for fp in b.GetFootprints():
   for p in fp.Pads():lookup[str(p.m_Uuid.AsString())]=p
  # Remove only now-dangling old tails on modified connector nets.
  bad=[]
  for v in d['violations']:
   if v['type'] in ['track_dangling','via_dangling']:
    for item in v['items']:
     t=lookup.get(item['uuid'])
     if isinstance(t,k.PCB_TRACK) and t.GetNetname() in PINMAP.values():bad.append(t)
  for t in {str(t.m_Uuid.AsString()):t for t in bad}.values():
   removed.append({'uuid':str(t.m_Uuid.AsString()),'net':t.GetNetname(),'start':xy(k,t.GetStart()),'end':xy(k,t.GetEnd()),'reason':'obsolete dangling connector branch'})
   b.Remove(t);KEEP.append(t)
  if bad:k.SaveBoard(str(path),b);continue
  if not d['unconnected_items']:break
  for pair in d['unconnected_items']:
   a,z=pair['items']
   if a['uuid'] not in lookup or z['uuid'] not in lookup:continue
   ai,zi=lookup[a['uuid']],lookup[z['uuid']];net=ai.GetNetname()
   if net not in PINMAP.values():raise RuntimeError('Unexpected missing net '+net)
   width=.8 if net=='FILTER_OUT' else .5 if net in ['GND','SYS_3V3'] else .2 if net=='BAT' and which=='LOGIC' else .25
   start=tuple(a['pos'][p] for p in ['x','y']);end=tuple(z['pos'][p] for p in ['x','y'])
   try:
    routed=router.route(b,net,start,end,width,base.item_layers(a['description']),base.item_layers(z['description']),which=='LOGIC',base.component_points(b,ai),base.component_points(b,zi))
   except RuntimeError:
    # The ADC divider has a narrow SMD escape; keep its 0.2mm high-impedance
    # sensing branch within native0.2mm clearance instead of the bulk guard.
    if net!='BAT' or which!='LOGIC':raise
    adc=types.ModuleType('adc_router');adc.__file__=base.__file__
    exec(code.replace('CLEAR=.275','CLEAR=.225'),adc.__dict__)
    routed=adc.route(b,net,start,end,width,base.item_layers(a['description']),base.item_layers(z['description']),True,base.component_points(b,ai),base.component_points(b,zi))
   routes.append(routed)
   k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(path),b)
  k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(path),b)
 else:raise RuntimeError('Interconnect routing rounds exhausted')
 d=run_drc(k,path,'final');b=k.LoadBoard(str(path));KEEP.append(b)
 j10=next((f for f in b.GetFootprints() if f.GetReference()=='J10'),None)
 if isp is not None:assert isp=={'xy':xy(k,j10.GetPosition()),'angle':j10.GetOrientationDegrees(),'uuid':str(j10.m_Uuid.AsString())}
 proof={'board':which,'source_sha256':sha(before),'native_sha256':sha(path),'pinmap':PINMAP,'connector':{'footprint':MALE if which=='POWER' else FEMALE,'origin':[64.15,11 if which=='POWER' else 49],'rotation':90},'removed_local_branches':removed,'new_routes':routes,'ISP_before_after':isp,'DRC_counts':{n:len(d.get(n,[])) for n in ['violations','unconnected_items','schematic_parity']},'DRC_violations':d['violations']}
 (AUDIT/(which.lower()+'_connector_changes.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'board':which,'DRC_counts':proof['DRC_counts']},ensure_ascii=False),flush=True)

def update_shield():
 k=load_kicad();AUDIT.mkdir(parents=True,exist_ok=True)
 project=ROOT/'design/MeshRepeater2_Shield';path=project/'MeshRepeater2_Shield.kicad_pcb'
 before=AUDIT/'MeshRepeater2_Shield_before.kicad_pcb'
 if not before.exists():shutil.copy2(path,before)
 b=k.LoadBoard(str(path));KEEP.append(b)
 old=next((f for f in b.GetFootprints() if f.GetReference()=='HS1'),None)
 f=k.FootprintLoad(str(project/'Shield.pretty'),SHIELD_HOLES);f.SetReference('HS1');f.SetFPID(k.LIB_ID('Shield',SHIELD_HOLES));f.SetPosition(vec(k,64.15,49))
 if old is not None:f.SetUuid(old.m_Uuid);b.Remove(old);KEEP.append(old)
 b.Add(f)
 replacements={
  'J101 <-> J201: cable pins 1:1; route around screen edge.':'J101 <-> J201: straight 2x6 pins THROUGH screen holes.',
  '1/3/5/7 FILTER_OUT   all even GND   9 BAT   11 MODE':'1/3/5 FILTER_OUT; 2/4/6/8 GND; 7 SYS_3V3; 9 BAT',
  'Cable supplies power/GND; metal stands are for shield contact.':'10 SDA; 11 MODE; 12 SCL. Stands connect shield foil.',
  'Full assembly instructions / cable / variants: project docs.':'Pin35mm / socket8.5mm / nominal engagement4.48mm.',
  'No SH1 frame/lid. Continuous foil: no slots or cut-out letters.':'12 x NPTH2.0mm / drill-to-foil gap0.50mm. Inspect pin fit.',
 }
 for t in b.GetDrawings():
  if isinstance(t,k.PCB_TEXT) and t.GetText() in replacements:t.SetText(replacements[t.GetText()])
 # Existing lower-face title at52.3 would intersect the new physical holes at
 # nativeY49..51.54; shorten its lateral span, keeping all text off the drilling.
 for t in b.GetDrawings():
  if isinstance(t,k.PCB_TEXT) and t.GetLayer()==k.F_SilkS and t.GetText()=='Disconnect solar + battery + USB before disassembly.':
   t.SetText('DISCONNECT ALL POWER BEFORE DISASSEMBLY');t.SetPosition(vec(k,42.,55.2));t.SetTextSize(vec(k,.8,.8))
  if isinstance(t,k.PCB_TEXT) and t.GetText()=='M3 holes 3.2mm / washer OD6 / PCB 1.52mm / foil one face':
   t.SetText('M3 3.2mm / contact OD6 / PCB1.52mm');t.SetPosition(vec(k,35,49.6));t.SetTextSize(vec(k,.85,.85))
  if isinstance(t,k.PCB_TEXT) and t.GetLayer()==k.B_SilkS and t.GetText()=='Mesh Repeater 2.0 / SHIELD / V2.0-A1':t.SetPosition(vec(k,35,52))
 # Merged circular copper clearances enclose five diamond-shaped isolated foil
 # slivers. Explicitly clear the whole contact array (copper only; no FR4 slot).
 z=next(z for z in b.Zones() if not z.GetIsRuleArea())
 outline=z.Outline()
 if outline.HoleCount(0)==0:
  hole=outline.NewHole(0)
  for x,y in [(62.65,47.5),(78.35,47.5),(78.35,53.04),(62.65,53.04)]:outline.Append(vec(k,x,y),0,hole)
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(path),b)
 d=run_drc(k,path,'final');b=k.LoadBoard(str(path));KEEP.append(b)
 z=next(iter(b.Zones()));filled=k.SHAPE_POLY_SET(z.GetFilledPolysList(k.F_Cu));filled.Unfracture()
 assert filled.OutlineCount()==1,'Shield foil must stay one connected region'
 assert len(list(b.GetTracks()))==0
 fp=next(f for f in b.GetFootprints() if f.GetReference()=='HS1')
 holes=[{'native_xy_mm':xy(k,p.GetPosition()),'physical_xy_mm':[xy(k,p.GetPosition())[0],60-xy(k,p.GetPosition())[1]],'drill_mm':k.ToMM(p.GetDrillSize().x),'clearance_mm':.5}for p in fp.Pads()]
 proof={'source_sha256':sha(before),'native_sha256':sha(path),'foil_outline_count':filled.OutlineCount(),'foil_hole_count':sum(filled.HoleCount(i)for i in range(filled.OutlineCount())),'physical_drill_web_mm':.54,'copper_clearances_may_merge':True,'holes':holes,'drill_fit_status':'Sample and incoming inspection required; selected generic male section/straightness not documented. Nominal .64 square, maximum accepted diagonal .94, min actual hole1.95, max relative XY misregistration .25 and pin lateral deviation .15mm proposed acceptance conditions.','DRC_counts':{n:len(d.get(n,[]))for n in ['violations','unconnected_items','schematic_parity']},'DRC_violations':d['violations']}
 (AUDIT/'shield_connector_changes.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'shield_foil_outline_count':proof['foil_outline_count'],'DRC_counts':proof['DRC_counts']},ensure_ascii=False),flush=True)

def logic_labels():
 k=load_kicad();path=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(path));KEEP.append(b)
 legends=[('1/3/5 OUT | 2/4/6/8 GND',54.5),('7 3V3 | 9 BAT | 10 SDA',55.8),('11 MODE | 12 SCL',57.1)]
 known={t for t,y in legends}
 for t in list(b.GetDrawings()):
  if isinstance(t,k.PCB_TEXT)and t.GetLayer()==k.B_SilkS and t.GetText()in known:b.Remove(t);KEEP.append(t)
  if isinstance(t,k.PCB_TEXT)and t.GetLayer()==k.B_SilkS and t.GetText()=='J201 2x6 H8.5':t.SetPosition(vec(k,70.5,58.4))
 for value,y in legends:text(k,b,value,70.5,y,k.B_SilkS,.8,180)
 k.SaveBoard(str(path),b);d=run_drc(k,path,'pinout_labels')
 assert not d['violations']and not d['unconnected_items'],d['violations']
 print('LOGIC pinout markings DRC clean',flush=True)

def power_footprint_only():
 """After INA owner hands off: replace J101 without touching any copper."""
 k=load_kicad();path=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb';b=k.LoadBoard(str(path));KEEP.append(b)
 trackids={str(t.m_Uuid.AsString())for t in b.GetTracks()}
 old=next(f for f in b.GetFootprints()if f.GetReference()=='J101')
 assert {p.GetNumber():p.GetNetname()for p in old.Pads()}==PINMAP,'INA owner must first route final J101 net assignment'
 before=AUDIT/'power_ina_handoff_before_footprint.kicad_pcb'
 if not before.exists():shutil.copy2(path,before)
 replace_connector(k,b,'POWER')
 for t in list(b.GetDrawings()):
  if isinstance(t,k.PCB_TEXT):
   at=xy(k,t.GetPosition())
   if 'J101'in t.GetText()or(61<=at[0]<=80 and 0<=at[1]<=18 and re.match(r'^\d+\s',t.GetText())):b.Remove(t);KEEP.append(t)
 text(k,b,'J101 2x6 L35',70.5,4.9,k.F_SilkS,.8)
 # On POWER the rear-face connector map remains in the native lower-face
 # orientation; three lines avoid an unreadable single long annotation.
 text(k,b,'J101 2x6 L35',70.5,4.9,k.B_SilkS,.8)
 for value,y in [('1/3/5 OUT | 2/4/6/8 GND',14.7),('7 3V3 | 9 BAT | 10 SDA',16.0),('11 MODE | 12 SCL',17.3)]:text(k,b,value,70.5,y,k.B_SilkS,.8)
 assert trackids=={str(t.m_Uuid.AsString())for t in b.GetTracks()}
 k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(path),b);d=run_drc(k,path,'footprint_only')
 proof={'native_sha256':sha(path),'source_handoff_sha256':sha(before),'copper_track_uuids_unchanged':True,'connector_footprint':MALE,'pinmap':PINMAP,'DRC_counts':{n:len(d.get(n,[]))for n in ['violations','unconnected_items','schematic_parity']},'DRC_violations':d['violations']}
 (AUDIT/'power_footprint_only_changes.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(proof['DRC_counts']),flush=True)

def mating_proof():
 """Read all three saved boards, without modifying or refilling them."""
 k=load_kicad();paths={name:ROOT/'design'/('MeshRepeater2_'+name.title())/('MeshRepeater2_'+name.title()+'.kicad_pcb')for name in ['POWER','LOGIC','SHIELD']}
 hashes={name:sha(path)for name,path in paths.items()}
 boards={name:k.LoadBoard(str(path))for name,path in paths.items()};KEEP.extend(boards.values())
 male=next(f for f in boards['POWER'].GetFootprints()if f.GetReference()=='J101')
 female=next(f for f in boards['LOGIC'].GetFootprints()if f.GetReference()=='J201')
 holes=next(f for f in boards['SHIELD'].GetFootprints()if f.GetReference()=='HS1')
 assert str(male.GetFPID().GetLibItemName()).startswith(MALE)
 assert str(female.GetFPID().GetLibItemName()).startswith(FEMALE)
 mp={p.GetNumber():p for p in male.Pads()};fp={p.GetNumber():p for p in female.Pads()};hp=list(holes.Pads())
 assert set(mp)==set(fp)==set(PINMAP)and len(hp)==12
 rows=[];used_holes=set()
 for number,expected in PINMAP.items():
  p=xy(k,mp[number].GetPosition());f=xy(k,fp[number].GetPosition());physical_f=(f[0],60-f[1])
  assert math.dist(p,physical_f)<1e-6,(number,p,physical_f)
  assert mp[number].GetNetname()==fp[number].GetNetname()==expected,(number,mp[number].GetNetname(),fp[number].GetNetname(),expected)
  matching=[h for h in hp if math.dist(p,(xy(k,h.GetPosition())[0],60-xy(k,h.GetPosition())[1]))<1e-6]
  assert len(matching)==1,(number,p,matching)
  h=matching[0];huid=str(h.m_Uuid.AsString());assert huid not in used_holes;used_holes.add(huid)
  assert h.GetAttribute()==k.PAD_ATTRIB_NPTH and abs(k.ToMM(h.GetDrillSize().x)-2)<1e-6
  rows.append({'pin':number,'net':expected,'POWER_actual_xy_mm':p,'LOGIC_native_xy_mm':f,'physical_LOGIC_xy_mm':physical_f,'shield_native_xy_mm':xy(k,h.GetPosition()),'physical_hole_xy_mm':[xy(k,h.GetPosition())[0],60-xy(k,h.GetPosition())[1]],'hole_drill_mm':k.ToMM(h.GetDrillSize().x),'hole_uuid':huid})
 isp=next(f for f in boards['LOGIC'].GetFootprints()if f.GetReference()=='J10')
 assert xy(k,isp.GetPosition())==(35.7,31.3)and abs(isp.GetOrientationDegrees())<1e-6
 foil=next(z for z in boards['SHIELD'].Zones()if not z.GetIsRuleArea());filled=k.SHAPE_POLY_SET(foil.GetFilledPolysList(k.F_Cu));filled.Unfracture()
 assert filled.OutlineCount()==1 and sum(filled.HoleCount(i)for i in range(filled.OutlineCount()))==5
 assert hashes=={name:sha(path)for name,path in paths.items()},'Input native board changed while checking mating'
 proof={'status':'SAVED_NATIVE_THREE_BOARD_ALIGNMENT_PASS','inputsha256':hashes,'input_sha256':hashes,'native_files':{name:str(path.relative_to(ROOT))for name,path in paths.items()},'matched_pins':rows,'actual_footprints':{'POWER':str(male.GetFPID().GetLibItemName()),'LOGIC':str(female.GetFPID().GetLibItemName()),'SHIELD':str(holes.GetFPID().GetLibItemName())},'all_12_actual_holes_match_actual_pads':True,'all_12_actual_physical_net_roles_match':True,'ISP_J10_native_xy_mm':xy(k,isp.GetPosition()),'ISP_J10_angle_deg':isp.GetOrientationDegrees(),'shield_foil_outline_count':1,'shield_foil_void_count':5,'nominal_working_face_gap_mm':36.02,'male_tip_above_POWER_mm':32,'socket_body_height_mm':8.5,'nominal_socket_insertion_mm':4.48,'sample_contact_fit_required':True,'height_qualification':'Selected sale drawings and fixed nominal stack only; this proves coordinate/net mating, not undocumented spring-contact fit or pin straightness.'}
 (AUDIT/'vertical_coordinate_mating.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':proof['status'],'input_sha256':hashes}),flush=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--footprints',action='store_true');ap.add_argument('--models',action='store_true');ap.add_argument('--board',choices=['LOGIC','POWER']);ap.add_argument('--shield',action='store_true');ap.add_argument('--logic-labels',action='store_true');ap.add_argument('--power-footprint-only',action='store_true');ap.add_argument('--mating-proof',action='store_true');args=ap.parse_args()
 if args.footprints:write_footprints()
 if args.models:write_models()
 if args.board:update_board(args.board)
 if args.shield:update_shield()
 if args.logic_labels:logic_labels()
 if args.power_footprint_only:power_footprint_only()
 if args.mating_proof:mating_proof()

if __name__=='__main__':main()
