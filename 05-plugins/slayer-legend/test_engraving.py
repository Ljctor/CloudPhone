"""engravings.json is well formed: its variants fill their patterns, its
gold layouts and tileable flags hold; the engraving rules turn, pack, count
and check right, the same way every time.
Run: python3 -m unittest test_engraving"""

import asyncio
import contextlib
import importlib.util
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("engraving_test_texts", os.path.join(HERE, "features", "texts.py"))
texts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(texts)
french = texts.french


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/engraving_rules")
TABLE = rules.load()
SHAPES = {name: shape["cells"] for name, shape in TABLE["shapes"].items()}
SOURCES = {"user-sheet", "none"}
CHECKS = {"screenshots-agree", "screenshots-differ", "community-agrees", "community-differs", "none"}
FULL4 = [[r, c] for r in range(4) for c in range(4)]
FULL5 = [[r, c] for r in range(5) for c in range(5)]
# Ambition as seen on the engraving screen: col 1 rows 0-3, cols 2-4 rows 1-4.
AMBITION = sorted([[r, 1] for r in range(4)] + [[r, c] for r in range(1, 5) for c in range(2, 5)])


def prefer(entry):
    """The shapes of the weapon's sheet Balanced variant, which
    Gold-balanced's fill comes closest to."""
    balanced = [v for v in entry["variants"] if v["name"] == "Balanced"]
    return rules.needed(balanced[0]) if balanced else {}


def engraved():
    return [entry for entry in TABLE["weapons"] if entry["grid"]]


class Data(unittest.TestCase):
    def test_header(self):
        self.assertEqual(TABLE["format"], 1)
        self.assertEqual(TABLE["source"]["url"], "https://github.com/BenDol/SlayerLegendWiki")
        self.assertIn(TABLE["rotation"], (None, True, False, rules.PER_PIECE))
        self.assertIs(TABLE["mirror"], False)
        self.assertEqual(TABLE["inventory_slots"], 8)

    def test_shapes(self):
        self.assertEqual(sorted(SHAPES), sorted("LJTOISZ"))
        for name, cells in SHAPES.items():
            self.assertEqual(len(cells), 4, name)
            self.assertEqual(cells, rules.normal(cells), name)

    def test_ids_and_names(self):
        weapons = TABLE["weapons"]
        self.assertEqual([entry["id"] for entry in weapons], list(range(1, 90)))
        names = [rules.fold(entry["name"]) for entry in weapons]
        names += [rules.fold(alias) for entry in weapons for alias in entry.get("aliases", [])]
        # The sheet names the 1840 weapon Silence, like the 460 one.
        self.assertEqual({name for name in names if names.count(name) > 1}, {"silence"})

    def test_entries(self):
        for entry in TABLE["weapons"]:
            with self.subTest(entry["name"]):
                self.assertIn(entry["source"], SOURCES)
                self.assertIs(entry["verified_in_game"], False)
                # Every weapon has one: the wiki's, else the green, blue,
                # red cycle by id (colour_deduced).
                self.assertEqual(entry["colour"], ("red", "green", "blue")[entry["id"] % 3])
                self.assertIn(entry["wiki_check"], CHECKS)
                if entry["id"] <= 12:
                    self.assertEqual(entry["wiki_check"], "none")
                    self.assertIsNone(entry["grid"])
                    self.assertIsNone(entry["cells"])
                    self.assertEqual(entry["source"], "none")
                    continue
                self.assertEqual(entry["source"], "user-sheet")
                self.assertEqual(entry["stage"], 320 + 20 * (entry["id"] - 13))
                self.assertIn(entry["grid"], (4, 5))
                self.assertIn(entry["wiki_check"], CHECKS)
                if entry["completion"] is not None:
                    self.assertGreater(entry["completion"]["atk"], 0)
                    self.assertGreater(entry["completion"]["hp"], 0)
                cells = [tuple(cell) for cell in entry["cells"]]
                self.assertEqual(cells, sorted(set(cells)))
                for row, col in cells:
                    self.assertTrue(0 <= row < entry["grid"] and 0 <= col < entry["grid"], (row, col))
                self.assertIsInstance(entry["tileable_with_rotation"], bool)
                self.assertIsInstance(entry["tileable_without"], bool)

    def test_variants_fill_their_pattern(self):
        for entry in engraved():
            names = [variant["name"] for variant in entry["variants"]]
            self.assertTrue(names)
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(set(names) <= {"Atk", "Balanced", "Crit"})
            for variant in entry["variants"]:
                with self.subTest(entry["name"], variant=variant["name"]):
                    self.assertIs(variant["ambiguous"], False)
                    for piece in variant["pieces"]:
                        self.assertEqual(rules.identify(piece["cells"], SHAPES), (piece["shape"], piece["rotation"]))
                    colours = [piece["colour"] for piece in variant["pieces"]]
                    self.assertEqual(len(colours), len(set(colours)))
                    self.assertTrue(rules.check(entry["cells"], [p["cells"] for p in variant["pieces"]])["complete"])

    def test_gold_layouts(self):
        for entry in engraved():
            for rotate, key in ((True, "with_rotation"), (False, "without_rotation")):
                with self.subTest(entry["name"], rotate=rotate):
                    layout = dict(entry["gold"][key])
                    balanced = layout.pop("balanced")
                    self.assertEqual(layout, rules.gold(entry["cells"], rotate))
                    self.assertEqual(balanced, rules.gold_balanced(entry["cells"], SHAPES, prefer(entry), rotate))
                    # Absent exactly when no complete filling exists.
                    self.assertEqual(balanced is not None,
                                     entry["tileable_with_rotation" if rotate else "tileable_without"])
                    if balanced:
                        self.assertEqual(balanced["max"], layout["count"])
                        self.assertLessEqual(balanced["bars"], layout["count"])
                        self.assertTrue(rules.check(entry["cells"], [p["cells"] for p in balanced["pieces"]])
                                        ["complete"])
                        for piece in balanced["pieces"]:
                            self.assertEqual(rules.identify(piece["cells"], SHAPES),
                                             (piece["shape"], piece["rotation"]))
                            if not rotate:
                                self.assertEqual(piece["rotation"], 0)
                        self.assertGreaterEqual(rules.needed(balanced).get("I", 0), balanced["bars"])
                    self.assertEqual(layout["count"], len(layout["bars"]))
                    result = rules.check(entry["cells"], layout["bars"])
                    self.assertEqual(result["outside"] + result["overlap"], [])
                    for bar in layout["bars"]:
                        self.assertEqual(rules.identify(bar, SHAPES)[0], "I")
                        if not rotate:
                            self.assertEqual(rules.identify(bar, SHAPES), ("I", 0))

    def test_per_piece_layouts(self):
        for entry in engraved():
            with self.subTest(entry["name"]):
                kept = entry["gold"]["per_piece"]
                self.assertEqual(kept["frontier"], rules.gold_frontier(entry["cells"]))
                counts = [(f["vertical"], f["horizontal"]) for f in kept["frontier"]]
                self.assertEqual(max(v + h for v, h in counts), entry["gold"]["with_rotation"]["count"])
                self.assertEqual(max(v for v, h in counts), entry["gold"]["without_rotation"]["count"])
                for layout in kept["frontier"]:
                    result = rules.check(entry["cells"], layout["bars"])
                    self.assertEqual(result["outside"] + result["overlap"], [])
                    turns = [rules.identify(bar, SHAPES) for bar in layout["bars"]]
                    self.assertEqual(sorted(turns), [("I", 0)] * layout["vertical"] + [("I", 1)] * layout["horizontal"])
                fillings = []
                for bars in ((0, 1), (0,), (1,)):
                    filling = rules.gold_balanced(entry["cells"], SHAPES, prefer(entry), True, bars)
                    if filling and filling not in fillings:
                        fillings.append(filling)
                self.assertEqual(kept["balanced"], sorted(fillings, key=lambda f: -f["bars"]))
                self.assertEqual(kept["balanced"][0], entry["gold"]["with_rotation"]["balanced"])
                for filling in kept["balanced"]:
                    self.assertTrue(rules.check(entry["cells"], [p["cells"] for p in filling["pieces"]])["complete"])

    def test_tileable_flags(self):
        shapes = list(SHAPES.values())
        for entry in engraved():
            for rotate, flag in ((True, "tileable_with_rotation"), (False, "tileable_without")):
                with self.subTest(entry["name"], rotate=rotate):
                    moves = rules.tiling(entry["cells"], shapes, rotate)
                    self.assertEqual(moves is not None, entry[flag])

    def test_ambition_as_seen(self):
        entry = rules.pattern_for("Ambition", TABLE)
        self.assertEqual(entry["cells"], AMBITION)
        self.assertEqual(entry["gold"]["with_rotation"]["count"], 4)
        # In game: 4 I bars fill it, and only vertical ones fit four.
        self.assertIn("count matches in game", entry["note"])
        self.assertFalse(entry["verified_in_game"])
        self.assertEqual([(f["vertical"], f["horizontal"]) for f in entry["gold"]["per_piece"]["frontier"]],
                         [(4, 0), (0, 3)])


