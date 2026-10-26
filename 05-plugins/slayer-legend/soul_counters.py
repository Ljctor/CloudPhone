"""Reads the souls counters off a Slayer Legend screenshot (width, height,
RGB bytes): the Equipment panel's row under its tabs, shown on the
Weapon tab and on the Soul Weapon screen (the farming modes' parking
screen). Four boxes, each a round icon then its count, right-aligned:
green, blue, red and white souls, « 94.6C », « 19.4C », « 16.1C »,
« 4.64C », then a refresh icon. Pure, stdlib only.

The count is written in the game's pixel font (pixel_font.py) at about
9/7 of its size, white over a one-pixel grey shadow: the ink is the white
alone. Its notation is the gold counter's (gold.parse): abbreviated, or
in full digits once the game's option says so; the full digits are read
only once FULL_DIGITS_CALIBRATED (a real capture of them a fixture).

Measured on real 480x1040 captures (2026-10-22, the Soul Weapon screen
open on Vision): fixtures/souls_row, souls_row_b.
"""

import importlib.util
import os


def _sibling(name):
    spec = importlib.util.spec_from_file_location(
        f"cloudphone_plugin_slayer_legend_souls_{name}", os.path.join(os.path.dirname(__file__), f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


font = _sibling("pixel_font")
gold = _sibling("gold")

COLOURS = ("green", "blue", "red", "white")
# Each box's icon and its text, (left, top, right, bottom) in pixels at
# 480x1040; the text runs from the icon to the box's right edge (full
# digits are wider, still right-aligned).
ICONS = {"green": (87, 498, 100, 511), "blue": (181, 498, 193, 510), "red": (274, 498, 287, 510),
         "white": (368, 498, 380, 510)}
TEXTS = {"green": (104, 491, 166, 516), "blue": (197, 491, 260, 516), "red": (291, 491, 353, 516),
         "white": (384, 491, 446, 516)}
# The text's white: the shadow (138) and the icons stay under it.
WHITE = 200
# A box with no dark background is no counter (another screen).
BACKGROUND = (25, 23, 21)

# The glyphs, cut from the fixtures (each the ink of its occurrences, more
# than half: "." 8, "1" 6, "4" 8, "6" 5, "9" 4, "C" 8, "7" 1), CAP rows and
# two below as pixel_font's. DRAWN: not seen yet, drawn in the same style;
# a reading with one of them is checked on a capture once one shows it.
CUT = {
    ".": [".", ".", ".", ".", ".", ".", "#", ".", "."],
    "1": [".#.", "##.", ".#.", ".#.", ".#.", "##.", "###", "...", "..."],
    "4": ["...#.", "..##.", ".###.", ".#.#.", "#####", "...#.", "...#.", ".....", "....."],
    "6": [".##.", ".##.", "##..", "###.", "#..#", "#..#", ".##.", "....", "...."],
    "7": ["####", "####", "...#", "..#.", "..#.", ".##.", "....", "....", "...."],
    "9": [".##.", "####", "#..#", "##.#", ".###", "..##", ".##.", "....", "...."],
    "C": [".###", "####", "#...", "#...", "#...", "#...", ".###", "....", "...."],
}
DRAWN = {
    "0": [".##.", "#..#", "#..#", "#..#", "#..#", "#..#", ".##.", "....", "...."],
    "2": [".##.", "#..#", "...#", "..#.", ".#..", "#...", "####", "....", "...."],
    "3": ["###.", "...#", "...#", ".##.", "...#", "...#", "###.", "....", "...."],
    "5": ["####", "#...", "###.", "...#", "...#", "#..#", ".##.", "....", "...."],
    "8": [".##.", "#..#", "#..#", ".##.", "#..#", "#..#", ".##.", "....", "...."],
    "A": [".##.", "#..#", "#..#", "####", "#..#", "#..#", "#..#", "....", "...."],
    "B": ["###.", "#..#", "#..#", "###.", "#..#", "#..#", "###.", "....", "...."],
    "D": ["###.", "#..#", "#..#", "#..#", "#..#", "#..#", "###.", "....", "...."],
    "E": ["####", "#...", "#...", "###.", "#...", "#...", "####", "....", "...."],
    "F": ["####", "#...", "#...", "###.", "#...", "#...", "#...", "....", "...."],
    "G": [".###", "#...", "#...", "#.##", "#..#", "#..#", ".###", "....", "...."],
    "H": ["#..#", "#..#", "#..#", "####", "#..#", "#..#", "#..#", "....", "...."],
}
FONT = {**DRAWN, **CUT}
# Full digits read only once a real capture of them is a fixture
# (test_gates.py: fixtures/souls_full); until then such a reading is None.
FULL_DIGITS_CALIBRATED = False


def _area(shot, box):
    """A box in pixels at 480x1040 as fractions of the screen."""
    left, top, right, bottom = box
    return (left / 480, top / 1040, right / 480, bottom / 1040)


def _icon(colour, r, g, b):
    if colour == "green":
        return g > 120 and g > r + 40 and g > b + 40
    if colour == "blue":
        return b > 150 and b > r + 60 and b > g + 30
    if colour == "red":
        return r > 150 and r > g + 60 and r > b + 60
    return min(r, g, b) > 150 and max(r, g, b) - min(r, g, b) < 30


def _share(shot, area, test):
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    hits = sum(bool(test(*pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]))
               for y in range(top, bottom) for x in range(left, right))
    return hits / ((right - left) * (bottom - top))


def shown(shot):
    """The row is on screen: every box's icon in its colour, the boxes'
    dark background left of the counts."""
    dark = lambda r, g, b: all(abs(v - c) <= 8 for v, c in zip((r, g, b), BACKGROUND))
    for colour in COLOURS:
        if _share(shot, _area(shot, ICONS[colour]), lambda r, g, b: _icon(colour, r, g, b)) < 0.2:
            return False
        left, top, right, bottom = TEXTS[colour]
        if _share(shot, _area(shot, (left, top, left + 8, bottom)), dark) < 0.8:
            return False
    return True


def read_text(shot, colour):
    """The count of one box as read ("94.6C", "?" for an unread glyph), or
    None when the box shows no text."""
    rows = font.crop(shot, _area(shot, TEXTS[colour]), min)
    marks = font.ink(rows, WHITE)
    if not marks:
        return None
    found = font.lines(marks)
    if not found:
        return None
    top, bottom = max(found, key=lambda line: line[1] - line[0])
    words = font.read_line(marks, top, bottom, font=FONT, space=1.0)
    return "".join(char.split("~")[0] if char else "?" for word in words for char, _, _ in word) or None


def read(shot):
    """{colour: {text, value, step, full} or None (unread)} for the four
    boxes, or None when the row is not on screen."""
    if not shown(shot):
        return None
    counts = {}
    for colour in COLOURS:
        text = read_text(shot, colour)
        parsed = gold.parse(text) if text and "?" not in text else None
        if parsed and parsed["full"] and not FULL_DIGITS_CALIBRATED:
            parsed = None
        counts[colour] = {"text": gold.normalize_text(text), **parsed} if parsed else None
    return counts
