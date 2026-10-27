"""Reads the gold counter off a Slayer Legend screenshot (width, height, RGB
bytes): "<coin> 111F" in white with a black outline, centred under the
stage name. Its height on screen depends on the panel open below the
battle, so the band where it may be is searched; Power Saving Mode does
not show it.

The amount is a number with up to 3 significant digits and a unit letter:
A is a thousand, B a thousand A, and so on (parse). The game can also
write it in full digits (its option); that reading is gated by
FULL_DIGITS_CALIBRATED until a real capture of it is a fixture.

The Soul Weapon screen, the farming modes' parking screen, shades the
battle above it: the counter is then read with its colours at
screens.PARKED_SHADE (read's shades).
"""

import importlib.util
import os
import re

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

# The ordinary 480x1040 capture compresses a long balance to roughly 7 px
# high, merging neighbouring glyphs. Keep that path gated. At 720x1560 or
# above, the digits can be read separately.
FULL_DIGITS_CALIBRATED = False
HIGH_RES_FULL_DIGITS_CALIBRATED = True
# Each 90-bit word is a 5x9, four-level ink grid of a real 720 px digit.
# Source crops: gold_full_mid and gold_full_mid_joined. The extra shapes
# distinguish small 4 from 8 when the game's font squeezes the balance.
FULL_720_TEMPLATES = {
    "0": (0x3fffff03c0f03c0f03ffcfc, 0xfcfff8be2f8be2f8bffcfc),
    "1": (0x3ffffcb82e0b82e0bf2fcb8, 0x3fffebe0f83e0f83fafffe0),
    "2": (0x3ffffc3f3f3f0f0303ffcfc, 0x3ffffc2f1f0f4f838bffcfc, 0x3ffabc0a0a0b4b8382fadfd),
    "3": (0xfcfff8be03f4fd38bffcfc, 0x3fffff03f03f0fc303ffcfc),
    "4": (0x1c0703fff7ddf7f5f87c1c0, 0x80657ffbac9b2b8b828080),
    "5": (0x3fffff03f03ff3fc03fffff, 0xfcfff8be03ff3fc0bfffff,
          0x1fdebf06d03aabfc5babfff, 0x1fdfaf82e03aabfc57aafff),
    "6": (0x3fffff03f3fff3fc0f3f0f0, 0xfcfff8be2fff3fc2f3f0f4,
          0x1fdfaf83e1fabbfc5b2b4f4, 0x1fdebf0bd2fabbfc6f2f4f4,
          0x1fdebf0bd2fefbfc6f2f4f4),
    "7": (0x741d0743d0e0f8380fffff, 0x300c0f03c3c0f0300fffff, 0x741d0b439280e0340eabff),
    "8": (0x1fdfaf82e1fabfff97fadfd, 0x1fdfaf83e1fabfff97fadfd,
          0x1fdfaf83e1feffff97fadfd),
    "9": (0x7c7e3d0e57ffe5f83fadfd,),
}
# Separators between groups of 3 in full digits.
SEPARATORS = re.compile("[,. \u00a0\u202f]")


def normalize_text(text):
    """Drop redundant integer zeros in a read counter, but keep 0.x.

    This changes only the displayed OCR text; parsing and the full-digit
    calibration gate still use the original reading.
    """
    return re.sub(r"^0+(?=\d)", "", text)


def parse(text):
    """{value, step, full} of a counter's text: abbreviated, "94.6C"
    (94.6 x 1000^3, step 0.1C: one unit of its last digit), or in full
    digits, "94600000000" or with separators between groups of 3 (step 1);
    None when it is neither."""
    if not text:
        return None
    unit = text[-1]
    if "A" <= unit <= "Z":
        number = text[:-1]
        if not number or number.startswith(".") or number.endswith(".") or number.count(".") > 1 \
                or not number.replace(".", "").isdigit():
            return None
        scale = 1000.0 ** (ord(unit) - ord("A") + 1)
        decimals = len(number.split(".")[1]) if "." in number else 0
        return {"value": float(round(float(number) * scale)), "step": scale / 10 ** decimals, "full": False}
    groups = SEPARATORS.split(text)
    if not all(group.isdigit() for group in groups):
        return None
    if len(groups) > 1 and (len(groups[0]) > 3 or any(len(group) != 3 for group in groups[1:])):
        return None
    digits = "".join(groups)
    # Up to 3 digits read the same in both notations.
    # Keep every digit: a float loses small gains when the balance is huge.
    return {"value": int(digits), "step": 1, "full": len(digits) > 3}


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


def _coin(r, g, b, shade=1.0):
    return r > 220 * shade and 120 * shade < g < 215 * shade and b < 90 * shade


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


def _digit_720(ink, glyph):
    """Match a 720 px digit to the real-capture four-level ink grids."""
    grid = stage._grid(ink, glyph, 5, 9)
    values = [min(3, round(v * 3)) for row in grid for v in row]
    scores = []
    for name, templates in FULL_720_TEMPLATES.items():
        distance = min(sum((value - ((template >> (2 * k)) & 3)) ** 2
                           for k, value in enumerate(values)) / 405 for template in templates)
        scores.append((distance, name))
    return min(scores)


