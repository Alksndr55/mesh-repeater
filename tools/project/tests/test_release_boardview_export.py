"""Regression cases behind the real KiCad/Nexus boardview failures."""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_boardview import BoardviewError, _assembly_metadata, _match, _normalize_units, _parse, _repair, _validate_geometry


RAW = '''$HEADER
GENCAD 1.4
UNITS INCH
$ENDHEADER
$PADS
PAD WRONG ROUND 0
CIRCLE 0 0 0.1
$ENDPADS
$PADSTACKS
PADSTACK STACK 0
PAD WRONG TOP 0 0
$ENDPADSTACKS
$SHAPES
SHAPE "TP9"
PIN "1" STACK 0 0 TOP 0 0
$ENDSHAPES
$COMPONENTS
COMPONENT "TP9"
DEVICE "DEV_TP9"
PLACE 0 0
LAYER TOP
ROTATION 0
SHAPE "TP9" 0 0
$ENDCOMPONENTS
$SIGNALS
$ENDSIGNALS
'''


class Pad:
    def __init__(self, x=0, angle=0, copper=True, net=0, number='1'):
        self.x, self.angle, self.copper, self.net, self.number = x, angle, copper, net, number

    def GetPosition(self): return SimpleNamespace(x=self.x, y=0)
    def GetSize(self): return SimpleNamespace(x=1.7, y=1.7)
    def GetDrillSize(self): return SimpleNamespace(x=0, y=0)
    def GetNumber(self): return self.number
    def GetShape(self): return 0
    def GetOrientationDegrees(self): return self.angle
    def GetNetCode(self): return self.net
    def IsOnLayer(self, layer): return self.copper and layer == 0


class Footprint:
    def __init__(self, pad): self.pad = pad
    def Pads(self): return [self.pad]
    def GetValue(self): return '1.7mm TEST'
    def GetOrientationDegrees(self): return 0


PCBNEW = SimpleNamespace(F_Cu=0, B_Cu=2, ToMM=lambda x: x,
                         PAD_SHAPE_CIRCLE=0, PAD_SHAPE_RECT=1, PAD_SHAPE_OVAL=2, PAD_SHAPE_ROUNDRECT=4)