class Rotations(unittest.TestCase):
    def test_counts(self):
        distinct = {name: len({tuple(map(tuple, turn)) for turn in rules.rotations(cells)})
                    for name, cells in SHAPES.items()}
        self.assertEqual(distinct, {"L": 4, "J": 4, "T": 4, "O": 1, "I": 2, "S": 2, "Z": 2})

    def test_quarter_turn_clockwise(self):
        # L (#. / #. / ##) turned clockwise is ### / #..
        self.assertEqual(rules.rotations(SHAPES["L"])[1], [[0, 0], [0, 1], [0, 2], [1, 0]])
        self.assertEqual(rules.rotations(SHAPES["I"])[1], [[0, 0], [0, 1], [0, 2], [0, 3]])

    def test_four_turns(self):
        for name, cells in SHAPES.items():
            turns = rules.rotations(cells)
            self.assertEqual(turns[0], cells)
            self.assertEqual(rules.rotations(turns[3])[1], cells, name)

    def test_no_mirror(self):
        for one, other in (("L", "J"), ("S", "Z")):
            self.assertFalse({tuple(map(tuple, t)) for t in rules.rotations(SHAPES[one])}
                             & {tuple(map(tuple, t)) for t in rules.rotations(SHAPES[other])})

    def test_placed_and_identify(self):
        self.assertEqual(rules.placed(SHAPES["O"], 0, [2, 3]), [[2, 3], [2, 4], [3, 3], [3, 4]])
        self.assertEqual(rules.identify(rules.placed(SHAPES["T"], 2, [1, 1]), SHAPES), ("T", 2))
        self.assertIsNone(rules.identify([[0, 0], [1, 1]], SHAPES))


