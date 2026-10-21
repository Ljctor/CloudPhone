"""The engraving setup's rules: the cards chosen (highest levels), the
locks, the grid against the variant, the drags planned, on the readings of
the real capture (fixtures/eg_*) and on variations of them.
Run: python3 -m unittest test_engraving_setup_rules"""

import copy
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_esr_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/engraving_setup_rules")
engraving_rules = load("features/engraving_rules")
es = load("engraving_screen")
fixtures = load("test_fixtures")
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
VISION = next(entry for entry in TABLE["weapons"] if entry["name"] == "Vision")
VARIANTS = engraving_rules.variants(VISION, engraving_rules.any_orientation(TABLE))
GOLD = VARIANTS["Gold-balanced"]
SHOT = fixtures.screen("eg_title", "eg_grid", "eg_cards")
GRID = es.grid(SHOT, 5)
CARDS = es.cards(SHOT, TABLE["shapes"])


def check(grid=GRID, cards=CARDS, variant=GOLD, name="Gold-balanced"):
    return rules.check(grid, cards, variant, VISION["cells"], "Vision", name)


def with_cards(**changes):
    """The capture's cards, changed: {index: {field: value}}."""
    cards = copy.deepcopy(CARDS)
    for index, fields in changes.items():
        cards[int(index[1:])].update(fields)
    return cards


def emptied(grid, cells):
    grid = copy.deepcopy(grid)
    for cell in cells:
        grid["cells"][tuple(cell)] = "empty"
    gone = {tuple(cell) for cell in cells}
    grid["pieces"] = [piece for piece in grid["pieces"] if not gone & set(map(tuple, piece))]
    return grid


class Choose(unittest.TestCase):
    def test_the_highest_levels_a_placed_one_first_among_equals(self):
        # I: Lv40 (n°7), Lv39 (n°1); L: three Lv39, the placed n°5 first.
        self.assertEqual(rules.choose(CARDS, GOLD), {"I": [6, 0], "L": [4, 1]})

    def test_the_capture_is_not_ready_an_l_38_is_placed_while_an_l_39_is_free(self):
        result = check()
        self.assertFalse(result["ok"])
        self.assertEqual(result["moves"], [])
        self.assertEqual(result["locks"], [])
        text = " ; ".join(result["problems"])
        self.assertIn("L Lv.38 (n°8)", text)
        self.assertIn("retrait pas appris", text)
        self.assertIn("L Lv.39 (n°2)", text)
        self.assertNotIn("pièces posées ne sont pas", text)

    def test_ready_when_the_chosen_cards_are_placed_and_all_locked(self):
        cards = with_cards(c1={"placed": True}, c7={"placed": False})
        self.assertEqual(check(cards=cards), {"ok": True, "problems": [], "chosen": {"I": [6, 0], "L": [1, 4]},
                                              "locks": [], "moves": []})

    def test_the_wrong_variant(self):
        result = check(variant=VARIANTS["Balanced"], name="Balanced")
        self.assertFalse(result["ok"])
        self.assertIn("les pièces posées ne sont pas celles de Balanced", result["problems"])
        self.assertIn("il manque 2 pièce(s) O", result["problems"])


class Locks(unittest.TestCase):
    def test_an_open_padlock_is_tapped(self):
        cards = with_cards(c1={"placed": True}, c7={"placed": False}, c3={"locked": False})
        result = check(cards=cards)
        self.assertFalse(result["ok"])
        self.assertEqual(result["locks"], [3])
        self.assertIn("pas verrouillée(s) : n°4", result["problems"])

    def test_a_padlock_not_read_is_never_tapped(self):
        cards = with_cards(c1={"placed": True}, c7={"placed": False}, c2={"locked": None})
        result = check(cards=cards)
        self.assertFalse(result["ok"])
        self.assertEqual(result["locks"], [])
        self.assertIn("cadenas pas lu fermé : n°3", result["problems"])


class Moves(unittest.TestCase):
    def test_an_unrotated_piece_onto_empty_cells_is_dragged(self):
        # A variant with a vertical bar (rotation 0) where the grid is empty.
        bar = [[1, 2], [2, 2], [3, 2], [4, 2]]
        variant = {"pieces": [{"shape": "I", "rotation": 0, "cells": bar}]}
        grid = {"cells": {cell: ("empty" if list(cell) in bar else "none") for cell in GRID["cells"]},
                "pieces": []}
        cards = with_cards(c0={"placed": False}, c4={"placed": False}, c6={"placed": False},
                           c7={"placed": False})
        result = rules.check(grid, cards, variant, bar, "Test", "Bar")
        self.assertEqual(result["moves"], [{"card": 6, "cells": [tuple(c) for c in bar], "rotation": 0}])
        self.assertFalse(result["ok"])

    def test_a_turned_piece_is_not_dragged(self):
        top = GOLD["pieces"][0]["cells"]
        cards = with_cards(c0={"placed": False}, c1={"placed": True}, c7={"placed": False})
        result = check(grid=emptied(GRID, top), cards=cards)
        self.assertEqual(result["moves"], [])
        self.assertTrue(any("rotation pas apprise" in p for p in result["problems"]))

    def test_nothing_is_planned_on_unread_cards(self):
        cards = with_cards(c5={"shape": None})
        result = check(grid=emptied(GRID, GOLD["pieces"][0]["cells"]), cards=cards)
        self.assertEqual(result["moves"], [])
        self.assertIn("pièce(s) illisible(s) : n°6", result["problems"])

    def test_an_unreadable_grid(self):
        self.assertEqual(check(grid=None)["problems"], ["grille illisible"])

    def test_dragged(self):
        bar = [(0, 1), (0, 2), (0, 3), (0, 4)]
        before = {"grid": emptied(GRID, bar), "cards": with_cards(c0={"placed": False})}
        after = {"grid": GRID, "cards": CARDS}
        move = {"card": 0, "cells": bar, "rotation": 1}
        self.assertTrue(rules.dragged(before, after, move))
        self.assertFalse(rules.dragged(before, before, move))
        self.assertFalse(rules.dragged(before, {"grid": GRID, "cards": before["cards"]}, move))

    def test_drop_point(self):
        x, y = rules.drop_point([(0, 1), (1, 1), (2, 1), (3, 1)], es.cell_centre)
        self.assertAlmostEqual(x, es.cell_centre(0, 1)[0])
        self.assertAlmostEqual(y, (es.cell_centre(0, 1)[1] + es.cell_centre(3, 1)[1]) / 2)

    def test_the_alert(self):
        self.assertEqual(rules.alert("Vision", "Gold-balanced", ["a", "b"]),
                         "Gravure de Vision (Gold-balanced) pas prête : a ; b")


if __name__ == "__main__":
    unittest.main()
