"""Synchronize current V2 PCB fields and schematic paths, without CAD edits.

Model+native XML must agree first. The already installed actual footprints
must match XML library IDs. No pads, nets, placement, copper, or models change.
Both an in-memory field-style check and a saved masked-S-expression comparison
bracket the write. A failed invariant restores the exact starting PCB bytes.
"""
from pathlib import Path
import argparse, hashlib, json, re, xml.etree.ElementTree as ET
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
ROOT=Path(__file__).resolve().parents[2]
KEEP=[]

def sha(data):return hashlib.sha256(data).hexdigest()
def safe(path):
 p=Path(path).resolve()
 if not p.is_relative_to(ROOT):raise ValueError('Metadata sync is confined to V2: '+str(p))
 return p

def parse(text):
 """Lossless-token S-expression tree; whitespace is semantically immaterial."""
 tokens=re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text)
 stack=[];result=None
 for token in tokens:
  if token=='(':
   node=[]
   if stack:stack[-1].append(node)
   stack.append(node)
  elif token==')':
   if not stack:raise ValueError('Unbalanced PCB S-expression')
   result=stack.pop()
  elif stack:stack[-1].append(token)
  else:raise ValueError('Unexpected PCB token')
 if stack or result is None:raise ValueError('Incomplete PCB S-expression')
 return result

def skeleton(node):
 if not isinstance(node,list):return node
 if node and node[0]=='footprint':
  return [skeleton(item)for item in node if not(isinstance(item,list)and item and item[0]in ['property','path'])]
 return [skeleton(item)for item in node]

def first_difference(a,z,path=()):
 if type(a)!=type(z):return {'path':path,'before':str(a)[:180],'after':str(z)[:180]}
 if isinstance(a,list):
  if len(a)!=len(z):return {'path':path,'before_list_length':len(a),'after_list_length':len(z)}
  for index,(aa,zz)in enumerate(zip(a,z)):
   d=first_difference(aa,zz,path+(index,))
   if d is not None:return d
 elif a!=z:return {'path':path,'before':str(a)[:180],'after':str(z)[:180]}
 return None

def full_fpid(f):
 fp=f.GetFPID();nick=str(fp.GetLibNickname());name=str(fp.GetLibItemName())
 return (nick+':' if nick else '')+name

def style(field):
 p=field.GetPosition();size=field.GetTextSize()
 return {'xy_iu':[p.x,p.y],'size_iu':[size.x,size.y],'angle_deg':field.GetTextAngle().AsDegrees(),
         'thickness_iu':field.GetTextThickness(),'layer':int(field.GetLayer()),'visible':field.IsVisible(),
         'mirrored':field.IsMirrored(),'hjust':int(field.GetHorizJustify()),'vjust':int(field.GetVertJustify())}