class Gold(unittest.TestCase):
    def test_full_grids(self):
        self.assertEqual(rules.gold(FULL5)["count"], 6)
        self.assertEqual(rules.gold(FULL5, rotate=False)["count"], 5)
        self.assertEqual(rules.gold(FULL4)["count"], 4)
        self.assertEqual(rules.gold(FULL4, rotate=False)["count"], 4)

    def test_orientation_matters(self):
        two_rows = [[r, c] for r in range(2) for c in range(4)]
        self.assertEqual(rules.gold(two_rows)["count"], 2)
        self.assertEqual(rules.gold(two_rows, rotate=False), {"count": 0, "bars": []})

    def test_small_grids(self):
        # A plus of 5x5 arms: one bar fits along each arm, but they cross.
        plus = sorted([[2, c] for c in range(5)] + [[r, 2] for r in range(5) if r != 2])
        self.assertEqual(rules.gold(plus)["count"], 1)
        self.assertEqual(rules.gold([[0, 0], [0, 1], [0, 2]])["count"], 0)
        self.assertEqual(rules.gold(AMBITION, rotate=False)["count"], 4)

    def test_tie_break(self):
        # Full 4x4: four rows or four columns; the rows come first in
        # lexicographic order ([0, 1] < [1, 0]).
        self.assertEqual(rules.gold(FULL4)["bars"], [[[r, c] for c in range(4)] for r in range(4)])
        self.assertEqual(rules.gold(FULL4, rotate=False)["bars"], [[[r, c] for r in range(4)] for c in range(4)])
        self.assertEqual(rules.gold(list(reversed(FULL5))), rules.gold(FULL5))

    def test_balanced_small(self):
        # Full 4x4: four bars and nothing else to fill.
        self.assertEqual(rules.gold_balanced(FULL4, SHAPES, {})["bars"], 4)
        # A bar over a 2x2 block: one bar, a square under it.
        cells = [[0, 0], [0, 1], [0, 2], [0, 3], [1, 0], [1, 1], [2, 0], [2, 1]]
        self.assertEqual(rules.gold_balanced(cells, SHAPES, {}),
                         {"bars": 1, "max": 1, "pieces": [
                             {"shape": "I", "rotation": 1, "cells": [[0, 0], [0, 1], [0, 2], [0, 3]]},
                             {"shape": "O", "rotation": 0, "cells": [[1, 0], [1, 1], [2, 0], [2, 1]]}]})
        # Without rotation the horizontal bar is not there: no bar fits,
        # and 8 cells of that shape do not fill with unturned pieces.
        self.assertIsNone(rules.gold_balanced(cells, SHAPES, {}, rotate=False))

    def test_balanced_fills_every_cell(self):
        # Dullness holds 2 bars, but no complete filling has 2.
        entry = rules.pattern_for("Dullness", TABLE)
        result = rules.gold_balanced(entry["cells"], SHAPES, prefer(entry))
        self.assertEqual((result["bars"], result["max"]), (1, 2))

    def test_balanced_prefers_the_sheet_mix(self):
        entry = rules.pattern_for("Dullness", TABLE)
        squares = rules.gold_balanced(entry["cells"], SHAPES, {"O": 5})
        ells = rules.gold_balanced(entry["cells"], SHAPES, {"L": 5})
        self.assertEqual(rules.needed(squares), {"I": 1, "J": 1, "O": 1})
        self.assertEqual(rules.needed(ells), {"I": 1, "L": 1, "S": 1})
        self.assertEqual(rules.gold_balanced(list(reversed(entry["cells"])), SHAPES, {"O": 5}), squares)

    def test_gold_variant(self):
        entry = rules.pattern_for("Ambition", TABLE)
        gold = rules.variants(entry)["Gold-maxed"]
        self.assertEqual(rules.needed(gold), {"I": 4})
        self.assertFalse(rules.needs_rotation(gold))
        self.assertEqual(list(rules.variants(entry)), ["Balanced", "Crit", "Gold-maxed", "Gold-balanced"])
        # Without rotation, Gold is the vertical layout; with it, the other.
        pride = rules.pattern_for("Exciting", TABLE)
        self.assertEqual(rules.variants(pride)["Gold-maxed"]["bars"], pride["gold"]["without_rotation"]["count"])
        self.assertEqual(rules.variants(pride, rotate=True)["Gold-maxed"]["bars"], pride["gold"]["with_rotation"]["count"])
        self.assertNotEqual(pride["gold"]["without_rotation"]["count"], pride["gold"]["with_rotation"]["count"])

    def test_placeable(self):
        # While rotation is not confirmed, a variant that turns pieces is
        # listed but not placeable.
        self.assertFalse(rules.rotation_allowed({"rotation": None}))
        self.assertTrue(rules.rotation_allowed({"rotation": True}))
        entry = rules.pattern_for("Ambition", TABLE)
        self.assertEqual({name: v["placeable"] for name, v in rules.variants(entry).items()},
                         {"Balanced": False, "Crit": False, "Gold-maxed": True, "Gold-balanced": True})
        self.assertTrue(all(v["placeable"] for v in rules.variants(entry, rotate=True).values()))

    def test_gold_leaves_cells_empty(self):
        entry = rules.pattern_for("Pride", TABLE)
        gold = rules.variants(entry)["Gold-maxed"]
        result = rules.check(entry["cells"], [piece["cells"] for piece in gold["pieces"]])
        self.assertEqual(len(result["missing"]), len(entry["cells"]) - 4 * gold["bars"])
        self.assertEqual(result["outside"] + result["overlap"], [])


