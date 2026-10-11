from pathlib import Path
import json, collections
from kicad_headless import configure_headless
configure_headless()
import pcbnew as k
configure_headless()
root=Path(__file__).resolve().parents[2]
b=k.LoadBoard(str(root/'baseline/S4_16/Meshcore_NaIon.kicad_pcb'))
c=json.loads((root/'design/v2_electrical_contract.json').read_text(encoding='utf-8'))
own={p['reference']:p['board'] for p in c['parts']}
def xy(p):return [round(k.ToMM(p.x),3),round(k.ToMM(p.y),3)]
for board in ['POWER','LOGIC']:
 print(board)
 print(json.dumps([{'r':f.GetReference(),'xy':xy(f.GetPosition()),'rot':f.GetOrientationDegrees(),'fp':str(f.GetFPID().GetLibItemName()),'pins':[(p.GetNumber(),p.GetNetname()) for p in f.Pads()]} for f in b.GetFootprints() if own[f.GetReference()]==board and (f.GetReference().startswith(('J','SW','H','TP','SH','D')))],ensure_ascii=True))
print('tracks',len(list(b.GetTracks())),'zones',len(list(b.Zones())))
print('boardapifill',[n for n in dir(k) if 'Fill' in n or 'Specctra' in n])
print('itemapi',[n for n in dir(k.PCB_TRACK) if 'Clone' in n or 'Duplicate' in n or 'Move' in n])
print('zoneapi',[n for n in dir(k.ZONE) if 'Move' in n or 'Clone' in n or 'Outline' in n])
print('oneCu')
bb=k.BOARD();bb.SetCopperLayerCount(1);print(bb.GetCopperLayerCount(),bb.GetEnabledLayers().CuStack())
