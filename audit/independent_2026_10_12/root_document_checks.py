from pathlib import Path
import csv, hashlib, json, re, urllib.parse

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
selected = [ROOT/'README.md', ROOT/'START_HERE_RU.md', ROOT/'output/V2_OVERVIEW_RU.html', *sorted((ROOT/'docs').glob('V2_*.md'))]
broken, checked = [], []
for path in selected:
    text = path.read_text(encoding='utf-8')
    urls = re.findall(r'(?:href|src)="([^"]+)"', text) if path.suffix == '.html' else re.findall(r'\]\(([^)\n]+)\)', text)
    for url in urls:
        if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',url) or url.startswith('#'):
            continue
        target = urllib.parse.unquote(url.split('#')[0]).strip('<>')
        if not target:
            continue
        dest = (path.parent / target).resolve()
        record = {'source':str(path.relative_to(ROOT)), 'url':url, 'exists':dest.exists()}
        checked.append(record)
        if not record['exists']:
            broken.append(record)

rows = list(csv.DictReader((ROOT/'bom/V2_COMPONENT_BOM.csv').open(encoding='utf-8-sig',newline='')))
ambiguous = [{k:r[k] for k in ('Board','Reference','Value_NaIon_COLD','Value_NaIon_NoCOLD','Value_LTO_2S','Physical_Package_Footprint','Note')} for r in rows if r['Reference'] in ('H1','H2','H3','H4')]
findings = [{'id':'DOC-01','severity':'low','origin':'V2 BOM integration','status':'confirmed','file':'bom/V2_COMPONENT_BOM.csv','line':71,'problem':'H1–H4 values say M3 NPTH, while physical footprint and notes specify grounded plated through holes. Native CAD is PTH; the ambiguity is in BOM text, not drill data.','recommended_fix':'Change all three assembly value labels for H1–H4 to M3 PTH GND, retaining geometry and purchase=no.','evidence':ambiguous}]
data = {'scope':'V2 document links and manufacturing wording; local existence is not supplier availability', 'checked_local_links':len(checked), 'broken_local_links':broken,'findings':findings,'legacy_manifest_status':'Root publication_manifest.json explicitly describes S4.16/ver1.0; V2 links use audit/V2_FINAL_ACCEPTANCE.json. It is legacy, not V2 evidence.','inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*selected,ROOT/'bom/V2_COMPONENT_BOM.csv',ROOT/'publication_manifest.json']}}
(OUT/'root_document_checks.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checked_local_links':len(checked),'broken_local_links':broken,'findings':[f['id'] for f in findings]},ensure_ascii=False))