class Pieces(unittest.TestCase):
    def test_needed(self):
        entry = rules.pattern_for("Ambition", TABLE)
        crit = rules.variants(entry)["Crit"]
        self.assertEqual(rules.needed(crit), {"I": 1, "L": 2, "O": 1})
        self.assertTrue(rules.needs_rotation(crit))

    def test_feasible(self):
        self.assertEqual(rules.feasible({"I": 1, "L": 2, "O": 1}, {"L": 3, "I": 1, "O": 2, "T": 1}), (True, {}))
        self.assertEqual(rules.feasible({"I": 1, "L": 2, "O": 1}, {"L": 1, "O": 1}), (False, {"I": 1, "L": 1}))
        self.assertEqual(rules.feasible({}, {}), (True, {}))

    def test_missing_alert(self):
        text = rules.missing_alert("Ambition", "Crit", {"I": 1, "L": 1}, TABLE["shapes"])
        self.assertEqual(text, "Engraving of Ambition (Crit): missing 1 × Line (I), 1 × L-Shape (L). "
                               "Nothing was placed.")


PER_PIECE = {"rotation": rules.PER_PIECE}


def brute_gold(cells, vertical, horizontal):
    """The most bars kept of any packing, each orientation cut to what is owned."""
    target = {tuple(cell) for cell in cells}
    best = 0
    for count in range(rules.gold(cells)["count"] + 1):
        for packing in rules.bar_packings(target, count, True):
            v = sum(1 for bar in packing if bar[0][1] == bar[1][1])
            best = max(best, min(v, vertical) + min(count - v, horizontal))
    return best


class Oriented(unittest.TestCase):
    """Pieces whose orientation is fixed when they drop ("rotation":
    "per-piece"): the inventory is counted by shape and orientation."""

    def test_modes(self):
        self.assertEqual([(rules.rotation_allowed(t), rules.per_piece(t), rules.any_orientation(t))
                          for t in ({"rotation": None}, {"rotation": True}, PER_PIECE, TABLE)],
                         [(False, False, False), (True, False, True), (False, True, True), (False, True, True)])

    def test_every_grid_has_its_gold_balanced(self):
        # Per piece, layouts hold pieces in any orientation: every grid
        # gets a complete gold filling, Vision's with 2 bars (no complete
        # filling holds Gold-maxed's 3), and every variant is placeable
        # (the pieces owned are checked by orientation when placing).
        for entry in engraved():
            listed = rules.variants(entry, rules.any_orientation(TABLE))
            self.assertIn("Gold-balanced", listed, entry["name"])
            self.assertTrue(all(v["placeable"] for v in listed.values()), entry["name"])
        vision = rules.variants(rules.weapon_by_id(36, TABLE), True)
        self.assertEqual((vision["Gold-maxed"]["bars"], vision["Gold-balanced"]["bars"]), (3, 2))
        need = rules.needed(vision["Gold-balanced"], TABLE["shapes"])
        self.assertEqual(need, {"I:1": 2, "L:1": 1, "L:3": 1})
        self.assertEqual(rules.feasible(need, {"I:0": 2, "L:1": 1, "L:3": 1}), (False, {"I:1": 2}))

    def test_orientation(self):
        self.assertEqual([rules.orientation(SHAPES["O"], r) for r in range(4)], [0, 0, 0, 0])
        self.assertEqual([rules.orientation(SHAPES["I"], r) for r in range(4)], [0, 1, 0, 1])
        self.assertEqual([rules.orientation(SHAPES["S"], r) for r in range(4)], [0, 1, 0, 1])
        self.assertEqual([rules.orientation(SHAPES["L"], r) for r in range(4)], [0, 1, 2, 3])
        self.assertEqual(rules.piece_key("I", 3, TABLE["shapes"]), "I:1")

    def test_needed(self):
        crit = rules.variants(rules.pattern_for("Ambition", TABLE))["Crit"]
        by_piece = rules.needed(crit, TABLE["shapes"])
        self.assertEqual(sum(by_piece.values()), sum(rules.needed(crit).values()))
        totals = {}
        for key, count in by_piece.items():
            totals[key.split(":")[0]] = totals.get(key.split(":")[0], 0) + count
        self.assertEqual(totals, rules.needed(crit))
        self.assertEqual(by_piece, {f"{p['shape']}:{p['rotation']}": by_piece[f"{p['shape']}:{p['rotation']}"]
                                    for p in crit["pieces"]})

    def test_sheet_variant_by_orientation(self):
        # The same shapes in another orientation: enough by shape, short by oriented piece.
        crit = rules.variants(rules.pattern_for("Ambition", TABLE), rotate=True)["Crit"]
        need = rules.needed(crit, TABLE["shapes"])
        self.assertEqual(rules.feasible(need, dict(need)), (True, {}))
        turned = dict(need)
        key = next(k for k in need if k.startswith("L:"))
        other = "L:" + str((int(key[2]) + 1) % 4)
        turned[key] -= 1
        turned[other] = turned.get(other, 0) + 1
        self.assertEqual(rules.feasible(rules.needed(crit), {"I": 1, "L": 2, "O": 1}), (True, {}))
        ok, missing = rules.feasible(need, turned)
        self.assertFalse(ok)
        self.assertEqual(missing, {key: 1})
        self.assertTrue(crit["placeable"])

    def test_gold_maxed_for_the_bars_owned(self):
        entry = rules.pattern_for("Ambition", TABLE)
        fit = lambda owned: rules.fit_gold_maxed(entry, owned)
        self.assertEqual(rules.needed(fit({"I:0": 4}), TABLE["shapes"]), {"I:0": 4})
        self.assertEqual(rules.needed(fit({"I:1": 5}), TABLE["shapes"]), {"I:1": 3})
        self.assertEqual(fit({"I:0": 2, "I:1": 5})["bars"], 3)
        self.assertEqual(fit({"L:0": 9})["pieces"], [])
        self.assertIsNone(rules.fit_gold_maxed(rules.pattern_for("Innocence", TABLE), {"I:0": 4}))
        # The best possible for every count owned, against every packing.
        for name in ("Ambition", "Exciting", "Pride"):
            entry = rules.pattern_for(name, TABLE)
            for vertical in range(6):
                for horizontal in range(6):
                    with self.subTest(name, vertical=vertical, horizontal=horizontal):
                        variant = rules.fit_gold_maxed(entry, {"I:0": vertical, "I:1": horizontal})
                        self.assertEqual(variant["bars"], brute_gold(entry["cells"], vertical, horizontal))
                        ok, _ = rules.feasible(rules.needed(variant, TABLE["shapes"]),
                                               {"I:0": vertical, "I:1": horizontal})
                        self.assertTrue(ok)
                        result = rules.check(entry["cells"], [p["cells"] for p in variant["pieces"]])
                        self.assertEqual(result["outside"] + result["overlap"], [])

    def test_gold_balanced_for_the_pieces_owned(self):
        entry = rules.pattern_for("Ambition", TABLE)
        fillings = entry["gold"]["per_piece"]["balanced"]
        self.assertGreater(len(fillings), 1)
        shapes = TABLE["shapes"]
        need = [rules.needed({"pieces": f["pieces"]}, shapes) for f in fillings]
        variant, missing = rules.fit_gold_balanced(entry, need[0], shapes)
        self.assertEqual((variant["bars"], missing), (fillings[0]["bars"], {}))
        # Only the second filling's pieces: the second, fewer bars.
        variant, missing = rules.fit_gold_balanced(entry, need[1], shapes)
        self.assertEqual((variant["bars"], missing), (fillings[1]["bars"], {}))
        self.assertTrue(rules.check(entry["cells"], [p["cells"] for p in variant["pieces"]])["complete"])
        # Nothing owned: the first, and all it lacks.
        variant, missing = rules.fit_gold_balanced(entry, {}, shapes)
        self.assertEqual((variant["bars"], missing), (fillings[0]["bars"], need[0]))
        self.assertEqual(rules.fit_gold_balanced(rules.pattern_for("Innocence", TABLE), {}, shapes), (None, {}))

    def test_no_search(self):
        # Fitting reads what engravings.json keeps: the searches are not called.
        names = ("solve", "tiling", "tilings", "gold", "gold_balanced", "gold_frontier", "bar_packings")
        kept = {name: getattr(rules, name) for name in names}

        def refuse(*args, **kwargs):
            raise AssertionError("searched at run time")

        try:
            for name in names:
                setattr(rules, name, refuse)
            entry = rules.pattern_for("Ambition", TABLE)
            rules.fit_gold_maxed(entry, {"I:0": 1, "I:1": 1})
            rules.fit_gold_balanced(entry, {"I:0": 4}, TABLE["shapes"])
            rules.needed(rules.variants(entry, rotate=True)["Crit"], TABLE["shapes"])
        finally:
            for name, function in kept.items():
                setattr(rules, name, function)

    def test_missing_alert(self):
        text = rules.missing_alert("Ambition", "Crit", {"I:1": 1, "L:2": 2}, TABLE["shapes"])
        self.assertEqual(text, "Engraving of Ambition (Crit): missing 1 × Line (I, orientation 1), "
                               "2 × L-Shape (L, orientation 2). Nothing was placed.")


