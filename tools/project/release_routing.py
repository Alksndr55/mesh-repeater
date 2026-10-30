"""Measure routing geometry and bind the two-face review to the exact PCB.

This stdlib gate does not infer good routing from DRC or from segment counts.
Whole-path choices, parallel spacing and return-current needs require the saved
review; measured angle/overlap/duplicate failures cannot be waived by it.
"""
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

from circuit_io import children, one, properties, sexpr, value


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def nm(token):
    number = Decimal(token)
    if not number.is_finite():
        raise ValueError('Coordinate must be finite')
    return round(number * 1000000)


def point(node):
    return tuple(nm(x) for x in node[1:3])


def geometry(path):
    tree = sexpr(Path(path).read_text('utf-8-sig'))
    netnames = {n[1]: value(n[-1]) for n in children(tree, 'net') if len(n) > 2}
    tracks, vias, failures = [], [], []
    groups = defaultdict(list)

    def net(node):
        field = one(node, 'net')
        if field is None:
            return ''
        return netnames.get(field[1], value(field[-1]))

    for node in children(tree, 'segment'):
        start, end = point(one(node, 'start')), point(one(node, 'end'))
        uid = value(one(node, 'uuid')[1])
        layer = value(one(node, 'layer')[1])
        width = nm(one(node, 'width')[1])
        dx, dy = end[0] - start[0], end[1] - start[1]
        row = {'uuid': uid, 'net': net(node), 'layer': layer,
               'start_mm': [x / 1000000 for x in start],
               'end_mm': [x / 1000000 for x in end],
               'width_mm': width / 1000000,
               'length_mm': math.hypot(dx, dy) / 1000000}
        tracks.append(row)
        if dx == dy == 0:
            failures.append({'kind': 'zero_length_track', 'uuid': uid})
            continue
        if min(abs(dx), abs(dy), abs(abs(dx) - abs(dy))) > 1:
            failures.append({'kind': 'non_octilinear_track', **row})
        if min(abs(dx), abs(dy), abs(abs(dx) - abs(dy))) > 1:
            continue
        if abs(dy) <= 1:
            ux, uy = 1, 0
        elif abs(dx) <= 1:
            ux, uy = 0, 1
        else:
            ux, uy = 1, 1 if dx * dy > 0 else -1
        # Use the same 1nm rounding policy for directions and coincident lines.
        offset = (uy * (start[0] + end[0]) - ux * (start[1] + end[1])) / 2
        lo, hi = sorted((ux * start[0] + uy * start[1],
                         ux * end[0] + uy * end[1]))
        groups[(row['net'], layer, ux, uy)].append((offset, lo, hi, uid))
    for node in children(tree, 'arc'):
        failures.append({'kind': 'curved_track', 'uuid': value(one(node, 'uuid')[1])})
    for (name, layer, ux, uy), entries in groups.items():
        scale = math.hypot(ux, uy)
        entries.sort()
        for index, (offset, lo, hi, uid) in enumerate(entries):
            for other_offset, a, b, other in entries[index + 1:]:
                if other_offset - offset > scale:
                    break
                # A <=1nm overlap at a shared endpoint is coordinate rounding.
                if min(hi, b) - max(lo, a) > scale:
                    failures.append({'kind': 'collinear_track_overlap', 'net': name,
                                     'layer': layer, 'uuids': [uid, other],
                                     'line_distance_nm': abs(other_offset-offset)/scale,
                                     'rounding_tolerance_nm': 1})
    seen = {}
    for node in children(tree, 'via'):
        xy = point(one(node, 'at'))
        uid = value(one(node, 'uuid')[1])
        layers = tuple(value(x) for x in one(node, 'layers')[1:])
        name = net(node)
        key = (xy, tuple(sorted(layers)))
        for (previous_xy, previous_layers), other in seen.items():
            if previous_layers == key[1] and all(abs(x-y) <= 1 for x, y in zip(xy, previous_xy)):
                failures.append({'kind': 'duplicate_via_location', 'uuids': [other, uid],
                                 'xy_mm': [x / 1000000 for x in xy], 'rounding_tolerance_nm': 1})
        seen[key] = uid
        vias.append({'uuid': uid, 'net': name, 'layers': layers,
                     'xy_mm': [x / 1000000 for x in xy], 'xy_nm': xy})
    solid = []
    for fp in children(tree, 'footprint'):
        fp_connection = one(fp, 'zone_connect')
        ref = properties(fp).get('Reference', '')
        for pad in children(fp, 'pad'):
            if net(pad) != 'GND':
                continue
            local = one(pad, 'zone_connect')
            effective = local if local is not None and local[1] != '-1' else fp_connection
            if effective is not None and (effective[1] == '2' or
                                         (effective[1] == '3' and pad[2] != 'thru_hole')):
                solid.append({'kind': 'pad', 'uuid': value(one(pad, 'uuid')[1]),
                              'reference': ref, 'pad': value(pad[1])})
    for zone in children(tree, 'zone'):
        connection = one(zone, 'connect_pads')
        if (one(zone, 'keepout') is None and net(zone) == 'GND' and connection
                and len(connection) > 1 and connection[1] in ('yes', 'thru_hole_only')):
            solid.append({'kind': 'zone', 'uuid': value(one(zone, 'uuid')[1]),
                          'name': value(one(zone, 'name')[1]) if one(zone, 'name') else '',
                          'connection_mode': connection[1]})
    return {'pcb_sha256': digest(path), 'tracks': tracks, 'vias': vias,
            'solid_ground_connections': solid,
            'failures': failures, 'segments': len(tracks), 'via_count': len(vias),
            'short_segments_below_0_05mm': [t for t in tracks if t['length_mm'] < 0.05]}


