"""Partition the verified S4.16 native geometry; keep critical local routes.

Only v2 files are written. The final net/UUID source is the native v2 schematic,
not the historic sheet names. Rebuilds are deliberate and reproducible.
"""
from pathlib import Path
import argparse, json, math, shutil, xml.etree.ElementTree as ET
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'baseline/S4_16'
CONTRACT=json.loads((ROOT/'design/v2_electrical_contract.json').read_text(encoding='utf-8'))
SOURCE={p['reference']:p for p in CONTRACT['parts']}
OLD_TO_LOGICAL={p['native_net']:p['logical_net'] for v in SOURCE.values() for p in v['exact_netpins'].values() if p['logical_net'] is not None}
def vec(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def xy(p):return k.ToMM(p.x),k.ToMM(p.y)
def text(b,s,pos,size=.9,layer=k.F_SilkS,angle=0):
 t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(vec(*pos));t.SetTextSize(vec(size,size));t.SetTextThickness(k.FromMM(max(.13,size*.16)));t.SetLayer(layer);t.SetMirrored(layer==k.B_SilkS);t.SetTextAngle(k.EDA_ANGLE(angle,k.DEGREES_T));b.Add(t);return t
def line(b,a,z,layer=k.Edge_Cuts,width=.05):
 t=k.PCB_SHAPE();t.SetShape(k.SHAPE_T_SEGMENT);t.SetStart(vec(*a));t.SetEnd(vec(*z));t.SetLayer(layer);t.SetWidth(k.FromMM(width));b.Add(t)
def rectangle(b,r,layer,width=.15):
 x,y,z,w=r
 for a,c in [((x,y),(z,y)),((z,y),(z,w)),((z,w),(x,w)),((x,w),(x,y))]:line(b,a,c,layer,width)
def plane(b,net,layer,r=(.4,.4,89.6,59.6),name='GND'):
 z=k.ZONE(b);z.SetLayer(layer);z.SetNet(net);z.SetZoneName(name);z.SetLocalClearance(k.FromMM(.2));z.SetMinThickness(k.FromMM(.2));z.SetThermalReliefGap(k.FromMM(.25));z.SetThermalReliefSpokeWidth(k.FromMM(.4));z.SetPadConnection(k.ZONE_CONNECTION_THERMAL)
 o=z.Outline();o.NewOutline();x,y,w,h=r
 for p in [(x,y),(w,y),(w,h),(x,h)]:o.Append(*vec(*p))
 b.Add(z);return z
def keepout(b,r):
 z=k.ZONE(b);z.SetIsRuleArea(True);z.SetZoneName('BLE_ANTENNA_NO_COPPER');z.SetLayerSet(k.LSET.AllCuMask(2));z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True);z.SetDoNotAllowZoneFills(True);o=z.Outline();o.NewOutline();x,y,w,h=r
 for p in [(x,y),(w,y),(w,h),(x,h)]:o.Append(*vec(*p))
 b.Add(z)
def native_nets(board_name,model):
 xml=ET.parse(ROOT/'audit/schematic'/board_name/'netlist.xml'); pins={};nn={}
 for node in xml.findall('nets/net'):
  name=node.get('name');nn[name]=node.get('code')
  for ep in node.findall('node'):
   if not ep.get('ref','').startswith('#'):pins[(ep.get('ref'),ep.get('pin'))]=name
 logical={}
 for p in model['parts']:
  for pin,net in p['nets'].items():
   if net is not None:
    name=pins[(p['ref'],pin)];assert logical.setdefault(net,name)==name,(net,name,logical[net])
 fields={n.get('ref'):{v.get('name'):v.text or '' for v in n.findall('fields/field')} for n in xml.findall('components/comp')}
 return pins,nn,logical,fields
def segment_dist(point,a,c):
 dx,dy=c[0]-a[0],c[1]-a[1];q=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
 return math.dist(point,(a[0]+q*dx,a[1]+q*dy))