class Solve(unittest.TestCase):
    def setUp(self):
        self.pride = rules.pattern_for("Pride", TABLE)["cells"]
        self.pieces = [SHAPES[name] for name in "LJTOISZL"]

    def test_fills_without_overlap(self):
        for entry in engraved():
            moves = rules.solve(entry["cells"], self.pieces)
            if moves is None:
                continue
            indexes = [move["piece_index"] for move in moves]
            self.assertEqual(len(indexes), len(set(indexes)))
            cells = [rules.placed(self.pieces[m["piece_index"]], m["rotation"], m["anchor"]) for m in moves]
            self.assertTrue(rules.check(entry["cells"], cells)["complete"], entry["name"])

    def test_deterministic(self):
        first = rules.solve(self.pride, self.pieces)
        self.assertIsNotNone(first)
        self.assertEqual(rules.solve(list(reversed(self.pride)), self.pieces), first)
        self.assertEqual(rules.solve(self.pride, [list(reversed(p)) for p in self.pieces]), first)

    def test_inventory_order(self):
        moves = rules.solve(FULL4, [SHAPES["O"]] * 5)
        self.assertEqual([move["piece_index"] for move in moves], [0, 1, 2, 3])
        self.assertEqual([move["anchor"] for move in moves], [[0, 0], [0, 2], [2, 0], [2, 2]])

    def test_none_and_rotation(self):
        self.assertIsNone(rules.solve([[0, 0], [0, 1], [0, 2]], self.pieces))
        row = [[0, 0], [0, 1], [0, 2], [0, 3]]
        self.assertEqual(rules.solve(row, [SHAPES["I"]]), [{"piece_index": 0, "rotation": 1, "anchor": [0, 0]}])
        self.assertIsNone(rules.solve(row, [SHAPES["I"]], rotate=False))


class Check(unittest.TestCase):
    def test_check(self):
        cells = [[0, 0], [0, 1], [1, 0], [1, 1], [2, 0]]
        result = rules.check(cells, [[[0, 0], [0, 1]], [[0, 1], [1, 1], [5, 5]]])
        self.assertEqual(result, {"missing": [[1, 0], [2, 0]], "outside": [[5, 5]], "overlap": [[0, 1]],
                                  "complete": False})
        self.assertTrue(rules.check(cells, [[[0, 0], [0, 1], [1, 0]], [[1, 1], [2, 0]]])["complete"])


