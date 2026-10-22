"""The pixel font against the fixtures it was cut from (fixtures/texts.json):
every text reads back exactly but for the characters not cut yet, close
letters stay apart by a margin, the soul weapons' and regions' names
survive render() then read(), and the glyphs still drawn are the ones
docs/TODO.md lists. Run: python3 -m unittest test_font"""

import importlib.util
import json
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TODO = os.path.join(HERE, "..", "..", "docs", "TODO.md")


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cutter = load("font_cut")
font = cutter.font
select = load("stage_select")
# Characters cut from the fixtures (averaged over two occurrences or more).
CUT = {key[0] for key in font.SOURCES}
# The close pairs, and how far apart (distance) a real glyph must read
# from the other letters of its group than from its own.
GROUPS = ("Il1", "O0DQ", "ce", "uv", "nh")
# Measured on the fixtures (2026-10-22): h/n 0.019 the closest, then n/h
# 0.029, e/c 0.031, O/0 0.042, 0/D 0.051, O/D 0.056, c/e 0.057, l/I 0.087,
# u/v 0.106, I/l 0.116, v/u 0.131.
MARGIN = 0.015


# Characters cut, but not yet from their own size in one fixture: there
# they may read as their look-alike. Listed in docs/TODO.md (« Read wrong
# at one size: »), to shrink with the calibration captures.
WAITING = {
    # The only small 0 (cap 8 px); the 0s cut are cap 12-13 (eg_popup_*):
    # a second « Owned : 0 » gives the small 0 its own shape.
    ("sw_owned_0", "0"): "O",
    # The tag's U (5 px wide at cap 9) against AUTO's two (6 px at cap 8):
    # its width reads closer to u; a second tag (capture 10's Equip and
    # Unequip) gives it its own shape.
    ("sw_tag_unequip", "U"): "u",
}


def todo(prefix):
    """docs/TODO.md's paragraph that starts with prefix, as one line."""
    with open(TODO, encoding="utf-8") as f:
        text = f.read()
    start = text.index("\n" + prefix) + 1
    end = text.find("\n\n", start)
    return " ".join(text[start:end if end >= 0 else None].split())


def pending(text, fixture=None):
    """The characters of text the font has not cut yet (or not at this
    fixture's size, WAITING)."""
    return sorted({c for c in text if c != " " and (c not in CUT or (fixture, c) in WAITING)})


def lines_read(entry):
    """[(truth, words)] for each text line of a texts.json entry."""
    marks, lines = cutter.ink_of(entry)
    return marks, [(truth, (top, bottom), font.read_line(marks, top, bottom))
                   for (top, bottom), truth in zip(lines, entry["text"])]


READ = [entry for entry in cutter.texts() if entry.get("read") is not False]


class ReadBack(unittest.TestCase):
    def test_every_text_reads_back(self):
        """Exactly, glyph for glyph; a character not cut yet may read as
        anything (one or two glyphs, or None), never one that is cut."""
        for entry in READ:
            _, found = lines_read(entry)
            self.assertEqual(len(found), len(entry["text"]), entry["fixture"])
            for truth, _, words in found:
                read = font.text(words)
                waiting = pending(truth, entry["fixture"])
                expected = "".join(".{1,2}" if c in waiting else re.escape(c) for c in truth)
                self.assertRegex(read, f"^{expected}$", (entry["fixture"], truth, waiting))

    def test_pending_characters(self):
        """The characters the fixtures show but the font has not cut (seen
        once): docs/TODO.md's « Characters seen once: » line."""
        waiting = {c for entry in READ for line in entry["text"] for c in pending(line)}
        line = todo("Characters seen once:")
        self.assertEqual(waiting, set(re.findall(r"`(.)`", line)))

    def test_waiting_is_listed(self):
        line = todo("Read wrong at one size:")
        for fixture, char in WAITING:
            self.assertIn(f"`{char}` in `{fixture}`", line)


