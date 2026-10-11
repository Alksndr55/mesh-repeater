"""Finalize the graphic-only LOGIC label proof after strict native DRC/export."""
from pathlib import Path
import argparse, gzip, hashlib, json
ROOT = Path(__file__).resolve().parents[2]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--visual-inspected', action='store_true')
    args = parser.parse_args()
    proof_file = ROOT / 'audit/logic_operator_labels.json'
    proof = json.loads(proof_file.read_text(encoding='utf-8'))
    pcb = ROOT / 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'
    out = ROOT / 'output/LOGIC'
    drcfile = out / 'MeshRepeater2_Logic_drc.json'
    drc = json.loads(drcfile.read_text(encoding='utf-8'))
    assert all(not drc[k] for k in ('violations', 'unconnected_items', 'schematic_parity'))
    assert not drc['ignored_checks']
    assert proof['pcb_sha256'] == sha(pcb)
    assert proof['invariant_before'] == proof['invariant_after']
    proof['strict_native_drc'] = {'violations': 0, 'unconnected': 0, 'parity': 0,
                                'ignored_checks': [], 'report_sha256': sha(drcfile)}
    for suffix in ('markings', 'footprint_variants'):
        path = ROOT / ('audit/MeshRepeater2_Logic_' + suffix + '.json')
        data = json.loads(path.read_text(encoding='utf-8'))
        data['pcb_sha256'] = proof['pcb_sha256']
        data['final_operator_label_validation'] = {
            'proof': 'audit/logic_operator_labels.json',
            'pcb_sha256': proof['pcb_sha256'],
            'unchanged_geometry_invariant': proof['invariant_after'],
            'source_synchronization_sha256_preserved_as_history': True,
            'only_four_board_texts_added': True,
        }
        if suffix == 'markings':
            existing = {r['uuid'] for r in data['all_text']}
            data['all_text'].extend(dict(row, owner=row['text'].split('\n')[0])
                                    for row in proof['labels'] if row['uuid'] not in existing)
            data['operator_labels'] = proof['labels']
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    step = out / 'MeshRepeater2_Logic.step'
    compressed = step.with_suffix('.step.gz')
    with compressed.open('wb') as dest:
        with gzip.GzipFile(filename='', mode='wb', fileobj=dest, mtime=0) as stream:
            stream.write(step.read_bytes())
    assert gzip.decompress(compressed.read_bytes()) == step.read_bytes()
    proof['step_sha256'] = sha(step)
    proof['step_gzip_sha256'] = sha(compressed)
    if args.visual_inspected:
        manifest_file = out / 'MeshRepeater2_Logic_exports.json'
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
        assert manifest['sha256'] == sha(pcb)
        for row in manifest['artifacts']:
            assert sha(ROOT / row['path']) == row['sha256'], row['path']
        proof['final_export_manifest_sha256'] = sha(manifest_file)
        proof['operator_view_visual_review'] = {
            'image': 'output/LOGIC/MeshRepeater2_Logic_operator_top.png',
            'sha256': sha(out / 'MeshRepeater2_Logic_operator_top.png'),
            'all_four_labels_readable_and_at_corresponding_ports': True,
            'view_transform': 'Native mirrored B view followed by 180-degree image rotation; physical assembly X180',
        }
    proof_file.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: proof[k] for k in ('pcb_sha256', 'step_sha256', 'step_gzip_sha256')}))


if __name__ == '__main__':
    main()
