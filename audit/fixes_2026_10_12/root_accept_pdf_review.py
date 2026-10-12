"""Bind root's completed visual review to the exact PDF renders."""
from pathlib import Path
import hashlib, json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ('dimensions','power_schematic','logic_schematic'):
    file=OUT/('root_pdf_'+name+'.json')
    review=json.loads(file.read_text(encoding='utf-8'))
    assert sha(ROOT/review['pdf']['path'])==review['pdf']['sha256']
    for image in review['rendered_pages']:
        assert sha(ROOT/image['image'])==image['image_sha256']
    review['pending_visual_inspection']=False
    review['visual_review']='Root inspected all-page Poppler contact sheets; enlarged schematic sheets and dimension pages 1/3 inspected. Titles, component annotations, Russian text and tables readable; no clipping or overlaps found.'
    file.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
    if name=='dimensions':
        audit=ROOT/'docs/mechanics/assembly_pdf_audit.json'
        d=json.loads(audit.read_text(encoding='utf-8'))
        d['all_pages_visually_inspected']=True
        d['visual_review_evidence']={'path':str(file.relative_to(ROOT)),'sha256':sha(file)}
        d['source_sha256']={'tools/cad/build_v2_assembly_pdf.py':sha(ROOT/'tools/cad/build_v2_assembly_pdf.py')}
        audit.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'PDFs_visually_reviewed':['dimensions','power_schematic','logic_schematic']}))
