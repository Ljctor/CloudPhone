"""Legendary Grade 3 balances on reviewed crops of real Equipment captures."""

import importlib.util
import json
import unittest
from unittest.mock import patch
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("/", "_"), HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screens = load("screens")
weapon = load("soul_weapon")
equipment = load("equipment_l3")
rules = load("features/game_rules")
game = load("features/game_readers")
model_fixtures = load("test_screen_model")


def shot(tab, include_row=True):
    pixels = bytearray(bytes((20, 16, 14)) * (480 * 1040))
    names = [f"equipment_l3_{tab}_tabs"]
    if include_row:
        names.append(f"equipment_l3_{tab}_row")
    for name in names:
        _, _, x, y, width, height, data = screens.fixture(name)
        for row in range(height):
            start = ((y + row) * 480 + x) * 3
            pixels[start:start + width * 3] = data[row * width * 3:(row + 1) * width * 3]
    return 480, 1040, bytes(pixels)


def scaled_720(capture):
    """Geometry check from the real 480 crop; this is not a native 720 capture."""
    _, _, source = capture
    pixels = bytearray(720 * 1560 * 3)
    for y in range(1560):
        source_row = (2 * y // 3) * 480 * 3
        target_row = y * 720 * 3
        for x in range(720):
            start = target_row + x * 3
            from_x = source_row + (2 * x // 3) * 3
            pixels[start:start + 3] = source[from_x:from_x + 3]
    return 720, 1560, bytes(pixels)


class EquipmentL3(unittest.TestCase):
    def test_card_visibility_uses_calibrated_geometry_without_requiring_readable_numbers(self):
        for tab in ('weapon', 'accessories'):
            original = shot(tab)
            for capture in (original, scaled_720(original)):
                self.assertTrue(equipment.card_visible(capture))
            width, height, pixels = original
            top = equipment._card_top(original, 1)
            damaged = bytearray(pixels)
            for y in range(top + 85, top + 105):
                for x in range(146, 222):
                    offset = (y * width + x) * 3
                    damaged[offset:offset + 3] = bytes(3)
            unread = (width, height, bytes(damaged))
            self.assertTrue(equipment.card_visible(unread), 'OCR failure is not permission to scroll past the card')
            self.assertIsNone(equipment.read(unread))
        for fixture in ('equipment_l3_weapon_phase_480', 'equipment_l3_weapon_threshold_480',
                        'equipment_l3_accessories_sixty_480', 'equipment_l3_accessories_sixtytwo_480',
                        'equipment_l3_accessories_sixtynine_480'):
            self.assertTrue(equipment.card_visible(model_fixtures.screen(fixture)))

    def test_clipped_missing_or_foreign_cards_are_not_visible(self):
        self.assertFalse(equipment.card_visible(shot('weapon', include_row=False)))
        self.assertFalse(equipment.card_visible((960, 2080, bytes(960 * 2080 * 3))))
        self.assertFalse(equipment.card_visible((480, 1040, b'incomplete capture')))
        for names in (
            ('battle_emerald', 'equipment_l3_accessories_tabs', 'equipment_orange_grade3_480'),
            ('battle_emerald', 'weapon_detail_tabs_720', 'weapon_detail_close_720'),
            ('battle_emerald', 'growth_at_equipment_tabs_720'),
        ):
            self.assertFalse(equipment.card_visible(model_fixtures.screen(*names)))
        # Translate a real red card below the calibrated visible-list limit.
        capture = shot('weapon')
        top = equipment._card_top(capture, 1)
        pixels = bytearray(480 * 1040 * 3)
        for row in range(106):
            start = ((top + row) * 480 + 146) * 3
            destination = ((820 + row) * 480 + 146) * 3
            pixels[destination:destination + 76 * 3] = capture[2][start:start + 76 * 3]
        clipped = (480, 1040, bytes(pixels))
        self.assertIsNotNone(equipment._card_top(clipped, 1))
        self.assertFalse(equipment.card_visible(clipped))

    def test_corrupted_known_digit_is_not_a_guessed_balance(self):
        capture = shot("weapon")
        top = equipment._card_top(capture, 1)
        width, height, data = capture
        pixels = bytearray(data)
        xs = [x for x in range(150, 215) if any(min(equipment._pixel(capture, x, y)) > 130
                                               for y in range(top + 85, top + 105))]
        left = min(xs)
        right = next(x for x in range(left, 215) if x not in xs)
        ys = [y for y in range(top + 85, top + 105) if any(min(equipment._pixel(capture, x, y)) > 130
                                                       for x in range(left, right))]
        points = [(x, y) for y in range(min(ys) + 1, max(ys)) for x in range(left, right)
                  if min(equipment._pixel(capture, x, y)) > 130]
        for x, y in points[:3]:
            i = (y * width + x) * 3
            pixels[i:i + 3] = b"\0\0\0"
        self.assertIsNone(equipment.read((width, height, bytes(pixels))))

    def test_real_weapon_and_accessory_counts(self):
        with (HERE / "stages.json").open(encoding="utf-8") as f:
            stages = json.load(f)
        readers = game.reader_table(screens, load("stage"), load("stage_select"), load("gold"),
                                    load("soul_counters"), weapon, load("engraving_screen"),
                                    load("battle_controls"), load("features/screen_rules"), stages,
                                    None, equipment=equipment)
        for tab, field, value in (("weapon", "weapon_l3", 3),
                                  ("accessories", "accessory_l3", 24)):
            for capture in (shot(tab), scaled_720(shot(tab))):
                self.assertEqual(weapon.tab(capture), tab)
                self.assertEqual(equipment.read(capture), value)
                self.assertEqual(readers["equipment_l3"](capture, "battle", {"equipment_weapon"}, False),
                                 {field: value})
            facts, _ = rules.noted({}, {field: value}, 1000.0)
            group = next(row for row in rules.answer(facts)["screens"]
                         if row["screen"] == "equipment_" + ("weapon" if tab == "weapon" else "accessories"))
            self.assertEqual(group["fields"][0]["value"], value)

    def test_real_settled_native_480_phases_and_new_six_are_read_exactly(self):
        for tab, fixture, expected in (
            ("weapon", "equipment_l3_weapon_phase_480", 3),
            ("accessories", "equipment_l3_accessories_sixty_480", 60),
            ("accessories", "equipment_l3_accessories_sixtytwo_480", 62),
            ("accessories", "equipment_l3_accessories_sixtynine_480", 69),
        ):
            with self.subTest(tab=tab):
                capture = model_fixtures.screen("battle_emerald", f"equipment_l3_{tab}_tabs", fixture)
                self.assertEqual(equipment.read(capture), expected)
                _, _, x, y, w, h, data = screens.fixture(fixture)
                width, height, pixels = capture
                damaged = bytearray(pixels)
                # Erasing the count cannot become zero or another balance.
                for row in range(y + 85, y + 105):
                    start = (row * width + x) * 3
                    damaged[start:start + w * 3] = bytes(w * 3)
                self.assertIsNone(equipment.read((width, height, bytes(damaged))))
        self.assertEqual(set(equipment.FONT_DERIVED_PHASES), set("789"))

    def test_source_font_derived_seven_eight_nine_read_with_real_card_geometry(self):
        # This is an explicitly generated font replay, not a claim that an
        # inventory balance containing 7–9 was observed on the real phone.
        # The surrounding frame comes from the existing reviewed real crop.
        original = shot("weapon")
        top = equipment._card_top(original, 1)
        for number in ('0', '7', '8', '9', '789', '9876'):
            with self.subTest(number=number):
                width, height, data = original
                pixels = bytearray(data)
                for y in range(top + 85, top + 105):
                    start = (y * width + 150) * 3
                    pixels[start:start + 65 * 3] = bytes(65 * 3)
                left = 153
                for char in number + '/5':
                    shape = equipment.SHAPES[char]
                    for y, row in enumerate(shape):
                        for x, on in enumerate(row):
                            if on == '#':
                                offset = ((top + 88 + y) * width + left + x) * 3
                                pixels[offset:offset + 3] = b'\xff\xff\xff'
                    left += len(shape[0]) + 2
                self.assertEqual(equipment.read((width, height, bytes(pixels))), int(number))
        # All derived raster phases remain distinct from another character
        # under the existing confidence gap; no threshold is relaxed.
        self.assertEqual(equipment.MAX_DISTANCE, .06)
        for char, phases in equipment.FONT_DERIVED_PHASES.items():
            for phase in phases:
                scores = sorted((min(equipment._distance(phase, item)
                                     for item in (shape,) + equipment.PHASES.get(other, ())), other)
                                for other, shape in equipment.SHAPES.items())
                self.assertEqual(scores[0], (0, char))
                self.assertGreaterEqual(scores[1][0] - scores[0][0], .06)

    def test_real_stationary_card_threshold_jitter_reads_without_relaxing_glyph_errors(self):
        capture = model_fixtures.screen("battle_emerald", "equipment_l3_weapon_tabs", "equipment_l3_weapon_threshold_480")
        self.assertEqual(equipment.MAX_DISTANCE, .06)
        self.assertEqual(equipment.read(capture), 3)
        # The original single threshold rejects this real stationary frame.
        top = equipment._card_top(capture, 1)
        glyph = next(equipment._glyphs(capture, top, 1, 130))
        error = min(equipment._distance(glyph, item) for item in (equipment.SHAPES['3'],) + equipment.PHASES['3'])
        self.assertGreater(error, equipment.MAX_DISTANCE)

    def test_leading_zero_and_overlong_counts_are_not_balances(self):
        capture = shot("weapon")
        for text in ('00/5', '03/5', '0789/5', '10000/5'):
            with self.subTest(text=text), patch.object(
                    equipment, '_glyphs', return_value=[equipment.SHAPES[c] for c in text]):
                self.assertIsNone(equipment.read(capture))

    def test_one_lone_threshold_or_disagreeing_complete_counts_are_uncertain(self):
        capture = shot("weapon")
        three = [equipment.SHAPES[c] for c in '3/5']
        five = [equipment.SHAPES[c] for c in '5/5']
        with patch.object(equipment, '_glyphs', side_effect=lambda sh, top, scale, threshold:
                          iter(three if threshold == 130 else [])):
            self.assertIsNone(equipment.read(capture))
        with patch.object(equipment, '_glyphs', side_effect=lambda sh, top, scale, threshold:
                          iter(five if threshold == 170 else three)):
            self.assertIsNone(equipment.read(capture))

    def test_real_orange_grade3_card_cannot_be_mistaken_for_legendary(self):
        capture = model_fixtures.screen("battle_emerald", "equipment_l3_accessories_tabs", "equipment_orange_grade3_480")
        self.assertIsNone(equipment._card_top(capture, 1), "an orange rarity frame is not a red Legendary frame")
        self.assertIsNone(equipment.read(capture))
        larger = scaled_720(capture)
        self.assertIsNone(equipment._card_top(larger, 1.5))
        self.assertIsNone(equipment.read(larger))

    def test_unseen_or_unreadable_card_does_not_report_a_balance(self):
        self.assertIsNone(equipment.read(shot("weapon", include_row=False)))
        capture = shot("weapon")
        self.assertIsNone(equipment.read((960, 2080, capture[2])))
        self.assertIsNone(equipment.read(scaled_720(shot("weapon", include_row=False))))
        pixels = bytearray(capture[2])
        # Erase the counter while keeping the red frame: it must not
        # turn into a fabricated zero.
        for y in range(817, 837):
            for x in range(150, 215):
                pixels[(y * 480 + x) * 3:(y * 480 + x) * 3 + 3] = b"\x00\x00\x00"
        self.assertIsNone(equipment.read((480, 1040, bytes(pixels))))


class EquipmentSafety(unittest.TestCase):
    def test_inspect_requires_selected_weapon_and_the_complete_proven_card(self):
        before = model_fixtures.screen("battle_emerald", "equipment_weapon_tabs_720", "equipment_inspect_card_720")
        self.assertTrue(equipment.inspect_weapon_safe(before))
        width, height, rgb = before
        moved = bytearray(rgb)
        for y in range(745, 876):
            start = (y * width + 51) * 3
            moved[start:start + 118 * 3] = bytes(118 * 3)
        self.assertFalse(equipment.inspect_weapon_safe((width, height, bytes(moved))))
        detail = model_fixtures.screen("battle_emerald", "weapon_detail_tabs_720", "weapon_detail_close_720")
        self.assertFalse(equipment.inspect_weapon_safe(detail))
        self.assertFalse(equipment.scroll_safe(detail, "weapon"))
        growth = model_fixtures.screen("battle_emerald", "growth_at_equipment_tabs_720")
        self.assertFalse(equipment.inspect_weapon_safe(growth))
        self.assertFalse(equipment.scroll_safe(growth, "weapon"))

    def test_native_480_complete_first_card_is_calibrated_without_accepting_shifted_list(self):
        before = model_fixtures.screen("battle_emerald", "equipment_l3_weapon_tabs", "equipment_inspect_card_480")
        self.assertEqual(before[:2], (480, 1040))
        self.assertTrue(equipment.inspect_weapon_safe(before))
        width, height, rgb = before
        for offset in (-20, 20):
            moved = bytearray(rgb)
            _, _, x, y, w, h, card = screens.fixture("equipment_inspect_card_480")
            for row in range(h):
                start = ((y + row) * width + x) * 3
                moved[start:start + w * 3] = bytes(w * 3)
            for row in range(h):
                start = ((y + row + offset) * width + x) * 3
                moved[start:start + w * 3] = card[row * w * 3:(row + 1) * w * 3]
            self.assertFalse(equipment.inspect_weapon_safe((width, height, bytes(moved))),
                             "a shifted first row cannot authorize the fixed inspect point")
        accessories = model_fixtures.screen("battle_emerald", "equipment_l3_accessories_tabs", "equipment_inspect_card_480")
        self.assertFalse(equipment.inspect_weapon_safe(accessories))

    def test_real_weapon_and_accessories_clear_gaps_before_and_after_scroll(self):
        captures = [
            ("weapon", "equipment_l3_weapon_tabs", "equipment_gap_weapon_first"),
            ("weapon", "equipment_l3_weapon_tabs", "equipment_gap_weapon_scrolled"),
            ("accessories", "equipment_l3_accessories_tabs", "equipment_gap_accessories_first"),
            ("accessories", "equipment_l3_accessories_tabs", "equipment_gap_accessories_scrolled"),
        ]
        for tab, tabs, gap in captures:
            with self.subTest(tab=tab, gap=gap):
                capture = model_fixtures.screen("battle_emerald", tabs, gap)
                self.assertTrue(equipment.scroll_safe(capture, tab))
                other = "accessories" if tab == "weapon" else "weapon"
                self.assertFalse(equipment.scroll_safe(capture, other))
                width, height, rgb = capture
                pixels = bytearray(rgb)
                x, y = round(.27 * width), round(.68 * height)
                i = (y * width + x) * 3
                pixels[i:i + 3] = bytes([255, 255, 255])
                self.assertFalse(equipment.scroll_safe((width, height, bytes(pixels)), tab),
                                 'an unexpected control crossing the drag path closes the gate')


if __name__ == "__main__":
    unittest.main()
