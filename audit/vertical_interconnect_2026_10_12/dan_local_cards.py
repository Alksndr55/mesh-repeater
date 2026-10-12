import urllib.request,re,html,json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'dan_local_sources';OUT.mkdir(exist_ok=True)
inventory=json.loads((ROOT/'dan_local_inventory.json').read_text(encoding='utf8'))['rows']
urls=[r['url'] for r in inventory if r['url'].split('/')[-2].split('-')[0] in ('209192','102464','195992','199685','199674','199675')]
urls+=['https://www.danomsk.ru/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/198108-sl-105-g-10-rozetka-plata-plata-/']

def fetch(u):
 with urllib.request.urlopen(u,timeout=40) as r:
  b=r.read();enc=r.headers.get_content_charset() or 'utf8'
 s=b.decode(enc,errors='replace'); aid=u.split('/')[-2].split('-')[0]
 (OUT/(aid+'.html')).write_text(s,encoding='utf8')
 s=re.sub(r'<(script|style)\b.*?</\1>','',s,flags=re.S|re.I)
 text=html.unescape(re.sub('<[^>]+>',' ',s));text=' '.join(text.split())
 (OUT/(aid+'.txt')).write_text(text,encoding='utf8')
 h1=re.search('<h1[^>]*>(.*?)</h1>',s,re.S|re.I)
 pdfs=list(set(urllib.parse.urljoin(u,p) for p in re.findall(r'href=["\']([^"\']+\.pdf)["\']',s,re.I)))
 start=text.find('Код товара:')
 body=text[start:start+700]
 return {'article':aid,'url':u,'title':html.unescape(re.sub('<[^>]+>',' ',h1.group(1))) if h1 else None,'card':body,'pdfs':pdfs}

if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(fetch,urls))
 (ROOT/'dan_local_cards.json').write_text(json.dumps({'date':'2026-10-12','cards':rows},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(rows,ensure_ascii=True,indent=2))
