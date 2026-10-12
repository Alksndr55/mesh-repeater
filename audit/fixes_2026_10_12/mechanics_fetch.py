"""Read-only supplier and manufacturer source acquisition, V2 fixes only."""
from pathlib import Path
import urllib.request
import urllib.parse
import hashlib
import html
import json
import re
import sys

DEST = Path(__file__).parent / 'mechanics_sources'
DEST.mkdir(exist_ok=True)
url = sys.argv[1]
name = sys.argv[2]
with urllib.request.urlopen(url, timeout=45) as response:
    raw = response.read()
    metadata = {'url':url, 'final_url':response.url, 'status':response.status,
                'content_type':response.headers.get('Content-Type'),
                'sha256':hashlib.sha256(raw).hexdigest(), 'bytes':len(raw),
                'checked':'2026-10-12'}
(DEST/name).write_bytes(raw)
(DEST/(name+'.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False))
if not raw.startswith(b'%PDF'):
    text = raw.decode('utf-8',errors='replace')
    text = re.sub(r'<script\b.*?</script>|<style\b.*?</style>','',text,flags=re.S|re.I)
    for link, title in re.findall(r'<a[^>]+href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>(.*?)</a>',text,re.S):
        if any(s in title+link for s in ('BLS','1071','.pdf','PDF')):
            print(html.unescape(re.sub('<[^>]+>',' ',title)).strip(),urllib.parse.urljoin(url,link))
    plain = html.unescape(re.sub('<[^>]+>',' ',text))
    plain = re.sub(r'\s+',' ',plain)
    for marker in ('На складе','Цена','CONTACT','Specifications'):
        print(marker, [plain[max(0,m.start()-100):m.start()+180] for m in re.finditer(re.escape(marker),plain)])
