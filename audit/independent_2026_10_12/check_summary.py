from pathlib import Path
from html.parser import HTMLParser
import hashlib, json, urllib.parse

OUT=Path(__file__).resolve().parent
path=OUT/'SUMMARY_RU.html'
class Inspect(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.articles=0; self.images=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='article':self.articles+=1
        if tag=='img':self.images+=1
        for key in ('href','src'):
            if key in a:self.links.append(a[key])
p=Inspect();p.feed(path.read_text(encoding='utf-8'))
broken=[]
for url in p.links:
    if urllib.parse.urlparse(url).scheme:continue
    if not (OUT/urllib.parse.unquote(url.split('#')[0])).exists():broken.append(url)
data={'html_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'local_links_checked':sum(not urllib.parse.urlparse(u).scheme for u in p.links),'broken_local_links':broken,'articles':p.articles,'expected_articles':7,'evidence_images':p.images,'pass':not broken and p.articles==7 and p.images==2}
(OUT/'summary_quality.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
if not data['pass']:raise SystemExit(1)
