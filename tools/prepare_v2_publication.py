"""Inventory exact Git blobs for public V2 branch; performs no network writes."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE='cf54f9970e716272d477afdb252b4e195d595cb6'
def main():
 entries=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
 known=set()
 for line in subprocess.check_output(['git','ls-tree','-r',BASE],cwd=ROOT).decode().splitlines():known.add(line.split()[2])
 files=[]
 for name in sorted(set(entries)):
  if not name:continue
  p=ROOT/name
  if not p.is_file():continue
  if '.publication_tmp' in p.parts:continue
  raw=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  files.append({'path':name.replace('\\','/'),'size':len(raw),'sha':blob,'sha256':hashlib.sha256(raw).hexdigest(),'known_in_base':blob in known})
 out=ROOT/'.publication_tmp';out.mkdir(exist_ok=True)
 (out/'files.json').write_text(json.dumps({'base':BASE,'files':files},ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'files':len(files),'unique_blobs':len({x['sha'] for x in files}),'new_unique_blobs':len({x['sha'] for x in files if not x['known_in_base']}),'total_bytes':sum(x['size'] for x in files),'manifest':'.publication_tmp/files.json'}))
if __name__=='__main__':main()
