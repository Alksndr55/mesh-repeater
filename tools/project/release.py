"""Check, export and package the current hardware products from project.json.

Uses Python's standard library and the installed KiCad CLI. Native CAD is the
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


ROOT = Path(__file__).resolve().parents[2]
QUOTE = r'"((?:\\.|[^"\\])*)"'
STATE_KEYS = ('violations', 'unconnected_items', 'schematic_parity', 'ignored_checks')


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
                if uri.startswith('${KICAD'):
                    self.standard_models.add(uri)
                else:
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
        for name in ('main.c', 'Makefile', 'watchdog.hex', 'source_hashes.json', 'INTEGRATION_RU.txt'):
            self.add(watchdog / name)
        for file in watchdog.rglob('*'):
            if file.is_file() and file.suffix.lower() in ('.c', '.h', '.s'):
                self.add(file)
        # These are small current stdlib commands, not the historical builders.
        for file in (ROOT / 'tools/project').glob('*.py'):
            self.add(file)
        if (ROOT / 'AGENTS.md').is_file():
            self.add(ROOT / 'AGENTS.md')
        self.add(self.args.config.resolve())
        return {self.rel(p): digest(p) for p in sorted(self.files)}

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
                artifacts[file.relative_to(self.output).as_posix()] = digest(file)
        file = self.output / 'shared_schematic.pdf'
        require(self.run(['sch', 'export', 'pdf', '-o', file, self.path(self.config['circuit']['schematic'])], 'common schematic PDF')
                and file.is_file(), 'Failed common schematic PDF')
        artifacts[file.relative_to(self.output).as_posix()] = digest(file)
        require(all(digest(self.path(p)) == h for p, h in frozen.items()), 'Source changed during export')
        proof = {'format_version': 1, 'product': self.key, 'version': self.version, 'status': 'PASS',
                 'kicad_version': self.args.kicad_version,
                 'source_sha256': frozen, 'checks_sha256': digest(self.audit / 'checks.json'),
                 'artifacts_sha256': artifacts, 'commands': self.commands[start:], 'sources_unchanged': True}
        write_json(self.audit / 'exports.json', proof)
        return proof

    def package(self):
        check = self.valid_checks()
        export_path = self.audit / 'exports.json'
        require(export_path.is_file(), 'Run export/build first: missing export proof')
        exports = json.loads(export_path.read_text('utf-8-sig'))
        require(exports['status'] == 'PASS' and exports['version'] == self.version
                and exports['source_sha256'] == check['source_sha256']
                and exports['checks_sha256'] == digest(self.audit / 'checks.json'), 'Exports are stale; run build again')
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
        # Notes are release-specific and do not overwrite the maintained README.
        members['RELEASE_README_RU.txt'] = (
            'Mesh Repeater ' + self.version + '\n\n'
            'Откройте проект из project.json в KiCad 10 с официальными библиотеками.\n'
            'Общая схема: ' + self.config['circuit']['schematic'] + '\n'
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
                        'shared PDF and verification entry points alias the current product run bytes'],
                    'files': {p: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                              for p, raw in sorted(members.items())},
                    'note': 'Manifest excludes its own recursive checksum. ZIP checksum is provided separately.'}
        members['RELEASE_MANIFEST.json'] = json_bytes(manifest)
        self.release_dir.mkdir(parents=True, exist_ok=True)
        archive = self.release_dir / ('Mesh_Repeater_' + self.version + '_KiCad.zip')
        prefix = 'Mesh_Repeater_' + self.version + '/'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for path, raw in sorted(members.items()):
                entry = zipfile.ZipInfo(prefix + path, (2026, 1, 1, 0, 0, 0))
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
