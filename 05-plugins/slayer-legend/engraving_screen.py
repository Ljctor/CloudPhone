"""Reads the Soul Weapon Engraving screen (the card's big icon on the Soul
Weapon screen) off a screenshot (width, height, RGB bytes). Pure, stdlib
only. Calibrated at 480x1040 on one capture of 2026-10-21 (Vision, its
5x5 grid filled as Gold-balanced, 8 cards, all locked).

- title(): "Soul Weapon Engraving" at the top (y 0.05-0.085), and
  weapon(): the weapon's name below it (y 0.09-0.125), matched against
  the weapons' names.
- grid(shot, size): the 5x5 grid (x 0.2115-0.7895, y 0.238-0.505, cells
  55.5 px): each cell "piece" (a blue crystal), "empty" (the stone of the
  pattern, no crystal) or "none" (black, outside the pattern); and the
  pieces placed, as sets of cells joined by the thick links between their
  crystals (the grid's own lines are 2 px, a link fills the border). A 4x4
  grid is not calibrated: None.
- cards(): the 8 cards of the inventory (2 rows of 4, 69 px boxes at x 72,
  163, 254, 345 and y 632, 723 px), each {shape, cells, level, locked,
  placed, kind}: the shape drawn in small crystals (cells on its own 21 px
  grid, matched to the sheet's shapes as drawn: the card shows the
  shape's base orientation whatever the piece's orientation in the grid,
  seen on every card), "Lv.NN" at the bottom (digits by templates cut from
  the capture: 0 3 4 5 6 8 9; 1 2 7 are drawn), the padlock at the top
  right (locked: a closed shackle; an open one is not captured yet: then
  None), "E" at the bottom left (placed in the grid), the round icon at
  the top left (kind: "gold" for the coin, the Line's EXTRA_GOLD; "atk"
  for the sword, the L-Shape's ATK).
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_engraving_screen_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

WIDTH, HEIGHT = 480, 1040
TITLE_AREA = (0.15, 0.05, 0.85, 0.088)
TITLE = "Soul Weapon Engraving"
WEAPON_AREA = (0.3, 0.09, 0.7, 0.125)
GRID_LEFT, GRID_TOP, CELL_W, CELL_H = 101.5 / 480, 247.5 / 1040, 55.5 / 480, 55.5 / 1040
CARD_XS = (72 / 480, 163 / 480, 254 / 480, 345 / 480)
CARD_YS = (632 / 1040, 723 / 1040)
CARD_W, CARD_H = 69 / 480, 69 / 1040
# The padlock's tap (its centre, from the card's top left) and the card's
# drag start (the middle of its drawing).
LOCK_DX, LOCK_DY = 61 / 480, 9 / 1040
DRAG_DX, DRAG_DY = 34 / 480, 32 / 1040

# Title shapes ("Soul Weapon" in the popup's title font, soul_weapon.py's).
TITLE_FONT = dict(font.FONT, **{
    "S": ['.###', '#...', '###.', '..##', '...#', '#.##', '.##.', '....', '....'],
    "o": ['....', '.##.', '####', '#..#', '#..#', '#.##', '.##.', '....', '....'],
    "u": ['....', '#..#', '#..#', '#..#', '#..#', '#.##', '.###', '....', '....'],
    "W": ['#..#..#', '#..#..#', '#######', '.#####.', '.#####.', '..#.#..', '.......', '.......', '.......'],
    "e": ['....', '.##.', '####', '####', '#...', '##..', '.###', '....', '....'],
    "a": ['....', '.##.', '.###', '.###', '#..#', '##.#', '.###', '....', '....'],
    "p": ['....', '###.', '####', '#..#', '#..#', '###.', '#...', '....', '....'],
    "n": ['....', '###.', '####', '#..#', '#..#', '#..#', '#..#', '....', '....'],
})

# Level digits, 5 x 8, cut from the capture's "Lv.NN" (1, 2, 7 drawn; 8
# and 9 cleaned of a crystal's pixels).
DIGITS = {
    0: [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    1: ["..#..", ".##..", "#.#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    2: [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#####"],
    3: [".###.", "#...#", "....#", "..##.", "....#", "....#", "#...#", ".###."],
    4: ["...##", "...##", "..#.#", ".#..#", "#...#", "#####", "...##", "....#"],
    5: ["#####", "#....", "#....", "####.", "...##", "....#", "#...#", "####."],
    6: ["..##.", ".#...", "#....", "####.", "#...#", "#...#", "#...#", ".###."],
    7: ["#####", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#..."],
    8: [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", ".###."],
    9: [".###.", "#...#", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
}
DIGITS = {digit: tuple(tuple(1 if ch == "#" else 0 for ch in row) for row in rows) for digit, rows in DIGITS.items()}

# The padlock, locked, as each card's place renders it (white pixels, x 52
# to 67 and y 1 to 13 from the card's top left; the places differ by a
# pixel's phase: one leg can look short). An open padlock is not captured.
LOCKED = {
    0: ['................', '.......###......', '......#...#.....', '................', '.....#.....#....', '.....#.....#....', '....#########...', '....####.####...', '....####.####...', '....####.####...', '....####.####...', '....#########...', '................'],
    1: ['................', '.......###......', '......#...#.....', '................', '.....#.....#....', '.....#.....#....', '....#########...', '....####.####...', '....####.####...', '....####.####...', '....####.####...', '....#########...', '................'],
    2: ['................', '.......###......', '......#...#.....', '................', '...........#....', '...........#....', '....#########...', '....####..###...', '....####..###...', '....####.####...', '....####.####...', '....#########...', '................'],
    3: ['................', '.......###......', '..........#.....', '......#.........', '......#....#....', '......#....#....', '....#########...', '....####..###...', '....####..###...', '....####.####...', '....####.####...', '....#########...', '................'],
    4: ['................', '.......###......', '......#...#.....', '................', '.....#.....#....', '.....#.....#....', '....#########...', '....####.####...', '....####.####...', '....####.####...', '....####.####...', '....#########...', '....########....'],
    5: ['................', '.......###......', '......#...#.....', '................', '.....#.....#....', '.....#.....#....', '....#########...', '....####.####...', '....####.####...', '....####.####...', '....####.####...', '....#########...', '.....########...'],
    6: ['................', '.......###......', '......#...#.....', '................', '...........#....', '...........#....', '....#########...', '....####..###...', '....####..###...', '....####.####...', '....####.####...', '....#########...', '.....########...'],
    7: ['................', '.......###......', '..........#.....', '......#.........', '......#....#....', '......#....#....', '....#########...', '....####..###...', '....####..###...', '....####.####...', '....####.####...', '....#########...', '.....########...'],
}


def _pixel(shot, x, y):
    width, _, pixels = shot
    i = (y * width + x) * 3
    return pixels[i], pixels[i + 1], pixels[i + 2]


def _px(shot, fx, fy):
    width, height, _ = shot
    return _pixel(shot, min(width - 1, max(0, int(fx * width))), min(height - 1, max(0, int(fy * height))))


def title(shot):
    """The screen's title reads "Soul Weapon Engraving"."""
    return any(font.distance(text.replace(" ", ""), TITLE.replace(" ", "")) <= 4
               for text, _, _ in font.read(shot, TITLE_AREA, font=TITLE_FONT))


