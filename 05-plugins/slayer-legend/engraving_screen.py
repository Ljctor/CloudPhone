"""Reads the Soul Weapon Engraving screen (the card's big icon on the Soul
Weapon screen) off a screenshot (width, height, RGB bytes). Pure, stdlib
only. Calibrated at 480x1040 on one capture of 2026-10-21 (Vision, its
5x5 grid filled as Gold-balanced, 8 cards, all locked). Native captures are
sampled on that lattice before reading; returned points remain fractions.
Below 480x1040 the fine card readers return unknown: lost digit/padlock
strokes cannot safely be reconstructed. Grid and preview geometry remain
available independently.

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
  the captures, including a narrow 1 in Lv.41), the padlock at the top
  right (closed white shackle, open grey shackle on a bright card, or
  unknown), "E" at the bottom left (placed in the grid), the round icon at
  the top left (kind: "gold" for the coin, the Line's EXTRA_GOLD; "atk"
  for the sword, the L-Shape's ATK).
"""

import importlib.util
import os
from functools import wraps

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_engraving_screen_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_engraving_pixels", os.path.join(os.path.dirname(__file__), "capture_pixels.py"))
_capture_pixels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_capture_pixels)
normalised_capture = _capture_pixels.canonical

WIDTH, HEIGHT = 480, 1040

# Readers below use the calibrated 480×1040 lattice and pixel thresholds.
# Canonicalise pixels once per immutable capture; public points remain screen
# fractions, so every returned tap/drag position is valid at native size.


def calibrated(reader):
    @wraps(reader)
    def read_native(shot, *args, **kwargs):
        # Below the calibration resolution, thin strokes have been lost:
        # e.g. a real Lv39 crop reduced to 360 can read as Lv9. Upsampling
        # cannot restore those strokes. Keep precise card gates closed;
        # large grid/preview/popup geometry can still be read independently.
        if shot[0] < WIDTH or shot[1] < HEIGHT:
            if reader.__name__ == "cards":
                return _unread_cards()
            if reader.__name__ == "crystals":
                return []
            if reader.__name__ in {"level", "bright", "locked", "placed", "kind"}:
                return None
        return reader(normalised_capture(shot), *args, **kwargs)
    return read_native


TITLE_AREA = (0.15, 0.05, 0.85, 0.088)
TITLE = "Soul Weapon Engraving"
WEAPON_AREA = (0.3, 0.09, 0.7, 0.125)
GRID_LEFT, GRID_TOP, CELL_W, CELL_H = 101.5 / 480, 247.5 / 1040, 55.5 / 480, 55.5 / 1040
CARD_XS = (72 / 480, 163 / 480, 254 / 480, 345 / 480)
CARD_YS = (632 / 1040, 723 / 1040)
CARD_W, CARD_H = 69 / 480, 69 / 1040
# The padlock's tap (its centre, from the card's top left) and the card's
# drag start (the middle of its drawing).
# The padlock glyph spans x 56-64 and y 1-12 from the card's top left (its
# shackle above, its body y 7-12): the tap aims at its middle.
LOCK_DX, LOCK_DY = 60 / 480, 7 / 1040
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
DIGIT_VARIANTS = {digit: [shape] for digit, shape in DIGITS.items()}
# Real narrow 1 from fixtures/eg_level_41 (Relax, second card): its two
# substantial columns differ from the old drawn 5-column approximation.
DIGIT_VARIANTS[1].append(tuple(tuple(ch == "#" for ch in row) for row in
    ["...##", "#####", "...##", "...##", "...##", "...##", "...##", "#####"]))

# The padlock, locked, as each card's place renders it (white pixels, x 52
# to 67 and y 1 to 13 from the card's top left; the places differ by a
# pixel's phase: one leg can look short). Open padlocks have their own
# brightness and grey-shackle checks, calibrated on eg_cards_unlocked.
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


@calibrated
def title(shot):
    """The screen's title reads "Soul Weapon Engraving"."""
    return any(font.distance(text.replace(" ", ""), TITLE.replace(" ", "")) <= 4
               for text, _, _ in font.read(shot, TITLE_AREA, font=TITLE_FONT))


@calibrated
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


@calibrated
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


@calibrated
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
            # Narrow 1s are real suffixes (Lv.41), not noise to discard.
            # Only the sparse Lv prefix before the number is ignored. Any
            # unrecognised suffix remains a token and makes level() fail.
            ink_count = sum(sum(row[x:right + 1]) for row in ink)
            if right - x + 1 >= 3 or runs or ink_count >= 6:
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


