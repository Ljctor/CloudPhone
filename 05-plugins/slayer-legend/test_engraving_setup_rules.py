"""The engraving setup's rules: the cards chosen, the next move (lock,
remove, place), the preview's moves, on the readings of real captures
(fixtures/eg_*) and variations of them.
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
texts = load("features/texts")
engraving_rules = load("features/engraving_rules")
es = load("engraving_screen")
fixtures = load("test_fixtures")
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
SHAPES = TABLE["shapes"]
VISION = next(entry for entry in TABLE["weapons"] if entry["name"] == "Vision")
VARIANTS = engraving_rules.variants(VISION, engraving_rules.any_orientation(TABLE))
GOLD, ATK = VARIANTS["Gold-balanced"], VARIANTS["Atk"]
# 2026-10-21: Vision as Gold-balanced, an L Lv38 placed while an L Lv39 is
# free. 2026-10-22: Vision as Atk (four L), all locked.
OLD = fixtures.screen("eg_title", "eg_grid", "eg_cards")
NOW = fixtures.screen("eg_grid_atk", "eg_cards_relocked")
OLD_GRID, OLD_CARDS = es.grid(OLD, 5), es.cards(OLD, SHAPES)
ATK_GRID, ATK_CARDS = es.grid(NOW, 5), es.cards(NOW, SHAPES)


def step(grid, cards, variant=GOLD, gold=True, probed=()):
    return rules.next_step(grid, cards, variant, SHAPES, gold, probed)


def changed(cards, **fields):
    cards = copy.deepcopy(cards)
    for key, value in fields.items():
        cards[int(key[1:])].update(value)
    return cards


def emptied(grid, cells):
    grid = copy.deepcopy(grid)
    gone = {tuple(c) for c in cells}
    for cell in gone:
        grid["cells"][cell] = "empty"
    grid["pieces"] = [p for p in grid["pieces"] if not gone & set(map(tuple, p))]
    return grid


def filled(grid, cells):
    grid = copy.deepcopy(grid)
    for cell in cells:
        grid["cells"][tuple(cell)] = "piece"
    grid["pieces"].append(sorted(tuple(c) for c in cells))
    return grid


class Choose(unittest.TestCase):
    def test_highest_levels_then_gold_option_at_a_tie(self):
        self.assertEqual(rules.choose(ATK_CARDS, GOLD, gold=True), {"I": [6, 0], "L": [1, 4]})
        # Atk: the L only, by level, placed first among equals.
        self.assertEqual(rules.choose(ATK_CARDS, ATK), {"L": [1, 4, 5, 7]})

    def test_a_higher_level_always_beats_a_gold_option(self):
        cards = changed(ATK_CARDS, c2={"level": 45, "kind": "atk"})
        self.assertEqual(rules.choose(cards, GOLD, gold=True)["I"], [2, 6])
        self.assertEqual(rules.choose(cards, GOLD, gold=False)["I"], [2, 6])

    def test_gold_only_breaks_a_tie_between_equal_levels(self):
        cards = changed(ATK_CARDS, c2={"level": 40, "kind": "atk"}, c6={"kind": "gold"})
        self.assertEqual(rules.choose(cards, GOLD, gold=True)["I"], [6, 2])

    def test_unread_level_never_authorises_an_inventory_choice(self):
        cards = changed(OLD_CARDS, c2={"level": None})
        self.assertEqual(step(OLD_GRID, cards)[0], "fail")
        self.assertTrue(rules.check(OLD_GRID, cards, GOLD, VISION["cells"], "Vision", "Gold-balanced", gold=True))


class NextStep(unittest.TestCase):
    def test_placed_lower_gold_card_is_replaced_by_higher_non_gold(self):
        # The exact layout is already right, but its Lv39 Gold bar must
        # give way to the free Lv45 bar even though that bar is not Gold.
        cards = changed(OLD_CARDS, c2={"level": 45, "kind": "atk"})
        self.assertEqual(step(OLD_GRID, cards), ("remove", [(0, 1), (0, 2), (0, 3), (0, 4)]))
        self.assertTrue(rules.check(OLD_GRID, cards, GOLD, VISION["cells"], "Vision", "Gold-balanced", gold=True))

    def test_atk_to_gold_balanced_takes_the_wrong_pieces_out_first(self):
        self.assertEqual(step(ATK_GRID, ATK_CARDS), ("remove", [(0, 1), (0, 2), (0, 3), (1, 1)]))
        grid = emptied(ATK_GRID, [(0, 1), (0, 2), (0, 3), (1, 1)])
        self.assertEqual(step(grid, changed(ATK_CARDS, c1={"placed": False})),
                         ("remove", [(0, 4), (1, 2), (1, 3), (1, 4)]))

    def test_an_open_padlock_is_locked_first(self):
        cards = changed(ATK_CARDS, c1={"placed": False, "locked": False})
        self.assertEqual(step(ATK_GRID, cards), ("lock", 1))

    def test_then_the_bars_placed_the_highest_first(self):
        top = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 1), (1, 2), (1, 3), (1, 4)]
        grid = emptied(ATK_GRID, top)
        cards = changed(ATK_CARDS, c1={"placed": False}, c4={"placed": False})
        self.assertEqual(step(grid, cards), ("place", 6, [(0, 1), (0, 2), (0, 3), (0, 4)]))
        grid = filled(grid, [(0, 1), (0, 2), (0, 3), (0, 4)])
        cards = changed(cards, c6={"placed": True})
        self.assertEqual(step(grid, cards), ("place", 0, [(1, 1), (1, 2), (1, 3), (1, 4)]))

    def test_a_lower_card_placed_is_found_by_taking_pieces_out(self):
        # 2026-10-21: the grid is Gold-balanced's, but the L Lv38 (#8) is
        # placed while the L Lv39 #2 is free: L pieces come out one by one.
        first = step(OLD_GRID, OLD_CARDS)
        self.assertEqual(first, ("remove", [(2, 2), (2, 3), (2, 4), (3, 2)]))
        # That one held #5 (chosen): placed back where it was.
        grid = emptied(OLD_GRID, first[1])
        cards = changed(OLD_CARDS, c4={"placed": False})
        self.assertEqual(step(grid, cards, probed=[first[1]]), ("place", 1, [(2, 2), (2, 3), (2, 4), (3, 2)]))
        # #2 went there instead; the other L comes out next.
        grid = filled(grid, first[1])
        cards = changed(cards, c1={"placed": True})
        second = step(grid, cards, probed=[first[1]])
        self.assertEqual(second, ("remove", [(3, 3), (4, 1), (4, 2), (4, 3)]))
        grid = emptied(grid, second[1])
        cards = changed(cards, c7={"placed": False})
        self.assertEqual(step(grid, cards, probed=[first[1], second[1]]),
                         ("place", 4, [(3, 3), (4, 1), (4, 2), (4, 3)]))
        cards = changed(cards, c4={"placed": True})
        self.assertEqual(step(filled(grid, second[1]), cards, probed=[first[1], second[1]]), ("done",))

    def test_failures(self):
        self.assertEqual(step(None, ATK_CARDS), ("fail", texts.t("grille illisible")))
        self.assertEqual(step(ATK_GRID, changed(ATK_CARDS, c3={"locked": None}))[0], "fail")
        self.assertIn("illisible", texts.french(step(ATK_GRID, changed(ATK_CARDS, c3={"shape": None}))[1]))
        self.assertIn("il manque", texts.french(step(ATK_GRID, changed(ATK_CARDS, c0={"shape": "L"}, c2={"shape": "L"},
                                                                       c3={"shape": "L"}, c6={"shape": "L"}))[1]))

    def test_done_and_check(self):
        self.assertEqual(step(ATK_GRID, ATK_CARDS, ATK, gold=False), ("done",))
        self.assertEqual(rules.check(ATK_GRID, ATK_CARDS, ATK, VISION["cells"], "Vision", "Atk"), [])
        problems = rules.check(ATK_GRID, ATK_CARDS, GOLD, VISION["cells"], "Vision", "Gold-balanced", gold=True)
        self.assertIn("les pièces posées ne sont pas celles de Gold-balanced", [texts.french(p) for p in problems])
        self.assertIn("pas lue(s) verrouillée(s) : n°2",
                      [texts.french(p) for p in rules.check(ATK_GRID, changed(ATK_CARDS, c1={"locked": False}), ATK,
                                                            VISION["cells"], "Vision", "Atk")])
        alert = rules.alert("Vision", "Atk", [texts.t("grille illisible"), texts.t("une pièce illisible")])
        self.assertEqual(texts.french(alert), "Gravure de Vision (Atk) pas prête : grille illisible ; une pièce illisible")
        self.assertTrue(texts.english(alert).startswith("Engraving of Vision (Atk) not ready"))


# The preview on the captures of 2026-10-22: the L taken out of
# (0,1),(0,2),(0,3),(1,1) dragged back (eg7), turned (eg8), moved (eg9).
REMOVED = set(es.cubes(fixtures.screen("eg_grid_removed")))
L_BASE = rules.normalised([tuple(c) for c in SHAPES["L"]["cells"]])
TARGET = [(0, 1), (0, 2), (0, 3), (1, 1)]


class PreviewStep(unittest.TestCase):
    def preview(self, name):
        screen = fixtures.screen(name)
        return set(es.cubes(screen)), es.bar(screen)["valid"]

    def test_as_dropped_it_is_turned(self):
        now, valid = self.preview("eg_preview_base")
        self.assertEqual(rules.preview_step(REMOVED, now, valid, L_BASE, 0, TARGET), ("rotate",))

    def test_turned_it_is_moved_one_column(self):
        now, valid = self.preview("eg_preview_turned")
        self.assertEqual(rules.preview_step(REMOVED, now, valid, L_BASE, 1, TARGET), ("move", (0, 0), (0, 1)))

    def test_on_its_cells_and_valid_it_is_confirmed(self):
        now, valid = self.preview("eg_preview_valid")
        self.assertEqual(rules.preview_step(REMOVED, now, valid, L_BASE, 1, TARGET), ("confirm",))
        self.assertEqual(rules.preview_step(REMOVED, now, False, L_BASE, 1, TARGET), ("cancel", texts.t("emplacement lu invalide")))

    def test_cancelled_when_lost(self):
        self.assertEqual(rules.preview_step(REMOVED, REMOVED, None, L_BASE, 0, TARGET)[0], "cancel")
        now, valid = self.preview("eg_preview_base")
        self.assertEqual(rules.preview_step(REMOVED, now, valid, L_BASE, 3, [(0, 0), (0, 1), (0, 2), (0, 3)])[0],
                         "cancel")

    def test_fit_sees_through_placed_cubes(self):
        # eg7: three cubes seen, the foot hidden on a placed one.
        self.assertEqual(rules.fit({(-1, 1), (0, 1), (1, 1)}, REMOVED, L_BASE), [(-1, 1)])


if __name__ == "__main__":
    unittest.main()