def trim_dangling(b):
 # Remove abandoned connector branches after partition. A ground via is a
 # legitimate plane connection and does not need a terminal component pad.
 removed=0
 for iteration in range(30):
  tracks=list(b.GetTracks());pads=[p for f in b.GetFootprints() for p in f.Pads()];drop=[]
  for t in tracks:
   if isinstance(t,k.PCB_VIA) or t.GetNetname()=='GND':continue
   for at in [xy(t.GetStart()),xy(t.GetEnd())]:
    # A connection may terminate anywhere inside a same-net land.
    if any(p.GetNetCode()==t.GetNetCode() and p.IsOnLayer(t.GetLayer()) and p.HitTest(vec(*at),0) for p in pads):continue
    attached=False
    for u in tracks:
     if u==t or u.GetNetCode()!=t.GetNetCode() or not u.IsOnLayer(t.GetLayer()):continue
     if segment_dist(at,xy(u.GetStart()),xy(u.GetEnd()))<.001:attached=True;break
    if not attached:drop.append(t);break
  if not drop:break
  for t in drop:b.Remove(t);removed+=1
 # Unused signal vias left by abandoned branches do not establish connectivity.
 for t in list(b.GetTracks()):
  if not isinstance(t,k.PCB_VIA) or t.GetNetname()=='GND':continue
  if not any(u!=t and u.GetNetCode()==t.GetNetCode() and segment_dist(xy(t.GetPosition()),xy(u.GetStart()),xy(u.GetEnd()))<.001 for u in b.GetTracks()):b.Remove(t);removed+=1
 return removed
