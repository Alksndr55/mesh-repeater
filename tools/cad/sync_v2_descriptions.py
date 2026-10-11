"""Synchronize approved descriptive metadata from native XML, not copper.

Only Description is permitted. Functional fields, identifiers, pads, routes
and placement are bracketed by the same exact native invariant as markings.
Re-save local footprint variants afterwards, since their metadata is exact.
"""
from finish_v2_markings import ROOT,k,safe,invariant
import argparse,hashlib,json,xml.etree.ElementTree as ET

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--pcb',required=True);ap.add_argument('--netlist',required=True);a=ap.parse_args()
 pcb=safe(a.pcb);xml=safe(a.netlist);before_sha=sha(pcb);b=k.LoadBoard(str(pcb));before=invariant(b)
 fields={n.get('ref'):{v.get('name'):v.text or '' for v in n.findall('fields/field')} for n in ET.parse(xml).findall('components/comp')};changed=[]
 for f in b.GetFootprints():
  ref=f.GetReference();old=f.GetField('Description');value=fields[ref].get('Description','')
  text=old.GetText() if old else ''
  if text!=value:
   changed.append({'reference':ref,'field':'Description','old':text,'new':value});f.SetField('Description',value)
 after=invariant(b)
 for row in changed:b.FindFootprintByReference(row['reference']).SetField('Description',row['old'])
 assert invariant(b)==before,'A non-description field or geometry changed'
 for row in changed:b.FindFootprintByReference(row['reference']).SetField('Description',row['new'])
 assert invariant(b)==after
 assert sha(pcb)==before_sha,'Concurrent board mutation'
 if changed:
  settings=pcb.with_suffix('.kicad_pro').read_bytes();k.SaveBoard(str(pcb),b);pcb.with_suffix('.kicad_pro').write_bytes(settings)
  assert invariant(k.LoadBoard(str(pcb)))==after
 report={'source_pcb_sha256':before_sha,'pcb_sha256':sha(pcb),'netlist':str(xml.relative_to(ROOT)),'netlist_sha256':sha(xml),'description_changes':changed,'non_description_electrical_and_placement_unchanged':True,'exact_footprint_variants_resync_required':bool(changed)}
 dest=ROOT/'audit'/(pcb.stem+'_descriptions_sync.json');dest.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'descriptions_changed':len(changed),'engineering_geometry_unchanged':True}))
if __name__=='__main__':main()
