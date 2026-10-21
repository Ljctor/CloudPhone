"""The readers on crops of real captures (fixtures/: the region banner,
stage rows, battle stage names, the unfolded controls, Battle settings'
title and presets; never a full screen, nothing with the account's name),
each pasted back where it was on an empty 480x1040 screen, and the pixel
font's confusion matrix on the texts they hold.
Run: python3 -m unittest test_fixtures"""

import collections
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


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
# The text each crop holds, and how it is read (channel, level).
TEXTS = {
    "title_select_region": ("Select Region", max, None),
    "banner_giants_glass": ("Giant's Glass", max, None),
    "row_913": ("Giant's Glass XIII", max, None),
    "row_914": ("Giant's Glass XIV", max, None),
    "row_915": ("Giant's Glass XV", max, None),
    "row_918": ("Giant's Glass XVIII", max, None),
    "row_919": ("Giant's Glass XIX", max, None),
    "row_920": ("Giant's Glass XX", max, None),
    "battle_name_920": ("Giant's Glass XX", min, select.WHITE_TEXT),
    "battle_name_920_b": ("Giant's Glass XX", min, select.WHITE_TEXT),
    "settings_title": ("Battle settings", max, None),
}


def crop(name):
    """(screen width, height, left, top, width, height, rgb bytes)."""
    with open(os.path.join(FIXTURES, f"{name}.txt"), encoding="ascii") as f:
        lines = [line.strip() for line in f if not line.startswith("#")]
    sw, sh, x, y, w, h = map(int, lines[0].split())
    return sw, sh, x, y, w, h, b"".join(bytes.fromhex(row) for row in lines[1:1 + h])


def screen(*names, colour=(20, 16, 14)):
    """An empty screen with the crops pasted back where they were."""
    sw, sh = crop(names[0])[:2]
    pixels = bytearray(bytes(colour) * (sw * sh))
    for name in names:
        _, _, x, y, w, h, data = crop(name)
        for row in range(h):
            start = ((y + row) * sw + x) * 3
            pixels[start:start + w * 3] = data[row * w * 3:(row + 1) * w * 3]
    return (sw, sh, bytes(pixels))


def area_of(name):
    sw, sh, x, y, w, h, _ = crop(name)
    return (x / sw, y / sh, (x + w) / sw, (y + h) / sh)


def glyphs(name):
    """[(truth, read)] glyph by glyph, when the cut gives as many glyphs as
    the text has characters; else None."""
    truth, channel, level = TEXTS[name]
    shot = screen(name)
    marks = font.ink(font.crop(shot, area_of(name), channel), level)
    found = font.lines(marks)
    if not found:
        return None
    top, bottom = max(found, key=lambda line: line[1] - line[0])
    read = [char for word in font.read_line(marks, top, bottom) for char, _, _ in word]
    chars = truth.replace(" ", "")
    return list(zip(chars, read)) if len(read) == len(chars) else None


class Readings(unittest.TestCase):
    def test_title_and_banner(self):
        shot = screen("title_select_region", "banner_giants_glass")
        self.assertTrue(select.popup(shot))
        self.assertEqual(select.banner(shot, NAMES), GIANT)

    def test_rows(self):
        for name in ("row_913", "row_914", "row_915", "row_918", "row_919", "row_920"):
            shot = screen(name)
            lines = [text for text, _, _ in font.read(shot, area_of(name))]
            words = lines[0].split(" ")
            self.assertEqual(font.roman(words[-1]) + GIANT * 20, int(name[-3:]), lines)
            self.assertEqual(select.which(" ".join(words[:-1]), NAMES), GIANT, lines)

    def test_battle_stage_name(self):
        for name in ("battle_name_920", "battle_name_920_b"):
            self.assertEqual(select.battle_stage(screen(name), NAMES), 920, name)

    def test_unfolded_controls(self):
        self.assertEqual(controls.badge(screen("controls_iii_auto_on")), "III")
        self.assertEqual(controls.badge(screen("controls_iv")), "IV")
        for name in ("controls_iii_auto_on", "controls_iv"):
            shot = screen(name)
            self.assertTrue(controls.auto_label(shot), name)
            self.assertEqual(controls.controls(shot), "unfolded", name)

    def test_taps_land_on_the_unfolded_controls(self):
        """The second tap of the unfold call, checked on the unfolded
        capture: the badge's tap on its numeral, the gear's on the AUTO
        tile; and the folded arrow's spot is on that tile once unfolded
        (why the controls must read folded before the arrow is tapped)."""
        sw, sh, data = screen("controls_iii_auto_on")

        def pixel(point):
            i = (int(point[1] * sh) * sw + int(point[0] * sw)) * 3
            return data[i:i + 3]

        white = [(x, y) for y in range(int(0.395 * sh), int(0.42 * sh)) for x in range(int(0.94 * sw), sw)
                 if min(data[(y * sw + x) * 3:(y * sw + x) * 3 + 3]) > 200]
        xs, ys = [x for x, _ in white], [y for _, y in white]
        bx, by = controls.BADGE_TAP[0] * sw, controls.BADGE_TAP[1] * sh
        self.assertTrue(min(xs) <= bx <= max(xs) and min(ys) <= by <= max(ys), (min(xs), max(xs), min(ys), max(ys)))
        for point in (controls.AUTO_TAP, controls.ARROW_TAP):
            r, g, b = pixel(point)
            self.assertTrue(max(r, g, b) - min(r, g, b) < 20 and max(r, g, b) > 150, (point, (r, g, b)))

    def test_battle_settings(self):
        shot = screen("settings_title", "settings_presets_iii")
        self.assertTrue(controls.settings_open(shot))
        self.assertEqual(controls.selected(shot), "III")

    @unittest.skipUnless(os.path.exists(os.path.join(FIXTURES, "controls_auto_off_1.txt")),
                         "no real capture with AUTO off yet: its two frames recalibrate auto()")
    def test_auto_both_states(self):
        self.assertEqual(controls.auto(screen("controls_auto_on_1"), screen("controls_auto_on_2")), "on")
        self.assertEqual(controls.auto(screen("controls_auto_off_1"), screen("controls_auto_off_2")), "off")


class Confusion(unittest.TestCase):
    def matrix(self):
        counts = collections.defaultdict(collections.Counter)
        uncut = []
        for name in TEXTS:
            pairs = glyphs(name)
            if pairs is None:
                uncut.append(name)
                continue
            for truth, read in pairs:
                counts[truth][read or "?"] += 1
        return counts, uncut

    def test_confusion_matrix(self):
        counts, uncut = self.matrix()
        wrong = {truth: dict(row) for truth, row in counts.items() if set(row) != {truth}}
        total = sum(sum(row.values()) for row in counts.values())
        right = sum(row[truth] for truth, row in counts.items())
        # The banner's letters touch: its cut may differ, the rest must not.
        self.assertLessEqual(set(uncut), {"banner_giants_glass"}, uncut)
        self.assertGreaterEqual(right / total, 0.95, wrong)
        # The numerals that name the stages are never confused.
        for numeral in "IVX":
            self.assertEqual(set(counts[numeral]), {numeral}, wrong)


if __name__ == "__main__":
    unittest.main()
