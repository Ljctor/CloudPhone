"""The pixel font, the Select Region reader and the battle controls'
reader, on synthetic screens drawn here (text rendered from the font
itself, flat colours, rotated gears). Run: python3 -m unittest test_reading"""

import importlib.util
import json
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 480, 1040


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


font = load("pixel_font")
select = load("stage_select")
controls = load("battle_controls")
with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
    NAMES = select.regions(json.load(f))
GIANT = NAMES.index("Giant's Glass")


class Canvas:
    def __init__(self, colour=(40, 32, 28), width=W, height=H):
        self.width, self.height = width, height
        self.pixels = bytearray(bytes(colour) * (width * height))

    def rect(self, area, colour):
        left, top, right, bottom = (round(area[0] * self.width), round(area[1] * self.height),
                                    round(area[2] * self.width), round(area[3] * self.height))
        for y in range(top, bottom):
            for x in range(left, right):
                self.pixels[(y * self.width + x) * 3:(y * self.width + x) * 3 + 3] = bytes(colour)

    def text(self, string, x, y, scale=2, colour=(255, 255, 255)):
        """string drawn from the font with its top left at (x, y) fractions."""
        rows = font.render(string, scale)
        left, top = round(x * self.width), round(y * self.height)
        for dy, row in enumerate(rows):
            for dx, on in enumerate(row):
                if on:
                    i = ((top + dy) * self.width + left + dx) * 3
                    self.pixels[i:i + 3] = bytes(colour)

    def shot(self):
        return (self.width, self.height, bytes(self.pixels))


def lines_of(rows):
    marks = [[bool(v) for v in row] for row in rows]
    return marks, font.lines(marks)


class Font(unittest.TestCase):
    def read(self, string, scale, gap=1):
        marks, found = lines_of(font.render(string, scale, gap=gap))
        self.assertEqual(len(found), 1)
        return font.text(font.read_line(marks, *found[0]))

    def test_every_shape_reads_back(self):
        for char in font.FONT:
            for scale in (2, 3):
                # A capital first, so that the line's top is a capital's.
                self.assertEqual(self.read(f"X{char}", scale), f"X{char}", (char, scale))

    def test_names(self):
        for string in ("Giant's Glass XIX", "Select Region", "Battle settings", "AUTO", "Move"):
            self.assertEqual(self.read(string, 2), string)

    def test_touching_letters_are_cut(self):
        # A fractional scale makes letters touch: no gap between them.
        self.assertEqual(self.read("Giant's", 2, gap=0).replace(" ", ""), "Giant's")

    def test_close(self):
        names = [name for name in NAMES if name]
        self.assertEqual(font.close("Giants Glass", names), "Giant's Glass")
        self.assertEqual(font.close("Gi?nt's Gl?ss", names), "Giant's Glass")
        self.assertIsNone(font.close("Shop", names))
        self.assertIsNone(font.close("", names))

    def test_roman(self):
        self.assertEqual([font.roman(r) for r in ("I", "IV", "IX", "XIV", "XIX", "XX")], [1, 4, 9, 14, 19, 20])
        self.assertIsNone(font.roman("X?"))
        self.assertIsNone(font.roman(""))

    def test_numeral_by_strokes(self):
        stroke = ["#.."] * 9
        vee = ["#...#", "#...#", "#...#", ".#.#.", ".#.#.", ".#.#.", "..#..", "..#..", "..#.."]
        shapes = {1: [stroke], 2: [stroke, stroke], 3: [stroke] * 3, 4: [stroke, vee], 5: [vee]}
        for value, parts in shapes.items():
            rows = ["".join(part[y] for part in parts) for y in range(9)]
            ink = [[False] * 12] + [[c == "#" for c in row] + [False] * 3 for row in rows] + [[False] * 12]
            ink = [row[:12] + [False] * (12 - len(row[:12])) for row in ink]
            self.assertEqual(font.numeral(ink), value, value)
        self.assertIsNone(font.numeral([[False] * 5] * 5))


def popup(region="Giant's Glass", stages=(918, 919, 920), first_y=0.479, cut=None):
    """A synthetic Select Region pop-up: title, banner, rows 0.126 apart
    with their name and an orange Move button. cut: a row index whose
    button runs past the list's bottom."""
    canvas = Canvas()
    canvas.text("Select Region", 0.35, 0.247, scale=3, colour=(200, 200, 200))
    canvas.rect((0.18, 0.297, 0.82, 0.324), (40, 104, 84))
    canvas.text(region, 0.38, 0.303, scale=2)
    for i, stage in enumerate(stages):
        y = first_y + 0.126 * i
        canvas.rect((0.10, y - 0.03, 0.90, y + 0.09), (52, 44, 38))
        value = (stage - 1) % 20 + 1
        roman = ""
        for letters, amount in (("X", 10), ("IX", 9), ("V", 5), ("IV", 4), ("I", 1)):
            while value >= amount:
                roman += letters
                value -= amount
        canvas.text(f"{region} {roman}", 0.145, y, scale=2)
        bottom = 0.86 if i == cut else y + 0.05
        canvas.rect((0.69, y + 0.0, 0.87, min(bottom, 0.99)), (232, 148, 40))
    return canvas.shot()


