"""Add the four reviewed exterior operator labels; preserve all other objects."""
from pathlib import Path
import hashlib, json
from finish_v2_markings import k, ROOT, invariant, v, rect, xy


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    pcb = ROOT / 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
    board = k.LoadBoard(str(pcb))
    before_sha, before = sha(pcb), invariant(board)
    original = {x.m_Uuid.AsString() for x in board.GetDrawings()}
    specs = [('USB', 18., 4., 1.), ('J5\nUART', 5.5, 20.8, .9),
             ('SW1\nUSER', 29., 54.7, .9), ('SW2\nRESET', 41., 54.7, .9)]
    rows = []
    for text, x, y, font in specs:
        if any(isinstance(t, k.PCB_TEXT) and t.GetLayer() == k.B_SilkS
               and t.GetText() == text for t in board.GetDrawings()):
            raise RuntimeError('Label already exists: ' + text)
        t = k.PCB_TEXT(board)
        t.SetText(text); t.SetLayer(k.B_SilkS); t.SetMirrored(True)
        t.SetPosition(v(x, y)); t.SetTextSize(v(font, font))
        t.SetTextThickness(k.FromMM(.15))
        t.SetTextAngle(k.EDA_ANGLE(180, k.DEGREES_T))
        board.Add(t)
        rows.append(dict(text=text, at_mm=xy(t.GetPosition()),
                         box_mm=rect(t.GetBoundingBox()), font_mm=font,
                         angle_deg=180., mirrored=True, layer='B.Silkscreen',
                         uuid=t.m_Uuid.AsString(), kind='operator_label'))
    assert invariant(board) == before
    assert original.issubset({x.m_Uuid.AsString() for x in board.GetDrawings()})
    assert len(list(board.GetDrawings())) == len(original) + 4
    k.SaveBoard(str(pcb), board)
    saved = k.LoadBoard(str(pcb))
    assert invariant(saved) == before
    proof = dict(source_pcb_sha256=before_sha, pcb_sha256=sha(pcb),
                 invariant_before=before, invariant_after=invariant(saved),
                 change='Four exterior B.SilkS PCB_TEXT objects only',
                 unchanged_copper_footprints_placement_models=True, labels=rows,
                 schematic_xml_change=False)
    (ROOT / 'audit/logic_operator_labels.json').write_text(
        json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(proof, ensure_ascii=False))


if __name__ == '__main__':
    main()