def read(shot, shades=(1.0,)):
    """The counter as {text: "111F", value: 1.11e20, step, full (parse),
    box: [left, top, right, bottom] as fractions of the screen}, or None
    when it is not on screen or not readable. shades: the brightnesses
    tried in turn (screens.PARKED_SHADE: under the Soul Weapon screen)."""
    for shade in shades:
        reading = _read(shot, shade)
        if reading:
            width, height, pixels = shot
            x0, y0, x1, y1 = reading["box"]
            brightest = 0
            for y in range(round(y0 * height), round(y1 * height)):
                for x in range(round(x0 * width), round(x1 * width)):
                    i = (y * width + x) * 3
                    r, g, b = pixels[i:i + 3]
                    if max(r, g, b) - min(r, g, b) < 30:
                        brightest = max(brightest, min(r, g, b))
            reading["shade"] = max(0.2, min(1.0, brightest / 255)) if brightest else shade
            return reading
    return None


def _read(shot, shade):
    width, height, pixels = shot
    x0, y0 = int(BAND[0] * width), int(BAND[1] * height)
    x1, y1 = int(BAND[2] * width), int(BAND[3] * height)
    ink = _ink(shot, x0, y0, x1, y1, 140 * shade)
    # Pure white only: the mid grey edges join neighbouring glyphs, so
    # glyphs are cut apart on this, and read on all the ink.
    core = _ink(shot, x0, y0, x1, y1, 245 * shade)
    line = 15 if width >= 900 else 11 if width >= 700 else TEXT_HEIGHT * height
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
            reading = _read_group(shot, ink, group, x0, y0, top, bottom, line, shade)
            if reading:
                return reading
        if width >= 700 and HIGH_RES_FULL_DIGITS_CALIBRATED:
            # In a long balance, a comma can touch the preceding digit at
            # the baseline. Above the baseline only the digits remain, so
            # cut them there and read their complete shapes on `ink`.
            candidates = []
            for fraction in (0.7, 0.6, 0.5):
                upper = _glyphs(core, top, min(bottom, top + int(fraction * line)))
                digits = []
                for left, right, _, _ in upper:
                    ys = [row for row in range(top, bottom + 1) if any(ink[row][left:right + 1])]
                    if ys and ys[-1] - ys[0] + 1 >= 0.5 * line:
                        digits.append((left, right, ys[0], ys[-1]))
                candidates.append(digits)
            most = max(map(len, candidates))
            for digits in candidates:
                if len(digits) != most or len(digits) < 7:
                    continue
                reading = (_read_full_720(shot, ink, digits, x0, y0, top, bottom, shade)
                           if 700 <= width < 900 else
                           _read_group(shot, ink, digits, x0, y0, top, bottom, line, shade))
                if reading and reading["full"]:
                    return reading
    return None


def _read_full_720(shot, ink, digits, x0, y0, top, bottom, shade):
    width, height, pixels = shot
    left = x0 + digits[0][0]
    coin = 0
    for y in range(y0 + top, y0 + bottom + 1):
        for x in range(max(0, left - 55), left):
            i = (y * width + x) * 3
            coin += _coin(pixels[i], pixels[i + 1], pixels[i + 2], shade)
    if coin < 20:
        return None
    text = ""
    for glyph in digits:
        distance, name = _digit_720(ink, glyph)
        if distance > 0.22:
            return None
        text += name
    parsed = parse(text)
    if not parsed or not parsed["full"]:
        return None
    box = [(x0 + digits[0][0]) / width, (y0 + top) / height,
           (x0 + digits[-1][1] + 1) / width, (y0 + bottom + 1) / height]
    return {"text": f"{parsed['value']:,}", **parsed, "box": box}


def _read_group(shot, ink, group, x0, y0, top, bottom, line, shade=1.0):
    width, height, pixels = shot
    # The coin: gold pixels within five text heights left of the number.
    left = x0 + group[0][0]
    coin = 0
    for y in range(y0 + top, y0 + bottom + 1):
        for x in range(max(0, int(left - 5 * line)), left):
            i = (y * width + x) * 3
            coin += _coin(pixels[i], pixels[i + 1], pixels[i + 2], shade)
    if coin < 0.6 * line * line * 0.3:
        return None
    full_calibrated = FULL_DIGITS_CALIBRATED or (width >= 700 and HIGH_RES_FULL_DIGITS_CALIBRATED)
    full_group = full_calibrated and (len(group) > 6 or any(g[3] - g[2] + 1 < 0.5 * line for g in group))
    text = ""
    for k, glyph in enumerate(group):
        if glyph[3] - glyph[2] + 1 < 0.5 * line:
            text += "."
            continue
        last = k == len(group) - 1
        shapes = DIGITS if last and full_group else LETTERS if last else DIGITS
        if full_group and width >= 700 and glyph[1] - glyph[0] + 1 <= 0.35 * line:
            name, distance = "1", 0.0
        else:
            name, distance = stage._best(ink, glyph, shapes)
        # Narrow 1 and 4 are slightly distorted by the game's high-res font.
        if distance > (0.24 if width >= 700 else 0.2):
            return None
        text += name
    parsed = parse(text)
    if parsed is None or parsed["full"] and not full_calibrated:
        return None
    box = [(x0 + group[0][0]) / width, (y0 + top) / height, (x0 + group[-1][1] + 1) / width, (y0 + bottom + 1) / height]
    if parsed["full"] and width >= 700:
        text = text.replace(".", ",") if "." in text else f"{parsed['value']:,}"
    return {"text": normalize_text(text), **parsed, "box": box}


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
