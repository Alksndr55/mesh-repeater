"""Remove the single audited obsolete C53 tail, keeping all other copper."""
from finish_v2_markings import ROOT,k,invariant,xy
import hashlib,json,subprocess

def main():
 p=ROOT/'design/MeshRepeater2_Power/MeshRepeater2_Power.kicad_pcb';before_sha=hashlib.sha256(p.read_bytes()).hexdigest();b=k.LoadBoard(str(p));uid='d5854ce5-c7f2-4d14-bc95-6994ace6fa8a';items=[t for t in b.GetTracks() if t.m_Uuid.AsString()==uid]
 if not items:print('Audited old C53 tail already absent');return
 t=items[0];assert t.GetNetname()=='BAT' and not isinstance(t,k.PCB_VIA) and abs(k.ToMM(t.GetLength())-.565685)<.002
 row={'uuid':uid,'net':t.GetNetname(),'layer':k.LayerName(t.GetLayer()),'from_mm':xy(t.GetStart()),'to_mm':xy(t.GetEnd()),'width_mm':k.ToMM(t.GetWidth()),'reason':'native DRC dangling tail at former C53 pad; new C53 pose48/11.9 has independent real connection'}
 b.Remove(t);retained=t;expected=invariant(b);k.ZONE_FILLER(b).Fill(b.Zones());settings=p.with_suffix('.kicad_pro').read_bytes();k.SaveBoard(str(p),b);p.with_suffix('.kicad_pro').write_bytes(settings);again=k.LoadBoard(str(p));assert invariant(again)==expected
 report=ROOT/'audit/v2_power_old_c53_tail_pruned.json';result={'before_pcb_sha256':before_sha,'after_pcb_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'removed':row,'all_other_electrical_placement_geometry_unchanged':True,'expected_retained_geometry_sha256':expected};report.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))
if __name__=='__main__':main()
