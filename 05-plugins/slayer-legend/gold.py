"""Reads the gold counter off a Slayer Legend screenshot (width, height, RGB
bytes): "<coin> 111F" in white with a black outline, centred under the
stage name. Its height on screen depends on the panel open below the
battle, so the band where it may be is searched; Power Saving Mode does
not show it.

The amount is a number with up to 3 significant digits and a unit letter:
A is a thousand, B a thousand A, and so on.
"""

import importlib.util
import os

# The stage reader's glyph matching, loaded beside this file (the gateway
# loads plugin files by path, not as a package).
_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_gold_stage", os.path.join(os.path.dirname(__file__), "stage.py"))
stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage)

# Where the counter may be, as (left, top, right, bottom) fractions.
BAND = (0.25, 0.10, 0.85, 0.30)
# Its text is 13 px high at 480x1040.
TEXT_HEIGHT = 13 / 1040

# The counter's glyphs as the game draws them at 480x1040: 13 rows, 2 px
# strokes (8 and the letters other than F are drawn in the same style).
DIGITS = {
    "0": [".######.", "########", "##....##", "##....##", "##....##", "##....##", "##....##",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "1": [".##..", "###..", "###..", ".##..", ".##..", ".##..", ".##..", ".##..", ".##..",
          ".##..", "#####", "#####", "#####"],
    "2": [".######.", "########", "##....##", "......##", "....####", "....###.", "...##...",
          ".####...", ".##.....", "##......", "########", "########", "########"],
    "3": [".######.", "########", "##....##", "......##", "...#####", "...####.", "......##",
          "......##", "......##", "##....##", "########", ".######.", ".######."],
    "4": ["......##..", "....####..", "....####..", "...##.##..", ".####.##..", ".##...##..",
          "##....##..", "##########", "##########", "......##..", "......##..", "......##..",
          "......##.."],
    "5": ["########", "########", "##......", "##......", "#######.", "#######.", "......##",
          "......##", "......##", "##....##", "########", ".######.", ".######."],
    "6": ["...####.", ".######.", ".##.....", "##......", "#######.", "#######.", "##....##",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "7": ["########", "########", "......##", "......##", "....####", "....###.", "....###.",
          "...####.", "...##...", "...##...", "...##...", "...##...", "...##..."],
    "8": [".######.", "########", "##....##", "##....##", "########", ".######.", "##....##",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "9": [".######.", "########", "##....##", "##....##", "##....##", "##....##", ".#######",
          ".#######", "......##", ".....##.", ".#####..", ".###....", ".###...."],
}
LETTERS = {
    "A": ["..####..", ".######.", "##....##", "##....##", "##....##", "########", "########",
          "##....##", "##....##", "##....##", "##....##", "##....##", "##....##"],
    "B": ["#######.", "########", "##....##", "##....##", "#######.", "#######.", "##....##",
          "##....##", "##....##", "##....##", "########", "#######.", "#######."],
    "C": [".######.", "########", "##....##", "##......", "##......", "##......", "##......",
          "##......", "##......", "##....##", "########", ".######.", ".######."],
    "D": ["######..", "#######.", "##...###", "##....##", "##....##", "##....##", "##....##",
          "##....##", "##....##", "##...###", "#######.", "######..", "######.."],
    "E": ["########", "########", "##......", "##......", "########", "########", "##......",
          "##......", "##......", "##......", "########", "########", "########"],
    "F": ["########", "########", "##......", "##......", "########", "########", "##......",
          "##......", "##......", "##......", "##......", "##......", "##......"],
    "G": [".######.", "########", "##....##", "##......", "##......", "##..####", "##..####",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "H": ["##....##", "##....##", "##....##", "##....##", "########", "########", "##....##",
          "##....##", "##....##", "##....##", "##....##", "##....##", "##....##"],
    "I": ["######", "######", "..##..", "..##..", "..##..", "..##..", "..##..", "..##..",
          "..##..", "..##..", "######", "######", "######"],
    "J": ["....####", "....####", "......##", "......##", "......##", "......##", "......##",
          "......##", "......##", "##....##", "########", ".######.", ".######."],
    "K": ["##....##", "##...###", "##..###.", "##.###..", "#####...", "####....", "#####...",
          "##.###..", "##..###.", "##...###", "##....##", "##....##", "##....##"],
    "L": ["##......", "##......", "##......", "##......", "##......", "##......", "##......",
          "##......", "##......", "##......", "########", "########", "########"],
    "M": ["##.....##", "###...###", "####.####", "##.###.##", "##..#..##", "##.....##", "##.....##",
          "##.....##", "##.....##", "##.....##", "##.....##", "##.....##", "##.....##"],
    "N": ["##....##", "###...##", "####..##", "##.##.##", "##..####", "##...###", "##....##",
          "##....##", "##....##", "##....##", "##....##", "##....##", "##....##"],
    "O": [".######.", "########", "##....##", "##....##", "##....##", "##....##", "##....##",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "P": ["#######.", "########", "##....##", "##....##", "##....##", "########", "#######.",
          "##......", "##......", "##......", "##......", "##......", "##......"],
    "Q": [".######.", "########", "##....##", "##....##", "##....##", "##....##", "##....##",
          "##.##.##", "##..####", "##...###", "########", ".#######", ".#######"],
    "R": ["#######.", "########", "##....##", "##....##", "##....##", "########", "#######.",
          "##.###..", "##..###.", "##...###", "##....##", "##....##", "##....##"],
    "S": [".######.", "########", "##....##", "##......", "#######.", ".#######", "......##",
          "......##", "......##", "##....##", "########", ".######.", ".######."],
    "T": ["########", "########", "...##...", "...##...", "...##...", "...##...", "...##...",
          "...##...", "...##...", "...##...", "...##...", "...##...", "...##..."],
    "U": ["##....##", "##....##", "##....##", "##....##", "##....##", "##....##", "##....##",
          "##....##", "##....##", "##....##", "########", ".######.", ".######."],
    "V": ["##....##", "##....##", "##....##", "##....##", "##....##", "##....##", "##....##",
          ".##..##.", ".##..##.", ".##..##.", "..####..", "...##...", "...##..."],
    "W": ["##.....##", "##.....##", "##.....##", "##.....##", "##.....##", "##..#..##", "##.###.##",
          "####.####", "###...###", "##.....##", "##.....##", "##.....##", "##.....##"],
    "X": ["##....##", "##....##", ".##..##.", ".##..##.", "..####..", "...##...", "..####..",
          ".##..##.", ".##..##.", "##....##", "##....##", "##....##", "##....##"],
    "Y": ["##....##", "##....##", "##....##", ".##..##.", ".##..##.", "..####..", "...##...",
          "...##...", "...##...", "...##...", "...##...", "...##...", "...##..."],
    "Z": ["########", "########", "......##", ".....##.", "....##..", "...##...", "..##....",
          ".##.....", "##......", "##......", "########", "########", "########"],
}

# Signs the page needs to write the rate in the same font (drawn in the
# same style; the game's counter never shows them).
SIGNS = {
    ".": ["..", "..", "..", "..", "..", "..", "..", "..", "..", "..", "##", "##", "##"],
    "(": ["..##", ".##.", ".##.", "##..", "##..", "##..", "##..", "##..", "##..", "##..", ".##.", ".##.", "..##"],
    ")": ["##..", ".##.", ".##.", "..##", "..##", "..##", "..##", "..##", "..##", "..##", ".##.", ".##.", "##.."],
    "/": [".....##", ".....##", "....##.", "....##.", "...##..", "...##..", "..##...", "..##...",
          ".##....", ".##....", "##.....", "##.....", "##....."],
    "s": ["......", "......", "......", "......", ".#####", "######", "##....", "#####.", ".#####",
          "....##", "######", "#####.", "#####."],
    " ": ["...."] * 13,
    ":": ["..", "..", "..", "##", "##", "##", "..", "..", "..", "##", "##", "##", ".."],
    "~": ["......", "......", "......", "......", ".##..#", "######", "#..##.", ".##..#", "######",
          "#..##.", "......", "......", "......"],
}


def _grey(pixels, i, low, high):
    r, g, b = pixels[i], pixels[i + 1], pixels[i + 2]
    return max(r, g, b) - min(r, g, b) <= 4 and low <= r <= high


def _coin(r, g, b):
    return r > 220 and 120 < g < 215 and b < 90


def _ink(shot, x0, y0, x1, y1, low=140):
    """The counter's text: light grey to white pixels (from `low`) within
    2 px of a near-black one. Text and outline are pure greys (r = g = b;
    the game scales its font, so edges are mid greys); the background is
    tinted."""
    width, height, pixels = shot
    ink = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            on = False
            if _grey(pixels, (y * width + x) * 3, low, 255):
                for dy in (-2, -1, 0, 1, 2):
                    for dx in (-2, -1, 0, 1, 2):
                        if 0 <= x + dx < width and 0 <= y + dy < height \
                                and _grey(pixels, ((y + dy) * width + x + dx) * 3, 0, 60):
                            on = True
            row.append(on)
        ink.append(row)
    return ink


def _glyphs(ink, top, bottom):
    """Runs of columns with ink between rows top and bottom, as glyphs
    (left, right, top, bottom) with their own ink's height."""
    width = len(ink[0])
    used = [any(ink[y][x] for y in range(top, bottom + 1)) for x in range(width)]
    found, x = [], 0
    while x < width:
        if not used[x]:
            x += 1
            continue
        right = x
        while right + 1 < width and used[right + 1]:
            right += 1
        ys = [y for y in range(top, bottom + 1) if any(ink[y][x:right + 1])]
        found.append((x, right, ys[0], ys[-1]))
        x = right + 1
    return found


def read(shot):
    """The counter as {text: "111F", value: 1.11e20, box: [left, top, right,
    bottom] as fractions of the screen}, or None when it is not on screen
    or not readable."""
    width, height, pixels = shot
    x0, y0 = int(BAND[0] * width), int(BAND[1] * height)
    x1, y1 = int(BAND[2] * width), int(BAND[3] * height)
    ink = _ink(shot, x0, y0, x1, y1)
    # Pure white only: the mid grey edges join neighbouring glyphs, so
    # glyphs are cut apart on this, and read on all the ink.
    core = _ink(shot, x0, y0, x1, y1, 245)
    line = TEXT_HEIGHT * height
    counts = [sum(row) for row in ink]
    y = 0
    while y < len(ink):
        if counts[y] < 2:
            y += 1
            continue
        top = y
        while y < len(ink) and counts[y] >= 1:
            y += 1
        bottom = y - 1
        if not 0.8 * line <= bottom - top + 1 <= 1.25 * line:
            continue
        glyphs = []
        for left, right, _, _ in _glyphs(core, top, bottom):
            ys = [row for row in range(top, bottom + 1) if any(ink[row][left:right + 1])]
            if ys and ys[-1] - ys[0] + 1 >= 0.15 * line:
                glyphs.append((left, right, ys[0], ys[-1]))
        # Glyphs belong together when the gaps are small; keep the group
        # with a coin just left of it.
        groups, group = [], []
        for glyph in glyphs:
            if group and glyph[0] - group[-1][1] > 0.4 * line:
                groups.append(group)
                group = []
            group.append(glyph)
        if group:
            groups.append(group)
        for group in groups:
            if len(group) < 2:
                continue
            reading = _read_group(shot, ink, group, x0, y0, top, bottom, line)
            if reading:
                return reading
    return None


def _read_group(shot, ink, group, x0, y0, top, bottom, line):
    width, height, pixels = shot
    # The coin: gold pixels within five text heights left of the number.
    left = x0 + group[0][0]
    coin = 0
    for y in range(y0 + top, y0 + bottom + 1):
        for x in range(max(0, int(left - 5 * line)), left):
            i = (y * width + x) * 3
            coin += _coin(pixels[i], pixels[i + 1], pixels[i + 2])
    if coin < 0.6 * line * line * 0.3:
        return None
    text = ""
    for k, glyph in enumerate(group):
        if glyph[3] - glyph[2] + 1 < 0.5 * line:
            text += "."
            continue
        last = k == len(group) - 1
        name, distance = stage._best(ink, glyph, LETTERS if last else DIGITS)
        if distance > 0.2:
            return None
        text += name
    number, unit = text[:-1], text[-1]
    if not number or number.startswith(".") or number.endswith(".") or number.count(".") > 1:
        return None
    if not number.replace(".", "").isdigit():
        return None
    box = [(x0 + group[0][0]) / width, (y0 + top) / height, (x0 + group[-1][1] + 1) / width, (y0 + bottom + 1) / height]
    return {"text": text, "value": float(number) * 1000.0 ** (ord(unit) - ord("A") + 1), "box": box}


def rate_text(per_second):
    """Gold per second in the game's notation: 3 digits, wherever the
    point falls, and a letter for each factor of 1000 (A is 10^3, B 10^6…)."""
    if per_second is None:
        return None
    if per_second <= 0:
        return "0.00"
    power, value = 0, per_second
    while True:
        digits = 0 if value >= 99.95 else 1 if value >= 9.995 else 2
        text = f"{value:.{digits}f}"
        # 999.6 rounds to "1000": one more letter instead.
        if float(text) < 1000 or power == 26:
            break
        value /= 1000
        power += 1
    return text + (chr(ord("A") + power - 1) if power else "")
