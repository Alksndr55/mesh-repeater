"""Correct only obsolete mounting-hole assembly metadata in current V2 files."""
from pathlib import Path
import hashlib, json, subprocess, sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools/cad'))
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
from sync_v2_footprint_library import local_geometry

project = ROOT/'design/MeshRepeater2_Power'
pcb = project/'MeshRepeater2_Power.kicad_pcb'
sch = project/'Interconnect.kicad_sch'
model_path = project/'model.json'
mapping_path = ROOT/'audit/MeshRepeater2_Power_footprint_variants.json'
targets = [pcb, sch, *[project/'Meshcore.pretty'/f'GND_M3_D3.2_OD6__V2_H{n}.kicad_mod' for n in range(1,5)]]
sha = lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
published = lambda p:subprocess.check_output(['git','cat-file','blob','HEAD:'+str(p.relative_to(ROOT)).replace('\\','/')], cwd=ROOT)
before = {str(p.relative_to(ROOT)):hashlib.sha256(published(p)).hexdigest() for p in [*targets, model_path, mapping_path]}
changes = []
for path in targets:
    old = published(path)
    count = old.count(b'M3 NPTH')
    assert count == (8 if path in (pcb, sch) else 2), (path,count)
    new = old.replace(b'M3 NPTH', b'M3 GND contact')
    assert path.read_bytes() in (old, new), ('Unexpected concurrent change',path)
    # Exact replacement preserves all other native tokens/UUIDs and geometry.
    assert len(new)-len(old) == count*(len(b'M3 GND contact')-len(b'M3 NPTH'))
    path.write_bytes(new)
    changes.append({'path':str(path.relative_to(ROOT)), 'property_text_replacements':count, 'only_literal_metadata_replaced':True})

model = json.loads(model_path.read_text(encoding='utf-8'))
for p in model['parts']:
    if p['ref'] not in {'H1','H2','H3','H4'}:continue
    assert p['kind'] == 'MountingHole' and p['value'] == 'M3 GND contact'
    p['value_lto2s'] = p['value']
    p['value_naion_no_cold'] = p['value']
for ref in ('H1','H2','H3','H4'):
    row = model['assembly_variants_authoritative'][ref]
    for field in ('Value_NaIon','Value_NaIon_NoCold','Value_LTO_2S'):
        row[field] = 'M3 GND contact'
model_path.write_text(json.dumps(model,ensure_ascii=False,indent=2),encoding='utf-8')

# Update the exact-library field mapping after independently loading both.
board = k.LoadBoard(str(pcb))
fps = {f.GetReference():f for f in board.GetFootprints()}
mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
field_checks = []
for row in mapping['maps']:
    if row['ref'] not in {'H1','H2','H3','H4'}:continue
    f = fps[row['ref']]
    proto = k.Cast_to_FOOTPRINT(f.Duplicate(False))
    proto.SetPosition(k.VECTOR2I(0,0));proto.SetOrientationDegrees(0)
    for p in proto.Pads():p.SetNetCode(0)
    lib = ROOT/row['library_file']
    loaded = k.FootprintLoad(str(lib.parent), lib.stem)
    native_geometry = local_geometry(proto)
    assert native_geometry == local_geometry(loaded), row['ref']
    row['library_sha256'] = sha(lib)
    row['normalized_native_geometry_sha256'] = native_geometry
    row['saved_library_geometry_sha256'] = native_geometry
    row['metadata_correction'] = 'Mounting hole variant labels NPTH -> GND contact; pad/drill/copper/Fab/courtyard/3D unchanged by exact text substitution.'
    fields = {field.GetName():field.GetText() for field in f.GetFields()}
    for field in ('Value_LTO_2S','Value_NaIon_NoCold'):
        assert fields[field] == 'M3 GND contact'
    field_checks.append({'ref':row['ref'],'native_equals_library':True,'variant_labels':'M3 GND contact'})
mapping['pcb_sha256'] = sha(pcb)
mapping['model_sha256'] = sha(model_path)
mapping['metadata_correction_proof'] = 'audit/fixes_2026_10_12/root_hole_metadata.json'
mapping_path.write_text(json.dumps(mapping,ensure_ascii=False,indent=2),encoding='utf-8')
data = {'purpose':'Extend DOC-01 fix into current hidden variant labels; frozen S4.16 contract not edited.', 'before_sha256':before, 'after_sha256':{p:sha(ROOT/p) for p in before}, 'native_changes':changes, 'library_mapping_checks':field_checks, 'physical_geometry_modified':False, 'functional_nets_modified':False}
(OUT/'root_hole_metadata.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'metadata_files':len(targets),'hole_checks':field_checks,'physical_geometry_modified':False}))
