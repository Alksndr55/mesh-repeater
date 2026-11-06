"""A release cannot silently drop body-click support or use a stale PDF."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import Product, ReleaseError, digest, write_json


class ClickablePdfPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.product = Product.__new__(Product)
        self.product.output = Path(self.temp.name)
        self.product.key, self.product.version = 'v1', 'v1.25'
        self.product.spec = {'boards': [{'name': 'MAIN', 'schematic': 'v1/main.kicad_sch'}]}
        self.product.dependencies = {
            'MAIN': {'schematics': ['v1/main.kicad_sch', 'v1/child.kicad_sch']},
            'COMMON_CIRCUIT': {'schematics': ['shared/common.kicad_sch']}}
        self.check = {'source_sha256': {p: p + '-hash'
            for v in self.product.dependencies.values() for p in v['schematics']}}
        self.exports = {'artifacts_sha256': {}}
        for name, pdf, report in self.product.pdf_records():
            pdf_path, report_path = self.product.output / pdf, self.product.output / report
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b'PDF fixture ' + name.encode())
            write_json(report_path, {'status': 'PASS', 'product': 'v1', 'version': 'v1.25',
                'board': name, 'pdf_sha256': digest(pdf_path),
                'schematic_sha256': {p: self.check['source_sha256'][p]
                    for p in self.product.dependencies[name]['schematics']},
                'original_text_has_priority': True, 'schematics_unchanged': True})
            self.exports['artifacts_sha256'].update({pdf: digest(pdf_path), report: digest(report_path)})

    def validate(self):
        self.product.validate_pdf_clickmaps(self.exports, self.check)

    def test_valid_main_and_common(self):
        self.validate()

    def test_missing_common_proof_cannot_be_omitted_from_artifacts(self):
        del self.exports['artifacts_sha256']['shared_pdf_clickmap.json']
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_modified_pdf_is_rejected(self):
        (self.product.output / 'MAIN/MAIN_schematic.pdf').write_bytes(b'changed')
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_stale_or_incomplete_native_binding_is_rejected(self):
        name = 'MAIN/MAIN_pdf_clickmap.json'
        path = self.product.output / name
        original = json.loads(path.read_text('utf-8'))
        for changes in ({'status': 'FAIL'}, {'version': 'v1.26'},
                        {'pdf_sha256': 'wrong'}, {'schematic_sha256': {}},
                        {'original_text_has_priority': False}):
            with self.subTest(changes=changes):
                write_json(path, {**original, **changes})
                self.exports['artifacts_sha256'][name] = digest(path)
                with self.assertRaises(ReleaseError):
                    self.validate()


if __name__ == '__main__':
    unittest.main()