class Loadout(unittest.TestCase):
    def test_valid(self):
        body = {"mode": "mpw18", "preset": "III", "soul_weapon": {"id": 32, "variant": "Crit"}}
        self.assertEqual(rules.loadout(body, TABLE), (("mpw18", {
            "stage": None, "preset": "III", "soul_weapon": {"id": 32, "variant": "Crit"}}), None))
        body = {"mode": "mpw4", "stage": 31, "preset": None, "soul_weapon": {"id": 32, "variant": "Gold-maxed"}}
        self.assertIsNone(rules.loadout(body, TABLE)[1])
        self.assertEqual(rules.loadout({"mode": "mpw4"}, TABLE), (("mpw4", rules.empty_loadout()), None))

    def test_absent_keeps_null_clears(self):
        stored = {"stage": 920, "preset": "III", "soul_weapon": {"id": 32, "variant": "Crit"}}
        self.assertEqual(rules.loadout({"mode": "mpw18", "preset": "II"}, TABLE, stored=stored)[0][1],
                         dict(stored, preset="II"))
        self.assertEqual(rules.loadout({"mode": "mpw18", "stage": None, "soul_weapon": None}, TABLE,
                                       stored=stored)[0][1], {"stage": None, "preset": "III", "soul_weapon": None})

    def test_refused(self):
        weapon = {"id": 32, "variant": "Crit"}
        for body in (None, {}, {"mode": "mine", "soul_weapon": weapon}, {"mode": "mpw18", "preset": "VI"},
                     {"mode": "mpw18", "stage": 0}, {"mode": "mpw18", "stage": "920"}, {"mode": "mpw18", "stage": 100000},
                     {"mode": "mpw18", "soul_weapon": {"id": "32", "variant": "Crit"}},
                     {"mode": "mpw18", "soul_weapon": {"id": 999, "variant": "Crit"}},
                     {"mode": "mpw18", "soul_weapon": {"id": 1, "variant": "Atk"}},
                     {"mode": "mpw18", "soul_weapon": {"id": 32, "variant": "Atk"}},
                     {"mode": "mpw18", "soul_weapon": {"id": 32}}):
            asked, error = rules.loadout(body, TABLE)
            self.assertIsNone(asked, body)
            self.assertTrue(error)

    def test_kept(self):
        saved = {"mpw18": {"stage": 920, "preset": "III", "soul_weapon": {"id": 32, "variant": "Crit"}},
                 "mpw4": {"stage": "x", "preset": "II", "soul_weapon": {"id": 32, "variant": "Nope"}}}
        self.assertEqual(rules.kept_loadouts(saved, TABLE),
                         {"mpw18": {"stage": 920, "preset": "III", "soul_weapon": {"id": 32, "variant": "Crit"}},
                          "mpw4": {"stage": None, "preset": "II", "soul_weapon": None}})
        empty = rules.empty_loadout()
        self.assertEqual(rules.kept_loadouts(None, TABLE), {"mpw18": empty, "mpw4": empty})