@calibrated
def level(shot, index):
    """The card's level, None when a digit does not read."""
    ink = _digits_ink(shot, index)
    runs = _digit_runs(ink)
    if not 1 <= len(runs) <= 2 or not DIGITS:
        return None
    value = 0
    for run in runs:
        glyph = _scaled(_digit_grid(ink, run))
        scored = sorted((min(sum(a != b for ra, rb in zip(glyph, shape) for a, b in zip(ra, rb))
                             for shape in variants), digit)
                        for digit, variants in DIGIT_VARIANTS.items())
        if scored[0][0] > 6 or (len(scored) > 1 and scored[1][0] - scored[0][0] < 2):
            return None
        value = value * 10 + scored[0][1]
    return value


@calibrated
def bright(shot, index):
    """The card is drawn bright (its piece unlocked; a locked card is
    dimmed): at least 20 pixels of its drawing at 200 or more."""
    x0, y0 = _card_px(shot, index)
    return sum(1 for x in range(x0 + 14, x0 + 50) for y in range(y0 + 15, y0 + 56)
               if max(_pixel(shot, x, y)) >= 200) >= 20


@calibrated
def locked(shot, index):
    """The card's padlock: True (closed: its white pixels within 4 of that
    place's closed padlock), False (open: no white in it, a grey open
    shackle, the card bright, as eg6's), None otherwise (not read). Only
    meaningful with no popup and no preview over the screen."""
    x0, y0 = _card_px(shot, index)
    seen = ["".join("#" if min(_pixel(shot, x, y)) >= 200 else "." for x in range(x0 + 52, x0 + 68))
            for y in range(y0 + 1, y0 + 14)]
    differ = sum(a != b for ra, rb in zip(seen, LOCKED[index]) for a, b in zip(ra, rb))
    if differ <= 4:
        return True
    box = [_pixel(shot, x, y) for x in range(x0 + 50, x0 + 68) for y in range(y0, y0 + 14)]
    white = sum(1 for p in box if min(p) >= 200)
    grey = sum(1 for p in box if 90 <= min(p) < 190)
    if white == 0 and grey >= 40 and bright(shot, index):
        return False
    return None


@calibrated
def placed(shot, index):
    """The card's "E" (its piece is in the grid): a white letter at the
    bottom left."""
    x0, y0 = _card_px(shot, index)
    white = sum(1 for x in range(x0 + 2, x0 + 12) for y in range(y0 + 52, y0 + 66)
                if min(_pixel(shot, x, y)) >= 200)
    return white >= 15


@calibrated
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


def _unread_cards():
    return [{"index": index, "shape": None, "rotation": None, "cells": None, "level": None, "locked": None,
             "placed": None, "kind": None, "bright": None} for index in range(8)]


@calibrated
def cards(shot, shapes):
    """The 8 cards: [{index, shape, rotation, cells, level, locked, placed,
    kind, bright}]. A bright (unlocked) card's drawing, level and icon are
    not calibrated: None (the sequence knows it from before it was
    unlocked). Under the piece popup nothing of the cards is read."""
    if popup(shot):
        return _unread_cards()
    out = []
    for index in range(8):
        lit = bright(shot, index)
        cells = None if lit else _drawing(shot, index)
        found = shape_of(cells, shapes) if cells else None
        out.append({"index": index, "shape": found[0] if found else None, "rotation": found[1] if found else None,
                    "cells": cells, "level": None if lit else level(shot, index), "locked": locked(shot, index),
                    "placed": placed(shot, index), "kind": None if lit else kind(shot, index), "bright": lit})
    return out


# -- The piece popup (a tap on a card's middle): brown, y 0.40-0.78, the
# card large with its padlock, Engraving Effect, Additional Options. Closed
# by a tap outside it, above (POPUP_CLOSE_TAP). Calibrated on eg2 (locked)
# and eg3 (unlocked by a tap on its padlock), 2026-10-22.
POPUP_BROWN = (68, 51, 35)
POPUP_POINTS = ((100 / 480, 600 / 1040), (240 / 480, 640 / 1040), (380 / 480, 700 / 1040))
POPUP_LOCK_TAP = (0.595, 0.475)
POPUP_LOCK_BOX = (276, 482, 297, 505)
POPUP_CLOSE_TAP = (0.5, 0.15)
POPUP_OPTION_AREA = (0.2, 0.71, 0.65, 0.755)


@calibrated
def popup(shot):
    """The piece popup is open: its brown at three places."""
    return all(all(abs(a - b) <= 8 for a, b in zip(_px(shot, fx, fy), POPUP_BROWN)) for fx, fy in POPUP_POINTS)


@calibrated
def popup_padlock(shot):
    """The popup's padlock: "closed" (white), "open" (grey, no white: eg3),
    None (no popup, or neither)."""
    if not popup(shot):
        return None
    width, height, _ = shot
    sx, sy = width / WIDTH, height / HEIGHT
    left, top, right, bottom = POPUP_LOCK_BOX
    box = [_pixel(shot, int(x * sx), int(y * sy)) for x in range(left, right) for y in range(top, bottom)]
    white = sum(1 for p in box if min(p) >= 200)
    grey = sum(1 for p in box if 90 <= min(p) < 190)
    if white >= 80:
        return "closed"
    if white <= 3 and grey >= 80:
        return "open"
    return None


