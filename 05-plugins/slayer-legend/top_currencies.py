"""Conservative OCR of the emerald and diamond balances in the game's top bar.

The icon positions and the 480x1040 text are measured on real battle and
equipment captures. The ten digit shapes come from real cube counter crops
using the same game font; an uncertain glyph leaves its counter unread.
"""

import importlib.util
import os
import re


_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_top_currency_digits",
    os.path.join(os.path.dirname(__file__), "cube_balance.py"))
_cubes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cubes)

COUNTERS = {
    "emerald": {"icon": (180, 18, 197, 35), "text": (200, 19, 255, 34)},
    "diamond": {"icon": (259, 18, 277, 35), "text": (280, 19, 335, 34)},
}
NUMBER = re.compile(r"(?:0|[1-9]\d{0,2}(?:,\d{3})*)\Z")


def _at(shot, x, y):
    width, height, pixels = shot
    x = min(width - 1, round(x * width / 480))
    y = min(height - 1, round(y * height / 1040))
    return pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]


def _icon(shot, field, shade):
    x0, y0, x1, y1 = COUNTERS[field]["icon"]
    hits = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = _at(shot, x, y)
            if field == "emerald":
                hits += g > 100 * shade and g > r * 1.3 and g > b * 1.3
            else:
                hits += b > 100 * shade and b > r * 1.2 and b > g * 1.05
    return hits >= (60 if field == "emerald" else 40)


def _glyphs(shot, field, shade):
    x0, y0, x1, y1 = COUNTERS[field]["text"]
    rows = []
    for y in range(y0, y1):
        row = []
        for x in range(x0, x1):
            r, g, b = _at(shot, x, y)
            row.append(min(r, g, b) >= 170 * shade and max(r, g, b) - min(r, g, b) < 45)
        rows.append(row)
    columns = [any(row[x] for row in rows) for x in range(x1 - x0)]
    runs, start = [], None
    for x, used in enumerate(columns + [False]):
        if used and start is None:
            start = x
        if not used and start is not None:
            runs.append((start, x))
            start = None
    glyphs = []
    for left, right in runs:
        ys = [y for y, row in enumerate(rows) if any(row[left:right])]
        top, bottom = min(ys), max(ys) + 1
        glyphs.append(tuple("".join("#" if rows[y][x] else "." for x in range(left, right))
                            for y in range(top, bottom)))
    return glyphs


def _distance(glyph, shape):
    height, width = len(glyph), len(glyph[0])
    shape_height, shape_width = len(shape), len(shape[0])
    different = 0
    for row in range(9):
        for col in range(7):
            a = glyph[min(height - 1, (2 * row + 1) * height // 18)][
                min(width - 1, (2 * col + 1) * width // 14)] == "#"
            b = shape[min(shape_height - 1, (2 * row + 1) * shape_height // 18)][
                min(shape_width - 1, (2 * col + 1) * shape_width // 14)] == "#"
            different += a != b
    return different / 63


def _character(glyph):
    height, width = len(glyph), len(glyph[0])
    if height <= 4 and width <= 3:
        return ","
    if not 8 <= height <= 11 or not 3 <= width <= 8:
        return None
    scores = sorted((_distance(glyph, shape), char) for char, shape in _cubes.SHAPES.items())
    score, char = scores[0]
    if score > 0.20:
        return None
    if scores[1][0] - score < 0.045 and {char, scores[1][1]} == {"0", "8"}:
        middle = glyph[height // 2]
        return "8" if all(pixel == "#" for pixel in middle[1:-1]) else "0"
    if scores[1][0] - score < 0.045:
        return None
    return char


def read(shot, field):
    """{text, value} or None. A missing icon, glyph, or separator rejects it."""
    if field not in COUNTERS:
        raise ValueError(field)
    width, height, _ = shot
    if width < 480 or height < 1040 or abs(width / height - 480 / 1040) > 0.01:
        return None
    for shade in (1.0, 0.70):
        if not _icon(shot, field, shade):
            continue
        glyphs = _glyphs(shot, field, shade)
        if not 1 <= len(glyphs) <= 11:
            continue
        characters = [_character(glyph) for glyph in glyphs]
        if None in characters:
            continue
        text = "".join(characters)
        if NUMBER.fullmatch(text):
            return {"text": text, "value": int(text.replace(",", ""))}
    return None