class Request:
    def __init__(self, body=None, **query):
        self.query = query
        self._body = body

    async def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Routes(unittest.TestCase):
    """The routes as the gateway sets them up (gateway.py), with state.json
    in a temporary directory; nothing touches Android."""

    def setup_gateway(self, data_dir):
        spec = importlib.util.spec_from_file_location("slayer_legend_test_engraving_gateway",
                                                      os.path.join(HERE, "gateway.py"))
        gateway = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gateway)
        routes = {}

        async def refuse(*args, **kwargs):
            raise AssertionError("no Android here")

        context = SimpleNamespace(
            app=SimpleNamespace(on_startup=[], on_shutdown=[]), id="slayer-legend", directory=HERE, data_dir=data_dir,
            add_get=lambda path, handler: routes.__setitem__(("GET", path), handler),
            add_post=lambda path, handler: routes.__setitem__(("POST", path), handler),
            screenshot=refuse, adb=refuse, analyse=refuse, notify=refuse,
            json=lambda value, status=200: SimpleNamespace(status=status, body=value))
        gateway.setup(context)
        return lambda method, path, request: asyncio.run(routes[(method, path)](request))

    def test_routes(self):
        with tempfile.TemporaryDirectory() as data_dir:
            call = self.setup_gateway(data_dir)
            listed = call("GET", "/engravings", Request()).body
            self.assertEqual(len(listed["weapons"]), 89)
            self.assertEqual(listed["rotation"], "per-piece")
            self.assertEqual(listed["weapons"][31]["variants"], ["Balanced", "Crit", "Gold-maxed", "Gold-balanced"])
            one = call("GET", "/engraving", Request(id="32")).body
            self.assertEqual(one["name"], "Ambition")
            self.assertEqual([v["needed"] for v in one["variants"]],
                             [{"J": 1, "L": 3}, {"I": 1, "L": 2, "O": 1}, {"I": 4}, {"I": 4}])
            self.assertEqual([v["placeable"] for v in one["variants"]], [True, True, True, True])
            # Per piece, also counted by oriented piece.
            self.assertEqual([v["needed_oriented"] for v in one["variants"]],
                             [{"J:3": 1, "L:0": 1, "L:3": 2}, {"I:0": 1, "L:0": 1, "L:3": 1, "O:0": 1},
                              {"I:0": 4}, {"I:0": 4}])
            vision = call("GET", "/engraving", Request(id="36")).body
            self.assertEqual([v["name"] for v in vision["variants"]], ["Atk", "Balanced", "Gold-maxed", "Gold-balanced"])
            # By id only.
            self.assertEqual(call("GET", "/engraving", Request(weapon="Ambition")).status, 404)
            self.assertEqual(call("GET", "/engraving", Request(id="x")).status, 404)
            self.assertEqual(call("GET", "/engraving", Request(id="999")).status, 404)

            empty = {"stage": None, "preset": None, "soul_weapon": None, "weapon": None, "placeable": None,
                     "revision": load("features/engraving").revision({"stage": None, "preset": None, "soul_weapon": None}),
                     "automation": rules.automation(None, TABLE)}
            self.assertEqual(call("GET", "/loadout", Request()).body, {"loadouts": {"mpw18": empty, "mpw4": empty}})
            body = {"mode": "mpw18", "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold-maxed"}}
            self.assertEqual(call("POST", "/loadout", Request(body)).status, 200)
            refused = call("POST", "/loadout", Request({"mode": "mpw4", "soul_weapon": {"id": 32, "variant": "Atk"}}))
            self.assertEqual(refused.status, 400)
            self.assertIn("Variante inconnue", french(refused.body["error_t"]))
            self.assertEqual(call("POST", "/loadout", Request(ValueError("not JSON"))).status, 400)
            self.assertEqual(call("POST", "/loadout", Request({"mode": ["mpw18"]})).status, 400)
            # The mode's stages are the loadouts': POST /mode sets them,
            # GET /mode reads them back, and a field left out is kept.
            self.assertEqual(call("POST", "/mode", Request({"mode": "mpw18", "stage18": 920})).status, 200)
            self.assertEqual(call("GET", "/mode", Request()).body["stage18"], 920)
            self.assertEqual(call("GET", "/loadout", Request()).body["loadouts"]["mpw18"]["stage"], 920)
            self.assertEqual(call("POST", "/loadout", Request({"mode": "mpw18", "stage": 940})).status, 200)
            self.assertEqual(call("GET", "/mode", Request()).body["stage18"], 940)
            self.assertEqual(call("GET", "/loadout", Request()).body["loadouts"]["mpw18"]["preset"], "III")

            # Kept across a gateway restart.
            again = self.setup_gateway(data_dir)
            self.assertEqual(again("GET", "/loadout", Request()).body["loadouts"],
                             {"mpw18": {"stage": 940, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold-maxed"},
                                        "revision": load("features/engraving").revision({"stage": 940, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold-maxed"}}),
                                        "weapon": "Ambition", "placeable": True,
                                        "automation": rules.automation(32, TABLE, True, "Gold-maxed")}, "mpw4": empty})
            self.assertEqual(again("GET", "/mode", Request()).body["stage18"], 940)

    def test_stale_browser_cannot_overwrite_another_target_or_stage_change(self):
        with tempfile.TemporaryDirectory() as data_dir:
            call = self.setup_gateway(data_dir)
            first = call("GET", "/loadout", Request()).body["loadouts"]["mpw18"]
            body = {"mode": "mpw18", "stage": 940, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold-maxed"},
                    "if_revision": first["revision"]}
            accepted = call("POST", "/loadout", Request(body))
            self.assertEqual(accepted.status, 200)
            saved = accepted.body["loadouts"]["mpw18"]
            self.assertNotEqual(saved["revision"], first["revision"])
            refused = call("POST", "/loadout", Request(dict(body, preset="V")))
            self.assertEqual(refused.status, 409)
            self.assertEqual(refused.body["loadouts"]["mpw18"], saved)
            restarted = self.setup_gateway(data_dir)
            self.assertEqual(restarted("GET", "/loadout", Request()).body["loadouts"]["mpw18"], saved)
            # A stage edited through the mode API also invalidates the editor's revision.
            call("POST", "/mode", Request({"mode": "mpw18", "stage18": 920}))
            refused = call("POST", "/loadout", Request(dict(body, if_revision=saved["revision"])))
            self.assertEqual(refused.status, 409)
            self.assertEqual(refused.body["loadouts"]["mpw18"]["stage"], 920)

    def test_stages_of_an_older_state_move_to_the_loadouts(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with open(os.path.join(data_dir, "state.json"), "w", encoding="utf-8") as f:
                json.dump({"mode": {"mode": "mpw18", "until": None, "stage18": 920, "stage4": 31, "highest": 950,
                                    "configured": True}}, f)
            call = self.setup_gateway(data_dir)
            loadouts = call("GET", "/loadout", Request()).body["loadouts"]
            self.assertEqual((loadouts["mpw18"]["stage"], loadouts["mpw4"]["stage"]), (920, 31))
            mode = call("GET", "/mode", Request()).body
            self.assertEqual((mode["stage18"], mode["stage4"], mode["highest"]), (920, 31, 950))
            with open(os.path.join(data_dir, "state.json"), encoding="utf-8") as f:
                kept = json.load(f)
            self.assertNotIn("stage18", kept["mode"])
            self.assertEqual(kept["loadouts"]["mpw4"]["stage"], 31)

    def test_unsupported_targets_are_reported_but_remain_saveable(self):
        with tempfile.TemporaryDirectory() as data_dir:
            call = self.setup_gateway(data_dir)
            listed = call("GET", "/engravings", Request()).body["weapons"]
            self.assertEqual(listed[12]["automation"]["code"], "unsupported_grid")
            detail = call("GET", "/engraving", Request(id="13")).body
            self.assertTrue(all(v["automation"]["code"] == "unsupported_grid" for v in detail["variants"]))
            for weapon_id, expected in ((13, "unsupported_grid"), (89, "ambiguous_weapon")):
                response = call("POST", "/loadout", Request({"mode": "mpw4", "soul_weapon": {
                    "id": weapon_id, "variant": "Gold-maxed"}}))
                self.assertEqual(response.status, 200)
                chosen = response.body["loadouts"]["mpw4"]
                self.assertEqual(chosen["soul_weapon"]["id"], weapon_id)
                self.assertEqual(chosen["automation"]["code"], expected)
                self.assertFalse(chosen["automation"]["runtime_verified"])

    def test_no_search_at_run_time(self):
        # The routes only read engravings.json: the searches run when it is built.
        with open(os.path.join(HERE, "features", "engraving.py"), encoding="utf-8") as f:
            source = f.read()
        for name in ("solve", "tiling", "gold", "gold_balanced", "gold_frontier", "bar_packings", "tilings"):
            self.assertNotIn(f"rules.{name}(", source)
            self.assertNotIn(f"{name}(", source.replace("rotation_allowed(", ""))
        self.assertNotIn("import engraving_rules", source)


class AutomationApplicability(unittest.TestCase):
    def test_static_support_is_not_runtime_verification(self):
        capability = rules.automation(32, TABLE, True, "Gold-maxed")
        self.assertTrue(capability["supported"])
        self.assertEqual(capability["scope"], "static")
        self.assertFalse(capability["runtime_verified"])
        self.assertFalse(TABLE["weapons"][31]["verified_in_game"])

    def test_actual_executor_limits_and_invalid_selection(self):
        for weapon_id, variant, expected in ((13, "Gold-maxed", "unsupported_grid"),
                                              (20, "Gold-maxed", "ambiguous_weapon"),
                                              (89, "Gold-maxed", "ambiguous_weapon"),
                                              (32, "missing", "unknown_variant"),
                                              (32, "", "unknown_variant"), (999, None, "unknown_weapon")):
            with self.subTest(id=weapon_id, variant=variant):
                capability = rules.automation(weapon_id, TABLE, True, variant)
                self.assertFalse(capability["supported"])
                self.assertEqual(capability["code"], expected)
                self.assertIsNotNone(capability["reason_t"])

    def test_preflight_stops_before_stage_preset_or_capture(self):
        stage = load("features/stage_change")
        feature = load("features/engraving")
        cases = [(13, "Gold-maxed", "real", "real", True, True, "failed"),
                 (89, "Gold-maxed", "real", "real", True, True, "failed"),
                 (32, "missing", "real", "real", True, True, "failed"),
                 (32, "Gold-maxed", "off", "real", True, True, "plan"),
                 (32, "Gold-maxed", "real", "off", True, True, "failed"),
                 (32, "Gold-maxed", "real", "real", False, True, "failed"),
                 (32, "Gold-maxed", "real", "real", True, False, "failed")]
        for weapon_id, variant, soul_switch, engraving_switch, capability_present, setup_present, expected in cases:
            with self.subTest(id=weapon_id, variant=variant, soul=soul_switch, engraving=engraving_switch,
                              capability=capability_present, setup=setup_present):
                chosen = {"id": weapon_id, "variant": variant}
                effects = []

                async def forbidden(*args, **kwargs):
                    effects.append("unexpected action or capture")
                    self.fail("preflight must stop before observing or changing the game")

                @contextlib.asynccontextmanager
                async def leased(*args, **kwargs):
                    yield

                store = SimpleNamespace(saved={}, register=lambda *args: None, save=lambda: None)
                ports = SimpleNamespace(store=store, clock=SimpleNamespace(monotonic=lambda: 0),
                                        leased=leased, capture=forbidden, analyse=forbidden, tap=forbidden,
                                        log=lambda *args: None, t=texts.t, english=texts.english,
                                        Busy=type("Busy", (RuntimeError,), {}))
                capability = feature.engraving(ports, rules)["api"]["applicability"]
                soul = {"feature": lambda *args: {"switch": lambda: soul_switch,
                                                  "state": lambda: {"engraving": engraving_switch}},
                        "reader": None, "rules": None, "table": TABLE,
                        "loadout": lambda mode: {"soul_weapon": chosen}, "applicability": capability,
                        "engraving": {"setup": "present"} if setup_present else None}
                if not capability_present:
                    soul.pop("applicability")
                api = stage.stage_change(ports, None, SimpleNamespace(regions=lambda table: []), None,
                                         None, {}, soul)["api"]
                answer = asyncio.run(api["farm"](931, "V", "mpw18"))
                self.assertEqual(answer["result"], expected)
                self.assertIsNotNone(answer["text_t"])
                self.assertEqual(effects, [])
                self.assertEqual(answer["timings"], {})


class Names(unittest.TestCase):
    def test_lookup(self):
        self.assertEqual(rules.pattern_for("Ambition", TABLE)["id"], 32)
        self.assertEqual(rules.pattern_for("fighting will", TABLE)["id"], 47)
        self.assertEqual(rules.pattern_for("Silence I", TABLE)["id"], 20)
        self.assertEqual(rules.pattern_for("Serenity", TABLE)["id"], 68)
        self.assertEqual(rules.pattern_for("Silence II", TABLE)["id"], 68)
        self.assertIsNone(rules.pattern_for("Innocence", TABLE)["grid"])
        self.assertEqual(rules.weapon_by_id(13, TABLE)["name"], "Pride")
        self.assertIsNone(rules.weapon_by_id(999, TABLE))

    def test_unknown(self):
        with self.assertRaises(rules.UnknownWeapon) as caught:
            rules.pattern_for("Ambitio", TABLE)
        self.assertIn("Ambition", str(caught.exception))
        with self.assertRaises(KeyError):
            rules.pattern_for("Excalibur", TABLE)
        with self.assertRaises(rules.UnknownWeapon) as caught:
            rules.pattern_for("Silence", TABLE)
        self.assertIn("20, 89", str(caught.exception))

    def test_default_table(self):
        self.assertEqual(rules.pattern_for("Pride")["id"], 13)


if __name__ == "__main__":
    unittest.main()
