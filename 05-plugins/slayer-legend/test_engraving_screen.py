"""The Soul Weapon Engraving screen's readers on crops of one real capture
(fixtures/eg_*: the title and the weapon's name, the 5x5 grid, the 8
cards; never a full screen, nothing with the account's name), pasted back
where they were on an empty 480x1040 screen.
Run: python3 -m unittest test_engraving_screen"""

import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_es_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


es = load("engraving_screen")
sw = load("soul_weapon")
fixtures = load("test_fixtures")
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
NAMES = sw.names_of(TABLE)
VISION = next(entry for entry in TABLE["weapons"] if entry["name"] == "Vision")
# The capture: Vision filled as Gold-balanced (two horizontal bars on top,
# two turned L below), its 8 cards as the game listed them.
LEVELS = [39, 39, 35, 36, 39, 39, 40, 38]
SHAPES = ["I", "L", "I", "I", "L", "L", "I", "L"]
PLACED = [True, False, False, False, True, False, True, True]


def shot():
    return fixtures.screen("eg_title", "eg_grid", "eg_cards")


def blank(screen, box):
    """The screen with a box (pixels) painted black."""
    width, height, pixels = screen
    pixels = bytearray(pixels)
    left, top, right, bottom = box
    for y in range(top, bottom):
        pixels[(y * width + left) * 3:(y * width + right) * 3] = bytes(3 * (right - left))
    return width, height, bytes(pixels)


class Screen(unittest.TestCase):
    def test_title_and_weapon(self):
        self.assertTrue(es.title(shot()))
        self.assertEqual(es.weapon(shot(), NAMES, sw.CARD_FONT), "Vision")

    def test_nothing_on_an_empty_screen(self):
        empty = fixtures.screen("eg_grid")
        self.assertFalse(es.title(empty))
        self.assertIsNone(es.weapon(empty, NAMES, sw.CARD_FONT))
        for card in es.cards(empty, TABLE["shapes"]):
            self.assertIsNone(card["shape"])
            self.assertIsNone(card["level"])
            self.assertIsNone(card["locked"])
            self.assertFalse(card["placed"])

    def test_grid(self):
        grid = es.grid(shot(), 5)
        filled = {cell for cell, state in grid["cells"].items() if state == "piece"}
        self.assertEqual(filled, set(map(tuple, VISION["cells"])))
        self.assertTrue(all(state == "none" for cell, state in grid["cells"].items() if cell not in filled))
        gold = VISION["gold"]["per_piece"]["balanced"][0]["pieces"]
        self.assertEqual(sorted(grid["pieces"]), sorted(sorted(map(tuple, piece["cells"])) for piece in gold))

    def test_a_4x4_grid_is_not_read(self):
        self.assertIsNone(es.grid(shot(), 4))

    def test_cards(self):
        cards = es.cards(shot(), TABLE["shapes"])
        self.assertEqual([card["shape"] for card in cards], SHAPES)
        self.assertEqual([card["level"] for card in cards], LEVELS)
        self.assertEqual([card["placed"] for card in cards], PLACED)
        self.assertEqual([card["locked"] for card in cards], [True] * 8)
        self.assertEqual([card["kind"] for card in cards], [es.KINDS[shape] for shape in SHAPES])

    def test_a_padlock_not_seen_is_not_read_locked(self):
        width, height, _ = shot()
        left, top = es.card_box(2)
        x, y = round(left * width), round(top * height)
        cards = es.cards(blank(shot(), (x + 50, y, x + 69, y + 16)), TABLE["shapes"])
        self.assertIsNone(cards[2]["locked"])
        self.assertTrue(all(card["locked"] for card in cards if card["index"] != 2))

    def test_points_inside_their_card(self):
        for index in range(8):
            left, top = es.card_box(index)
            for x, y in (es.lock_point(index), es.drag_point(index)):
                self.assertTrue(left < x < left + 69 / 480 and top < y < top + 69 / 1040)


if __name__ == "__main__":
    unittest.main()
