"""Read selected public files, bounded output; never reads credentials."""
from pathlib import Path
import base64,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'.publication_tmp'
def main():
 m=json.loads((folder/'files.json').read_text(encoding='utf8'))
 done=set()
 for cache in ('uploaded.json','uploaded_large.json'):
  if (folder/cache).exists():done.update(json.loads((folder/cache).read_text(encoding='utf-8-sig')))
 unique={}
 for f in m['files']:
  if not f['known_in_base'] and f['sha'] not in done:unique.setdefault(f['sha'],f)
 blobs=[];length=0
 for sha,f in sorted(unique.items(),key=lambda x:x[1]['size']):
  if f['size']>32000:continue
  if blobs and length+f['size']>48000:break
  p=(ROOT/f['path']).resolve()
  if not p.is_relative_to(ROOT):raise ValueError('Outside project')
  data=p.read_bytes();actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
  if actual!=sha:continue
  blobs.append({'path':f['path'],'sha':sha,'content':base64.b64encode(data).decode()});length+=len(data)
 print(json.dumps({'blobs':blobs,'remaining_unique':len(unique),'bytes':length}))
if __name__=='__main__':main()
