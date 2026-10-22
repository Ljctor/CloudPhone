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


# Captures of 2026-10-22 (Vision): eg6 a piece just dragged out (its card
# bright, padlock open), eg10 all locked again; eg2 and eg3 the piece popup
# locked then unlocked; eg7, eg8, eg9 a preview (as dropped, turned,
# moved).
class Padlocks(unittest.TestCase):
    def test_a_card_unlocked_by_its_removal(self):
        cards = es.cards(fixtures.screen("eg_cards_unlocked"), TABLE["shapes"])
        self.assertEqual([c["locked"] for c in cards], [True, False] + [True] * 6)
        self.assertEqual([c["bright"] for c in cards], [False, True] + [False] * 6)
        self.assertFalse(cards[1]["placed"])
        # A bright card's drawing is not read (not calibrated).
        self.assertIsNone(cards[1]["shape"])
        self.assertEqual(cards[0]["shape"], "I")

    def test_all_locked_again(self):
        cards = es.cards(fixtures.screen("eg_cards_relocked"), TABLE["shapes"])
        self.assertEqual([c["locked"] for c in cards], [True] * 8)
        self.assertEqual([c["placed"] for c in cards], [False, True, False, False, True, True, False, True])
        self.assertEqual([c["level"] for c in cards], LEVELS)

    def test_the_popup(self):
        locked, unlocked = fixtures.screen("eg_popup_locked"), fixtures.screen("eg_popup_unlocked")
        self.assertTrue(es.popup(locked) and es.popup(unlocked))
        self.assertEqual(es.popup_padlock(locked), "closed")
        self.assertEqual(es.popup_padlock(unlocked), "open")
        self.assertTrue(es.popup_gold(locked))
        # Nothing of the cards is read under it.
        self.assertTrue(all(c["locked"] is None for c in es.cards(unlocked, TABLE["shapes"])))
        for other in (fixtures.screen("eg_cards_relocked"), shot(), fixtures.screen("eg_preview_valid")):
            self.assertFalse(es.popup(other))
            self.assertIsNone(es.popup_padlock(other))


class Preview(unittest.TestCase):
    def test_as_dropped_invalid(self):
        screen = fixtures.screen("eg_preview_base")
        found = es.bar(screen)
        self.assertFalse(found["valid"])
        self.assertAlmostEqual(found["cancel"][0], 0.348, places=2)
        self.assertAlmostEqual(found["confirm"][0] - found["rotate"][0], found["rotate"][0] - found["cancel"][0])
        before = es.cubes(fixtures.screen("eg_grid_removed"))
        new = sorted(cell for cell in es.cubes(screen) if cell not in before)
        # The L in its card orientation, one cube above the grid, its foot
        # over a placed cube (hidden).
        self.assertEqual(new, [(-1, 1), (0, 1), (1, 1)])

    def test_turned(self):
        screen = fixtures.screen("eg_preview_turned")
        self.assertFalse(es.bar(screen)["valid"])
        before = es.cubes(fixtures.screen("eg_grid_removed"))
        found = es.cubes(screen)
        self.assertEqual(sorted(cell for cell in found if cell not in before), [(0, 0), (0, 1), (0, 2), (1, 0)])
        self.assertEqual(sorted(cell for cell, kind in found.items() if kind == "red"), [(0, 0), (1, 0)])

    def test_moved_valid(self):
        screen = fixtures.screen("eg_preview_valid")
        found = es.bar(screen)
        self.assertTrue(found["valid"])
        before = es.cubes(fixtures.screen("eg_grid_removed"))
        self.assertEqual(sorted(cell for cell in es.cubes(screen) if cell not in before),
                         [(0, 1), (0, 2), (0, 3), (1, 1)])

    def test_no_bar_without_a_preview(self):
        for name in ("eg_grid_removed", "eg_grid_atk", "eg_popup_locked", "eg_cards_relocked"):
            self.assertIsNone(es.bar(fixtures.screen(name)))

    def test_the_grid_before_and_after(self):
        atk = es.grid(fixtures.screen("eg_grid_atk"), 5)
        self.assertEqual(sorted(atk["pieces"]), [[(0, 1), (0, 2), (0, 3), (1, 1)], [(0, 4), (1, 2), (1, 3), (1, 4)],
                                                 [(2, 2), (2, 3), (2, 4), (3, 2)], [(3, 3), (4, 1), (4, 2), (4, 3)]])
        removed = es.grid(fixtures.screen("eg_grid_removed"), 5)
        self.assertEqual([removed["cells"][cell] for cell in [(0, 1), (0, 2), (0, 3), (1, 1)]], ["empty"] * 4)
        self.assertEqual(len(removed["pieces"]), 3)

    def test_hold_point(self):
        # eg7: dropped at (0.44, 0.30), the L's cells rows -1 to 1, cols 1-2.
        x, y = es.hold_point([(-1, 1), (0, 1), (1, 1), (1, 2)])
        self.assertAlmostEqual(x, 0.44, places=2)
        self.assertAlmostEqual(y, 0.30, places=2)


if __name__ == "__main__":
    unittest.main()