def weapon(shot, names, card_font):
    """The weapon's name under the title (one of names), or None."""
    for text, _, _ in font.read(shot, WEAPON_AREA, font=card_font):
        found = font.close(text, names, most=0.3, margin=2)
        if found:
            return found
    return None


def _cell_box(row, col):
    left = GRID_LEFT + col * CELL_W
    top = GRID_TOP + row * CELL_H
    return left, top


def cell_centre(row, col):
    left, top = _cell_box(row, col)
    return left + CELL_W / 2, top + CELL_H / 2


def _cell_state(shot, row, col):
    width, height, _ = shot
    left, top = _cell_box(row, col)
    cx, cy = int((left + CELL_W / 2) * width), int((top + CELL_H / 2) * height)
    samples = [_pixel(shot, cx + dx, cy + dy) for dx in range(-12, 13, 3) for dy in range(-12, 13, 3)]
    blue = sum(1 for r, g, b in samples if b > 150 and b > r + 60)
    if blue >= 0.5 * len(samples):
        return "piece"
    corner = [_pixel(shot, int(left * width) + 5 + dx, int(top * height) + 5 + dy)
              for dx in range(0, 8, 2) for dy in range(0, 8, 2)]
    mean = sum(max(p) for p in corner) / len(corner)
    if blue <= 0.1 * len(samples) and mean >= 90:
        return "empty"
    if blue <= 0.1 * len(samples) and mean < 75:
        return "none"
    return None


def _bright_run(shot, points):
    return sum(1 for x, y in points if min(_pixel(shot, x, y)[1:]) > 200)


