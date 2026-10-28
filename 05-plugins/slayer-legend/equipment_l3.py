"""Read the Legendary Grade 3 count on the open Equipment tab.

The six colour rows are fixed in the game's grid: the red row is
Legendary and the second column is Grade 3. The numerator under that card
is the displayed balance; /5 is the combine threshold, not a divisor.
The templates below were cut from real 480x1040 Weapon/Accessories
captures. Geometry also accepts the native 720x1560 phone size, while
the OCR still requires the same distinct glyph shapes and /5 suffix.
Unknown digits, a clipped card, and other resolutions do not produce a
reading. No game input is made here.
"""

import importlib.util
import os
import re

WIDTH, HEIGHT = 480, 1040
CARD_X = (146, 222)
COUNT_X = (150, 215)
ROW_TOP = (465, 840)
# Known crops disagree by at most .036 at native 720. A broad .18 match
# accepted damaged glyphs; missing digit calibrations must not be guessed.
MAX_DISTANCE = 0.06

# White cores of the counter glyphs at 480x1040, from the red Grade 3
# cards (the other cards in those captures provide 0 and 1). 6–9 have
# not yet been observed in this counter font and deliberately do not read.
SHAPES = {
    "0": (".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."),
    "1": (".#.", "##.", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "3": (".####.", "##..##", "....##", "..###.", "....##", "....##", "##..##", ".####."),
    "4": ("....##.", "...###.", "..####.", ".##.##.", "##..##.", "#######", "....##.", "....##."),
    "5": ("######", "##....", "##....", "#####.", "....##", "....##", "##..##", ".####."),
    "/": ("....#", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#...", "#....", "#...."),
}


def _pixel(shot, x, y):
    width, _, pixels = shot
    i = (y * width + x) * 3
    return pixels[i], pixels[i + 1], pixels[i + 2]


def _red_line(shot, y, scale):
    hits = 0
    for x in range(round(CARD_X[0] * scale), round(CARD_X[1] * scale)):
        r, g, b = _pixel(shot, x, y)
        hits += r > 140 and r > 1.5 * g and r > 1.3 * b
    return hits >= 60 * scale


def _card_top(shot, scale):
    """Top border of one whole red Grade 3 card, or None."""
    tops = []
    previous = False
    for y in range(round(ROW_TOP[0] * scale), round(ROW_TOP[1] * scale)):
        red = _red_line(shot, y, scale)
        if red and not previous and any(_red_line(shot, y + dy, scale)
                                        for dy in range(round(81 * scale), round(86 * scale))):
            tops.append(y)
        previous = red
    return tops[0] if len(tops) == 1 else None


def _distance(glyph, shape):
    """Pixel disagreement after scaling the observed glyph to a template."""
    height, width = len(glyph), len(glyph[0])
    rows, cols = len(shape), len(shape[0])
    wrong = 0
    for y in range(rows):
        source_y = min(height - 1, int((y + 0.5) * height / rows))
        for x in range(cols):
            source_x = min(width - 1, int((x + 0.5) * width / cols))
            wrong += (glyph[source_y][source_x] == "#") != (shape[y][x] == "#")
    return wrong / (rows * cols) + 0.04 * abs(width - cols) / max(width, cols)


def _glyphs(shot, top, scale):
    x0, x1 = (round(x * scale) for x in COUNT_X)
    rows = [[min(_pixel(shot, x, y)) > 130 for x in range(x0, x1)]
            for y in range(top + round(85 * scale), top + round(105 * scale))]
    used = [any(row[x] for row in rows) for x in range(x1 - x0)]
    runs, start = [], None
    for x, on in enumerate(used + [False]):
        if on and start is None:
            start = x
        elif not on and start is not None:
            runs.append((start, x))
            start = None
    for left, right in runs:
        ys = [y for y in range(len(rows)) if any(rows[y][x] for x in range(left, right))]
        if not ys:
            continue
        yield tuple("".join("#" if rows[y][x] else "." for x in range(left, right))
                    for y in range(min(ys), max(ys) + 1))


def read(shot):
    """Numerator of the visible red Grade 3 /5 card, or None."""
    if shot[:2] not in ((WIDTH, HEIGHT), (720, 1560)):
        return None
    scale = shot[0] / WIDTH
    top = _card_top(shot, scale)
    if top is None or top + round(105 * scale) > round(900 * scale):
        return None
    chars = []
    for glyph in _glyphs(shot, top, scale):
        closest = sorted((_distance(glyph, shape), char) for char, shape in SHAPES.items())
        if closest[0][0] > MAX_DISTANCE or closest[1][0] - closest[0][0] < 0.06:
            return None
        chars.append(closest[0][1])
    text = "".join(chars)
    return int(text[:-2]) if re.fullmatch(r"[0-5]{1,4}/5", text) else None


_safety = None


def _safety_readers():
    global _safety
    if _safety is None:
        spec = importlib.util.spec_from_file_location(
            "cloudphone_plugin_slayer_legend_equipment_safety", os.path.join(os.path.dirname(__file__), "screens.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _safety = module, module.Patch("equipment_inspect_card_720", limit=.35)
    return _safety


def _equipment_visible(shot, tab):
    model, _ = _safety_readers()
    seen = model.look(shot)
    identity = {"weapon": "equipment_weapon", "accessories": "equipment_accessories"}.get(tab)
    return bool(identity and seen["screen"] == "battle" and seen.get("plain") is False
                and identity in seen["overlays"]
                and all(item in {"panel", identity, "better_weapon_toast"} for item in seen["overlays"]))


def inspect_weapon_safe(shot):
    """The proven (.15,.52) inspect point is inside the complete first
    Common weapon card. A shifted list, another tab or a popup fails closed.
    This authorises inspecting that card, never its Enhance or Equip buttons."""
    if not INSPECT_LEARNED or not _equipment_visible(shot, "weapon"):
        return False
    _, card = _safety_readers()
    return card.margin(shot) >= .3


def scroll_safe(shot, tab):
    """Both endpoints and the entire drag stay in the observed dark gap
    between columns, above Batch Combine. Tested before/after real scrolling
    on each tab; any bright/coloured control crossing the gap refuses it."""
    if not SCROLL_LEARNED or not _equipment_visible(shot, tab):
        return False
    width, height, _ = shot
    return all(max(_pixel(shot, x, y)) < 80
               for x in range(round(.26 * width), round(.28 * width))
               for y in range(round(.55 * height), round(.81 * height)))


# Real before/after card inspection (Equipment -> ordinary weapon detail),
# real Weapon/Accessories first/scrolled gaps, plus modal/Growth negatives.
# Every required state is listed in test_gates.py and read by its tests.
INSPECT_LEARNED = True
SCROLL_LEARNED = True
