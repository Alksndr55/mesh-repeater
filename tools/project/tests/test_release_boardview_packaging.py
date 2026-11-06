"""Packaging cannot accept absent, changed, or stale repair boardviews."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release import Product, ReleaseError, digest, write_json, BOARDVIEW_VARIANTS


class BoardviewPackageGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.product = Product.__new__(Product)
        self.product.output = Path(self.temp.name)
        self.product.key = 'v2'
        self.product.version = 'v2.10'
        self.product.spec = {'boards': [
            {'name': name, 'pcb': 'v2/design/' + name + '/' + name + '.kicad_pcb'}
            for name in ('POWER', 'LOGIC', 'SHIELD')]}
        self.exports = {'artifacts_sha256': {}}
        self.check = {'source_sha256': {}}
        for board in self.product.spec['boards']:
            pcb_hash = hashlib.sha256(board['name'].encode()).hexdigest()
            self.check['source_sha256'][board['pcb']] = pcb_hash
            model_hash = None
            if board['name'] != 'SHIELD':
                model_hash = hashlib.sha256(('model-' + board['name']).encode()).hexdigest()
                self.check['source_sha256'][str(Path(board['pcb']).parent / 'model.json').replace('\\','/')] = model_hash
            for variant in BOARDVIEW_VARIANTS:
                cad, proof = self.product.boardview_paths(board, variant)
                cad_path, proof_path = self.product.output / cad, self.product.output / proof
                cad_path.parent.mkdir(parents=True, exist_ok=True)
                cad_path.write_text('CAD fixture for ' + board['name'] + '/' + variant, 'utf-8')
                write_json(proof_path, {'status': 'PASS', 'units': 'THOU',
                    'product': self.product.key, 'version': self.product.version,
                    'board': board['name'], 'pcb_sha256': pcb_hash, 'model_sha256': model_hash,
                    'assembly_variant': variant, 'cad_sha256': digest(cad_path)})
                self.exports['artifacts_sha256'].update({cad: digest(cad_path), proof: digest(proof_path)})
        self.cad, self.proof = self.product.boardview_paths(self.product.spec['boards'][0], BOARDVIEW_VARIANTS[0])

    def validate(self):
        self.product.validate_boardviews(self.exports, self.check)

    def edit_proof(self, **values):
        path = self.product.output / self.proof
        data = json.loads(path.read_text('utf-8'))
        data.update(values)
        write_json(path, data)
        self.exports['artifacts_sha256'][self.proof] = digest(path)

    def test_all_physical_boards_required(self):
        self.validate()
        shield_cad, _ = self.product.boardview_paths(self.product.spec['boards'][-1], 'LTO_2S')
        del self.exports['artifacts_sha256'][shield_cad]
        with self.assertRaisesRegex(ReleaseError, 'Missing or changed boardview'):
            self.validate()

    def test_existing_cad_omitted_from_manifest_is_rejected(self):
        del self.exports['artifacts_sha256'][self.cad]
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_missing_cad_is_rejected(self):
        (self.product.output / self.cad).unlink()
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_changed_cad_is_rejected(self):
        (self.product.output / self.cad).write_text('different CAD', 'utf-8')
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_missing_verification_is_rejected(self):
        del self.exports['artifacts_sha256'][self.proof]
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_stale_pcb_binding_is_rejected(self):
        self.edit_proof(pcb_sha256='0' * 64)
        with self.assertRaisesRegex(ReleaseError, 'Stale or failed boardview'):
            self.validate()

    def test_stale_assembly_model_is_rejected(self):
        self.edit_proof(model_sha256='0' * 64)
        with self.assertRaises(ReleaseError):
            self.validate()

    def test_failed_or_inch_or_wrong_version_report_is_rejected(self):
        for values in ({'status': 'FAIL'}, {'units': 'INCH'}, {'version': 'v2.09'}, {'assembly_variant':'LTO_2S'}):
            with self.subTest(values=values):
                self.edit_proof(status='PASS', units='THOU', version=self.product.version, assembly_variant=BOARDVIEW_VARIANTS[0])
                self.edit_proof(**values)
                with self.assertRaises(ReleaseError):
                    self.validate()


if __name__ == '__main__':
    unittest.main()