def verify_routing(root, spec):
    result = {'status': 'FAIL', 'product_version': spec['version'], 'boards': [],
              'failures': [], 'scope': 'Measured routing geometry, grid ledger and exact-PCB two-face review. '
              'Whole-path style, parallel spacing and electrical return needs are reviewed explicitly; '
              'DRC alone is not routing acceptance.'}
    for board in spec['boards']:
        name = board['name']
        try:
            pcb = root / board['pcb']
            measured = geometry(pcb)
            errors = list(measured['failures'])
            review_path = pcb.parent / 'routing_review.json'
            review = json.loads(review_path.read_text('utf-8-sig'))
            def check(ok, message):
                if not ok:
                    errors.append({'kind': 'review_contract', 'message': message})
            check(review.get('format_version') == 1, 'Unknown review format')
            check(review.get('status') == 'PASS', 'Routing review has not passed')
            check(review.get('product_version') == spec['version'], 'Review product version is stale')
            check(review.get('pcb_sha256') == measured['pcb_sha256'], 'PCB changed after routing review')
            reviewer = review.get('reviewer')
            check(isinstance(reviewer, str) and bool(reviewer.strip()), 'Missing named reviewer')
            check(set(review.get('reviewed_faces', [])) == {'F.Cu', 'B.Cu'}, 'Both copper faces must be reviewed')
            for key in ('whole_paths', 'parallel_spacing', 'signal_and_ground_duplicates', 'critical_returns',
                        'pad_entries_and_junctions', 'ground_plane_connections', 'thermal_reliefs'):
                check(review.get('checks', {}).get(key) == 'PASS', 'Missing explicit review: ' + key)
            # GND traces can defeat a thermal relief without overlapping another
            # trace. Enumerate every retained one; a blanket PASS is insufficient.
            # The native filled-copper inspection is still required to judge the
            # reason. This stdlib gate cannot infer current loops from net names.
            def exact_reason_ledger(field, actual, identity, additional_fields=()):
                entries = review.get(field)
                check(isinstance(entries, list), 'An explicit ' + field + ' array is required')
                entries = entries if isinstance(entries, list) else []
                expected = {identity(row): row for row in actual}
                keys = [identity(row) for row in entries]
                check(len(keys) == len(set(keys)), 'Repeated entry in ' + field)
                check(set(keys) == set(expected), field + ' must cover exactly the measured objects')
                for row in entries:
                    reason = row.get('electrical_reason')
                    check(isinstance(reason, str) and bool(reason.strip()), 'Missing individual reason in ' + field)
                    original = expected.get(identity(row))
                    if original is not None:
                        for key in additional_fields:
                            check(row.get(key) == original.get(key), field + ' object differs: ' + str(identity(row)))
            exact_reason_ledger('retained_ground_tracks', [t for t in measured['tracks'] if t['net'] == 'GND'],
                                lambda row: row.get('uuid'), ('layer', 'start_mm', 'end_mm', 'width_mm'))
            exact_reason_ledger('solid_ground_connections', measured['solid_ground_connections'],
                                lambda row: (row.get('kind'), row.get('uuid')))
            check(review.get('grid_mm') == 5 and review.get('grid_origin_mm') == [0, 0],
                  'Expected 5mm ground grid from (0,0)')
            ground = [v for v in measured['vias'] if v['net'] == 'GND']
            offgrid = {v['uuid']: v for v in ground
                       if any(min(x % 5000000, (-x) % 5000000) > 1 for x in v['xy_nm'])}
            check(isinstance(review.get('off_grid_vias'), list), 'An explicit off-grid ledger array is required')
            ledger = review.get('off_grid_vias') if isinstance(review.get('off_grid_vias'), list) else []
            ids = [v.get('uuid') for v in ledger]
            check(len(ids) == len(set(ids)), 'Repeated ground-via exception UUID')
            check(set(ids) == set(offgrid), 'Exception ledger must cover exactly all off-grid GND vias')
            for entry in ledger:
                uid = entry.get('uuid')
                if uid not in offgrid:
                    continue
                check(tuple(nm(str(x)) for x in entry.get('xy_mm', [])) == offgrid[uid]['xy_nm'],
                      'Exception coordinates differ from PCB: ' + str(uid))
                check(entry.get('category') in ('local_return', 'island_bridge', 'rf_fence'),
                      'Exception needs an electrical category: ' + str(uid))
                reason = entry.get('electrical_reason')
                check(isinstance(reason, str) and bool(reason.strip()),
                      'Missing individual electrical reason: ' + str(uid))
            summary = {k: measured[k] for k in ('pcb_sha256', 'segments', 'via_count', 'short_segments_below_0_05mm')}
            summary.update(name=name, ground_vias=len(ground), ground_on_grid=len(ground)-len(offgrid),
                           ground_off_grid=len(offgrid), review_sha256=digest(review_path),
                           retained_ground_tracks=len(review.get('retained_ground_tracks') or []),
                           solid_ground_connections=len(measured['solid_ground_connections']),
                           failures=errors, status='FAIL' if errors else 'PASS')
            result['boards'].append(summary)
            result['failures'].extend({'board': name, **e} for e in errors)
        except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, ArithmeticError) as exc:
            result['failures'].append({'board': name, 'kind': 'routing_gate_input', 'message': str(exc)})
    result['status'] = 'FAIL' if result['failures'] else 'PASS'
    return result
