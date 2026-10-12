"""Fresh read-only footprint proof: the mechanical model fix changed no pads."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('mechanical',ROOT/'tools/cad/build_v2_mechanical_library.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
import pcbnew as k
before=json.loads((OUT/'mechanics.before.json').read_text(encoding='utf-8'))
checks=[]
for target in module.DESIGNS:
    for name,d in module.DEFINITIONS.items():
        path=target/'Meshcore.pretty'/(name+'.kicad_mod')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        rel=str(path.relative_to(ROOT)).replace('\\','/')
        assert digest==before[rel],rel
        fp=k.FootprintLoad(str(path.parent),name);assert fp is not None
        actual=[]
        for pad in fp.Pads():
            pos=pad.GetPosition();drill=pad.GetDrillSize()
            actual.append((pad.GetNumber(),round(k.ToMM(pos.x),5),round(k.ToMM(pos.y),5),
                           round(k.ToMM(drill.x),5),
                           'NPTH' if pad.GetAttribute()==k.PAD_ATTRIB_NPTH else 'THT'))
        assert sorted(actual)==sorted(d['pads']),(name,actual,d['pads'])
        checks.append({'project':target.name,'footprint':name,'pads':len(actual),
           'pad_geometry':actual,'status':'KiCad10 load and dimension match; file unchanged by mechanical fixes',
           'path':rel,'sha256':digest,'checked':'2026-10-12'})
unchanged=[rel for rel,digest in before.items() if rel.endswith('.kicad_mod')
           and hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==digest]
assert len(unchanged)==sum(rel.endswith('.kicad_mod')for rel in before)
path=ROOT/'docs/mechanical_library_checks.json'
backup=OUT/'mechanical_library_checks.before.json';assert not backup.exists();shutil.copyfile(path,backup)
path.write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'mechanics.footprint_checks.json').write_text(json.dumps({
    'checked':'2026-10-12','mechanical_base_footprints':checks,
    'all_library_footprint_files_hash_unchanged':len(unchanged),
    'unchanged_paths':unchanged,'native_boards_written':False,
    'native_schematics_written':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'base_footprints_loaded':len(checks),
                 'all_library_footprint_files_hash_unchanged':len(unchanged),
                 'pad_geometry_changed':False}))