class BoardviewExportTests(unittest.TestCase):
    def model_file(self, parts):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'model.json'
        path.write_text(json.dumps({'parts': parts}), 'utf-8')
        return path

    def test_nonempty_wrong_stack_is_repaired(self):
        # POWER TP9 exposed this case; checking only empty stacks misses it.
        pad = Pad()
        text, report = _repair(RAW, {'TP9': Footprint(pad)}, PCBNEW)
        self.assertEqual(report['repaired_padstacks'], 1)
        parsed = _parse(text)
        stack = parsed['stacks'][parsed['shapes']['TP9'][0][2]]
        _validate_geometry(parsed, stack, pad, PCBNEW, 'TP9.1')
        self.assertEqual(parsed['components']['TP9']['DEVICE'], ['1.7mm TEST'])

    def test_future_local_rotation_fails_before_misleading_export(self):
        with self.assertRaisesRegex(BoardviewError, 'local pad rotation'):
            _repair(RAW, {'TP9': Footprint(Pad(angle=90))}, PCBNEW)

    def test_connected_non_copper_pad_cannot_be_discarded(self):
        with self.assertRaisesRegex(BoardviewError, 'connected/drilled'):
            _repair(RAW, {'TP9': Footprint(Pad(copper=False, net=1))}, PCBNEW)

    def test_duplicate_number_positions_are_not_collapsed(self):
        a, b = Pad(x=1, number='2'), Pad(x=2, number='2')
        remaining = [a, b]
        pin = ['PIN', '2', 'STACK', '0', '0', 'TOP', '0', '0']
        self.assertIs(_match(remaining, pin, (2, 0), PCBNEW, 'J13'), b)
        self.assertIs(_match(remaining, pin, (1, 0), PCBNEW, 'J13'), a)
        self.assertFalse(remaining)

    def test_thou_conversion_keeps_angles_names_and_values(self):
        source = RAW.replace('PLACE 0 0', 'PLACE 1 -2').replace('ROTATION 0', 'ROTATION 90')
        source = source.replace('DEVICE "DEV_TP9"', 'DEVICE "10k 1%"')
        source = source.replace('$ENDCOMPONENTS', 'TEXT 1 2 0.1 90 MIRRORX SILKSCREEN_TOP "10k 1%" 0 0 0.5 0.25\n$ENDCOMPONENTS')
        result = _normalize_units(source)
        parsed = _parse(result)
        self.assertEqual(parsed['units'], 'THOU')
        self.assertEqual(parsed['components']['TP9']['PLACE'], ['1000', '-2000'])
        self.assertEqual(parsed['components']['TP9']['ROTATION'], ['90'])
        self.assertEqual(parsed['components']['TP9']['DEVICE'], ['10k 1%'])
        text = next(t for _, t in parsed['sections']['COMPONENTS'] if t[0] == 'TEXT')
        self.assertEqual(text[4:8], ['90', 'MIRRORX', 'SILKSCREEN_TOP', '10k 1%'])
        self.assertEqual(text[10:12], ['500.0', '250.00'])

    def test_assembly_changes_values_and_fit_without_removing_geometry(self):
        native = {'TP9': Footprint(Pad())}
        model = self.model_file([{'ref': 'TP9', 'value': '10k', 'value_lto2s': '22k',
                                  'fit_naion': True, 'fit_lto2s': False, 'dnp': False}])
        source = model.read_bytes()
        sodium = _assembly_metadata(native, None, model)
        lto = _assembly_metadata(native, 'LTO_2S', model)
        self.assertEqual(sodium['assembly_variant'], 'NaIon_COLD')
        self.assertEqual(sodium['component_values'], {'TP9': '10k'})
        self.assertEqual(lto['component_values'], {'TP9': '22k'})
        self.assertEqual(lto['component_fitted'], {'TP9': False})
        self.assertEqual(lto['component_device_text'], {'TP9': 'DNP | 22k'})
        self.assertEqual(lto['model_sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual(model.read_bytes(), source)
        exports = [_normalize_units(_repair(RAW, native, PCBNEW, a['component_device_text'])[0]) for a in (sodium, lto)]
        without_device = lambda text: [line for line in text.splitlines() if not line.startswith('DEVICE ')]
        self.assertEqual(without_device(exports[0]), without_device(exports[1]))
        self.assertEqual(len(_parse(exports[1])['shapes']['TP9']), 1)

    def test_dnp_fallback_does_not_duplicate_marker(self):
        model = self.model_file([{'ref': 'TP9', 'value': 'DNP', 'dnp': True}])
        assembly = _assembly_metadata({'TP9': Footprint(Pad())}, 'LTO_2S', model)
        self.assertEqual(assembly['component_device_text'], {'TP9': 'DNP'})
        self.assertEqual(assembly['component_fitted'], {'TP9': False})

    def test_model_references_must_be_exact_and_unique(self):
        native = {'TP9': Footprint(Pad())}
        for refs in ([], ['TP8'], ['TP9', 'TP8'], ['TP9', 'TP9']):
            with self.subTest(refs=refs):
                model = self.model_file([{'ref': ref, 'value': '10k'} for ref in refs])
                with self.assertRaises(BoardviewError):
                    _assembly_metadata(native, 'NaIon_COLD', model)

    def test_common_mechanical_board_keeps_values_and_variant_label(self):
        assembly = _assembly_metadata({'TP9': Footprint(Pad())}, 'LTO_2S', None)
        self.assertEqual(assembly['assembly_variant'], 'LTO_2S')
        self.assertEqual(assembly['component_values'], {'TP9': '1.7mm TEST'})
        self.assertEqual(assembly['component_fitted'], {'TP9': True})
        self.assertNotIn('model_sha256', assembly)
        with self.assertRaises(BoardviewError):
            _assembly_metadata({'TP9': Footprint(Pad())}, 'NaIon_NoCold', None)


if __name__ == '__main__':
    unittest.main()