def _linked(shot, a, b):
    """Two adjacent crystals joined by a link across their border."""
    width, height, _ = shot
    (r1, c1), (r2, c2) = sorted([a, b])
    if r1 == r2:
        x = int((GRID_LEFT + (c1 + 1) * CELL_W) * width)
        y = int((GRID_TOP + (r1 + 0.5) * CELL_H) * height)
        points = [(x + d, y) for d in range(-8, 9)]
    else:
        x = int((GRID_LEFT + (c1 + 0.5) * CELL_W) * width)
        y = int((GRID_TOP + (r1 + 1) * CELL_H) * height)
        points = [(x, y + d) for d in range(-8, 9)]
    return _bright_run(shot, points) >= 14


def grid(shot, size):
    """{cells: {(row, col): "piece", "empty" or "none"}, pieces: [sorted
    cells]} of the size x size grid; None for a 4x4 grid (not calibrated)
    or a cell that reads as none of the three."""
    if size != 5:
        return None
    cells = {}
    for row in range(5):
        for col in range(5):
            state = _cell_state(shot, row, col)
            if state is None:
                return None
            cells[(row, col)] = state
    filled = {cell for cell, state in cells.items() if state == "piece"}
    pieces, seen = [], set()
    for start in sorted(filled):
        if start in seen:
            continue
        group, todo = set(), [start]
        while todo:
            cell = todo.pop()
            if cell in group:
                continue
            group.add(cell)
            r, c = cell
            for other in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if other in filled and other not in group and _linked(shot, cell, other):
                    todo.append(other)
        seen |= group
        pieces.append(sorted(group))
    return {"cells": cells, "pieces": pieces}


