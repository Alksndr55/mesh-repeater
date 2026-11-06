"""A release must not depend on the recipient's global KiCad 3D libraries."""
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import release

class ModelDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Mesh 3D package ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()
        self.patch_root=patch.object(release,'ROOT',self.root)
        self.patch_root.start();self.addCleanup(self.patch_root.stop)
        self.folder=self.root/'v1';self.folder.mkdir()
        (self.folder/'board.kicad_pro').write_text('{}')
        (self.folder/'routing_review.json').write_text('{}')
        self.record={'name':'MAIN','project':'v1/board.kicad_pro','pcb':'v1/board.kicad_pcb'}
        self.product=release.Product.__new__(release.Product)
        self.product.files=set();self.product.standard_models=set();self.product.dependencies={}

    def board_model(self,uri):
        (self.folder/'board.kicad_pcb').write_text('(kicad_pcb (model "'+uri+'"))')

    def test_global_standard_model_is_rejected(self):
        self.board_model('${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805.step')
        with self.assertRaisesRegex(release.ReleaseError,'3D model is not bundled'):
            self.product.project(self.record)

    def test_local_model_is_collected_and_hashable(self):
        self.board_model('${KIPRJMOD}/3dmodels/R_0805.step')
        model=self.folder/'3dmodels/R_0805.step';model.parent.mkdir();model.write_bytes(b'ISO-10303-21; fixture')
        self.product.project(self.record)
        self.assertIn(model,self.product.files)
        self.assertEqual(self.product.dependencies['MAIN']['models'],['v1/3dmodels/R_0805.step'])
        self.assertFalse(self.product.standard_models)

    def test_missing_local_model_blocks_release(self):
        self.board_model('${KIPRJMOD}/3dmodels/missing.step')
        with self.assertRaisesRegex(release.ReleaseError,'Missing release dependency'):
            self.product.project(self.record)

    def test_library_only_global_model_is_also_rejected(self):
        (self.folder/'board.kicad_pcb').write_text('(kicad_pcb (footprint "Local:R_0805"))')
        (self.folder/'fp-lib-table').write_text('(fp_lib_table (lib (name "Local") (uri "${KIPRJMOD}/Local.pretty")))')
        lib=self.folder/'Local.pretty';lib.mkdir()
        (lib/'R_0805.kicad_mod').write_text('(footprint "R_0805" (model "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0805.step"))')
        with self.assertRaisesRegex(release.ReleaseError,'3D model is not bundled'):
            self.product.project(self.record)

if __name__=='__main__':unittest.main()