@calibrated
def popup_gold(shot):
    """The popup's Additional Options read "Monster Gold …" (the pixel
    font reads its "Gold")."""
    if not popup(shot):
        return False
    return any("Gold" in text.split() for text, _, _ in font.read(shot, POPUP_OPTION_AREA))


# -- The preview of a piece being placed (a slow drag from a card onto the
# grid): its cubes over the grid in the card's orientation, the cubes
# outside the shape tinted red, and a bar under it: cancel (red X), rotate
# (a quarter turn clockwise, in place), confirm (a check, bright green when
# the spot is valid, grey-green when not). A swipe from one of its cubes
# moves it by that many cells. Calibrated on eg7 (invalid), eg8 (turned)
# and eg9 (moved, valid), 2026-10-22.
BAR_AREA = (60, 200, 420, 600)
BAR_STEP = 45  # px from the cancel's middle to rotate, and again to confirm
# Where the finger holds the piece: its cells' middle sits this many cells
# above the finger (eg7: dropped at row 0.69, its middle on row 0).
HOLD_ROWS = 0.7


def _red(p):
    return p[0] > 200 and p[1] < 60 and p[2] < 60


@calibrated
def bar(shot):
    """{cancel, rotate, confirm: (x, y) fractions, valid: True, False or
    None} of the preview's bar, None without one (no red cancel)."""
    width, height, _ = shot
    sx, sy = width / WIDTH, height / HEIGHT
    left, top, right, bottom = BAR_AREA
    red = [(x, y) for x in range(int(left * sx), int(right * sx)) for y in range(int(top * sy), int(bottom * sy))
           if _red(_pixel(shot, x, y))]
    if len(red) < 150:
        return None
    cx, cy = sum(x for x, _ in red) / len(red), sum(y for _, y in red) / len(red)
    if max(x for x, _ in red) - min(x for x, _ in red) > 40 * sx:
        return None
    step = BAR_STEP * sx
    tick = [_pixel(shot, int(cx + 2 * step + dx), int(cy + dy)) for dx in range(-16, 17) for dy in range(-14, 15)]
    lit = sum(1 for p in tick if p[1] > 180 and p[0] < 170 and p[2] < 90)
    dim = sum(1 for p in tick if p[1] > 90 and p[1] > p[0] + 25 and p[1] > p[2] + 40)
    valid = True if lit >= 100 else False if dim >= 100 and lit < 20 else None
    return {"cancel": (cx / width, cy / height), "rotate": ((cx + step) / width, cy / height),
            "confirm": ((cx + 2 * step) / width, cy / height), "valid": valid}


@calibrated
def cubes(shot):
    """{(row, col): "cube" or "red"} of the cells holding a cube (placed or
    previewed), rows and cols -1 to 5 (the preview may stick out of the
    grid): a cube is blue on at least 25 of 81 samples (one half hidden by
    the bar still counts), a red one pink and blue on at least 8 each."""
    width, height, _ = shot
    out = {}
    for row in range(-1, 6):
        for col in range(-1, 6):
            cx, cy = cell_centre(row, col)
            x0, y0 = int(cx * width), int(cy * height)
            samples = [_pixel(shot, x0 + dx, y0 + dy) for dx in range(-12, 13, 3) for dy in range(-12, 13, 3)
                       if 0 <= x0 + dx < width and 0 <= y0 + dy < height]
            blue = sum(1 for r, g, b in samples if b > 150 and b > r + 60)
            pink = sum(1 for r, g, b in samples if r > 150 and b > 120 and r > g + 30)
            if pink >= 8 and blue >= 8:
                out[(row, col)] = "red"
            elif blue >= 25:
                out[(row, col)] = "cube"
    return out


def hold_point(cells):
    """Where to drop a card so that its preview lands on cells (in the
    card's orientation): their middle, HOLD_ROWS lower."""
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    x, _ = cell_centre(0, (min(cols) + max(cols)) / 2)
    _, y = cell_centre((min(rows) + max(rows)) / 2 + HOLD_ROWS, 0)
    return x, y


INVENTORY_DROP = (0.5, 0.68)

# The gates (05-plugins/AGENTS.md, test_gates.py): each reading has real
# captures of every state it tells apart.
PADLOCK_LEARNED = True    # eg_cards_unlocked (open), eg_cards_relocked (closed)
POPUP_LEARNED = True      # eg_popup_unlocked, eg_popup_locked; no popup: eg_cards_relocked
PREVIEW_LEARNED = True    # eg_preview_base, eg_preview_turned (invalid), eg_preview_valid
