from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'tools/cad'));from kicad_headless import configure_headless;configure_headless()
import pcbnew as k
configure_headless()
P=ROOT/'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb';b=k.LoadBoard(str(P));held=[]
for t in list(b.GetTracks()):
 if str(t.m_Uuid.AsString())=='ef31dba0-68e7-4269-b7d8-0212e82ee0d0':b.Remove(t);held.append(t)
k.ZONE_FILLER(b).Fill(b.Zones());k.SaveBoard(str(P),b)
f=OUT/'routing_ground_stitches.json';x=json.load(open(f,encoding='utf8'));x['removed_by_final_DRC_BLE_keepout']=[a for a in x['added'] if a['uuid']=='ef31dba0-68e7-4269-b7d8-0212e82ee0d0'];x['added']=[a for a in x['added'] if a['uuid']!='ef31dba0-68e7-4269-b7d8-0212e82ee0d0'];f.write_text(json.dumps(x,indent=2),encoding='utf8')
