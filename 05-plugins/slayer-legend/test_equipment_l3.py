"""Legendary Grade 3 balances on reviewed crops of real Equipment captures."""

import importlib.util
import json
import unittest
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
