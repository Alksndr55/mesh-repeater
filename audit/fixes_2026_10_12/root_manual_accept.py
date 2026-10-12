"""Record root's completed visual review of the regenerated assembly manual."""
from pathlib import Path
import hashlib, json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
review = json.loads((OUT/'root_pdf_manual.json').read_text(encoding='utf-8'))
pdf = ROOT/review['pdf']['path']
assert hashlib.sha256(pdf.read_bytes()).hexdigest() == review['pdf']['sha256']
assert review['page_count'] == 9 and min(p['text_characters'] for p in review['rendered_pages']) > 800
review['pending_visual_inspection'] = False
review['visual_review'] = 'Root inspected all nine pages on the Poppler contact sheet and page 3 at full render size. Tables, page breaks, Russian glyphs and new J3/J5 cable pin map are readable; no clipping or overlap found.'
(OUT/'root_pdf_manual.json').write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding='utf-8')
sources = ['docs/V2_ASSEMBLY_INSTRUCTIONS_RU.md', 'docs/V2_LIMITATIONS_RU.md', 'tools/cad/render_v2_manual.py']
report = {
    'pdf': review['pdf'], 'pages': review['page_count'], 'all_pages_visually_inspected': True,
    'render_method': 'Poppler PNG; all-page contact sheet plus full page 3',
    'empty_or_single_line_pages': False, 'fonts': 'Embedded Arial; searchable Russian text',
    'source_sha256': {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
    'visual_review_evidence': {'path':str((OUT/'root_pdf_manual.json').relative_to(ROOT)), 'sha256':hashlib.sha256((OUT/'root_pdf_manual.json').read_bytes()).hexdigest()},
}
(ROOT/'audit/v2_manual_pdf_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pages':report['pages'], 'pdf_sha256':review['pdf']['sha256']}))
