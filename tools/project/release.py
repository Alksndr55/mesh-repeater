"""Check, export and package the current hardware products from project.json.

Uses KiCad's Python runtime and the installed KiCad CLI. Native CAD is the
input: this command never regenerates, reroutes, or saves editable sources.
Run ``python tools/project/release.py build --product all`` from any directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zipfile

from release_bom import verify_bom
from release_watchdog import verify_watchdog
from release_routing import verify_routing
from release_boardview import export_boardview
from release_pdf import enhance_schematic_pdf


ROOT = Path(__file__).resolve().parents[2]
QUOTE = r'"((?:\\.|[^"\\])*)"'
STATE_KEYS = ('violations', 'unconnected_items', 'schematic_parity', 'ignored_checks')
BOARDVIEW_VARIANTS = ('NaIon_COLD', 'LTO_2S')
NEXUS_BUNDLE = 'third_party/NexusBV/0.9'


class ReleaseError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise ReleaseError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def decoded(value):
    return json.loads('"' + value + '"')


def strings(text, prefix):
    return [decoded(m) for m in re.findall(prefix + r'\s+' + QUOTE, text)]


def table_entries(path):
    """Read the small lib-table format, including single-line native tables."""
    if not path.exists():
        return {}
    pattern = r'\(lib\s+\(name\s+' + QUOTE + r'\).*?\(uri\s+' + QUOTE + r'\)'
    return {decoded(name): decoded(uri) for name, uri in
            re.findall(pattern, path.read_text('utf-8-sig'), re.S)}


class Product:
    def __init__(self, args, config, key, cli):
        self.args, self.config, self.key, self.cli = args, config, key, cli
        self.spec = config['products'][key]
        self.version = self.spec['version']
        require(re.fullmatch(r'v[12]\.\d{2,}', self.version), 'Expected version v1.XX/v2.XX with two or more digits: ' + self.version)
        require(self.version.startswith(key + '.'), 'Product/version prefix mismatch: ' + key + ' / ' + self.version)
        self.product_root = self.path(self.spec['root'])
        if args.work_dir:
            base = args.work_dir.resolve() / key
            self.audit, self.output = base / 'audit/current', base / 'output/current'
            self.release_dir = base / 'releases' / self.version
        else:
            self.audit = self.product_root / 'audit/current'
            self.output = self.product_root / 'output/current'
            self.release_dir = ROOT / 'releases' / self.version
        self.files, self.standard_models = set(), set()
        self.dependencies = {}
        self.commands = []
        self.circuit_tool = ROOT / 'tools/project/verify_circuit.py'

    def path(self, relative):
        p = (ROOT / relative).resolve()
        require(p.is_relative_to(ROOT), 'Path escapes project: ' + str(relative))
        return p

    def rel(self, path):
        return Path(path).relative_to(ROOT).as_posix()

    def add(self, path):
        path = path.resolve()
        require(path.is_relative_to(ROOT), 'Dependency outside project: ' + str(path))
        require(path.is_file(), 'Missing release dependency: ' + self.rel(path))
        require(not any(part.lower() in {'.git', 'archive', 'baseline', '.publication_tmp', '__pycache__'}
                        for part in path.relative_to(ROOT).parts), 'Historical dependency: ' + self.rel(path))
        self.files.add(path)

    def local_uri(self, project, uri):
        if uri.startswith('${KIPRJMOD}/'):
            p = (project / uri[len('${KIPRJMOD}/'):]).resolve()
        elif '${' not in uri and not Path(uri).is_absolute():
            p = (project / uri).resolve()
        else:
            raise ReleaseError('Non-portable local dependency: ' + uri)
        require(p.is_relative_to(project), 'Dependency escapes native project: ' + uri)
        return p

    def project(self, record):
        project_file = self.path(record['project'])
        folder = project_file.parent
        self.add(project_file)
        for name in ('model.json', 'schematic_manifest.json', 'asset_manifest.json', 'README_RU.md'):
            if (folder / name).is_file():
                self.add(folder / name)
        rules = project_file.with_suffix('.kicad_dru')
        if rules.exists():
            self.add(rules)
        pcb = self.path(record['pcb']) if record.get('pcb') else None
        sources, sheets = [], set()
        if pcb:
            self.add(pcb)
            self.add(folder / 'routing_review.json')
            sources.append(pcb)
        pending = [self.path(record['schematic'])] if record.get('schematic') else []
        while pending:
            sheet = pending.pop()
            if sheet in sheets:
                continue
            require(sheet.parent == folder, 'Schematic sheet outside its native project: ' + str(sheet))
            self.add(sheet)
            sheets.add(sheet)
            pending.extend((sheet.parent / child).resolve() for child in
                           strings(sheet.read_text('utf-8-sig'), r'\(property\s+"Sheetfile"'))
        sources.extend(sorted(sheets))
        tables = {}
        for table in ('fp-lib-table', 'sym-lib-table'):
            file = folder / table
            if not file.exists():
                continue
            self.add(file)
            for name, uri in table_entries(file).items():
                if uri.startswith('${KIPRJMOD}/') or '${' not in uri:
                    location = self.local_uri(folder, uri)
                    tables[(table, name)] = location
                    if table == 'sym-lib-table':
                        self.add(location)
                else:
                    require(uri.startswith('${KICAD'), 'Unexpected library URI: ' + uri)
        used_footprints = set()
        if pcb:
            used_footprints.update(strings(pcb.read_text('utf-8-sig'), r'\(footprint'))
        for sheet in sheets:
            used_footprints.update(x for x in strings(sheet.read_text('utf-8-sig'),
                                                     r'\(property\s+"Footprint"') if x)
        footprint_files = set()
        for identity in used_footprints:
            require(':' in identity, 'Missing footprint library identity: ' + identity)
            library, name = identity.split(':', 1)
            location = tables.get(('fp-lib-table', library))
            require(location is not None, 'Unresolved local footprint: ' + identity)
            file = location / (name + '.kicad_mod')
            self.add(file)
            footprint_files.add(file)
        local_models = set()
        for file in ([pcb] if pcb else []) + sorted(footprint_files):
            for uri in strings(file.read_text('utf-8-sig'), r'\(model'):
                require(not uri.startswith('${KICAD'),
                        '3D model is not bundled in its native project: ' + uri)
                model = self.local_uri(folder, uri)
                self.add(model)
                local_models.add(model)
        # Current datasheet references in symbols are useful offline; do not
        # import whole historical reference directories to satisfy old notes.
        for file in sources:
            for uri in strings(file.read_text('utf-8-sig'), r'\(property\s+"Datasheet"'):
                if uri.startswith('${KIPRJMOD}/'):
                    self.add(self.local_uri(folder, uri))
        self.dependencies[record['name']] = {
            'schematics': sorted(self.rel(p) for p in sheets),
            'footprints': sorted(self.rel(p) for p in footprint_files),
            'models': sorted(self.rel(p) for p in local_models),
        }

    def collect(self):
        for board in self.spec['boards']:
            self.project(board)
        circuit = self.config['circuit']
        self.project({'name': 'COMMON_CIRCUIT', 'project': circuit['project'],
                      'schematic': circuit['schematic']})
        self.add(self.path(circuit['profiles']))
        self.add(self.path(self.spec['bom']))
        for document in self.spec.get('documents', []):
            self.add(self.path(document))
        for base in (self.product_root, ROOT / 'shared'):
            for name in ('README.md', 'AGENTS.md', 'LICENSE', 'LICENSE.md', 'THIRD_PARTY_NOTICES.md'):
                if (base / name).is_file():
                    self.add(base / name)
                    if name.startswith('LICENSE'):
                        text = (base / name).read_text('utf-8-sig')
                        for target in re.findall(r'\]\(([^)]+asset_manifest\.json(?:#[^)]*)?)\)', text):
                            link = urlsplit(target.strip('<>'))
                            if not link.scheme and not link.netloc:
                                self.add((base / unquote(link.path)).resolve())
            if (base / 'LICENSES').is_dir():
                for file in (base / 'LICENSES').rglob('*'):
                    if file.is_file():
                        self.add(file)
        watchdog = self.product_root / 'design/watchdog_reference'
        require(watchdog.is_dir(), 'Missing current watchdog firmware directory: ' + self.rel(watchdog))
        for name in ('main.c', 'Makefile', 'watchdog.hex', 'source_hashes.json', 'INTEGRATION_RU.txt',
                     'build.ps1', 'VERSION', 'LICENSE.md', 'verification/software_checks.json'):
            self.add(watchdog / name)
        for file in watchdog.rglob('*'):
            if file.is_file() and file.suffix.lower() in ('.c', '.h', '.s', '.cpp', '.ps1', '.md', '.json', '.txt'):
                self.add(file)
        # Current release tools and their pinned pure-Python PDF dependency.
        for file in (ROOT / 'tools/project').rglob('*.py'):
            self.add(file)
        for name in ('PYPDF_LICENSE', 'PYPDF_NOTICE.txt'):
            self.add(ROOT / 'tools/project/vendor' / name)
        if (ROOT / 'AGENTS.md').is_file():
            self.add(ROOT / 'AGENTS.md')
        self.collect_nexus_bundle()
        self.add(self.args.config.resolve())
        return {self.rel(p): digest(p) for p in sorted(self.files)}

    def collect_nexus_bundle(self):
        """Freeze only the vendor files explicitly listed in the portable bundle."""
        folder = self.path(NEXUS_BUNDLE)
        manifest_path = folder / 'bundle_manifest.json'
        self.add(manifest_path)
        manifest = json.loads(manifest_path.read_text('utf-8-sig'))
        require(isinstance(manifest, dict) and manifest.get('name') == 'NexusBV'
                and manifest.get('version') == '0.9' and manifest.get('platform') == 'Windows x64',
                'Unexpected NexusBV bundle identity')
        files = manifest.get('files')
        require(isinstance(files, dict) and files, 'Missing NexusBV bundle file list')
        require({'NexusBV.exe', 'nexusbv_core.dll', 'pdfium.dll'} <= set(files),
                'Missing required NexusBV runtime entry')
        seen = set()
        for relative, expected in files.items():
            parts = relative.split('/')
            require(relative and all(part and part not in ('.', '..')
                    and not re.search(r'[\x00-\x1f<>:"\\|?*]', part)
                    and not part.endswith((' ', '.')) for part in parts)
                    and relative.casefold() not in seen
                    and relative.casefold() != 'bundle_manifest.json',
                    'Unsafe or duplicate NexusBV bundle path: ' + relative)
            seen.add(relative.casefold())
            file = folder.joinpath(*parts)
            require(file.resolve() == file and file.resolve().is_relative_to(folder),
                    'NexusBV bundle path redirects outside its listed location: ' + relative)
            require(isinstance(expected, dict) and isinstance(expected.get('sha256'), str)
                    and re.fullmatch(r'[0-9a-f]{64}', expected['sha256'])
                    and type(expected.get('bytes')) is int and expected['bytes'] >= 0,
                    'Invalid NexusBV bundle checksum record: ' + relative)
            self.add(file)
            raw = file.read_bytes()
            require(len(raw) == expected['bytes']
                    and hashlib.sha256(raw).hexdigest() == expected['sha256'],
                    'Changed NexusBV bundle file: ' + relative)

    def portable(self, value):
        if isinstance(value, dict):
            return {k: self.portable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.portable(v) for v in value]
        if isinstance(value, str):
            replacements = [(str(self.audit), '<AUDIT>'), (str(self.output), '<OUTPUT>'), (str(ROOT), '<PROJECT>')]
            if self.args.work_dir:
                replacements.insert(0, (str(self.args.work_dir.resolve()), '<WORK>'))
            for old, new in replacements:
                value = value.replace(old, new).replace(old.replace('\\', '/'), new)
            return value
        return value

    def run(self, args, label):
        command = [str(self.cli), *map(str, args)]
        p = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace')
        self.commands.append(self.portable({'label': label, 'command': command, 'returncode': p.returncode,
                                            'stdout': p.stdout, 'stderr': p.stderr}))
        return p.returncode == 0

    def check(self):
        self.audit.mkdir(parents=True, exist_ok=True)
        frozen = self.collect()
        checks, reports = [], {}
        for board in self.spec['boards']:
            name = board['name']
            pcb = self.path(board['pcb'])
            revision = strings(pcb.read_text('utf-8-sig'), r'\(rev')
            checks.append({'name': name + ' native revision matches manifest',
                           'passed': bool(revision) and revision[0] == self.version,
                           'actual': revision[0] if revision else None})
            reportdir = self.audit / name
            reportdir.mkdir(parents=True, exist_ok=True)
            drc_path = reportdir / 'drc.json'
            args = ['pcb', 'drc', '--format', 'json', '--severity-all', '--all-track-errors',
                    '--refill-zones', '--exit-code-violations']
            if board.get('schematic'):
                args.append('--schematic-parity')
            success = self.run([*args, '-o', drc_path, pcb], name + ' DRC')
            if drc_path.exists():
                drc = json.loads(drc_path.read_text('utf-8-sig'))
                counts = {k: len(drc.get(k, [])) for k in STATE_KEYS}
                checks.append({'name': name + ' DRC/connectivity/parity/ignored zero',
                               'passed': success and not any(counts.values()), 'counts': counts})
                reports[self.rel_report(drc_path)] = digest(drc_path)
            else:
                checks.append({'name': name + ' DRC report created', 'passed': False})
            if board.get('schematic'):
                sch = self.path(board['schematic'])
                erc_path, xml_path = reportdir / 'erc.json', reportdir / 'netlist.xml'
                erc_ok = self.run(['sch', 'erc', '--format', 'json', '--severity-all', '--exit-code-violations',
                                   '-o', erc_path, sch], name + ' ERC')
                if erc_path.exists():
                    erc = json.loads(erc_path.read_text('utf-8-sig'))
                    count = len(erc.get('violations', [])) + sum(len(s.get('violations', [])) for s in erc.get('sheets', []))
                    checks.append({'name': name + ' ERC zero without ignored checks',
                                   'passed': erc_ok and count == 0 and not erc.get('ignored_checks'), 'violations': count})
                    reports[self.rel_report(erc_path)] = digest(erc_path)
                else:
                    checks.append({'name': name + ' ERC report created', 'passed': False})
                net_ok = self.run(['sch', 'export', 'netlist', '--format', 'kicadxml', '-o', xml_path, sch], name + ' XML')
                checks.append({'name': name + ' fresh native XML', 'passed': net_ok and xml_path.is_file()})
                if xml_path.exists():
                    reports[self.rel_report(xml_path)] = digest(xml_path)
        if self.circuit_tool.exists():
            circuit_out = self.audit / 'circuit'
            command = [sys.executable, str(self.circuit_tool), '--product', self.key,
                       '--config', str(self.args.config.resolve()), '--kicad-cli', str(self.cli), '--out', str(circuit_out)]
            p = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', errors='replace')
            self.commands.append(self.portable({'label': 'shared circuit and physical profile contract', 'command': command,
                                               'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}))
            checks.append({'name': 'shared circuit and physical profile contract', 'passed': p.returncode == 0})
            for file in sorted(circuit_out.rglob('*')) if circuit_out.exists() else []:
                if file.is_file():
                    reports[self.rel_report(file)] = digest(file)
        else:
            checks.append({'name': 'shared circuit verifier exists', 'passed': False})
        bom_report = verify_bom(ROOT, self.spec, self.audit)
        write_json(self.audit / 'bom.json', bom_report)
        reports['bom.json'] = digest(self.audit / 'bom.json')
        checks.append({'name': 'BOM identities, assembly variants and actual PCB metadata',
                       'passed': bom_report['status'] == 'PASS', 'failures': len(bom_report['failures'])})
        watchdog_report = verify_watchdog(ROOT, self.spec)
        write_json(self.audit / 'watchdog.json', watchdog_report)
        reports['watchdog.json'] = digest(self.audit / 'watchdog.json')
        checks.append({'name': 'watchdog source, HEX, fuse profile and verified build provenance',
                       'passed': watchdog_report['status'] == 'PASS', 'failures': len(watchdog_report['failures'])})
        routing_report = verify_routing(ROOT, self.spec)
        write_json(self.audit / 'routing.json', routing_report)
        reports['routing.json'] = digest(self.audit / 'routing.json')
        checks.append({'name': 'routing geometry, 5mm ground ledger and exact-PCB two-face review',
                       'passed': routing_report['status'] == 'PASS', 'failures': len(routing_report['failures'])})
        unchanged = all(self.path(p).exists() and digest(self.path(p)) == h for p, h in frozen.items())
        checks.append({'name': 'all editable sources and dependencies unchanged', 'passed': unchanged})
        report = {'format_version': 1, 'product': self.key, 'version': self.version,
                  'status': 'PASS' if all(c['passed'] for c in checks) else 'FAIL',
                  'created_utc': datetime.now(timezone.utc).isoformat(), 'kicad_version': self.args.kicad_version,
                  'source_sha256': frozen, 'reports_sha256': reports, 'checks': checks, 'commands': self.commands,
                  'scope': 'Native CAD, parity and shared-circuit checks; no prototype measurement or manufacturing claim.'}
        write_json(self.audit / 'checks.json', report)
        failures = [c['name'] for c in checks if not c['passed']]
        require(not failures, self.key + ' checks failed: ' + '; '.join(failures) + '. See ' + str(self.audit / 'checks.json'))
        return report

    def rel_report(self, path):
        return path.relative_to(self.audit).as_posix()

    def valid_checks(self):
        file = self.audit / 'checks.json'
        require(file.is_file(), 'Run check/export/build first: missing ' + str(file))
        report = json.loads(file.read_text('utf-8-sig'))
        require(report.get('status') == 'PASS' and report.get('version') == self.version, 'Checks failed or version changed')
        require(report.get('kicad_version') == self.args.kicad_version,
                'KiCad version changed since checks; run build again')
        require(report['source_sha256'] == self.collect(), 'Sources changed since checks; run build again')
        for path, expected in report['reports_sha256'].items():
            file = self.audit / path
            require(file.is_file() and digest(file) == expected, 'Check evidence changed: ' + path)
        return report

    def export(self):
        report = self.valid_checks()
        self.output.mkdir(parents=True, exist_ok=True)
        artifacts, start = {}, len(self.commands)
        frozen = report['source_sha256']
        for board in self.spec['boards']:
            name = board['name']
            out = self.output / name
            out.mkdir(parents=True, exist_ok=True)
            pcb = self.path(board['pcb'])
            model = pcb.parent / 'model.json'
            for variant in BOARDVIEW_VARIANTS:
                cad_name, proof_name = self.boardview_paths(board, variant)
                cad = self.output / cad_name
                boardview = export_boardview(pcb, cad, self.cli, assembly_variant=variant,
                                             model_path=model if model.is_file() else None)
                require(boardview.get('status') == 'PASS' and boardview.get('units') == 'THOU'
                        and boardview.get('assembly_variant') == variant
                        and boardview.get('pcb_sha256') == digest(pcb)
                        and boardview.get('cad_sha256') == digest(cad), 'Failed boardview export: ' + name + '/' + variant)
                boardview.update(product=self.key, version=self.version, board=name)
                write_json(self.output / proof_name, self.portable(boardview))
                artifacts[cad_name] = digest(cad)
                artifacts[proof_name] = digest(self.output / proof_name)
            for side, layers, mirror in [('front', 'F.Cu,F.SilkS,Edge.Cuts', False),
                                          ('back', 'B.Cu,B.SilkS,Edge.Cuts', True)]:
                file = out / (name + '_' + side + '.svg')
                args = ['pcb', 'export', 'svg', '--layers', layers, '--mode-single', '--fit-page-to-board',
                        '--exclude-drawing-sheet', '--check-zones']
                if mirror:
                    args.append('--mirror')
                require(self.run([*args, '-o', file, pcb], name + ' native ' + side + ' SVG') and file.is_file(),
                        'Failed SVG export: ' + name + '/' + side)
                artifacts[file.relative_to(self.output).as_posix()] = digest(file)
            if board.get('schematic'):
                file = out / (name + '_schematic.pdf')
                require(self.run(['sch', 'export', 'pdf', '-o', file, self.path(board['schematic'])], name + ' schematic PDF')
                        and file.is_file(), 'Failed schematic PDF: ' + name)
                self.enhance_pdf(board['schematic'], file, name, artifacts)
                artifacts[file.relative_to(self.output).as_posix()] = digest(file)
        file = self.output / 'shared_schematic.pdf'
        require(self.run(['sch', 'export', 'pdf', '-o', file, self.path(self.config['circuit']['schematic'])], 'common schematic PDF')
                and file.is_file(), 'Failed common schematic PDF')
        self.enhance_pdf(self.config['circuit']['schematic'], file, 'COMMON_CIRCUIT', artifacts)
        artifacts[file.relative_to(self.output).as_posix()] = digest(file)
        require(all(digest(self.path(p)) == h for p, h in frozen.items()), 'Source changed during export')
        proof = {'format_version': 1, 'product': self.key, 'version': self.version, 'status': 'PASS',
                 'kicad_version': self.args.kicad_version,
                 'source_sha256': frozen, 'checks_sha256': digest(self.audit / 'checks.json'),
                 'artifacts_sha256': artifacts, 'commands': self.commands[start:], 'sources_unchanged': True}
        write_json(self.audit / 'exports.json', proof)
        return proof

    def pdf_records(self):
        return [(b['name'], b['name'] + '/' + b['name'] + '_schematic.pdf',
                 b['name'] + '/' + b['name'] + '_pdf_clickmap.json')
                for b in self.spec['boards'] if b.get('schematic')] + [
                    ('COMMON_CIRCUIT', 'shared_schematic.pdf', 'shared_pdf_clickmap.json')]

    def enhance_pdf(self, schematic, file, name, artifacts):
        proof = enhance_schematic_pdf(self.path(schematic), file)
        proof['schematic_sha256'] = {self.rel(Path(p)): h for p, h in proof['schematic_sha256'].items()}
        proof.update(product=self.key, version=self.version, board=name)
        proof_name = next(record[2] for record in self.pdf_records() if record[0] == name)
        write_json(self.output / proof_name, self.portable(proof))
        artifacts[proof_name] = digest(self.output / proof_name)

    def validate_pdf_clickmaps(self, exports, check):
        for name, pdf_name, proof_name in self.pdf_records():
            for artifact in (pdf_name, proof_name):
                expected = exports['artifacts_sha256'].get(artifact)
                file = self.output / artifact
                require(expected and file.is_file() and digest(file) == expected,
                        'Missing or changed clickable PDF artifact: ' + artifact)
            proof = json.loads((self.output / proof_name).read_text('utf-8-sig'))
            sources = {p: check['source_sha256'][p] for p in self.dependencies[name]['schematics']}
            require(proof.get('status') == 'PASS' and proof.get('product') == self.key
                    and proof.get('version') == self.version and proof.get('board') == name
                    and proof.get('pdf_sha256') == digest(self.output / pdf_name)
                    and proof.get('schematic_sha256') == sources
                    and proof.get('original_text_has_priority') is True
                    and proof.get('schematics_unchanged') is True,
                    'Stale or failed clickable PDF verification: ' + name)

    def boardview_paths(self, board, variant):
        require(variant in BOARDVIEW_VARIANTS, 'Unknown boardview assembly variant: ' + variant)
        name = board['name']
        return (name + '/Mesh_Repeater_' + self.version + '_' + name + '_' + variant + '.cad',
                name + '/' + name + '_' + variant + '_boardview.json')

    def validate_boardviews(self, exports, check):
        """A partial artifact list must never silently omit a boardview."""
        for board in self.spec['boards']:
            model_name = str(Path(board['pcb']).parent / 'model.json').replace('\\', '/')
            for variant in BOARDVIEW_VARIANTS:
                cad_name, proof_name = self.boardview_paths(board, variant)
                for name in (cad_name, proof_name):
                    expected = exports['artifacts_sha256'].get(name)
                    file = self.output / name
                    require(expected and file.is_file() and digest(file) == expected,
                            'Missing or changed boardview artifact: ' + name)
                proof = json.loads((self.output / proof_name).read_text('utf-8-sig'))
                require(proof.get('status') == 'PASS' and proof.get('units') == 'THOU'
                        and proof.get('product') == self.key and proof.get('version') == self.version
                        and proof.get('board') == board['name'] and proof.get('assembly_variant') == variant
                        and proof.get('pcb_sha256') == check['source_sha256'][board['pcb']]
                        and proof.get('model_sha256') == check['source_sha256'].get(model_name)
                        and proof.get('cad_sha256') == digest(self.output / cad_name),
                        'Stale or failed boardview verification: ' + board['name'] + '/' + variant)

    def nexus_launchers(self, members):
        """Create launchers for this product without requiring CAD associations."""
        executable = NEXUS_BUNDLE + '/NexusBV.exe'
        require(executable in members, 'Missing packaged NexusBV executable')
        launchers, entries = {}, []
        for board in self.spec['boards']:
            name = board['name']
            require(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'Unsafe launcher board name: ' + name)
            for variant in BOARDVIEW_VARIANTS:
                cad, _ = self.boardview_paths(board, variant)
                targets = [self.spec['root'] + '/output/current/' + cad]
                if board.get('schematic'):
                    targets.append(self.spec['root'] + '/output/current/' + name + '/' + name + '_schematic.pdf')
                for target in targets:
                    require(target in members, 'Missing NexusBV launcher target: ' + target)
                    require(not any(c in target for c in ('%', '"', '\r', '\n')),
                            'Unsafe NexusBV launcher target: ' + target)
                filename = 'START_' + name + '_' + variant + '.cmd'
                paths = ['%~dp0' + p.replace('/', '\\') for p in [executable, *targets]]
                lines = ['@echo off', 'setlocal DisableDelayedExpansion']
                lines += ['if not exist "' + path + '" goto missing' for path in paths]
                lines += ['start "" /D "%~dp0' + NEXUS_BUNDLE.replace('/', '\\') + '" '
                          + ' '.join('"' + path + '"' for path in paths),
                          'if errorlevel 1 goto failed', 'exit /b 0', ':missing',
                          'echo Required files are missing. Extract the complete ZIP before starting.',
                          'pause', 'exit /b 1', ':failed', 'echo NexusBV could not start.',
                          'pause', 'exit /b 1']
                launchers[filename] = ('\r\n'.join(lines) + '\r\n').encode('ascii')
                entries.append((filename, name + ' - ' + variant))
        require(1 <= len(entries) <= 9, 'NexusBV launch menu supports one to nine boardviews')
        choices = ''.join(str(i) for i in range(1, len(entries) + 1)) + 'Q'
        lines = ['@echo off', 'setlocal DisableDelayedExpansion',
                 'echo Mesh Repeater ' + self.version + ' - NexusBV 0.9', 'echo.']
        lines += ['echo ' + str(i) + '. ' + label for i, (_, label) in enumerate(entries, 1)]
        lines += ['echo Q. Exit', 'choice /C ' + choices + ' /N /M "Open boardview: "',
                  'if errorlevel 255 exit /b 1', 'if errorlevel ' + str(len(entries) + 1) + ' exit /b 0']
        lines += ['if errorlevel ' + str(i) + ' goto board' + str(i)
                  for i in range(len(entries), 0, -1)]
        lines += ['exit /b 1']
        for i, (filename, _) in enumerate(entries, 1):
            # Transfer directly to the other batch file: CALL would expand path
            # characters a second time when the extracted directory contains %.
            lines += [':board' + str(i), 'if not exist "%~dp0' + filename + '" goto missing',
                      '"%~dp0' + filename + '"', 'exit /b']
        lines += [':missing', 'echo Extract the complete ZIP before starting.', 'pause', 'exit /b 1']
        launchers['START.cmd'] = ('\r\n'.join(lines) + '\r\n').encode('ascii')
        return launchers

    def package(self):
        check = self.valid_checks()
        export_path = self.audit / 'exports.json'
        require(export_path.is_file(), 'Run export/build first: missing export proof')
        exports = json.loads(export_path.read_text('utf-8-sig'))
        require(exports['status'] == 'PASS' and exports['version'] == self.version
                and exports['source_sha256'] == check['source_sha256']
                and exports['checks_sha256'] == digest(self.audit / 'checks.json'), 'Exports are stale; run build again')
        self.validate_boardviews(exports, check)
        self.validate_pdf_clickmaps(exports, check)
        members = {self.rel(p): p.read_bytes() for p in self.files if p != self.args.config.resolve()}
        portable_config = dict(self.config)
        portable_config['products'] = {self.key: self.spec}
        portable_config.pop('managed_by_thread', None)
        members['project.json'] = json_bytes(portable_config)
        for path, expected in exports['artifacts_sha256'].items():
            file = self.output / path
            require(file.is_file() and digest(file) == expected, 'Export changed: ' + path)
            members[self.spec['root'] + '/output/current/' + path] = file.read_bytes()
        for path in ['checks.json', 'exports.json', *check['reports_sha256']]:
            file = self.audit / path
            # Preserve the exact checked evidence, including its hashes. Native
            # XML may record the original source location as provenance; this
            # is not a dependency of the editable portable project.
            members[self.spec['root'] + '/audit/current/' + path] = file.read_bytes()
        # Shared entry points keep stable paths in both single-product packages.
        # Bind these aliases to this run, never to an older shared export.
        members['shared/output/pdf/MeshRepeater_schematic.pdf'] = (self.output / 'shared_schematic.pdf').read_bytes()
        members['shared/verification/circuit.json'] = (self.audit / 'circuit/circuit.json').read_bytes()
        members.update(self.nexus_launchers(members))
        # Notes are release-specific and do not overwrite the maintained README.
        board_entries = ''.join('  ' + b['name'] + ': ' + b['project'] + '\n'
                                for b in self.spec['boards'])
        boardview_entries = ''.join('  ' + self.spec['root'] + '/output/current/' + self.boardview_paths(b, variant)[0] + '\n'
                                    for b in self.spec['boards'] for variant in BOARDVIEW_VARIANTS)
        members['RELEASE_README_RU.txt'] = (
            'Mesh Repeater ' + self.version + '\n\n'
            'Полностью распакуйте ZIP в обычную папку до запуска START.cmd или открытия файлов.\n'
            'Portable NexusBV 0.9 для Windows 10/11 x64 включён; установка не требуется.\n'
            'Откройте START.cmd в корне распакованного пакета и выберите плату и химию.\n'
            'Или запустите START_<плата>_<химия>.cmd: CAD и PDF этой платы откроются вместе.\n'
            'Для SHIELD открывается только CAD. Не запускайте команды прямо из ZIP.\n'
            'Сохраняйте структуру папок пакета: программа и схемы нужны для запуска.\n'
            'Откройте нужный проект платы в KiCad 10:\n'
            + board_entries +
            'Все используемые 3D-модели включены и используют относительные пути.\n'
            'Для 3D включите категории «Модели выводные» и «Модели SMD».\n'
            'Общая схема: ' + self.config['circuit']['schematic'] + '\n'
            'У общей схемы нет собственной PCB; физические платы перечислены выше.\n'
            'Boardview с номиналами: откройте CAD через File → Open в NexusBV:\n'
            + boardview_entries +
            'NaIon_COLD — натрий с COLD-защитой; LTO_2S — LTO 2S.\n'
            'Номиналы соответствуют сборке; DNP означает «не устанавливать».\n'
            'Top / Bottom — стороны; номинал виден в Info и карточке компонента.\n'
            'Для перехода со схемы дважды щёлкните по телу символа или его обозначению\n'
            '(например R15) в PDF внутри NexusBV. Имена цепей также доступны для поиска.\n'
            'Надписи внутри символа сохраняют свой поиск: нажимайте по свободной части тела.\n'
            'PDF схемы находится рядом с CAD: <плата>_schematic.pdf; для SHIELD схемы нет.\n'
            'PDF показывает общую схему; номиналы/FIT выбранной химии смотрите в CAD и BOM.\n'
            'Проверка: python tools/project/release.py check --product ' + self.key + '\n'
            'Пакет содержит выбранную аппаратную версию и общую схему/профили.\n'
            'Производственные пакеты, расчёты заказа, исторические снимки и среды сборки исключены.\n'
            'Проверки CAD не заменяют испытаний образца.\n').encode('utf-8')
        forbidden = {'.git', 'archive', 'baseline', 'tmp', '.publication_tmp', '__pycache__'}
        for path in members:
            require(not any(p.lower() in forbidden for p in Path(path).parts), 'Forbidden release member: ' + path)
            require(not any(term in path.lower() for term in ('rezonit', 'резонит')),
                    'Removed manufacturer package in release: ' + path)
            require(not path.lower().endswith(('.zip', '.7z', '.rar', '.pyc', '.lck', '.bak', '.kicad_prl')),
                    'Backup/nested archive in release: ' + path)
        self.validate_document_links(members)
        manifest = {'format_version': 1, 'product': self.key, 'version': self.version,
                    'legacy_revision': self.spec.get('legacy_revision'), 'date': self.config.get('date'),
                    'repository': self.spec.get('repository'), 'kicad_version': self.args.kicad_version,
                    'source_sha256': check['source_sha256'], 'local_dependencies': self.dependencies,
                    'external_standard_models': sorted(self.standard_models),
                    'package_transformations': ['project.json selects only this product and omits local chat metadata',
                        'shared PDF and verification entry points alias the current product run bytes',
                        'START.cmd and board/assembly launchers use package-relative NexusBV, CAD and PDF paths'],
                    'files': {p: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                              for p, raw in sorted(members.items())},
                    'note': 'Manifest excludes its own recursive checksum. ZIP checksum is provided separately.'}
        members['RELEASE_MANIFEST.json'] = json_bytes(manifest)
        self.release_dir.mkdir(parents=True, exist_ok=True)
        archive = self.release_dir / ('Mesh_Repeater_' + self.version + '_KiCad.zip')
        prefix = 'Mesh_Repeater_' + self.version + '/'
        edition = datetime.strptime(self.config['date'], '%Y-%m-%d')
        zip_date = (edition.year, edition.month, edition.day, 0, 0, 0)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path, raw in sorted(members.items()):
                entry = zipfile.ZipInfo(prefix + path, zip_date)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                z.writestr(entry, raw)
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None, 'ZIP CRC verification failed')
            require(set(z.namelist()) == {prefix + p for p in members}, 'ZIP member mismatch')
            for path, raw in members.items():
                require(z.read(prefix + path) == raw, 'ZIP byte mismatch: ' + path)
        checksum = digest(archive)
        (self.release_dir / 'SHA256SUMS.txt').write_text(checksum + '  ' + archive.name + '\n', encoding='utf-8')
        write_json(self.release_dir / 'RELEASE_MANIFEST.json', manifest)
        write_json(self.audit / 'package.json', {'status': 'PASS', 'version': self.version,
                   'archive': archive.name, 'sha256': checksum, 'members': len(members), 'CRC': 'PASS'})
        return archive

    @staticmethod
    def validate_document_links(members):
        """Reject broken local links instead of importing historical payloads."""
        broken = []
        for path, raw in members.items():
            if Path(path).suffix.lower() not in ('.md', '.html'):
                continue
            text = raw.decode('utf-8-sig')
            text = re.sub(r'(?ms)^```[^\n]*\n.*?^```\s*$', '', text)
            if path.lower().endswith('.md'):
                links = re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text)
            else:
                links = re.findall(r'(?:href|src)=["\']([^"\']+)["\']', text)
            for link in links:
                link = link.strip()
                if not link:
                    continue
                # Markdown may add a quoted title after the URL.
                link = link[1:link.index('>')] if link.startswith('<') and '>' in link else link.split()[0]
                parsed = urlsplit(link)
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parsed.path)))
                if target.startswith('../') or target.startswith('/'):
                    broken.append(path + ' -> ' + link + ' (outside package)')
                elif target != '.' and target not in members and not any(p.startswith(target.rstrip('/') + '/') for p in members):
                    broken.append(path + ' -> ' + link)
        require(not broken, 'Broken package documentation links: ' + '; '.join(broken))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'export', 'package', 'build'])
    parser.add_argument('--product', choices=['v1', 'v2', 'all'], default='all')
    parser.add_argument('--config', type=Path, default=ROOT / 'project.json')
    parser.add_argument('--kicad-cli', type=Path, default=None)
    parser.add_argument('--work-dir', type=Path, help='Write audit, export and release results below this isolated directory')
    args = parser.parse_args()
    args.config = args.config.resolve()
    cli = args.kicad_cli or os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')
    if not cli:
        known = Path('C:/Program Files/KiCad/10.0/bin/kicad-cli.exe')
        cli = known if known.is_file() else None
    require(cli is not None, 'KiCad CLI not found; pass --kicad-cli or set KICAD_CLI')
    cli = Path(cli).resolve()
    require(cli.is_file(), 'KiCad CLI not found: ' + str(cli))
    args.kicad_version = subprocess.check_output([str(cli), 'version'], encoding='utf-8').strip()
    config = json.loads(args.config.read_text('utf-8-sig'))
    require(config.get('format_version') == 1, 'Unsupported project.json format_version')
    products = list(config['products']) if args.product == 'all' else [args.product]
    require(all(p in config['products'] for p in products), 'Requested product is absent from project.json')
    failures = []
    for key in products:
        try:
            product = Product(args, config, key, cli)
            if args.command in ('check', 'export', 'build'):
                product.check()
            if args.command in ('export', 'build'):
                product.export()
            if args.command in ('package', 'build'):
                result = product.package()
                print(key + ': PASS ' + str(result))
            else:
                print(key + ': PASS ' + str(product.audit / 'checks.json'))
        except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            failures.append(key)
            print(key + ': FAIL ' + str(exc), file=sys.stderr)
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ReleaseError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print('FAIL: ' + str(error), file=sys.stderr)
        sys.exit(1)
