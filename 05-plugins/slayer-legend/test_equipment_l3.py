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
game = load("features/game")


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


class EquipmentL3(unittest.TestCase):
    def test_real_weapon_and_accessory_counts(self):
        with (HERE / "stages.json").open(encoding="utf-8") as f:
            stages = json.load(f)
        readers = game.reader_table(screens, load("stage"), load("stage_select"), load("gold"),
                                    load("soul_counters"), weapon, load("engraving_screen"),
                                    load("battle_controls"), load("features/screen_rules"), stages,
                                    None, equipment=equipment)
        for tab, field, value in (("weapon", "weapon_l3", 3),
                                  ("accessories", "accessory_l3", 24)):
            capture = shot(tab)
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
        pixels = bytearray(capture[2])
        # Erase the counter while keeping the red frame: it must not
        # turn into a fabricated zero.
        for y in range(817, 837):
            for x in range(150, 215):
                pixels[(y * 480 + x) * 3:(y * 480 + x) * 3 + 3] = b"\x00\x00\x00"
        self.assertIsNone(equipment.read((480, 1040, bytes(pixels))))


if __name__ == "__main__":
    unittest.main()
