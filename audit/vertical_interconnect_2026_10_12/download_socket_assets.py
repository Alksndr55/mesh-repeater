from pathlib import Path
from urllib.request import urlopen
from concurrent.futures import ThreadPoolExecutor
import json
from PIL import Image, ImageDraw
p=Path(__file__).resolve().parent/'sources'
urls=json.loads((p/'ali_socket_images.json').read_text())
urls.append('https://ae-pic-a1.aliexpress-media.com/kf/S8e1a5b7da8914693856ceb887b51ddbdv.jpg')
def grab(item):
 i,u=item
 dest=p/f'ali_socket_2x6_asset_{i}.png'
 with urlopen(u,timeout=25) as r:
  raw=r.read()
 import io
 im=Image.open(io.BytesIO(raw)).convert('RGB');im.save(dest)
 return im
with ThreadPoolExecutor(max_workers=7) as pool: ims=list(pool.map(grab,enumerate(urls)))
sheet=Image.new('RGB',(1400,800),'white');draw=ImageDraw.Draw(sheet)
for i,im in enumerate(ims):
 im.thumbnail((340,360));x=(i%4)*350;y=(i//4)*400
 sheet.paste(im,(x,y+25));draw.text((x+5,y+5),str(i),fill='black')
sheet.save(p/'ali_socket_2x6_contacts.png')
print('Saved',len(ims),'visible-page assets')
