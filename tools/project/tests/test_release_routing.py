"""Regression probes for routing failures that a PASS review cannot conceal."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from release_routing import verify_routing


TRACK = '(segment (start 0 0) (end 2 0) (width 0.25) (layer "F.Cu") (net "SIG") (uuid "t1"))'
VIA = '(via (at 5 5) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "GND") (uuid "v1"))'


class RoutingGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pcb = self.root / 'v1/design/main/main.kicad_pcb'
        self.pcb.parent.mkdir(parents=True)
        self.spec = {'version': 'v1.24', 'boards': [{'name': 'MAIN', 'pcb': 'v1/design/main/main.kicad_pcb'}]}
        self.write_board()
        self.write_review()

    def write_board(self, tracks=TRACK, vias=VIA, extra=''):
        self.pcb.write_text('(kicad_pcb (version 20260206) (generator "pcbnew") '
                            '(layers (0 "F.Cu" signal) (2 "B.Cu" signal)) '
                            + tracks + vias + extra + ')', 'utf-8')

    def write_review(self, **changes):
        review = {'format_version': 1, 'status': 'PASS', 'product_version': 'v1.24',
                  'pcb_sha256': hashlib.sha256(self.pcb.read_bytes()).hexdigest(),
                  'reviewer': 'independent regression fixture', 'reviewed_faces': ['F.Cu', 'B.Cu'],
                  'checks': {k: 'PASS' for k in ('whole_paths', 'parallel_spacing',
                             'signal_and_ground_duplicates', 'critical_returns', 'pad_entries_and_junctions',
                             'ground_plane_connections', 'thermal_reliefs')},
                  'retained_ground_tracks': [], 'solid_ground_connections': [],
                  'grid_mm': 5, 'grid_origin_mm': [0, 0], 'off_grid_vias': []}
        review.update(changes)
        (self.pcb.parent / 'routing_review.json').write_text(json.dumps(review), 'utf-8')

    def check(self):
        return verify_routing(self.root, self.spec)

    def fail_kind(self, kind):
        report = self.check()
        self.assertEqual(report['status'], 'FAIL')
        self.assertIn(kind, [f['kind'] for f in report['failures']])

    def test_valid_board(self):
        self.assertEqual(self.check()['status'], 'PASS')

    def test_one_nm_rounding_is_allowed(self):
        self.write_board(TRACK.replace('(end 2 0)', '(end 2 2.000001)'))
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_oblique_track_cannot_be_approved(self):
        self.write_board(TRACK.replace('(end 2 0)', '(end 2 2.000002)'))
        self.write_review()
        self.fail_kind('non_octilinear_track')

    def test_zero_length_cannot_be_approved(self):
        self.write_board(TRACK.replace('(end 2 0)', '(end 0 0)'))
        self.write_review()
        self.fail_kind('zero_length_track')

    def test_partial_overlap_with_different_width_cannot_be_approved(self):
        other = TRACK.replace('(start 0 0)', '(start 1 0)').replace('(end 2 0)', '(end 3 0)')
        other = other.replace('0.25', '0.8').replace('"t1"', '"t2"')
        self.write_board(TRACK + other)
        self.write_review()
        self.fail_kind('collinear_track_overlap')

    def test_reversed_duplicate_cannot_be_approved(self):
        other = TRACK.replace('(start 0 0)', '(start 2 0)').replace('(end 2 0)', '(end 0 0)')
        self.write_board(TRACK + other.replace('"t1"', '"t2"'))
        self.write_review()
        self.fail_kind('collinear_track_overlap')

    def test_touching_collinear_segments_are_not_overlap(self):
        other = TRACK.replace('(start 0 0)', '(start 2 0)').replace('(end 2 0)', '(end 3 0)')
        self.write_board(TRACK + other.replace('"t1"', '"t2"'))
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_duplicate_via_cannot_be_approved(self):
        self.write_board(vias=VIA + VIA.replace('"v1"', '"v2"'))
        self.write_review()
        self.fail_kind('duplicate_via_location')

    def test_duplicate_via_reversed_layer_order_cannot_be_approved(self):
        other = VIA.replace('"v1"', '"v2"').replace('(layers "F.Cu" "B.Cu")', '(layers "B.Cu" "F.Cu")')
        self.write_board(vias=VIA + other)
        self.write_review()
        self.fail_kind('duplicate_via_location')

    def test_arc_is_not_a_45_degree_track(self):
        self.write_board(extra='(arc (start 0 0) (mid 1 1) (end 2 0) (width 0.25) '
                               '(layer "F.Cu") (net "SIG") (uuid "a1"))')
        self.write_review()
        self.fail_kind('curved_track')

    def test_changed_pcb_invalidates_review(self):
        self.write_board(TRACK.replace('(end 2 0)', '(end 3 0)'))
        self.fail_kind('review_contract')

    def test_one_face_review_is_insufficient(self):
        self.write_review(reviewed_faces=['F.Cu'])
        self.fail_kind('review_contract')

    def test_whole_path_review_is_required(self):
        self.write_review(checks={'parallel_spacing': 'PASS', 'critical_returns': 'PASS'})
        self.fail_kind('review_contract')

    def test_stale_product_version_is_rejected(self):
        self.write_review(product_version='v1.23')
        self.fail_kind('review_contract')

    def exception(self, xy=(5.1, 5)):
        return {'uuid': 'v1', 'xy_mm': list(xy), 'category': 'local_return',
                'electrical_reason': 'C1.2 local interlayer bypass return, verified on both faces'}

    def test_justified_offgrid_via(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        self.write_review(off_grid_vias=[self.exception()])
        self.assertEqual(self.check()['status'], 'PASS')

    def test_missing_offgrid_exception_is_rejected(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        self.write_review()
        self.fail_kind('review_contract')

    def test_exception_coordinate_must_match(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        self.write_review(off_grid_vias=[self.exception((5.2, 5))])
        self.fail_kind('review_contract')

    def test_extra_exception_for_grid_via_is_rejected(self):
        self.write_review(off_grid_vias=[self.exception((5, 5))])
        self.fail_kind('review_contract')

    def test_duplicate_exception_is_rejected(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        self.write_review(off_grid_vias=[self.exception(), self.exception()])
        self.fail_kind('review_contract')

    def test_empty_electrical_reason_is_rejected(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        entry = self.exception(); entry['electrical_reason'] = ' '
        self.write_review(off_grid_vias=[entry])
        self.fail_kind('review_contract')

    def test_short_pad_fanout_is_reported_without_blanket_rejection(self):
        self.write_board(TRACK.replace('(end 2 0)', '(end 0.01 0)'))
        self.write_review()
        result = self.check()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(len(result['boards'][0]['short_segments_below_0_05mm']), 1)

    def test_null_reason_is_not_an_electrical_reason(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        entry = self.exception(); entry['electrical_reason'] = None
        self.write_review(off_grid_vias=[entry])
        self.fail_kind('review_contract')

    def test_whitespace_reviewer_is_rejected(self):
        self.write_review(reviewer='   ')
        self.fail_kind('review_contract')

    def test_nonstring_reviewer_is_rejected(self):
        self.write_review(reviewer={'name': 'somebody'})
        self.fail_kind('review_contract')

    def test_nm_offset_horizontal_duplicate_is_rejected(self):
        other = TRACK.replace('(start 0 0)', '(start 0 0.000001)').replace('(end 2 0)', '(end 2 0.000001)')
        self.write_board(TRACK + other.replace('"t1"', '"t2"'))
        self.write_review()
        self.fail_kind('collinear_track_overlap')

    def test_nm_offset_diagonal_duplicate_is_rejected(self):
        first = TRACK.replace('(end 2 0)', '(end 2 2)')
        other = first.replace('(start 0 0)', '(start 0 0.000001)').replace('(end 2 2)', '(end 2 2.000001)')
        self.write_board(first + other.replace('"t1"', '"t2"'))
        self.write_review()
        self.fail_kind('collinear_track_overlap')

    def test_nm_offset_duplicate_via_is_rejected(self):
        other = VIA.replace('(at 5 5)', '(at 5.000001 5)').replace('"v1"', '"v2"')
        self.write_board(vias=VIA + other)
        self.write_review()
        self.fail_kind('duplicate_via_location')

    def test_nm_rounding_at_common_endpoint_is_not_a_duplicate(self):
        other = TRACK.replace('(start 0 0)', '(start 1.999999 0)').replace('(end 2 0)', '(end 3 0)')
        self.write_board(TRACK + other.replace('"t1"', '"t2"'))
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_invalid_coordinate_returns_fail_instead_of_crashing(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        entry = self.exception(); entry['xy_mm'] = ['not-a-number', 5]
        self.write_review(off_grid_vias=[entry])
        self.fail_kind('routing_gate_input')

    def test_nonfinite_coordinate_is_rejected(self):
        self.write_board(vias=VIA.replace('(at 5 5)', '(at 5.1 5)'))
        entry = self.exception(); entry['xy_mm'] = ['NaN', 5]
        self.write_review(off_grid_vias=[entry])
        self.fail_kind('routing_gate_input')

    def test_explicit_empty_ledger_is_required(self):
        self.write_review()
        path = self.pcb.parent / 'routing_review.json'
        review = json.loads(path.read_text('utf-8')); review.pop('off_grid_vias')
        path.write_text(json.dumps(review), 'utf-8')
        self.fail_kind('review_contract')

    def test_numeric_net_format(self):
        self.write_board(tracks=TRACK.replace('(net "SIG")', '(net 1)'),
                         vias=VIA.replace('(net "GND")', '(net 2)'),
                         extra='(net 1 "SIG") (net 2 "GND")')
        self.write_review()
        result = self.check()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['boards'][0]['ground_vias'], 1)

    def test_ground_track_requires_individual_review(self):
        self.write_board(tracks=TRACK.replace('"SIG"', '"GND"'))
        self.write_review()
        self.fail_kind('review_contract')

    def test_reviewed_ground_track_is_bound_to_geometry(self):
        self.write_board(tracks=TRACK.replace('"SIG"', '"GND"'))
        row = {'uuid':'t1', 'layer':'F.Cu', 'start_mm':[0,0], 'end_mm':[2,0], 'width_mm':0.25,
               'electrical_reason':'Test fixture: one retained local return after native plane inspection'}
        self.write_review(retained_ground_tracks=[row])
        self.assertEqual(self.check()['status'], 'PASS')
        row['end_mm'] = [3,0]
        self.write_review(retained_ground_tracks=[row])
        self.fail_kind('review_contract')

    def test_ground_track_reason_cannot_be_null(self):
        self.write_board(tracks=TRACK.replace('"SIG"', '"GND"'))
        self.write_review(retained_ground_tracks=[{'uuid':'t1', 'layer':'F.Cu', 'start_mm':[0,0],
                          'end_mm':[2,0], 'width_mm':0.25, 'electrical_reason':None}])
        self.fail_kind('review_contract')

    def test_solid_ground_zone_requires_review(self):
        self.write_board(extra='(zone (net "GND") (layer "F.Cu") (uuid "z1") (name "GND_TOP") (connect_pads yes))')
        self.write_review()
        self.fail_kind('review_contract')

    def test_thermal_ground_zone_does_not_need_solid_exception(self):
        self.write_board(extra='(zone (net "GND") (layer "F.Cu") (uuid "z1") (connect_pads (clearance 0.2)))')
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_through_hole_only_zone_has_solid_smd_connections(self):
        self.write_board(extra='(zone (net "GND") (layer "F.Cu") (uuid "z1") (connect_pads thru_hole_only))'
                         '(footprint "X" (property "Reference" "C1") '
                         '(pad "2" smd rect (net "GND") (uuid "p1")))')
        self.write_review()
        self.fail_kind('review_contract')

    def test_through_hole_only_local_pad_mode_is_solid_for_smd(self):
        self.write_board(extra='(footprint "X" (property "Reference" "C1") '
                         '(pad "2" smd rect (net "GND") (uuid "p1") (zone_connect 3)))')
        self.write_review()
        self.fail_kind('review_contract')

    def test_through_hole_only_local_pad_mode_remains_thermal_for_pth(self):
        self.write_board(extra='(footprint "X" (property "Reference" "J1") '
                         '(pad "2" thru_hole circle (net "GND") (uuid "p1") (zone_connect 3)))')
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_solid_ground_pad_and_inherited_footprint_require_review(self):
        for local in ('(zone_connect 2)', ''):
            with self.subTest(local=local):
                self.write_board(extra='(footprint "X" (property "Reference" "C1") (zone_connect 2) '
                                 '(pad "2" smd rect (net "GND") (uuid "p1") '+local+'))')
                self.write_review()
                self.fail_kind('review_contract')

    def test_explicit_pad_thermal_overrides_solid_footprint(self):
        self.write_board(extra='(footprint "X" (property "Reference" "C1") (zone_connect 2) '
                         '(pad "2" smd rect (net "GND") (uuid "p1") (zone_connect 1)))')
        self.write_review()
        self.assertEqual(self.check()['status'], 'PASS')

    def test_mechanical_or_rf_solid_connection_can_be_documented(self):
        self.write_board(extra='(zone (net "GND") (layer "F.Cu") (uuid "z1") (name "RF_CPW") (connect_pads yes))')
        self.write_review(solid_ground_connections=[{'kind':'zone','uuid':'z1','electrical_reason':'RF coplanar reference'}])
        self.assertEqual(self.check()['status'], 'PASS')

    def test_duplicate_solid_exception_is_rejected(self):
        self.write_board(extra='(zone (net "GND") (layer "F.Cu") (uuid "z1") (connect_pads yes))')
        entry={'kind':'zone','uuid':'z1','electrical_reason':'RF reference fixture'}
        self.write_review(solid_ground_connections=[entry,entry])
        self.fail_kind('review_contract')

    def test_new_review_scope_cannot_be_omitted(self):
        for key in ('pad_entries_and_junctions','ground_plane_connections','thermal_reliefs'):
            with self.subTest(key=key):
                self.write_review()
                path=self.pcb.parent/'routing_review.json'
                review=json.loads(path.read_text('utf-8')); review['checks'].pop(key)
                path.write_text(json.dumps(review),'utf-8')
                self.fail_kind('review_contract')


if __name__ == '__main__':
    unittest.main()
