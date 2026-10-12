import urllib.request, re, html, json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'dan_local_sources'
OUT.mkdir(exist_ok=True)
URL='https://www.danomsk.ru/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/'

def fetch(p):
    u=URL+('?PAGEN_1='+str(p) if p>1 else '')
    with urllib.request.urlopen(u,timeout=40) as r:
        b=r.read(); encoding=r.headers.get_content_charset() or 'utf-8'
    s=b.decode(encoding, errors='replace')
    (OUT/f'catalog_page{p}.html').write_text(s,encoding='utf-8')
    rows=[]
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',s,re.S|re.I):
        href,text=match.groups(); text=html.unescape(re.sub('<[^>]+>',' ',text));text=' '.join(text.split())
        if '/306-soediniteli-pryamougolnye/' in href and len(href)>len('/shop/7-kommutatsiya/121-razemy/306-soediniteli-pryamougolnye/') and re.search(r'DS102[13]|\bP[LB][SD]-|\bPBS-|\bPBD-|\bPLS-',text,re.I):
            rows.append({'text':text,'url':urllib.parse.urljoin(URL,href),'page':p})
    return rows

if __name__=='__main__':
    rows=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(fetch,range(1,9)): rows.extend(result)
    rows=list({r['url']:r for r in rows}.values())
    (ROOT/'dan_local_inventory.json').write_text(json.dumps({'date':'2026-10-12','catalog_pages':8,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(rows,ensure_ascii=True))
