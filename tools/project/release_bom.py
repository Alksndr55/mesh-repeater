"""Read-only assembly BOM validation against fresh native XML, PCB and model."""
from __future__ import annotations

from collections import Counter
import csv
import json
import math
from pathlib import Path

from circuit_io import children, netlist, one, properties, sexpr, value


VARIANTS = [('NaIon_COLD', 'NaIon', 'naion'),
            ('NaIon_NoCOLD', 'NaIon_NoCold', 'naion_no_cold'),
            ('LTO_2S', 'LTO_2S', 'lto2s')]


def verify_bom(root: Path, product: dict, native_directory: Path,
               csv_path: Path | None = None) -> dict:
    path = csv_path or root / product['bom']
    failures, summaries, expected_keys = [], {}, set()

    def fail(board, reference, field, expected, actual):
        failures.append({'board': board, 'reference': reference, 'field': field,
                         'expected': expected, 'actual': actual})

    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        required = {'Board', 'Reference', 'Footprint', 'Layer', 'X_mm', 'Y_mm', 'Rotation_deg'}
        required |= {prefix + suffix for suffix, _, _ in VARIANTS for prefix in ('Value_', 'MPN_', 'Fit_')}
        missing = required - set(reader.fieldnames or [])
        if missing:
            fail('', '', 'required CSV columns', sorted(required), sorted(reader.fieldnames or []))
            return {'status': 'FAIL', 'failures': failures, 'rows': len(rows)}
    counts = Counter((row['Board'], row['Reference']) for row in rows)
    for key, count in counts.items():
        if count != 1:
            fail(*key, 'duplicate Board/Reference', 1, count)
    indexed = {(row['Board'], row['Reference']): row for row in rows}
    for board in product['boards']:
        name = board['name']
        model_file = (root / board['project']).parent / 'model.json'
        if not model_file.exists():
            # SHIELD has fabrication holes/contact/window footprints, but no
            # assembled electronic-component model or assembly BOM rows.
            summaries[name] = {'scope': 'mechanical board; excluded from electronic assembly BOM'}
            if board.get('schematic'):
                fail(name, '', 'electronic component model exists', True, False)
            continue
        model_list = json.loads(model_file.read_text('utf-8-sig'))['parts']
        model = {part['ref']: part for part in model_list}
        if len(model) != len(model_list):
            fail(name, '', 'unique model references', len(model_list), len(model))
        tree = sexpr((root / board['pcb']).read_text('utf-8-sig'))
        footprints = children(tree, 'footprint')
        pcb = {properties(fp).get('Reference'): fp for fp in footprints}
        if len(pcb) != len(footprints):
            fail(name, '', 'unique PCB references', len(footprints), len(pcb))
        xml = netlist(native_directory / name / 'netlist.xml')['parts']
        if set(model) != set(pcb) or set(model) != set(xml):
            fail(name, '', 'exact model/PCB/native XML references', sorted(model),
                 {'pcb': sorted(pcb), 'xml': sorted(xml)})
        expected_keys |= {(name, ref) for ref in model}
        checked = 0
        for ref in sorted(set(model) & set(pcb) & set(xml)):
            row = indexed.get((name, ref))
            if row is None:
                continue  # Missing identity is reported by the exact-set check.
            part, fp, native = model[ref], pcb[ref], xml[ref]['fields']
            fields = properties(fp)
            footprint = value(fp[1])
            for label, actual in [('BOM', row['Footprint']), ('model', part['footprint']),
                                  ('native XML', native['Footprint'])]:
                if actual != footprint:
                    fail(name, ref, label + ' footprint matches PCB', footprint, actual)
            for field, expected in [('Value', part['value']), ('MPN', part.get('mpn', ''))]:
                for label, actual in [('native XML', native.get(field, '')), ('PCB', fields.get(field, ''))]:
                    if actual != expected:
                        fail(name, ref, label + ' ' + field + ' matches model', expected, actual)
            for csv_suffix, native_suffix, model_suffix in VARIANTS:
                expected = {
                    'Value_': part.get('value_' + model_suffix, part['value']),
                    'MPN_': part.get('mpn_' + model_suffix, part.get('mpn', '')),
                    'Fit_': 'yes' if part.get('fit_' + model_suffix, not part.get('dnp', False)) else 'no',
                }
                for prefix, wanted in expected.items():
                    column = prefix + csv_suffix
                    if row[column] != wanted:
                        fail(name, ref, column, wanted, row[column])
                    native_field = prefix + native_suffix
                    for label, source in [('native XML', native), ('PCB', fields)]:
                        if native_field in source and source[native_field] != wanted:
                            fail(name, ref, label + ' ' + native_field, wanted, source[native_field])
            layer = value(one(fp, 'layer')[1])
            if row['Layer'] != layer:
                fail(name, ref, 'Layer', layer, row['Layer'])
            pose = one(fp, 'at')
            x, y = float(pose[1]), float(pose[2])
            angle = float(pose[3]) if len(pose) > 3 else 0.0
            for column, expected, tolerance in [('X_mm', x, .000051), ('Y_mm', y, .000051),
                                                 ('Rotation_deg', angle, .000501)]:
                try:
                    actual = float(row[column])
                    delta = ((actual-expected+180) % 360)-180 if column == 'Rotation_deg' else actual-expected
                    if not math.isfinite(actual) or abs(delta) > tolerance:
                        fail(name, ref, column, expected, row[column])
                except (ValueError, TypeError):
                    fail(name, ref, column, expected, row[column])
            for column, expected, actual in [('model x', x, part.get('x')), ('model y', y, part.get('y')),
                                              ('model rotation', angle, part.get('rotation'))]:
                if actual is None:
                    fail(name, ref, column, expected, actual)
                    continue
                delta = ((actual-expected+180) % 360)-180 if column == 'model rotation' else actual-expected
                if abs(delta) > .00001:
                    fail(name, ref, column, expected, actual)
            checked += 1
        summaries[name] = {'pcb_references': len(pcb), 'model_references': len(model),
                           'native_xml_references': len(xml), 'rows_checked': checked}
    if set(indexed) != expected_keys:
        fail('', '', 'exact electronic Board/Reference set',
             [list(k) for k in sorted(expected_keys)],
             {'missing': [list(k) for k in sorted(expected_keys-set(indexed))],
              'extra': [list(k) for k in sorted(set(indexed)-expected_keys)]})
    return {'status': 'PASS' if not failures else 'FAIL', 'rows': len(rows), 'boards': summaries,
            'scope': 'Exact electronic Board/Reference set; three assembly Value/MPN/Fit columns; '
                     'PCB/XML/model identity; actual PCB footprint, layer, coordinates and rotation. '
                     'Mechanical SHIELD fabrication features are outside the assembly BOM.',
            'failures': failures}
