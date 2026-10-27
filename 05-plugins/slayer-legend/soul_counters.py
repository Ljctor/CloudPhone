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
only once calibrated on a real capture. At 720x1560, grouped full
digits use their own captured glyph templates and comma positions;
the lower-resolution reading is still gated.

Measured on real 480x1040 captures (2026-10-22, the Soul Weapon screen
open on Vision): fixtures/souls_row, souls_row_b; and on a real
720x1560 capture: fixtures/souls_full_mid.
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
# The Soul Weapon row at 720x1560 has enough pixels to separate the
# individual full-size digits. The 480x1040 rendering remains gated.
HIGH_RES_FULL_DIGITS_CALIBRATED = True
# 5x9, four-level ink grids cut from the real souls_full_mid capture. A
# digit can have more than one shape: the four boxes use different text
# sizes, and a narrow value changes the game's font scaling.
SOUL_720_TEMPLATES = {
    "0": (534245830228600894250444984, 616457439085968241769496061, 616528413069031898460696061),
    "1": (1237915211085841551190916068, 1237927040083018827279882228, 1237934082105028938877108192,
          1237934100551773029766528992, 1237938845999226001392926708, 1237938845999226007840620532),
    "2": (1237542191465611778300292605, 1237561104007987747464592893, 1237561104007992145511103997),
    "3": (229477275943595753163109565, 534245823303006855404087480, 610410153429463078121944568,
          616457138233296602593672701, 618822151497790338726538493),
    "4": (387335582091194468753948992, 1006885248297046306706113344),
    "5": (616457433380996390374260735, 616528411912493227290832895),
    "6": (229478464618067859956932784, 229478464618067859957981360, 618821858663620976548435444),
    "7": (140372477627089319013362687, 140372551774635058950745087, 212978931832531103224059903),
    "8": (534245830228428193615472824, 616452785962222976421751293, 616457144010296733000973821,
          616457144010301131047484925, 616457439158276679144488445, 616528411915028495885905405),
    "9": (74236658338512090592359613, 145265528181309317391739064, 150483964393148804402953725,
          151692890212763433577659901, 229059125271931138015390205),
}


def _digit_720(marks, top, bottom, left, right):
    ys = [y for y in range(top, bottom + 1) if any(marks[y][left:right + 1])]
    if not ys or ys[-1] - ys[0] + 1 < 0.65 * (bottom - top + 1):
        return None
    grid = font._grid(marks, (left, right, ys[0], ys[-1]), 5, 9)
    values = [min(3, round(value * 3)) for row in grid for value in row]
    distances = sorted((min(sum((value - (template >> (2 * k) & 3)) ** 2
                                for k, value in enumerate(values)) / 405 for template in templates), digit)
                       for digit, templates in SOUL_720_TEMPLATES.items())
    if distances[0][0] > 0.12 or distances[1][0] - distances[0][0] < 0.012:
        return None
    return distances[0]


def _full_720(shot, colour):
    """Read grouped full digits only when their separators and every glyph
    are independently visible. An uncertain digit leaves the value unread,
    so one OCR error cannot create a bogus souls-per-second spike."""
    rows = font.crop(shot, _area(shot, TEXTS[colour]), min)
    marks = font.ink(rows, WHITE)
    found = font.lines(marks)
    if not found:
        return None
    top, bottom = max(found, key=lambda line: line[1] - line[0])
    height = bottom - top + 1
    if not 10 <= height <= 14:
        return None
    # A comma alone reaches the line's lowest pixel. The upper part has
    # digits only, even where a comma joins the next digit at the baseline.
    commas = font._runs([marks[bottom]], 0, 0)
    if len(commas) not in (2, 3) or any(right - left > 2 for left, right in commas):
        return None
    upper = font._runs(marks, top, top + round(height * 0.6) - 1)
    groups = [[] for _ in range(len(commas) + 1)]
    for run in upper:
        group = sum(run[0] > right for _, right in commas)
        if group and run[0] <= commas[group - 1][1] or group < len(commas) and run[1] >= commas[group][0]:
            return None
        groups[group].append(run)
    digits = []
    for index, runs in enumerate(groups):
        expected = 3 if index else (len(runs) if len(runs) <= 3 else 0)
        if not 1 <= expected <= 3 or not runs or len(runs) > expected:
            return None
        runs = list(runs)
        while len(runs) < expected:
            # Split touching digits at the boundary whose two real-font
            # shapes give the strongest match. A comma never enters here.
            choices = []
            for j, (left, right) in enumerate(runs):
                if right - left < 8:
                    continue
                for cut in range(left + 3, right - 2):
                    a = _digit_720(marks, top, bottom, left, cut)
                    b = _digit_720(marks, top, bottom, cut + 1, right)
                    if a and b:
                        choices.append((a[0] + b[0], j, (left, cut), (cut + 1, right)))
            if not choices:
                return None
            _, j, a, b = min(choices)
            runs[j:j + 1] = [a, b]
        read = [_digit_720(marks, top, bottom, left, right) for left, right in runs]
        if any(item is None for item in read):
            return None
        digits.append("".join(item[1] for item in read))
    text = ",".join(digits)
    parsed = gold.parse(text)
    return {"text": text, **parsed} if parsed and parsed["full"] else None


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
        if 700 <= shot[0] < 900 and HIGH_RES_FULL_DIGITS_CALIBRATED:
            full = _full_720(shot, colour)
            if full:
                counts[colour] = full
                continue
        text = read_text(shot, colour)
        parsed = gold.parse(text) if text and "?" not in text else None
        if parsed and parsed["full"] and not FULL_DIGITS_CALIBRATED:
            parsed = None
        counts[colour] = {"text": gold.normalize_text(text), **parsed} if parsed else None
    return counts