def build(which):
 project=ROOT/'design'/('MeshRepeater2_'+which.title());model=json.loads((project/'model.json').read_text(encoding='utf-8'));parts={p['ref']:p for p in model['parts']}
 pins,nn,logical,fields=native_nets(which,model)
 old=k.LoadBoard(str(BASE/'Meshcore_NaIon.kicad_pcb'));b=k.BOARD();b.SetDesignSettings(old.GetDesignSettings())
 nets={name:k.NETINFO_ITEM(b,name,i+1) for i,name in enumerate(sorted(nn))}
 for ni in nets.values():b.Add(ni)
 originals={f.GetReference():f for f in old.GetFootprints()};fps={}
 for ref,p in parts.items():
  oldfp=originals.get(ref);name=p['footprint'].split(':')[-1]
  f=k.Cast_to_FOOTPRINT(oldfp.Duplicate(False)) if oldfp is not None and str(oldfp.GetFPID().GetLibItemName())==name else k.FootprintLoad(str(project/'Meshcore.pretty'),name)
  if f is None:raise ValueError(('Missing actual footprint',ref,name))
  f.SetReference(ref);f.SetValue(p['value']);f.SetFPID(k.LIB_ID('Meshcore',name));f.SetPosition(vec(p['x'],p['y']));f.SetOrientationDegrees(p['rotation']);f.SetDNP(bool(p.get('dnp',False)))
  path=k.KIID_PATH()
  for u in (p['sheet_path']+'/'+p['schematic_uuid']).strip('/').split('/'):path.push_back(k.KIID(u))
  f.SetPath(path)
  for name,value in fields.get(ref,{}).items():
   if name!='Footprint':f.SetField(name,value)
  f.Reference().SetVisible(False);f.Value().SetVisible(False)
  for field in f.GetFields():
   if field.GetName() not in ['Reference','Value']:field.SetVisible(False)
  for pd in f.Pads():
   ep=(ref,pd.GetNumber())
   if ep in pins:pd.SetNet(nets[pins[ep]])
   else:pd.SetNetCode(0)
  # The continuous middle foil takes the place of the old removable lid.
  if ref=='SH1':
   mods=f.Models()
   for m in mods:
    if 'lid' in m.m_Filename.lower():m.m_Show=False
  b.Add(f);fps[ref]=f
 retained=0
 for t in old.GetTracks():
  ln=OLD_TO_LOGICAL.get(t.GetNetname())
  if ln not in logical:continue
  a,z=xy(t.GetStart()),xy(t.GetEnd())
  if which=='POWER':
   if min(a[1],z[1])<50 or max(a[1],z[1])>94:continue
   shift=(0,-37)
  else:
   if max(a[1],z[1])>48:continue
   shift=(0,0)
  u=t.Duplicate();u.Move(vec(*shift));u.SetNet(nets[logical[ln]]);u.SetLocked(True);b.Add(u);retained+=1
 # Keep the exact RF CPW zone, local antenna exclusion and original RF route.
 if which=='LOGIC':
  for z in old.Zones():
   if z.GetZoneName()=='RF_CPW_GND':
    zz=k.Cast_to_ZONE(z.Duplicate(False));zz.SetNet(nets[logical['GND']]);b.Add(zz)
  keepout(b,(12,30.5,24,45.5))
 b.SetCopperLayerCount(2);b.GetDesignSettings().SetBoardThickness(k.FromMM(1.52));rectangle(b,(0,0,90,60),k.Edge_Cuts,.05)
 b.GetTitleBlock().SetTitle('Mesh Repeater 2.0 — '+which);b.GetTitleBlock().SetRevision('V2.0-A1');b.GetTitleBlock().SetDate('2026-10-11');b.GetTitleBlock().SetCompany('Designed by @Alksndritm')
 plane(b,nets[logical['GND']],k.F_Cu,name='GND_TOP');plane(b,nets[logical['GND']],k.B_Cu,name='GND_REFERENCE')
 removed=trim_dangling(b)
 # Show ref/value next to the part, with its physical orientation. Mirrored
 # reverse labels project to the same footprint position, not an unrelated grid.
 for ref,f in fps.items():
  if ref.startswith(('H','SH','M','J','TP')):continue
  px,py=xy(f.GetPosition());p=parts[ref];ang=p['rotation']%180
  nominal=p['value'].split()[0];label=ref+' '+nominal
  if which=='POWER':text(b,label,(px,py),.75,k.B_SilkS,ang)
  else:text(b,label,(px,py),.75,k.B_SilkS,ang)
 if which=='POWER':
  text(b,'POWER V2.0-A1',(45,58.5),1.1);text(b,'D3 CHARGE',(51,4.5),.7);text(b,'D4 DONE',(56,4.5),.7)
  rectangle(b,(9.2,35.5,29.8,50.5),k.F_SilkS,.22);text(b,'LTO BALANCERS',(19.5,34.5),.9)
  rectangle(b,(33,35.5,50,55.7),k.F_SilkS,.22);text(b,'COLD OPTION',(41.5,34.5),.9)
 else:
  text(b,'Mesh Repeater 2.0',(47,50),1.7,k.B_SilkS,180);text(b,'Designed by @Alksndritm',(47,46.5),1,k.B_SilkS,180)
  text(b,'J11: REMOVE BEFORE USB',(71,40),.9,k.B_SilkS,180)
  # Exterior view is mirrored in Y by the assembly rotation: projected LEDs.
  text(b,'D3 CHARGE',(51,56),.75,k.B_SilkS,180);text(b,'D4 DONE',(56,56),.75,k.B_SilkS,180)
 output=project/(model['project']+'.kicad_pcb');k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(output),b)
 dru='(version 1)\n'
 if which=='LOGIC':dru+='(rule "RF GND gap 0.25 mm" (layer F.Cu) (condition "(A.NetName == \'ANT_RF\' || A.NetName == \'ANT_SMA\') && B.NetName == \'GND\'") (constraint clearance (min 0.25mm)))\n'
 (project/(model['project']+'.kicad_dru')).write_text(dru,encoding='utf-8')
 proof={'board':which,'retained_s4_16_track_items':retained,'abandoned_branch_items_removed':removed,'footprints':len(fps),'pcb':str(output.relative_to(ROOT)),'j10_preserved':None if which=='POWER' else {'xy':xy(fps['J10'].GetPosition()),'rotation':fps['J10'].GetOrientationDegrees()}}
 out=ROOT/'audit'/('v2_'+which.lower()+'_initial_geometry.json');out.write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',choices=['POWER','LOGIC','BOTH'],default='BOTH');args=ap.parse_args()
 for name in ['POWER','LOGIC'] if args.board=='BOTH' else [args.board]:build(name)
if __name__=='__main__':main()
