"""Build the same assembly BOM format for both physical products."""
from pathlib import Path
import argparse
import csv
import json
import os
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product', choices=['v1', 'v2'], action='append')
    args = parser.parse_args()
    font_config = Path(sys.executable).parent.parent / 'etc/fonts'
    if (font_config / 'fonts.conf').is_file():
        os.environ.setdefault('FONTCONFIG_PATH', str(font_config))
    import wx
    log = wx.LogStderr()
    wx.Log.SetActiveTarget(log)
    import pcbnew
    wx.Log.SetActiveTarget(log)
    config = json.loads((ROOT / 'project.json').read_text('utf-8'))
    fields = ['Board', 'Reference', 'Kind', 'Value_NaIon_COLD', 'Fit_NaIon_COLD', 'MPN_NaIon_COLD',
              'Value_NaIon_NoCOLD', 'Fit_NaIon_NoCOLD', 'MPN_NaIon_NoCOLD',
              'Value_LTO_2S', 'Fit_LTO_2S', 'MPN_LTO_2S', 'Footprint', 'Layer',
              'X_mm', 'Y_mm', 'Rotation_deg', 'Datasheet', 'Vendor_URL', 'Assembly', 'Note']
    for product_id in args.product or config['products']:
        product = config['products'][product_id]
        rows = []
        for spec in product['boards']:
            model_path = (ROOT / spec['project']).parent / 'model.json'
            if not model_path.is_file():
                continue  # Shield has no assembled electronic components.
            model = json.loads(model_path.read_text('utf-8'))
            board = pcbnew.LoadBoard(str(ROOT / spec['pcb']))
            footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
            parts = {p['ref']: p for p in model['parts']}
            if set(parts) != set(footprints):
                raise ValueError(f'{product_id}/{spec["name"]}: model/PCB references differ')
            for ref in sorted(parts, key=lambda s: (re.sub(r'\d+', '', s), int(re.search(r'\d+', s)[0]) if re.search(r'\d+', s) else 0)):
                p, fp = parts[ref], footprints[ref]
                row = {'Board': spec['name'], 'Reference': ref, 'Kind': p.get('kind', ''),
                       'Footprint': str(fp.GetFPID().GetLibNickname()) + ':' + str(fp.GetFPID().GetLibItemName()), 'Layer': board.GetLayerName(fp.GetLayer()),
                       'X_mm': f'{pcbnew.ToMM(fp.GetPosition().x):.4f}',
                       'Y_mm': f'{pcbnew.ToMM(fp.GetPosition().y):.4f}',
                       'Rotation_deg': f'{fp.GetOrientationDegrees():.3f}',
                       'Datasheet': p.get('datasheet', ''), 'Vendor_URL': p.get('vendor_url', ''),
                       'Assembly': p.get('assembly', ''), 'Note': p.get('note', '')}
                for suffix, key in [('NaIon_COLD', 'naion'), ('NaIon_NoCOLD', 'naion_no_cold'), ('LTO_2S', 'lto2s')]:
                    row['Value_' + suffix] = p.get('value_' + key, p['value'])
                    row['MPN_' + suffix] = p.get('mpn_' + key, p.get('mpn', ''))
                    row['Fit_' + suffix] = 'yes' if p.get('fit_' + key, not p.get('dnp', False)) else 'no'
                rows.append(row)
        dest = ROOT / product['bom']
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps({'product': product_id, 'rows': len(rows), 'path': str(dest)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
