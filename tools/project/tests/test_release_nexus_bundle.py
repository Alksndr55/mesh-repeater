"""Portable viewer files and launch paths must be complete and hash-bound."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release
from release import BOARDVIEW_VARIANTS, NEXUS_BUNDLE, Product, ReleaseError, digest, write_json


class NexusBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='Mesh package ! with spaces ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.patch_root = patch.object(release, 'ROOT', self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
        self.bundle = self.root / NEXUS_BUNDLE
        self.bundle.mkdir(parents=True)
        self.manifest = {'name': 'NexusBV', 'version': '0.9', 'platform': 'Windows x64', 'files': {}}
        for name in ('NexusBV.exe', 'nexusbv_core.dll', 'pdfium.dll', 'themes/default.json', 'readme_ru.txt'):
            file = self.bundle / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(('fixture: ' + name).encode())
            self.manifest['files'][name] = {'sha256': digest(file), 'bytes': file.stat().st_size}
        self.save_manifest()
        self.config_path = self.root / 'project.json'
        self.config_path.write_text('{}', 'utf-8')
        self.product = Product.__new__(Product)
        self.product.args = SimpleNamespace(config=self.config_path, kicad_version='test', work_dir=None)
        self.product.key, self.product.version = 'v1', 'v1.26'
        self.product.product_root = self.root / 'v1'
        self.product.audit = self.root / 'audit'
        self.product.output = self.root / 'output'
        self.product.release_dir = self.root / 'releases'
        self.product.files, self.product.standard_models = set(), set()
        self.product.dependencies = {}
        self.set_boards('v1', ['MAIN'])

    def set_boards(self, key, names):
        self.product.key, self.product.version = key, {'v1': 'v1.26', 'v2': 'v2.10'}[key]
        self.product.spec = {'root': key, 'version': self.product.version, 'bom': key + '/bom.csv',
                             'boards': [{'name': name, 'project': key + '/' + name + '.kicad_pro',
                                         'schematic': None if name == 'SHIELD' else key + '/' + name + '.kicad_sch'}
                                        for name in names]}
        self.product.config = {'date': '2026-11-06', 'products': {key: self.product.spec},
                               'circuit': {'project': 'shared/common.kicad_pro',
                                           'schematic': 'shared/common.kicad_sch', 'profiles': 'shared/variants.json'}}

    def save_manifest(self):
        write_json(self.bundle / 'bundle_manifest.json', self.manifest)

    def test_collects_only_listed_files_and_manifest(self):
        (self.bundle / 'private-history.db').write_bytes(b'not for release')
        self.product.collect_nexus_bundle()
        actual = {p.relative_to(self.bundle).as_posix() for p in self.product.files}
        self.assertEqual(actual, set(self.manifest['files']) | {'bundle_manifest.json'})

    def test_missing_manifest_and_missing_runtime_are_rejected(self):
        manifest_path = self.bundle / 'bundle_manifest.json'
        manifest_path.unlink()
        with self.assertRaisesRegex(ReleaseError, 'Missing release dependency'):
            self.product.collect_nexus_bundle()
        self.save_manifest()
        (self.bundle / 'nexusbv_core.dll').unlink()
        with self.assertRaisesRegex(ReleaseError, 'Missing release dependency'):
            self.product.collect_nexus_bundle()

    def test_required_entries_cannot_be_omitted(self):
        for name in ('NexusBV.exe', 'nexusbv_core.dll', 'pdfium.dll'):
            with self.subTest(name=name):
                record = self.manifest['files'].pop(name)
                self.save_manifest()
                with self.assertRaisesRegex(ReleaseError, 'Missing required NexusBV'):
                    self.product.collect_nexus_bundle()
                self.manifest['files'][name] = record

    def test_changed_hash_or_size_is_rejected(self):
        entry = self.manifest['files']['NexusBV.exe']
        original = dict(entry)
        for field, value in [('sha256', '0' * 64), ('bytes', entry['bytes'] + 1)]:
            with self.subTest(field=field):
                entry.update(original)
                entry[field] = value
                self.save_manifest()
                with self.assertRaisesRegex(ReleaseError, 'Changed NexusBV bundle'):
                    self.product.collect_nexus_bundle()

    def test_identity_and_checksum_schema_are_validated(self):
        for field, value in [('name', 'OtherViewer'), ('version', '0.8'), ('platform', 'Linux')]:
            with self.subTest(field=field):
                original = self.manifest[field]
                self.manifest[field] = value
                self.save_manifest()
                with self.assertRaisesRegex(ReleaseError, 'Unexpected NexusBV bundle identity'):
                    self.product.collect_nexus_bundle()
                self.manifest[field] = original
        record = self.manifest['files']['NexusBV.exe']
        original = dict(record)
        for bad in ({'sha256': 'abc'}, {'bytes': -1}, {'bytes': True}):
            with self.subTest(record=bad):
                record.update(original)
                record.update(bad)
                self.save_manifest()
                with self.assertRaisesRegex(ReleaseError, 'Invalid NexusBV bundle checksum'):
                    self.product.collect_nexus_bundle()

    def test_unsafe_and_windows_ambiguous_paths_are_rejected(self):
        for name in ('../outside.dll', '/absolute.dll', 'C:/absolute.dll', 'C:relative.dll',
                     'themes/../../outside.dll', 'themes\\outside.dll', 'themes//file.dll',
                     'themes/./file.dll', 'file.dll:stream', 'file.dll.', 'file.dll ',
                     'bundle_manifest.json', 'NEXUSBV.EXE'):
            with self.subTest(name=name):
                self.manifest['files'][name] = {'sha256': '0' * 64, 'bytes': 1}
                self.save_manifest()
                with self.assertRaisesRegex(ReleaseError, 'Unsafe or duplicate NexusBV bundle path'):
                    self.product.collect_nexus_bundle()
                del self.manifest['files'][name]

    def prepare_collect(self):
        self.product.project = Mock()
        for relative in ('shared/variants.json', 'v1/bom.csv',
                         'tools/project/vendor/PYPDF_LICENSE', 'tools/project/vendor/PYPDF_NOTICE.txt'):
            file = self.root / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'fixture')
        watchdog = self.product.product_root / 'design/watchdog_reference'
        for name in ('main.c', 'Makefile', 'watchdog.hex', 'source_hashes.json', 'INTEGRATION_RU.txt',
                     'build.ps1', 'VERSION', 'LICENSE.md', 'verification/software_checks.json'):
            file = watchdog / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'fixture')

    def test_refreshed_vendor_manifest_cannot_bypass_frozen_checks(self):
        self.prepare_collect()
        frozen = self.product.collect()
        self.assertIn(NEXUS_BUNDLE + '/bundle_manifest.json', frozen)
        self.assertIn(NEXUS_BUNDLE + '/pdfium.dll', frozen)
        write_json(self.product.audit / 'checks.json', {'status': 'PASS', 'version': self.product.version,
                   'kicad_version': 'test', 'source_sha256': frozen, 'reports_sha256': {}})
        self.product.valid_checks()
        file = self.bundle / 'NexusBV.exe'
        file.write_bytes(b'updated vendor executable')
        self.manifest['files']['NexusBV.exe'] = {'sha256': digest(file), 'bytes': file.stat().st_size}
        self.save_manifest()
        with self.assertRaisesRegex(ReleaseError, 'Sources changed since checks'):
            self.product.valid_checks()

    def launcher_members(self):
        members = {NEXUS_BUNDLE + '/NexusBV.exe': b'executable fixture'}
        for board in self.product.spec['boards']:
            for variant in BOARDVIEW_VARIANTS:
                cad, _ = self.product.boardview_paths(board, variant)
                members[self.product.key + '/output/current/' + cad] = b'CAD fixture'
            if board.get('schematic'):
                name = board['name']
                members[self.product.key + '/output/current/' + name + '/' + name + '_schematic.pdf'] = b'PDF fixture'
        return members

    def test_both_products_launch_correct_current_cad_and_pdf(self):
        for key, boards in [('v1', ['MAIN']), ('v2', ['POWER', 'LOGIC', 'SHIELD'])]:
            with self.subTest(product=key):
                self.set_boards(key, boards)
                members = self.launcher_members()
                launchers = self.product.nexus_launchers(members)
                self.assertEqual(len(launchers), 1 + 2 * len(boards))
                menu = launchers['START.cmd'].decode('ascii')
                self.assertIn(self.product.version, menu)
                self.assertNotIn('call ', menu.lower())
                for board in self.product.spec['boards']:
                    for variant in BOARDVIEW_VARIANTS:
                        filename = 'START_' + board['name'] + '_' + variant + '.cmd'
                        raw = launchers[filename]
                        text = raw.decode('ascii')
                        self.assertNotIn(b'\n', raw.replace(b'\r\n', b''))
                        self.assertIn('setlocal DisableDelayedExpansion', text)
                        self.assertNotIn(str(self.root), text)
                        cad, _ = self.product.boardview_paths(board, variant)
                        command = next(line for line in text.splitlines() if line.startswith('start '))
                        self.assertIn('start "" /D "%~dp0third_party\\NexusBV\\0.9" ', command)
                        self.assertIn('"%~dp0' + (key + '/output/current/' + cad).replace('/', '\\') + '"', command)
                        self.assertEqual(command.count('.pdf"'), 0 if board['name'] == 'SHIELD' else 1)
                        self.assertIn('"%~dp0' + filename + '"', menu)

    def test_launchers_reject_missing_exe_cad_or_pdf(self):
        original = self.launcher_members()
        for target in original:
            with self.subTest(missing=target):
                members = dict(original)
                del members[target]
                with self.assertRaisesRegex(ReleaseError, 'Missing (packaged NexusBV|NexusBV launcher target)'):
                    self.product.nexus_launchers(members)

    def test_package_hashes_runtime_and_all_launchers(self):
        self.set_boards('v2', ['POWER', 'LOGIC', 'SHIELD'])
        self.product.collect_nexus_bundle()
        source_hashes = {self.product.rel(p): digest(p) for p in self.product.files}
        check = {'source_sha256': source_hashes, 'reports_sha256': {}}
        self.product.valid_checks = Mock(return_value=check)
        self.product.validate_boardviews = Mock()
        self.product.validate_pdf_clickmaps = Mock()
        write_json(self.product.audit / 'checks.json', check)
        write_json(self.product.audit / 'circuit/circuit.json', {'status': 'PASS'})
        artifacts = {}
        for path, raw in self.launcher_members().items():
            prefix = self.product.key + '/output/current/'
            if path.startswith(prefix):
                name = path[len(prefix):]
                file = self.product.output / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(raw)
                artifacts[name] = digest(file)
        shared = self.product.output / 'shared_schematic.pdf'
        shared.write_bytes(b'shared PDF fixture')
        artifacts['shared_schematic.pdf'] = digest(shared)
        write_json(self.product.audit / 'exports.json', {'status': 'PASS', 'version': self.product.version,
                   'source_sha256': source_hashes, 'checks_sha256': digest(self.product.audit / 'checks.json'),
                   'artifacts_sha256': artifacts})
        archive = self.product.package()
        with zipfile.ZipFile(archive) as zipped:
            prefix = 'Mesh_Repeater_' + self.product.version + '/'
            manifest = json.loads(zipped.read(prefix + 'RELEASE_MANIFEST.json'))
            launchers = [p for p in manifest['files'] if p.endswith('.cmd')]
            self.assertEqual(len(launchers), 7)
            expected = set(launchers) | {NEXUS_BUNDLE + '/' + p for p in self.manifest['files']}
            expected.add(NEXUS_BUNDLE + '/bundle_manifest.json')
            for path in expected:
                raw = zipped.read(prefix + path)
                self.assertEqual(manifest['files'][path], {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
            self.assertIsNone(zipped.testzip())


if __name__ == '__main__':
    unittest.main()
