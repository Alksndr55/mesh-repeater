"""Read-only source/proof manifest. Refuses to certify a changed native LOGIC."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
EXPECTED = '6cbd7850caa14163ebe4d40aba4435ac8fe17f327d68419dfb94e0a1bc361bc8'
PCB = ROOT / 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if sha(PCB) != EXPECTED:
    raise SystemExit('Native LOGIC differs from the reviewed freeze. Revalidate before manifest.')

native = json.loads((OUT / 'routing_after_native.json').read_text(encoding='utf8'))
review = json.loads((OUT / 'reviewer_routing.json').read_text(encoding='utf8'))
summary = json.loads((OUT / 'routing_summary.json').read_text(encoding='utf8'))
drc = json.loads((OUT / 'routing_native_final_drc.json').read_text(encoding='utf8'))
negative = json.loads((OUT / 'reviewer_RF_negative.json').read_text(encoding='utf8'))
assert native['sha256'] == review['sha256'] == summary['final_native_sha256'] == EXPECTED
assert all(summary['checks'].values())
assert not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']
assert not drc['ignored_checks']
assert negative['native_input_sha256'] == EXPECTED and negative['status'] == 'PASS'

paths = [
    PCB,
    PCB.with_suffix('.kicad_dru'),
    OUT / 'routing_before.kicad_pcb',
    OUT / 'routing_after_native.json',
    OUT / 'routing_summary.json',
    OUT / 'routing_native_final_drc.json',
    OUT / 'routing_ground_stitches.json',
    OUT / 'reviewer_routing.json',
    OUT / 'reviewer_RF_negative.json',
    OUT / 'routing_fixes_RU.md',
]
result = {
    'date': '2026-10-12',
    'scope': 'V2 LOGIC native PCB and RF custom rules; no schematic, GPIO, values, or footprint pose changes',
    'reviewed_native_sha256': EXPECTED,
    'CAD_findings': {'R1': 'fixed, independently accepted with disclosed residual reference gaps', 'R2': 'fixed; ANT_RF lower reference restored and RF non-GND negative probe PASS'},
    'CAD_checks': {'violations': 0, 'unconnected': 0, 'schematic_parity': 0, 'ignored_checks': 0, 'physical_GND_components': len(native['GND_physical_components']), 'new_GND_vias': summary['new_ground_vias_count']},
    'preservation_checks': summary['checks'],
    'metrics': summary['metrics'],
    'not_claimed': ['uninterrupted opposite-layer plane under every digital signal', 'SI/EMI bench qualification', 'RF launch or SAW impedance qualification'],
    'files': [{'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in paths],
    'delivery_authority': 'design/MeshRepeater2_Logic/MeshRepeater2_Logic.kicad_pcb; scratch candidates are not manufacturing deliverables',
}
(OUT / 'routing_manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print('Freeze verified. Wrote routing_manifest.json; no CAD mutation.')
