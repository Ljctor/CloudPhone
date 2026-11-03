"""Read the Legendary Grade 3 count on the open Equipment tab.

The six colour rows are fixed in the game's grid: the red row is
Legendary and the second column is Grade 3. The numerator under that card
is the displayed balance; /5 is the combine threshold, not a divisor.
The templates below were cut from real 480x1040 Weapon/Accessories
captures. Geometry also accepts the native 720x1560 phone size, while
the OCR still requires the same distinct glyph shapes and /5 suffix.
Unmatched digits, a clipped card, and other resolutions do not produce a
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
# cards (the other cards in those captures provide 0 and 1). Native 480
# captures additionally prove 6 in 60/5 and both vertical raster phases.
# Independent source-font replays supply 7–9 below; these are not real crops.
SHAPES = {
    "0": (".####.", "##..##", "##..##", "##..##", "##..##", "##..##", "##..##", ".####."),
    "1": (".#.", "##.", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "3": (".####.", "##..##", "....##", "..###.", "....##", "....##", "##..##", ".####."),
    "4": ("....##.", "...###.", "..####.", ".##.##.", "##..##.", "#######", "....##.", "....##."),
    "5": ("######", "##....", "##....", "#####.", "....##", "....##", "##..##", ".####."),
    "6": ('..###.', '.####.', '###...', '#####.', '######', '##..##', '##..##', '##..##', '.####.'),
    "/": ("....#", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#...", "#....", "#...."),
}


# Exact white-core masks from the reviewed settled native480 cards. Match
# the nearest phase per character, so the ambiguity gap remains between
# different characters rather than duplicate templates for the same one.
PHASES = {
    '3': (
        ('.####.', '######', '##..##', '..####', '..####', '....##', '##..##', '##..##', '.####.'),
    ),
    '0': (
        ('.###.', '#####', '#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'),
    ),
    '5': (
        ('######', '######', '##....', '#####.', '######', '....##', '##..##', '##..##', '.####.'),
        ('#####', '#####', '#....', '####.', '#####', '....#', '#...#', '#...#', '.###.'),
    ),
    '/': (
        ('....#', '....#', '...##', '...#.', '..##.', '..#..', '.##..', '.#...', '.#...', '#....', '#....'),
        ('....##', '....##', '...###', '...##.', '..###.', '..##..', '.###..', '.##...', '.##...', '##....', '##....'),
    ),
    '2': (
        ('.###.', '#####', '#...#', '...##', '..##.', '.##..', '##...', '#....', '#####'),
    ),
}


# A later real settled native480 69/5 card has another subpixel phase.
# Its 90 and 110 white cores agree exactly; retain those observed shapes
# rather than relaxing the glyph error or the cross-character gap.
PHASES['6'] = PHASES.get('6', ()) + (('..###.', '.###..', '##....', '#####.', '######', '##..##', '##..##', '#####.', '.###..'),)
PHASES['/'] = PHASES.get('/', ()) + (('....##', '....##', '...##.', '...##.', '..##..', '..##..', '.##...', '.##...', '##....', '##....', '#.....'),)
PHASES['5'] = PHASES.get('5', ()) + (('#####', '#####', '#....', '####.', '#####', '....#', '#...#', '#####', '.###.'),)


# Source-derived white cores, not observed inventory captures. The privately
# extracted Beantown.ttf is AaSirius1 Regular, SHA256
# 81d4d6d8855841cc55d613ea070249664f5749c9dd0ff32826fe2afd68c7bed1.
# The actual cardCount component uses Font323, normal style, best fit and
# a .5 parent scale. FreeType NO_HINTING + MONO at 25 px, no synthetic
# bold, followed by bilinear .5 sampling reproduces every real 0–6 and
# slash template exactly. Entire real native480 "3 / 5" (two settling
# phases) and "60 / 5" rows also replay with zero white-core disagreement
# at one shared origin, baseline and threshold per row. No digit-specific
# deformation or amount-conditioned fitting was used. These remaining
# digits use that same font/raster family, quarter-pixel x/y phases and
# the existing 90/110/130/150/170 white-core thresholds. No full font or
# private game asset is required at runtime or included in the repository.
FONT_DERIVED_PHASES = {
    '7': (
        ('#####', '....#', '....#', '...##', '...#.', '..##.', '..#..', '..#..'),
        ('#####', '#####', '....#', '...##', '...##', '..##.', '..##.', '..##.'),
        ('#####', '#####', '....#', '...##', '...##', '..###', '..##.', '..##.', '..##.'),
        ('#####', '#####', '....#', '...##', '...#.', '..##.', '..#..', '..#..', '..#..'),
        ('#####', '#####', '....#', '....#', '...#.', '...#.', '..#..', '..#..', '..#..'),
        ('#####', '....#', '....#', '...##', '...##', '..##.', '..##.', '..##.'),
        ('#####', '....#', '....#', '...#.', '...#.', '..#..', '..#..', '..#..'),
        ('######', '######', '....##', '...###', '...##.', '..###.', '..##..', '..##..'),
        ('######', '....##', '....##', '...##.', '...##.', '..##..', '..##..', '..##..'),
        ('######', '######', '....##', '...###', '...##.', '..###.', '..##..', '..##..', '..##..'),
        ('######', '######', '....##', '....##', '...##.', '...##.', '..##..', '..##..', '..##..'),
        ('######', '....##', '.....#', '....#.', '....#.', '...#..', '...#..', '...#..'),
        ('######', '######', '.....#', '....##', '....#.', '...##.', '...#..', '...#..', '...#..'),
        ('######', '.....#', '.....#', '....#.', '....#.', '...#..', '...#..', '...#..'),
        ('#####', '#####', '....#', '...##', '...#.', '..##.', '..#..', '..#..'),
    ),
    '8': (
        ('.####.', '##..##', '##..##', '.####.', '##..##', '##..##', '##..##', '.####.'),
        ('.####', '#####', '##..#', '#####', '#####', '##..#', '##..#', '#####'),
        ('.###.', '##..#', '#...#', '.####', '##..#', '#...#', '#...#', '.#..#'),
        ('.####', '#####', '##..#', '#####', '#####', '##..#', '##..#', '##..#', '.####'),
        ('.###.', '#####', '#...#', '#####', '#####', '#...#', '#...#', '#...#', '.###.'),
        ('.###.', '.####', '#...#', '##..#', '.####', '#...#', '#...#', '#...#', '.###.'),
        ('.####', '##..#', '##..#', '.####', '##..#', '##..#', '##..#', '.####'),
        ('.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '#...#', '.###.'),
        ('.####.', '######', '##..##', '######', '######', '##..##', '##..##', '######'),
        ('.####.', '##..##', '##..##', '.####.', '##..##', '##..##', '##..##', '.#..#.'),
        ('.####.', '######', '##..##', '######', '######', '##..##', '##..##', '##..##', '.####.'),
        ('.####.', '.####.', '##..##', '##..##', '.####.', '##..##', '##..##', '##..##', '.####.'),
        ('..###.', '##..##', '##...#', '.####.', '##..##', '##...#', '##...#', '.#..#.'),
        ('..###.', '######', '##...#', '######', '######', '##...#', '##...#', '##...#', '..###.'),
        ('..###.', '.####.', '##...#', '##..##', '.####.', '##...#', '##...#', '##...#', '..###.'),
        ('..###.', '##...#', '##...#', '..###.', '##...#', '##...#', '##...#', '..###.'),
        ('.###.', '#####', '#...#', '#####', '#####', '#...#', '#...#', '#####'),
        ('.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '#...#'),
        ('.###.', '.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '#...#', '.###.'),
    ),
    '9': (
        ('.####.', '##..##', '##..##', '##..##', '.#####', '....##', '...##.', '.###..'),
        ('.####', '#####', '##..#', '##..#', '#####', '.####', '...##', '.###.'),
        ('.###.', '##..#', '#...#', '#...#', '.####', '....#', '...##', '...#.'),
        ('.####', '#####', '##..#', '##..#', '#####', '.####', '...##', '...##', '.###.'),
        ('.###.', '#####', '#...#', '#...#', '#####', '.####', '...##', '...#.', '.##..'),
        ('.###.', '.####', '#...#', '#...#', '##..#', '.####', '....#', '...#.', '.##..'),
        ('.####', '##..#', '##..#', '##..#', '.####', '....#', '...##', '.###.'),
        ('.###.', '#...#', '#...#', '#...#', '.####', '....#', '...#.', '.##..'),
        ('.####.', '######', '##..##', '##..##', '######', '.#####', '...###', '.####.'),
        ('.####.', '##..##', '##..##', '##..##', '.#####', '....##', '...##.', '...#..'),
        ('.####.', '######', '##..##', '##..##', '######', '.#####', '...###', '...##.', '.###..'),
        ('.####.', '.####.', '##..##', '##..##', '##..##', '.#####', '....##', '...##.', '.###..'),
        ('.####.', '######', '##..##', '##..##', '######', '..####', '...###', '..###.'),
        ('..###.', '##..##', '##...#', '##...#', '.#####', '....##', '....#.', '...#..'),
        ('..###.', '######', '##...#', '##...#', '######', '..####', '....##', '....#.', '..##..'),
        ('.####.', '######', '##..##', '##..##', '######', '.#####', '....##', '...##.', '.###..'),
        ('..###.', '.####.', '##...#', '##...#', '##..##', '..####', '....##', '....#.', '..##..'),
        ('..###.', '##...#', '##...#', '##...#', '..####', '.....#', '....#.', '..##..'),
        ('.###.', '#####', '#...#', '#...#', '#####', '.####', '...##', '.###.'),
        ('.###.', '#...#', '#...#', '#...#', '.####', '....#', '...#.'),
        ('.###.', '.###.', '#...#', '#...#', '#...#', '.####', '....#', '...#.', '.##..'),
    ),
}

SHAPES.update({char: phases[0] for char, phases in FONT_DERIVED_PHASES.items()})
PHASES.update({char: phases[1:] for char, phases in FONT_DERIVED_PHASES.items()})


def _pixel(shot, x, y):
    width, _, pixels = shot
    i = (y * width + x) * 3
    return pixels[i], pixels[i + 1], pixels[i + 2]


def _red_line(shot, y, scale):
    hits = 0
    for x in range(round(CARD_X[0] * scale), round(CARD_X[1] * scale)):
        r, g, b = _pixel(shot, x, y)
        # The adjacent orange rarity border is (239,137,68) on real
        # native captures; brightness alone must not call it Legendary.
        hits += r > 140 and r > 2.5 * g and r > 2.5 * b
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


def _visible_card_top(shot):
    if not shot or len(shot) != 3 or shot[:2] not in ((WIDTH, HEIGHT), (720, 1560)):
        return None
    if len(shot[2]) != shot[0] * shot[1] * 3:
        return None
    scale = shot[0] / WIDTH
    top = _card_top(shot, scale)
    return top if top is not None and top + round(105 * scale) <= round(900 * scale) else None


def card_visible(shot):
    """A whole calibrated red Grade 3 card is visible, even if its number
    is unread. The caller still verifies the selected Equipment tab before
    navigating; this adds no action or coordinate authority."""
    return _visible_card_top(shot) is not None


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


def _glyphs(shot, top, scale, threshold=130):
    x0, x1 = (round(x * scale) for x in COUNT_X)
    rows = [[min(_pixel(shot, x, y)) > threshold for x in range(x0, x1)]
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
    top = _visible_card_top(shot)
    if top is None:
        return None
    scale = shot[0] / WIDTH
    values = []
    # Subpixel settling shifts anti-aliased edge intensities even when the
    # card's integer geometry is unchanged. Normalize the whole line at a
    # bounded set of white-core levels instead of relaxing glyph errors or
    # learning a new literal mask for each intensity fluctuation.
    for threshold in (90, 110, 130, 150, 170):
        chars = []
        for glyph in _glyphs(shot, top, scale, threshold):
            closest = sorted((min(_distance(glyph, item) for item in (shape,) + PHASES.get(char, ())), char)
                             for char, shape in SHAPES.items())
            if closest[0][0] > MAX_DISTANCE or closest[1][0] - closest[0][0] < 0.06:
                break
            chars.append(closest[0][1])
        else:
            text = "".join(chars)
            if re.fullmatch(r"(?:0|[1-9][0-9]{0,3})/5", text):
                values.append(int(text[:-2]))
    # One lone parse, or two confident but different complete values, is
    # uncertain. The thresholds never vote an unknown glyph into existence.
    return values[0] if len(values) >= 2 and len(set(values)) == 1 else None


_safety = None


def _safety_readers():
    global _safety
    if _safety is None:
        spec = importlib.util.spec_from_file_location(
            "cloudphone_plugin_slayer_legend_equipment_safety", os.path.join(os.path.dirname(__file__), "screens.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _safety = module, {
            (480, 1040): module.Patch("equipment_inspect_card_480", limit=.35),
            (720, 1560): module.Patch("equipment_inspect_card_720", limit=.35),
        }
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
    _, cards = _safety_readers()
    # Native rendering changes the card's thin edges; resizing a 720
    # signature to 480 is not a calibrated native-480 safety reading.
    card = cards.get(shot[:2])
    return card is not None and card.margin(shot) >= .3


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
