"""Apply release labels only; never rebuild or route a board."""
from pathlib import Path
from datetime import date
import argparse
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'project.json').read_text('utf-8'))
    if config.get('date'):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', config['date']):
            raise ValueError('Expected ISO release date YYYY-MM-DD')
        date.fromisoformat(config['date'])
    for product_id, product in config['products'].items():
        if product_id not in ('v1', 'v2') or not re.fullmatch(re.escape(product_id) + r'\.\d{2,}', product['version']):
            raise ValueError(f"Invalid version for {product_id}: {product['version']}")
    changes = []
    for product_id, product in config['products'].items():
        version = product['version']
        seen = set()
        for board in product['boards']:
            folder = (ROOT / board['project']).parent
            for path in [ROOT / board['pcb'], *folder.glob('*.kicad_sch')]:
                if path in seen:
                    continue
                seen.add(path)
                before = path.read_text('utf-8')
                after = re.sub(r'\(rev "[^"\n]*"\)', f'(rev "{version}")', before)
                if config.get('date'):
                    after = re.sub(r'\(date "[^"\n]*"\)', f'(date "{config["date"]}")', after)
                if path.suffix == '.kicad_pcb':
                    # Only board graphic text is changed, never pads, tracks or zones.
                    def label(match):
                        text = match.group(1)
                        text = re.sub(r'Mesh Repeater (?:ver [12]\.0|v[12]\.\d{2,})', f'Mesh Repeater {version}', text)
                        text = re.sub(r'Mesh Repeater 2\.0 — ЭКРАН A\d+', f'Mesh Repeater {version} — ЭКРАН', text)
                        if re.fullmatch(r'S4\.\d+|v[12]\.\d{2,}', text):
                            text = version
                        return '(gr_text "' + text + '"'
                    after = re.sub(r'\(gr_text "((?:\\.|[^"\\])*)"', label, after)
                    pcb_after = after
                if before != after:
                    changes.append({'path': path.relative_to(ROOT).as_posix(),
                                    'before': hashlib.sha256(before.encode()).hexdigest(),
                                    'after': hashlib.sha256(after.encode()).hexdigest()})
                    if args.apply:
                        path.write_text(after, 'utf-8', newline='\n')
            model_path = folder / 'model.json'
            if model_path.exists():
                model = json.loads(model_path.read_text('utf-8'))
                modified = False
                for key in ('revision', 'schematic_revision', 'board_revision'):
                    if key in model and model[key] != version:
                        model[key] = version
                        modified = True
                if 'date' in model and config.get('date') and model['date'] != config['date']:
                    model['date'] = config['date']
                    modified = True
                if modified:
                    changes.append({'path': model_path.relative_to(ROOT).as_posix(), 'metadata_only': True})
                    if args.apply:
                        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + '\n', 'utf-8')
            asset_path = folder / 'asset_manifest.json'
            if asset_path.exists():
                before = asset_path.read_text('utf-8')
                asset = json.loads(before)
                asset.update(revision=version, board_sha256=hashlib.sha256(pcb_after.encode()).hexdigest())
                if config.get('date'):
                    asset['date'] = config['date']
                after = json.dumps(asset, ensure_ascii=False, indent=2) + '\n'
                if json.loads(before) != asset:
                    changes.append({'path': asset_path.relative_to(ROOT).as_posix(), 'metadata_only': True})
                    if args.apply:
                        asset_path.write_text(after, 'utf-8')
        firmware = ROOT / product['root'] / 'design/watchdog_reference'
        firmware_manifest = firmware / 'source_hashes.json'
        if firmware_manifest.exists():
            before = firmware_manifest.read_text('utf-8')
            manifest = json.loads(before)
            if 'product_version' in manifest:
                manifest['product_version'] = version
                integration_file = firmware / 'verification/integration_checks.json'
                if integration_file.exists():
                    integration = json.loads(integration_file.read_text('utf-8'))
                    integration['product_version'] = version
                    integration_bytes = (json.dumps(integration, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
                    if integration_file.read_bytes() != integration_bytes:
                        changes.append({'path': integration_file.relative_to(ROOT).as_posix(), 'metadata_only': True})
                        if args.apply:
                            integration_file.write_bytes(integration_bytes)
                    record = manifest.get('files', {}).get('verification/integration_checks.json')
                    if record is not None:
                        record.update(bytes=len(integration_bytes), sha256=hashlib.sha256(integration_bytes).hexdigest())
                if json.loads(before) != manifest:
                    changes.append({'path': firmware_manifest.relative_to(ROOT).as_posix(), 'metadata_only': True})
                    if args.apply:
                        firmware_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    if 'v1' in config['products'] and 'v2' in config['products']:
        pair = config['products']['v1']['version'] + ' / ' + config['products']['v2']['version']
        folder = (ROOT / config['circuit']['project']).parent
        for path in folder.glob('*.kicad_sch'):
            before = path.read_text('utf-8')
            after = re.sub(r'\(rev "[^"\n]*"\)', f'(rev "{pair}")', before)
            after = re.sub(r'v1\.\d{2,}\s*/\s*v2\.\d{2,}', pair, after)
            if config.get('date'):
                after = re.sub(r'\(date "[^"\n]*"\)', f'(date "{config["date"]}")', after)
                after = re.sub(r'(v1\.\d{2,}\s*/\s*v2\.\d{2,}\s*/\s*)\d{4}-\d{2}-\d{2}',
                               lambda m: m[1] + config['date'], after)
            if before != after:
                changes.append({'path': path.relative_to(ROOT).as_posix(), 'metadata_only': True})
                if args.apply:
                    path.write_text(after, 'utf-8', newline='\n')
    print(json.dumps({'applied': args.apply, 'changes': changes}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