class SelectRegion(unittest.TestCase):
    def test_regions(self):
        self.assertEqual(NAMES[GIANT - 1:GIANT + 2], ["Ancient Ruins", "Giant's Glass", "Desert Gorge"])
        self.assertEqual(GIANT, (901 - 1) // 20)
        self.assertIsNone(NAMES[0])  # the first stages are named apart

    def test_view(self):
        view = select.view(popup(), NAMES)
        self.assertTrue(view["popup"])
        self.assertEqual(view["region"], GIANT)
        self.assertEqual([row["stage"] for row in view["rows"]], [918, 919, 920])
        for row, y in zip(view["rows"], (0.479, 0.605, 0.731)):
            self.assertAlmostEqual(row["y"], y, delta=0.002)
            # The button's middle: halfway down its 0.05.
            self.assertAlmostEqual(row["move"], y + 0.025, delta=0.003)

    def test_other_region(self):
        view = select.view(popup("Desert Gorge", (921, 922)), NAMES)
        self.assertEqual((view["region"], [row["stage"] for row in view["rows"]]), (GIANT + 1, [921, 922]))

    def test_button_cut_by_the_list(self):
        view = select.view(popup(stages=(918, 919, 920), cut=2), NAMES)
        self.assertIsNone(view["rows"][2]["move"])
        self.assertIsNotNone(view["rows"][1]["move"])

    def test_no_popup(self):
        canvas = Canvas()
        canvas.text("Battle settings", 0.30, 0.247, scale=3)
        self.assertEqual(select.view(canvas.shot(), NAMES), {"popup": False, "region": None, "rows": []})

    def test_battle_stage(self):
        canvas = Canvas((120, 150, 140))
        canvas.rect((0.315, 0.066, 0.655, 0.088), (30, 30, 30))
        canvas.text("Giant's Glass XX", 0.35, 0.070, scale=2)
        self.assertEqual(select.battle_stage(canvas.shot(), NAMES), 920)
        self.assertIsNone(select.battle_stage(Canvas((30, 30, 30)).shot(), NAMES))


def gear(canvas, angle, label=True):
    """The AUTO tile with a gear of 6 teeth turned by angle."""
    canvas.rect((0.875, 0.424, 0.995, 0.466), (180, 180, 180))
    cx, cy = 0.934 * W, 0.442 * H
    for y in range(int(0.430 * H), int(0.454 * H)):
        for x in range(int(0.906 * W), int(0.963 * W)):
            r, a = math.hypot(x - cx, y - cy), math.atan2(y - cy, x - cx) - angle
            tooth = math.cos(6 * a) > 0.3
            if 4 < r < (12 if tooth else 9):
                canvas.pixels[(y * W + x) * 3:(y * W + x) * 3 + 3] = bytes((70, 70, 70))
    if label:
        canvas.text("AUTO", 0.905, 0.455, scale=1)


def battle(angle, fight=0, label=True, grey=False, badge=None):
    canvas = Canvas((60, 90, 80))
    canvas.rect((0.10 + 0.01 * fight, 0.32, 0.30 + 0.01 * fight, 0.40), (230, 60, 60))  # the fight moves
    for area in controls.SKILLS:
        canvas.rect(area, (90, 90, 90) if grey else (220, 120, 30))
    gear(canvas, angle, label)
    if badge:
        canvas.rect((0.95, 0.395, 0.99, 0.415), (150, 150, 150))
        canvas.text(badge, 0.955, 0.4005, scale=1)
    return canvas.shot()


class Controls(unittest.TestCase):
    def test_spinning_gear_is_on(self):
        self.assertEqual(controls.auto(battle(0.0, 0, grey=True), battle(0.25, 3, grey=True)), "on")

    def test_still_gear_is_off(self):
        self.assertEqual(controls.auto(battle(0.0, 0), battle(0.0, 3)), "off")

    def test_cannot_tell(self):
        # The same frame twice (the fight did not move): nothing is told.
        self.assertIsNone(controls.auto(battle(0.0, 0), battle(0.0, 0)))
        # Folded (no AUTO label): nothing either.
        self.assertIsNone(controls.auto(battle(0.0, 0, label=False), battle(0.3, 3, label=False)))
        # A still gear, but the skills cool down: the hints disagree.
        self.assertIsNone(controls.auto(battle(0.0, 0, grey=True), battle(0.0, 3, grey=True)))

    def test_badge(self):
        self.assertEqual(controls.badge(battle(0.0, badge="III")), "III")
        self.assertEqual(controls.badge(battle(0.0, badge="IV")), "IV")
        self.assertIsNone(controls.badge(battle(0.0)))
        self.assertTrue(controls.folded(battle(0.0, label=False)))
        self.assertFalse(controls.folded(battle(0.0, badge="II")))

    def settings(self, chosen):
        canvas = Canvas()
        canvas.text("Battle settings", 0.035, 0.232, scale=3)
        for i, x in enumerate(controls.PRESET_X):
            if controls.NUMERALS[i] == chosen:
                canvas.rect((x - 0.062, 0.276, x + 0.062, 0.334), (255, 255, 255))
                canvas.rect((x - 0.052, 0.281, x + 0.052, 0.329), (20, 20, 20))
            canvas.text(controls.NUMERALS[i], x - 0.015, 0.297, scale=2,
                        colour=(255, 255, 255) if controls.NUMERALS[i] == chosen else (70, 70, 70))
        return canvas.shot()

    def test_settings(self):
        for name in controls.NUMERALS:
            shot = self.settings(name)
            self.assertTrue(controls.settings_open(shot))
            self.assertEqual(controls.selected(shot), name)
        self.assertIsNone(controls.selected(self.settings(None)))
        self.assertFalse(controls.settings_open(popup()))


if __name__ == "__main__":
    unittest.main()
