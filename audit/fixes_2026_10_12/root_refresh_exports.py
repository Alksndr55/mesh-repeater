"""Bind current derived exports to saved native boards; no CAD mutations."""
from pathlib import Path
import hashlib, json, shutil

ROOT=Path(__file__).resolve().parents[2]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for name in ('POWER','LOGIC','SHIELD'):
    directory=ROOT/'output'/name
    stem='MeshRepeater2_'+name.title()
    path=directory/(stem+'_exports.json')
    m=json.loads(path.read_text(encoding='utf-8'))
    assert sha(ROOT/m['pcb'])==m['sha256'],name
    fresh=ROOT/'audit/fixes_2026_10_12'/(name.lower()+'_saved_drc.json')
    d=json.loads(fresh.read_text(encoding='utf-8'))
    assert not any(d.get(k) for k in ('violations','unconnected_items','schematic_parity','ignored_checks')),name
    shutil.copyfile(fresh,directory/(stem+'_drc.json'))
    log=directory/(stem+'_step_export.log')
    if log.exists():
        text=log.read_text(encoding='utf-8')
        m['step_export']={'exit_code':0,'wire_self_interference_warnings':text.count('Wire self-interference check failed'),'copper_fidelity_qualified':False,'log':str(log.relative_to(ROOT))}
    m['artifacts']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted(directory.glob(stem+'*')) if p.is_file() and p!=path]
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    rows.append({'board':name,'pcb_sha256':m['sha256'],'artifact_count':len(m['artifacts']),'step_export':m.get('step_export')})
print(json.dumps(rows))
