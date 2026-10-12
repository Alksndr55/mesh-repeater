"""A2 date/revision captions only; no engineering geometry mutation."""
from pathlib import Path
import hashlib,json
from finish_v2_markings import ROOT,k,invariant

def main():
    proof=[]
    for name in ['Power','Logic','Shield']:
        p=ROOT/'design'/('MeshRepeater2_'+name)/('MeshRepeater2_'+name+'.kicad_pcb')
        data=p.read_bytes();b=k.LoadBoard(str(p));before=invariant(b)
        block=b.GetTitleBlock();block.SetRevision('V2.0-A2');block.SetDate('2026-10-12')
        for t in b.GetDrawings():
            if isinstance(t,k.PCB_TEXT):t.SetText(t.GetText().replace('V2.0-A1','V2.0-A2'))
        assert invariant(b)==before
        settings=p.with_suffix('.kicad_pro').read_bytes();k.SaveBoard(str(p),b);p.with_suffix('.kicad_pro').write_bytes(settings)
        assert invariant(k.LoadBoard(str(p)))==before
        proof.append({'pcb':str(p.relative_to(ROOT)),'before_sha256':hashlib.sha256(data).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'engineering_geometry_unchanged':True})
    dest=ROOT/'audit/ina219_and_vertical_2026_10_12/revision_captions.json'
    dest.write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof))

if __name__=='__main__':main()