def card_box(index):
    """(left, top) of card index (0-7, row by row), fractions."""
    return CARD_XS[index % 4], CARD_YS[index // 4]


def lock_point(index):
    left, top = card_box(index)
    return left + LOCK_DX, top + LOCK_DY


def drag_point(index):
    left, top = card_box(index)
    return left + DRAG_DX, top + DRAG_DY


def _card_px(shot, index):
    width, height, _ = shot
    left, top = card_box(index)
    return int(round(left * width)), int(round(top * height))


def crystals(shot, index):
    """The centres (x, y pixels) of the crystals drawn on a card: the bright
    top facets (red + green >= 84; the links between them are dimmer), in
    the card's middle (not its icon, padlock, E or Lv text), each facet a
    group of at least 3 pixels, facets closer than 7 px merged."""
    x0, y0 = _card_px(shot, index)
    bright = {(x, y) for x in range(x0 + 14, x0 + 60) for y in range(y0 + 3, y0 + 56)
              if sum(_pixel(shot, x, y)[:2]) >= 84 and not (x > x0 + 50 and y < y0 + 20)}
    groups, seen = [], set()
    for start in sorted(bright):
        if start in seen:
            continue
        group, todo = [], [start]
        while todo:
            x, y = todo.pop()
            if (x, y) in seen:
                continue
            seen.add((x, y))
            group.append((x, y))
            todo.extend((x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (x + dx, y + dy) in bright)
        if len(group) >= 3:
            groups.append((sum(x for x, _ in group) / len(group), sum(y for _, y in group) / len(group)))
    merged = []
    for cx, cy in groups:
        near = next((m for m in merged if abs(m[0] - cx) < 7 and abs(m[1] - cy) < 7), None)
        if near:
            near[0], near[1] = (near[0] + cx) / 2, (near[1] + cy) / 2
        else:
            merged.append([cx, cy])
    return [tuple(m) for m in merged]


def _drawing(shot, index):
    """The card's shape: its crystals on their own lattice (the spacing of
    the two closest), normalised (top left at (0, 0)), or None."""
    centres = crystals(shot, index)
    if not 1 <= len(centres) <= 6:
        return None
    if len(centres) == 1:
        return [(0, 0)]
    pitch = min(max(abs(a[0] - b[0]), abs(a[1] - b[1])) for i, a in enumerate(centres) for b in centres[i + 1:])
    if pitch < 10:
        return None
    left, top = min(x for x, _ in centres), min(y for _, y in centres)
    cells = set()
    for x, y in centres:
        col, row = (x - left) / pitch, (y - top) / pitch
        if abs(col - round(col)) > 0.3 or abs(row - round(row)) > 0.3:
            return None
        cells.add((round(row), round(col)))
    return sorted(cells) if len(cells) == len(centres) else None


def normalised(cells):
    rows = min(r for r, _ in cells)
    cols = min(c for _, c in cells)
    return sorted((r - rows, c - cols) for r, c in cells)


def turned(cells, quarter_turns):
    """The cells turned clockwise quarter_turns times, normalised."""
    out = list(cells)
    for _ in range(quarter_turns % 4):
        out = [(c, -r) for r, c in out]
    return normalised(out)


def shape_of(cells, shapes):
    """(shape, rotation) the drawn cells are, among the sheet's shapes (as
    engravings.json gives them, row, col): the lowest rotation that gives
    them; None when none does."""
    if not cells:
        return None
    for name, shape in shapes.items():
        base = normalised([tuple(cell) for cell in shape["cells"]])
        for rotation in range(4):
            if turned(base, rotation) == normalised(cells):
                return name, rotation
    return None


def _digits_ink(shot, index):
    x0, y0 = _card_px(shot, index)
    return [[min(_pixel(shot, x, y)) >= 44 for x in range(x0 + 33, x0 + 53)] for y in range(y0 + 56, y0 + 64)]


def _digit_runs(ink):
    cols = len(ink[0])
    # A column is a digit's when it has ink above the last row (the dot
    # of "Lv." sits on the last row alone).
    used = [sum(ink[y][x] for y in range(len(ink))) >= 2 for x in range(cols)]
    runs, x = [], 0
    while x < cols:
        if used[x]:
            right = x
            while right + 1 < cols and used[right + 1]:
                right += 1
            if right - x + 1 >= 3:
                runs.append((x, right))
            x = right + 1
        else:
            x += 1
    return runs


def _digit_grid(ink, run):
    left, right = run
    return tuple(tuple(1 if ink[y][x] else 0 for x in range(left, right + 1)) for y in range(len(ink)))


def _scaled(glyph, cols=5):
    """A digit's bitmap resampled to cols x 8."""
    width = len(glyph[0])
    return tuple(tuple(glyph[y][min(width - 1, int(x * width / cols))] for x in range(cols)) for y in range(len(glyph)))


def level(shot, index):
    """The card's level, None when a digit does not read."""
    ink = _digits_ink(shot, index)
    runs = _digit_runs(ink)
    if not 1 <= len(runs) <= 2 or not DIGITS:
        return None
    value = 0
    for run in runs:
        glyph = _scaled(_digit_grid(ink, run))
        scored = sorted((sum(a != b for ra, rb in zip(glyph, shape) for a, b in zip(ra, rb)), digit)
                        for digit, shape in DIGITS.items())
        if scored[0][0] > 6 or (len(scored) > 1 and scored[1][0] - scored[0][0] < 2):
            return None
        value = value * 10 + scored[0][1]
    return value


def locked(shot, index):
    """The card's padlock reads locked (True): its white pixels within 4 of
    that place's locked padlock; None otherwise (open, or not read: an open
    padlock is not captured yet, so nothing is told apart from it)."""
    x0, y0 = _card_px(shot, index)
    seen = ["".join("#" if min(_pixel(shot, x, y)) >= 200 else "." for x in range(x0 + 52, x0 + 68))
            for y in range(y0 + 1, y0 + 14)]
    differ = sum(a != b for ra, rb in zip(seen, LOCKED[index]) for a, b in zip(ra, rb))
    return True if differ <= 4 else None


def placed(shot, index):
    """The card's "E" (its piece is in the grid): a white letter at the
    bottom left."""
    x0, y0 = _card_px(shot, index)
    white = sum(1 for x in range(x0 + 2, x0 + 12) for y in range(y0 + 52, y0 + 66)
                if min(_pixel(shot, x, y)) >= 200)
    return white >= 15


def kind(shot, index):
    """The round icon at the top left: "gold" (a coin: a dim engraved
    texture inside the ring) or "atk" (a sword: a flat stroke, no texture),
    None between the two. Counted as the dim pixels (green 25 to 49) inside
    the ring: about 30 on a coin, 3 on a sword, whatever the card's column."""
    x0, y0 = _card_px(shot, index)
    cx, cy = x0 + 2, y0 + 2
    inner = [(x, y) for x in range(cx - 7, cx + 8) for y in range(cy - 7, cy + 8)
             if (x - cx) ** 2 + (y - cy) ** 2 <= 49]
    dim = sum(1 for x, y in inner if 25 <= _pixel(shot, x, y)[1] < 50)
    if dim >= 20:
        return "gold"
    if dim <= 8:
        return "atk"
    return None


KINDS = {"I": "gold", "L": "atk"}


def cards(shot, shapes):
    """The 8 cards: [{shape, rotation, cells, level, locked, placed, kind}]."""
    out = []
    for index in range(8):
        cells = _drawing(shot, index)
        found = shape_of(cells, shapes) if cells else None
        out.append({"index": index, "shape": found[0] if found else None, "rotation": found[1] if found else None,
                    "cells": cells, "level": level(shot, index), "locked": locked(shot, index),
                    "placed": placed(shot, index), "kind": kind(shot, index)})
    return out
