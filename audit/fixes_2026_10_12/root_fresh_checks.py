"""Independent read-only KiCad checks; all output stays beside this script."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib, json, subprocess, time

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CLI = Path(r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe')

def run(args):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return p.returncode, p.stdout, p.stderr

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
before = {p: sha(ROOT / p) for p in tracked if p}
(OUT / 'root_tracked_before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
head = run(['git', 'rev-parse', 'HEAD'])[1].strip()
version = run([str(CLI), '--version'])[1].strip()
tasks = []
for name in ('Power', 'Logic', 'Shield'):
    project = ROOT / 'design' / ('MeshRepeater2_' + name)
    board = project / ('MeshRepeater2_' + name + '.kicad_pcb')
    for refill in (False, True):
        ident = name.lower() + ('_refill_drc' if refill else '_saved_drc')
        output = OUT / (ident + '.json')
        command = [str(CLI), 'pcb', 'drc', '--format', 'json', '--severity-all', '--all-track-errors', '--exit-code-violations', '-o', str(output)]
        if name != 'Shield':
            command.append('--schematic-parity')
        if refill:
            command.append('--refill-zones')
        command.append(str(board))
        tasks.append((ident, command, output))
    if name != 'Shield':
        ident = name.lower() + '_erc'
        output = OUT / (ident + '.json')
        command = [str(CLI), 'sch', 'erc', '--format', 'json', '--severity-all', '--exit-code-violations', '-o', str(output), str(project / ('MeshRepeater2_' + name + '.kicad_sch'))]
        tasks.append((ident, command, output))

def check(task):
    ident, command, output = task
    start = time.monotonic()
    code, stdout, stderr = run(command)
    result = {'id': ident, 'command': command, 'exit_code': code, 'elapsed_seconds': round(time.monotonic()-start, 3), 'stdout': stdout, 'stderr': stderr, 'report_present': output.exists()}
    if output.exists():
        data = json.loads(output.read_text(encoding='utf-8'))
        result['top_level_keys'] = list(data)
        result['counts'] = {k: len(v) for k, v in data.items() if isinstance(v, list)}
        if 'sheets' in data:
            result['erc_items'] = sum(len(s.get('violations', [])) for s in data['sheets'])
        result['report_sha256'] = sha(output)
    return result

results = []
with ThreadPoolExecutor(max_workers=3) as pool:
    future_map = {pool.submit(check, task): task[0] for task in tasks}
    for future in as_completed(future_map):
        result = future.result()
        results.append(result)
        print(json.dumps({k: result[k] for k in ('id', 'exit_code', 'elapsed_seconds', 'counts') if k in result}), flush=True)

after = {p: sha(ROOT / p) for p in tracked if p}
changed = [{'path': p, 'before': before[p], 'after': after[p]} for p in before if before[p] != after[p]]
summary = {'commit': head, 'kicad_version': version, 'tracked_file_count': len(before), 'tracked_changes': changed, 'checks': sorted(results, key=lambda r: r['id'])}
(OUT / 'root_fresh_checks.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'tracked_file_count': len(before), 'tracked_changes': changed, 'checks': len(results)}, ensure_ascii=False), flush=True)
