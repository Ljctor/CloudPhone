"""Read the Legendary Grade 3 count on the open Equipment tab.

The six colour rows are fixed in the game's grid: the red row is
Legendary and the second column is Grade 3. The numerator under that card
is the displayed balance; /5 is the combine threshold, not a divisor.
The templates below were cut from real 480x1040 Weapon/Accessories
captures. Unknown digits, a clipped card, and other resolutions do not
produce a reading. No game input is made here.
"""

import re

WIDTH, HEIGHT = 480, 1040
CARD_X = (146, 222)
COUNT_X = (150, 215)
ROW_TOP = (465, 840)

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


def _red_line(shot, y):
    hits = 0
    for x in range(*CARD_X):
        r, g, b = _pixel(shot, x, y)
        hits += r > 170 and r > 1.6 * g and r > 1.4 * b
    return hits >= 60


def _card_top(shot):
    """Top border of one whole red Grade 3 card, or None."""
    tops = []
    previous = False
    for y in range(*ROW_TOP):
        red = _red_line(shot, y)
        if red and not previous and any(_red_line(shot, y + dy) for dy in range(81, 86)):
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


def _glyphs(shot, top):
    x0, x1 = COUNT_X
    rows = [[min(_pixel(shot, x, y)) > 130 for x in range(x0, x1)]
            for y in range(top + 85, top + 105)]
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
    if shot[:2] != (WIDTH, HEIGHT):
        return None
    top = _card_top(shot)
    if top is None or top + 105 > 900:
        return None
    chars = []
    for glyph in _glyphs(shot, top):
        closest = sorted((_distance(glyph, shape), char) for char, shape in SHAPES.items())
        if closest[0][0] > 0.18 or closest[1][0] - closest[0][0] < 0.06:
            return None
        chars.append(closest[0][1])
    text = "".join(chars)
    return int(text[:-2]) if re.fullmatch(r"[0-5]{1,4}/5", text) else None
