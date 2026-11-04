"""Pure motion geometry and calibration checks on reviewed real grid crops."""
import unittest

from features import engraving_setup_rules as rules
from test_engraving_screen import es, fixtures


class PreviewGeometry(unittest.TestCase):
    def test_unique_complete_preview(self):
        base = [(0, 0), (0, 1), (1, 0)]
        cells = {(2, 2), (2, 3), (3, 2)}
        self.assertEqual(rules.unique_preview_cells(set(), cells, base, 0), tuple(sorted(cells)))

    def test_hidden_cube_with_multiple_fits_is_unknown(self):
        # Either horizontal domino can account for the one new cube.
        self.assertIsNone(rules.unique_preview_cells({(2, 1), (2, 3)}, {(2, 1), (2, 2), (2, 3)},
                                                     [(0, 0), (0, 1)], 0))

    def test_partial_shape_is_unknown(self):
        self.assertIsNone(rules.unique_preview_cells(set(), {(2, 2)},
                                                     [(0, 0), (0, 1), (1, 0)], 0))

    def test_integer_and_half_cell_rotation_pivots(self):
        before = {(1, 1), (1, 2), (2, 1)}
        for pivot in [(1, 1), (1.5, 1.5), (2, 1)]:
            after = {(c - pivot[1] + pivot[0], -(r - pivot[0]) + pivot[1]) for r, c in before}
            self.assertEqual(rules.clockwise_rotation_pivot(before, after), pivot)

    def test_rotation_with_missing_or_wrong_shape_is_unknown(self):
        before = {(1, 1), (1, 2), (2, 1)}
        for after in [set(), {(1, 1)}, {(1, 1), (1, 2), (1, 3)}, before]:
            self.assertIsNone(rules.clockwise_rotation_pivot(before, after))
        self.assertIsNone(rules.clockwise_rotation_pivot(set(), set()))

    def test_drag_measures_response_including_lift(self):
        before = {(2, 1), (2, 2), (3, 1)}
        after = {(2, 2), (2, 3), (3, 2)}
        response = rules.drag_response(before, after, (2, 1), (2.7, 2))
        self.assertEqual(response['piece_delta'], (0, 1))
        self.assertEqual(response['grab'], (0, 0))
        self.assertAlmostEqual(response['residual'][0], -.7)
        self.assertEqual(response['residual'][1], 0)

    def test_response_tracks_grab_and_orientation(self):
        before = {(2, 1), (2, 2), (3, 1)}
        after = {(3, 3), (3, 4), (4, 3)}
        response = rules.drag_response(before, after, (3, 1), (4, 3))
        self.assertEqual(response['grab'], (1, 0))
        self.assertEqual(response['residual'], (0, 0))
        self.assertEqual(response['shape'], ((0, 0), (0, 1), (1, 0)))

    def test_drag_does_not_calibrate_from_rotation_or_partial_cells(self):
        before = {(2, 1), (2, 2), (3, 1)}
        for after in [set(), {(2, 2)}, {(2, 1), (2, 2), (3, 2)}]:
            self.assertIsNone(rules.drag_response(before, after, (2, 1), (3, 2)))

    def test_landing_offset_does_not_assume_touched_cube_tracks_finger(self):
        cells = {(1, 1), (2, 0), (2, 1), (3, 1)}
        response = rules.landing_response(cells, (3.7, 0))
        target = {(r + 1, c + 2) for r, c in cells}
        endpoint = rules.landing_endpoint(target, response)
        self.assertAlmostEqual(endpoint[0], 4.7)
        self.assertEqual(endpoint[1], 2)
        self.assertIsNone(rules.landing_endpoint(target, None))
        self.assertIsNone(rules.landing_response(set(), (0, 0)))
        self.assertIsNone(rules.landing_endpoint({(0, 0), (0, 1), (1, 1), (0, 2)}, response))

    def test_initial_l_aim_matches_measured_one_turn_geometry(self):
        base = [(0, 0), (1, 0), (2, 0), (2, 1)]
        target = [(0, 0), (0, 1), (0, 2), (1, 0)]
        self.assertEqual(rules.initial_placement_cells(base, target, (1, 0)),
                         ((-1, 1), (0, 1), (1, 1), (1, 2)))

    def test_initial_t_aim_aligns_measured_pivot_for_two_turns(self):
        base = [(0, 0), (1, 0), (1, 1), (2, 0)]
        target = [(1, 1), (2, 0), (2, 1), (3, 1)]
        self.assertEqual(rules.initial_placement_cells(base, target, (1, 0)),
                         ((1, 1), (2, 1), (2, 2), (3, 1)))

    def test_initial_aim_requires_calibration_and_matching_shape(self):
        base = [(0, 0), (1, 0), (1, 1), (2, 0)]
        self.assertIsNone(rules.initial_placement_cells(base, base, None))
        self.assertIsNone(rules.initial_placement_cells(base, [(0, 0), (1, 0)], (1, 0)))
        self.assertIsNone(rules.initial_placement_cells(base, [(0, 0), (0, 1), (1, 0), (1, 1)], (1, 0)))

    def test_real_t_rotation_pivot(self):
        # The base preview occupies (0,0),(1,0),(1,1),(2,0) immediately
        # before this reviewed one-tap capture on an otherwise empty grid.
        base = [(0, 0), (1, 0), (1, 1), (2, 0)]
        after = es.cubes(fixtures.screen('eg_relax_preview_t-rotate-1-after'))
        self.assertEqual(rules.clockwise_rotation_pivot(base, after), rules.ROTATION_PIVOTS['T'])

    def test_real_l_drop_and_rotation_pivot_with_placed_t(self):
        base = [(0, 0), (1, 0), (2, 0), (2, 1)]
        under = {(1, 1), (2, 0), (2, 1), (3, 1)}
        after = es.cubes(fixtures.screen('eg_relax_preview_l-rotate-1-after'))
        rotated = rules.unique_preview_cells(under, after, base, 1)
        self.assertEqual(rotated, ((0, 0), (0, 1), (0, 2), (1, 0)))
        for name in ['eg_relax_preview_l-drop-pivot-after', 'eg_relax_preview_l-rotate-1-before']:
            cells = es.cubes(fixtures.screen(name))
            initial = rules.unique_preview_cells(under, cells, base, 0)
            self.assertEqual(initial, ((-1, 1), (0, 1), (1, 1), (1, 2)))
            self.assertEqual(rules.clockwise_rotation_pivot(initial, rotated), (0, 1))
            self.assertEqual(rules.initial_placement_cells(base, rotated, rules.ROTATION_PIVOTS['L']), initial)
            self.assertEqual(rules.landing_response(initial, (1.7, 1))['endpoint_offset'], (2.7, 0))

    def test_unobserved_shape_pivots_stay_unknown(self):
        for shape in ['O', 'J', 'S', 'Z']:
            self.assertIsNone(rules.ROTATION_PIVOTS.get(shape))

    def test_real_l_preview_drag_lands_left_of_inventory_anchor(self):
        # A complete T and two I pieces were already placed. The preview
        # drag repeatedly landed one column left of the requested L cells.
        # Its measured response must be local to this preview gesture, not
        # a global change to the calibrated inventory drop or rotation pivot.
        base = [(0, 0), (1, 0), (2, 0), (2, 1)]
        under = {(1, 1), (2, 0), (2, 1), (3, 1),
                 (1, 2), (2, 2), (3, 2), (4, 2),
                 (1, 3), (2, 3), (3, 3), (4, 3)}
        wrong = fixtures.screen('eg_relax_preview_l-left-after-move')
        right = fixtures.screen('eg_relax_preview_l-target')
        observed = rules.unique_preview_cells(under, es.cubes(wrong), base, 1)
        target = rules.unique_preview_cells(under, es.cubes(right), base, 1)
        self.assertEqual(observed, ((0, -1), (0, 0), (0, 1), (1, -1)))
        self.assertEqual(target, ((0, 0), (0, 1), (0, 2), (1, 0)))
        self.assertFalse(es.bar(wrong)['valid'])
        self.assertTrue(es.bar(right)['valid'])
        endpoint = (1 + es.HOLD_ROWS, 0)
        response = rules.landing_response(observed, endpoint)
        corrected = rules.landing_endpoint(target, response)
        self.assertAlmostEqual(corrected[0], endpoint[0])
        self.assertEqual(corrected[1], 1)

    def test_real_i_rotation_pivot_with_overlap(self):
        under = {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (2, 0), (2, 1), (3, 1)}
        base = [(0, 0), (1, 0), (2, 0), (3, 0)]
        initial = rules.unique_preview_cells(under, es.cubes(fixtures.screen('eg_relax_preview_i-drop-after')),
                                             base, 0)
        rotated = rules.unique_preview_cells(under, es.cubes(fixtures.screen('eg_relax_preview_i-rotate-1-after')),
                                             base, 1)
        self.assertEqual(initial, ((1, 2), (2, 2), (3, 2), (4, 2)))
        self.assertEqual(rotated, ((3, 1), (3, 2), (3, 3), (3, 4)))
        self.assertEqual(rules.clockwise_rotation_pivot(initial, rotated), (3, 2))
        self.assertEqual(rules.initial_placement_cells(base, rotated, rules.ROTATION_PIVOTS['I']), initial)


if __name__ == '__main__':
    unittest.main()