def expected_path(part,component):
 root_path=part['sheet_path'].strip('/').split('/')
 symbol=part['schematic_uuid'];component_stamps=(component.findtext('tstamps')or'').split()
 if symbol not in component_stamps:raise ValueError('Model/XML schematic UUID differs for '+part['ref'])
 xml_sheet=component.find('sheetpath').get('tstamps','').strip('/').split('/')
 if xml_sheet and any(xml_sheet):
  if root_path[-len(xml_sheet):]!=xml_sheet:raise ValueError('Model/XML sheet path differs for '+part['ref'])
 uuids=root_path+[symbol]
 if not all(re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',s)for s in uuids):raise ValueError('Invalid model UUID path for '+part['ref'])
 return '/'+('/'.join(uuids))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);ap.add_argument('--model',type=Path,required=True);ap.add_argument('--xml',type=Path,required=True);ap.add_argument('--report',type=Path);ap.add_argument('--check-only',action='store_true');args=ap.parse_args()
 pcb,model_path,xml_path=map(safe,[args.pcb,args.model,args.xml])
 report=safe(args.report)if args.report else safe(ROOT/'audit/ina219_vertical_interconnect_2026_10_12'/(pcb.stem+'_metadata_sync.json'))
 model=json.loads(model_path.read_text(encoding='utf-8'));parts={p['ref']:p for p in model['parts']}
 xml=ET.parse(xml_path);components={c.get('ref'):c for c in xml.findall('components/comp')}
 xml_pin_nets={(n.get('ref'),n.get('pin')):net.get('name')for net in xml.findall('nets/net')for n in net.findall('node')if not n.get('ref','').startswith('#')}
 initial=pcb.read_bytes();before_skeleton=skeleton(parse(initial.decode('utf-8')))
 project_path=pcb.with_suffix('.kicad_pro');project_bytes=project_path.read_bytes()if project_path.exists()else None
 b=k.LoadBoard(str(pcb));KEEP.append(b);footprints={f.GetReference():f for f in b.GetFootprints()}
 if len(footprints)!=len(list(b.GetFootprints())):raise ValueError('Duplicate native PCB references')
 if set(footprints)!=set(parts):raise ValueError('PCB/model reference set differs: '+str(set(footprints)^set(parts)))
 if not set(parts).issubset(components):raise ValueError('Native XML lacks model references')
 expected={};original_styles={};changes=[]
 # Validate all prerequisites before making any board mutation.
 for ref,part in parts.items():
  c=components[ref];f=footprints[ref];value=c.findtext('value')or'';fp=c.findtext('footprint')or''
  if value!=part['value']:raise ValueError('Model/XML value differs for '+ref)
  if fp!=part['footprint']or fp!=full_fpid(f):raise ValueError('Actual/model/XML footprint differs for '+ref+': '+repr([full_fpid(f),part['footprint'],fp]))
  for pad in f.Pads():
   key=(ref,pad.GetNumber());expected_net=xml_pin_nets.get(key)
   if expected_net is not None and pad.GetNetname()!=expected_net:raise ValueError('Actual/XML pad net differs for '+repr(key)+': '+repr([pad.GetNetname(),expected_net]))
  fields={e.get('name'):e.text or''for e in c.findall('fields/field')}
  fields.pop('Footprint',None);fields.pop('Reference',None);fields.pop('Value',None)
  fields.setdefault('Datasheet',c.findtext('datasheet')or'')
  fields.setdefault('Description',c.findtext('description')or'')
  expected[ref]={'value':value,'fields':fields,'path':expected_path(part,c),'footprint':fp}
  original_styles[ref]={q.GetName():style(q)for q in f.GetFields()}
 for ref,e in expected.items():
  f=footprints[ref];old_fields={q.GetName():q.GetText()for q in f.GetFields()}
  differing={name:{'before':old_fields.get(name),'after':value}for name,value in e['fields'].items()if old_fields.get(name)!=value}
  old_path=str(f.GetPath().AsString());old_value=f.GetValue()
  if differing or old_path!=e['path']or old_value!=e['value']:
   changes.append({'ref':ref,'fields':differing,'path_before':old_path,'path_after':e['path'],'value_before':old_value,'value_after':e['value']})
  if args.check_only:continue
  f.SetValue(e['value'])
  for name,value in e['fields'].items():
   existed=f.HasField(name);f.SetField(name,value)
   if not existed:f.GetField(name).SetVisible(False)
  path=k.KIID_PATH()
  for uuid in e['path'].strip('/').split('/'):path.push_back(k.KIID(uuid))
  f.SetPath(path)
  for name,prior in original_styles[ref].items():
   assert prior==style(f.GetField(name)),('Existing field style changed',ref,name)
 proof={'pcb':str(pcb.relative_to(ROOT)),'model':str(model_path.relative_to(ROOT)),'xml':str(xml_path.relative_to(ROOT)),
        'input_sha256':{'pcb':sha(initial),'model':sha(model_path.read_bytes()),'xml':sha(xml_path.read_bytes())},
        'allowed_mutations':['footprint property text values','new hidden property fields','schematic instance path'],
        'unchanged':['footprint library ID and UUID','placement and orientation','existing field style','pads and nets','tracks and vias','zones and filled geometry','3D models','all non-property footprint artwork','project settings'],
        'changes':changes,'check_only':args.check_only}
 if args.check_only:
  proof['status']='ALREADY_SYNCHRONIZED'if not changes else 'METADATA_SYNC_NEEDED';proof['native_sha256']=sha(initial)
 else:
  try:
   k.SaveBoard(str(pcb),b)
   # pcbnew can serialize process-default project settings. Restore the exact
   # caller-owned settings, never convert DRC severities or exclusions here.
   if project_bytes is not None and project_path.read_bytes()!=project_bytes:project_path.write_bytes(project_bytes)
   after=pcb.read_bytes();after_skeleton=skeleton(parse(after.decode('utf-8')))
   mismatch=first_difference(before_skeleton,after_skeleton)
   if mismatch is not None:raise AssertionError('PCB geometry changed during metadata synchronization: '+repr(mismatch))
   saved=k.LoadBoard(str(pcb));KEEP.append(saved);saved_fps={f.GetReference():f for f in saved.GetFootprints()}
   assert set(saved_fps)==set(footprints)
   for ref,e in expected.items():
    f=saved_fps[ref];assert f.GetValue()==e['value']and str(f.GetPath().AsString())==e['path'],ref
    actual={q.GetName():q.GetText()for q in f.GetFields()}
    assert all(actual.get(n)==v for n,v in e['fields'].items()),ref
    for name,prior in original_styles[ref].items():assert prior==style(f.GetField(name)),(ref,name)
   proof['status']='SYNCED_WITH_SAVED_GEOMETRY_INVARIANT'
   proof['masked_geometry_sha256']=sha(json.dumps(before_skeleton,separators=(',',':')).encode('utf-8'))
   proof['native_sha256']=sha(after)
  except Exception:
   pcb.write_bytes(initial)
   if project_bytes is not None:project_path.write_bytes(project_bytes)
   raise
 report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':proof['status'],'changed_parts':len(changes),'native_sha256':proof['native_sha256'],'report':str(report.relative_to(ROOT))}),flush=True)

if __name__=='__main__':main()