class Confusion(unittest.TestCase):
    def margins(self):
        """[(truth, own distance, the closest other of its group, its
        distance)] for every real glyph of a group, read where the cut gives
        as many glyphs as the line has characters."""
        found = []
        for entry in READ:
            marks, lines = lines_read(entry)
            for truth, (top, bottom), words in lines:
                glyphs = [cut for word in words for _, _, cut in word]
                chars = truth.replace(" ", "")
                if len(glyphs) != len(chars):
                    continue
                _, cap = font.metrics(marks, top, bottom)
                box_bottom = top + round(cap * font.ROWS / font.CAP) - 1
                for char, (left, right) in zip(chars, glyphs):
                    group = next((g for g in GROUPS if char in g), None)
                    others = [c for c in group or "" if c != char and any(key[0] == c for key in font.FONT)]
                    if not others or char not in CUT or (entry["fixture"], char) in WAITING:
                        continue
                    box = (left, right, top, box_bottom)
                    own = font.match(marks, box, cap, only=[char])[1]
                    other, distance = font.match(marks, box, cap, only=others)
                    found.append((char, own, other, distance))
        return found

    def test_close_letters_stay_apart(self):
        found = self.margins()
        self.assertTrue(found)
        for char, own, other, distance in found:
            self.assertGreaterEqual(distance - own, MARGIN, (char, other, round(own, 4), round(distance, 4)))

    def test_rn_is_not_m_and_drawn_pairs(self):
        marks_of = lambda string, scale: [[bool(v) for v in row] for row in font.render(string, scale)]
        for string in ("rn", "m", "Il", "ce", "uv", "nh", "OD"):
            for scale in (2, 3):
                marks = marks_of("X" + string, scale)
                (top, bottom), = font.lines(marks)
                self.assertEqual(font.text(font.read_line(marks, top, bottom)).replace(" ", ""), "X" + string,
                                 (string, scale))


def names_cut(names):
    """(names whose every character is in the font, the others)."""
    known = {key[0] for key in font.FONT}
    return ([n for n in names if set(n) - {" "} <= known], [n for n in names if not set(n) - {" "} <= known])


class RoundTrip(unittest.TestCase):
    def round_trip(self, names):
        readable, left = names_cut(names)
        for name in readable:
            for scale in (2, 3):
                marks = [[bool(v) for v in row] for row in font.render(name, scale)]
                found = font.lines(marks)
                self.assertEqual(len(found), 1, name)
                read = font.text(font.read_line(marks, *found[0]))
                self.assertEqual(read, name, (name, scale))
        return readable, left

    def test_soul_weapon_names(self):
        with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
            names = [w["name"] for w in json.load(f)["weapons"]]
        self.assertEqual(len(names), 89)
        readable, left = self.round_trip(names)
        # Every name waits only for characters the font lacks.
        for name in left:
            self.assertTrue(set(name) - {" "} - {key[0] for key in font.FONT}, name)

    def test_region_names(self):
        with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
            names = [n for n in select.regions(json.load(f)) if n]
        readable, left = self.round_trip(names)
        for name in left:
            self.assertTrue(set(name) - {" "} - {key[0] for key in font.FONT}, name)


class StillDrawn(unittest.TestCase):
    def test_todo_lists_the_glyphs_not_cut(self):
        """docs/TODO.md's « Glyphs not cut yet: » line names exactly the
        drawn glyphs and those cut once (to shrink toward none)."""
        line = todo("Glyphs not cut yet:")
        listed = set(re.findall(r"`(.)`", line))
        self.assertEqual(listed, set(font.DRAWN) | set(font.CUT_ONCE))
        for char in listed:
            self.assertNotIn(char, CUT, f"{char} is cut now: take it out of DRAWN/CUT_ONCE and TODO")

    def test_every_cut_shape_has_two_occurrences(self):
        for key, (count, fixtures) in font.SOURCES.items():
            self.assertGreaterEqual(count, cutter.LEAST, key)
            self.assertTrue(fixtures, key)


if __name__ == "__main__":
    unittest.main()
