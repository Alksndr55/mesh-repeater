"""Preserve previous published evidence before canonical reports are refreshed."""
from pathlib import Path
import hashlib, json, subprocess

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
paths=['audit/V2_FINAL_ACCEPTANCE.json','audit/v2_native_boards_final.json','audit/v2_schematic_equivalence.json','audit/v2_routing_engineering.json','audit/v2_independent_final_review.json','audit/v2_manual_pdf_audit.json','docs/mechanics/assembly_geometry_report.json','docs/mechanics/native_render_report.json','docs/mechanics/assembly_pdf_audit.json']
saved=[]
for relative in paths:
    dest=OUT/'published_before'/relative
    dest.parent.mkdir(parents=True,exist_ok=True)
    content=subprocess.check_output(['git','cat-file','blob',head+':'+relative],cwd=ROOT)
    dest.write_bytes(content)
    saved.append({'path':relative,'sha256':hashlib.sha256(content).hexdigest(),'copy':str(dest.relative_to(ROOT))})
data={'source_commit':head,'changes_scope':'V2 only; fix R1,R2,M-01,M-02,DOC-01 from independent audit, retain previously explicit electrical conditions pending user selection','preserved_reports':saved,'baseline_native_pcb_sha256':hashlib.sha256((ROOT/'baseline/S4_16/Meshcore_NaIon.kicad_pcb').read_bytes()).hexdigest()}
(OUT/'SOURCE.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'source_commit':head,'reports_saved':len(saved)},ensure_ascii=False))
