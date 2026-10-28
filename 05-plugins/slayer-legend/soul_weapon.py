"""Reads the Soul Weapon screen (Equipment -> Weapon -> the sword icon) off
a screenshot (width, height, RGB bytes). Pure, stdlib only.

What it reads, calibrated at 480x1040 on two captures of 2026-10-21 (the
card on the equipped "Ambition", Owned : 1, then on "Grand", Owned : 0,
picked in the list):

- title(): "Soul Weapon" at the top left of the popup (y 0.52-0.55).
- name(): the selected weapon's name on the card, matched against the
  closed list of the weapons' names (engravings.json) with a margin:
  None unless one name is clearly the closest.
- owned(): the digit after "Owned :" at the card's top right, 0 or 1, by
  its strokes (narrow stem: 1; hollow: 0); None for anything else.
- rows(): the list's cells (x 0.03-0.15, y 0.55-0.93), each {top, bottom,
  selected}: a cell is a run of rows whose left border is the list's brown
  (or the selection's red) frame, the selected one has its top in red.
  Cells cut by the list's edges are left out.
- tags(): the orange tags in the list column ([left, top, right, bottom]),
  and tag(): the text of the one tag, matched against templates of its
  white text cut from real captures (TAG_TEMPLATES: Unequip from
  fixtures/sw_tag_unequip; Equip from native Relax Owned:1), else None.
  TAG_LEARNED (both templates there) gates the Equip tap.
- tab(): the Equipment panel's active tab, "weapon" or "accessories" (the
  Accessories tab has its own top-right icon, Black Orb), by which tab's
  text is clearly the brightest; None otherwise.
- equipped_badge(): the card's sword badge (top right) is red. The real
  owned, unequipped Relax also shows red: this colour cannot establish
  equipment state. BADGE_TELLS stays False.

The engraving screen (from the card's big icon) is read by
engraving_screen.py.
"""

import importlib.util
import os
from functools import wraps

# The pixel font, loaded beside this file (the gateway loads plugin files
# by path, not as a package).
_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_soul_weapon_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_soul_weapon_pixels", os.path.join(os.path.dirname(__file__), "capture_pixels.py"))
_capture_pixels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_capture_pixels)


def calibrated(reader):
    @wraps(reader)
    def read_native(shot, *args, **kwargs):
        if shot[0] < 480 or shot[1] < 1040:
            if reader.__name__ == "tag":
                boxes = tags(shot)
                return None, boxes[0] if len(boxes) == 1 else None
            if reader.__name__ in {"title", "weapon_detail"}:
                return False
            if reader.__name__ not in {"rows", "tags"}:
                return None
        return reader(_capture_pixels.canonical(shot), *args, **kwargs)
    return read_native

TITLE_AREA = (0.0, 0.515, 0.35, 0.55)
TITLE = "Soul Weapon"
NAME_AREA = (0.42, 0.59, 0.84, 0.625)
OWNED_AREA = (0.78, 0.558, 0.96, 0.58)
OWNED_LEVEL = 120
LIST_X = (0.025, 0.15)
LIST_Y = (0.55, 0.93)
# The actual list viewport starts at native y870 (canonical y580), below
# the title/header padding included in LIST_Y. A cell touching this edge
# is clipped even when its surviving border run looks almost full-height.
LIST_CONTENT_TOP = 580 / 1040
# Where a cell is tapped to select it: in its upper part, above where its
# Equip / Unequip tag shows (the tag sits in the cell's lower half).
SELECT_X = 0.087
SELECT_DEPTH = 0.3
TAB_Y = (0.402, 0.423)
TABS = {"weapon": (0.03, 0.2), "accessories": (0.22, 0.4), "relic": (0.42, 0.58), "spirit": (0.6, 0.77)}
BADGE_AREA = (0.855, 0.59, 0.915, 0.62)
# Red is also present on the actual unequipped, owned Relax. Never use
# this colour as equipped-state evidence.
BADGE_TELLS = False

# Shapes cut from the title "Soul Weapon" (its x-height is taller than the
# stage names'): used for the title only.
TITLE_FONT = dict(font.FONT, **{
    "S": ['.###', '#...', '###.', '..##', '...#', '#.##', '.##.', '....', '....'],
    "o": ['....', '.##.', '####', '#..#', '#..#', '#.##', '.##.', '....', '....'],
    "u": ['....', '#..#', '#..#', '#..#', '#..#', '#.##', '.###', '....', '....'],
    "l": ['#', '#', '#', '#', '#', '#', '#', '.', '.'],
    "W": ['#..#..#', '#..#..#', '#######', '.#####.', '.#####.', '..#.#..', '.......', '.......', '.......'],
    "e": ['....', '.##.', '####', '####', '#...', '##..', '.###', '....', '....'],
    "a": ['....', '.##.', '.###', '.###', '#..#', '##.#', '.###', '....', '....'],
    "p": ['....', '###.', '####', '#..#', '#..#', '###.', '#...', '....', '....'],
    "n": ['....', '###.', '####', '#..#', '#..#', '#..#', '#..#', '....', '....'],
})

# The card's name font is the stage names' (pixel_font.FONT), with the
# letters it lacked cut from the card ("Ambition", "Grand") and from
# "Equip Effect" below it.
CARD_FONT = dict(font.FONT, **{
    # Actual Skilfulness/Relax headers: previously absent lowercase k/x.
    'k': ['96000', '96024', '96297', '98873', '99510', '98876', '85288', '00000', '00000'],
    'x': ['00000', '42024', '68497', '07873', '04941', '68588', '85058', '00000', '00000'],

    # Real Friendship header (sw_name_friendship), previously absent F.
    "F": ['99994', '91112', '98888', '96668', '90004', '90004', '80004', '00000', '00000'],
    # Actual 480 Ecstasy header (sw_name_ecstasy): E/c phase and missing y.
    'E~ecstasy': ['99994', '91110', '98844', '96634', '90004', '96667', '88884', '00000', '00000'],
    'c~ecstasy': ['0000', '2442', '8667', '9003', '9001', '8667', '4884', '0000', '0000'],
    'y~ecstasy': ['0000', '3014', '8039', '8787', '5991', '1740', '6820', '8700', '0000'],

    # Real Honor header, sw_name_honor: the font previously lacked H.
    "H": ['90009', '90009', '98889', '96669', '90009', '90009', '80008', '00000', '00000'],
    "A": ['.##.', '####', '####', '#..#', '####', '#..#', '#..#', '....', '....'],
    "m": ['.......', '.......', '#######', '##.##.#', '##.##.#', '##.##.#', '##.##.#', '.......', '.......'],
    "b": ['#....', '#....', '#####', '##.##', '#..##', '#####', '####.', '.....', '.....'],
    "G": ['#####', '#....', '#.###', '#.###', '#...#', '#####', '.####', '.....', '.....'],
    "E": ['####', '#...', '##..', '###.', '#...', '#...', '####', '....', '....'],
    "q": ['....', '....', '.###', '#..#', '#..#', '####', '...#', '...#', '....'],
    "u": ['....', '....', '#..#', '#..#', '#..#', '#..#', '.###', '....', '....'],
    "p": ['....', '....', '####', '#..#', '#..#', '####', '##..', '#...', '....'],
    "f": ['.###', '.#..', '##..', '####', '.#..', '.#..', '.#..', '....', '....'],
    "a": ['.....', '.....', '.####', '#####', '#..##', '#####', '.####', '.....', '.....'],
    "d": ['...##', '...##', '#####', '#.###', '#..##', '#####', '.####', '.....', '.....'],
    # From "Vision" (2026-10-21).
    "s": ['.....', '.....', '#####', '####.', '...##', '#####', '.###.', '.....', '.....'],
    "o": ['....', '....', '####', '#..#', '#..#', '####', '.##.', '....', '....'],
})

# Native 720 capture phase (sw_name_ambition_720, sw_name_wild_720).
# Whole-word masks avoid guessing through aliased rn/m, h/b and n/o
# glyphs. The legacy OCR confidence and ambiguity margin stay unchanged.
NAME_INK = 180
NAME_TEMPLATE_MOST = 0.02
NAME_NATIVE_TEMPLATES = {'Ambition': ('...###................##........###..###.....###..................',
              '..#####...............##........###..###.....###..................',
              '..##.##...#####.####..##.####..####.#######.####..#####...######..',
              '..##.##...#####.####..##.####..####.#######.####..#####...######..',
              '##....###.##..##..###.####..##..###..###....######....###.##...###',
              '##....###.##..##...##.####..##..###..###.....#####....###.##....##',
              '##....###.##..##...##.##....##..###..###.....#####....###.##....##',
              '#########.##..##...##.##....##..###..###.....#####....###.##....##',
              '#########.##..##...##.##....##..###..###.....#####....###.##....##',
              '##....###.##..##...##.##....##..###..###.....#####....###.##....##',
              '##....###.##..##...##.########..###..######..############.##....##',
              '##....###.##..##...##.#######...###....####..###..#####...##....##'),
 'Wild': ('##....###...###..######.......##',
          '##....###...###..######.......##',
          '##....###...###.#######..####.##',
          '##....###...###.#######..####.##',
          '.###.##.##.###...######.##..####',
          '..##.##.##.###...######.##..####',
          '..##.##.##.###...######.##....##',
          '..##.##.##.###...######.##....##',
          '..##.##.##.###...######.##....##',
          '...###...###.....######.##....##',
          '...###....##.....######.########',
          '...###....##.....######..#######')}


# Exact native Relax name, from the same reviewed Owned:1 / Equip capture.
NAME_NATIVE_TEMPLATES["Relax"] = (
    "#######............##...................",
    "#########..........##...................",
    "##....###..#####...##..######..###...###",
    "##....###..#####...##..######..###...###",
    "##....###.##...###.##.......##..###.##..",
    "##....###.##....##.##.......##..###.##..",
    "#######...########.##..#######....##....",
    "#######...########.##.########....##....",
    "##.###....##.......##.##....##....##....",
    "##..###...##.......##.##....##..###.##..",
    "##...####.########.##.########.####.####",
    "##....###..#######.##..#######.###...###",
)


def _name_ink(shot):
    left, top, right, bottom = _box(shot, NAME_AREA)
    points = {(x, y) for y in range(top, bottom) for x in range(left, right)
              if min(_pixel(shot, x, y)) >= NAME_INK}
    if not points:
        return ()
    xs, ys = zip(*points)
    return tuple("".join("#" if (x, y) in points else "." for x in range(min(xs), max(xs) + 1))
                 for y in range(min(ys), max(ys) + 1))


# A name read is within this many edits per character of its weapon's,
# every other name at least NAME_MARGIN edits further.
NAME_MOST = 0.3
NAME_MARGIN = 2


def _pixel(shot, x, y):
    width, _, pixels = shot
    i = (y * width + x) * 3
    return pixels[i], pixels[i + 1], pixels[i + 2]


def _box(shot, area):
    width, height, _ = shot
    return (max(0, int(area[0] * width)), max(0, int(area[1] * height)),
            min(width, int(area[2] * width)), min(height, int(area[3] * height)))


@calibrated
def title(shot):
    """The popup's title reads "Soul Weapon"."""
    return any(font.distance(text, TITLE) <= 1 for text, _, _ in
               font.read(shot, TITLE_AREA, font=TITLE_FONT, caps=(0.012, 0.02)))


def names_of(table):
    """The weapons' names, each once (two weapons share "Silence")."""
    return sorted({entry["name"] for entry in table["weapons"]})


@calibrated
def read_name(shot):
    """The card's name as read, "?" for an unread glyph; None without one."""
    marks = _name_ink(shot)
    captured = [text for text, template in NAME_NATIVE_TEMPLATES.items()
                if marks and _tag_distance(marks, template) <= NAME_TEMPLATE_MOST]
    if len(captured) == 1:
        return captured[0]
    lines = font.read(shot, NAME_AREA, font=CARD_FONT, caps=(0.009, 0.016))
    return max(lines, key=lambda line: len(line[0]))[0] if lines else None


@calibrated
def name(shot, names):
    """The selected weapon's name (one of names), None when it does not
    read clearly as one."""
    text = read_name(shot)
    if text in NAME_NATIVE_TEMPLATES:
        return text if text in names else None
    return font.close(text, names, most=NAME_MOST, margin=NAME_MARGIN)


def _owned_ink(shot):
    rows = font.crop(shot, OWNED_AREA, min)
    return font.ink(rows, OWNED_LEVEL)


@calibrated
def owned(shot):
    """"Owned : N": 0 or 1, None when the digit is neither or unread."""
    marks = _owned_ink(shot)
    if not marks:
        return None
    lines = font.lines(marks)
    if len(lines) != 1:
        return None
    top, bottom = lines[0]
    runs, cap = font.metrics(marks, top, bottom)
    if cap < 6 or len(runs) < 3:
        return None
    # The digit: the last run, past the colon (a run two columns wide of
    # two dots) that comes before it.
    colon = next((i for i in range(len(runs) - 1, -1, -1) if runs[i][1] - runs[i][0] <= 2 and i < len(runs) - 1),
                 None)
    if colon is None or colon != len(runs) - 2:
        return None
    left, right = runs[-1]
    width = right - left + 1
    ys = [y for y in range(top, bottom + 1) if any(marks[y][left:right + 1])]
    height = ys[-1] - ys[0] + 1
    if height < cap - 1:
        return None
    if width <= 0.5 * height:
        return 1
    middle = [marks[y][left:right + 1] for y in range(ys[0] + height // 3, ys[0] + 2 * height // 3 + 1)]
    hollow = all(row[0] or row[1] for row in middle) and all(row[-1] or row[-2] for row in middle) \
        and all(not any(row[2:-2]) for row in middle)
    return 0 if hollow and width >= 0.6 * height else None


def _frame(rgb):
    r, g, b = rgb
    return 40 <= r <= 75 and 26 <= g <= 52 and 12 <= b <= 36 and r > g > b


def _red(rgb):
    r, g, b = rgb
    return r > 140 and g < 60 and b < 60


@calibrated
def rows(shot):
    """The list's whole cells, top to bottom: [{top, bottom, selected}]
    (fractions of the screen height)."""
    width, height, _ = shot
    left, top, right, bottom = _box(shot, (0.0, LIST_CONTENT_TOP, 0.2, LIST_Y[1]))
    x0, x1 = int(0.02 * width), int(0.04 * width)
    right0, right1 = int(0.135 * width), int(0.155 * width)
    edges = (*range(x0, x1), *range(right0, right1))
    inside = []
    for y in range(top, bottom):
        inside.append(any(_frame(_pixel(shot, x, y)) or _red(_pixel(shot, x, y))
                          # Actual native borders: equipped gold and the
                          # brighter unselected owned Relax brown. Border
                          # colour only finds cells, never equipment state.
                          or (x >= right0 and _pixel(shot, x, y) in ((83, 60, 26), (121, 87, 53)))
                          for x in edges))
    cells, start = [], None
    for i, on in enumerate(inside + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            first, last = top + start, top + i - 1
            # Whole cells only: not touching the list's edges, 0.045 to
            # 0.07 of the screen high.
            if start > 1 and i < len(inside) and 0.045 <= (last - first + 1) / height <= 0.07:
                xs = range(int(0.05 * width), int(0.13 * width))
                red = sum(1 for x in xs for y in (first, first + 1, first + 2) if _red(_pixel(shot, x, y)))
                cells.append({"top": first / height, "bottom": (last + 1) / height,
                              "selected": red >= 0.7 * 3 * len(xs)})
            start = None
    return cells


def select_point(cell):
    """Where a cell is tapped to select it."""
    return (SELECT_X, cell["top"] + SELECT_DEPTH * (cell["bottom"] - cell["top"]))


def _orange(rgb):
    r, g, b = rgb
    return r > 190 and 90 <= g <= 190 and b < 90 and r - g > 40


@calibrated
def tags(shot):
    """The orange boxes in the list column, [left, top, right, bottom]
    (fractions), at least 0.04 wide and 0.008 high."""
    width, height, _ = shot
    left, top, right, bottom = _box(shot, (0.0, LIST_Y[0], LIST_X[1], LIST_Y[1]))
    marked = [y for y in range(top, bottom) if sum(1 for x in range(left, right, 2)
                                                   if _orange(_pixel(shot, x, y))) >= 0.02 * width]
    boxes, run = [], []
    for y in marked + [None]:
        if y is not None and (not run or y == run[-1] + 1):
            run.append(y)
            continue
        if run and len(run) >= 0.008 * height:
            xs = [x for x in range(left, right) for yy in (run[0], run[len(run) // 2], run[-1])
                  if _orange(_pixel(shot, x, yy))]
            if xs and (max(xs) - min(xs) + 1) >= 0.04 * width:
                boxes.append([min(xs) / width, run[0] / height, (max(xs) + 1) / width, (run[-1] + 1) / height])
        run = [y] if y is not None else []
    return boxes


# The tag's white text (min channel at least TAG_INK), cropped to its ink,
# as cut from real captures: "Unequip" from fixtures/sw_tag_unequip
# (2026-10-22, the equipped Vision). "Equip" is from the actual native
# Relax Owned:1 capture, selected but never equipped during calibration.
TAG_INK = 100
TAG_TEMPLATES = {
    "Equip": (
        "#####.............##......",
        "#####..............#......",
        "####..#####.#...#.########",
        "####..#####.#...#.########",
        "#.....#...#.#...#.####..##",
        "#.....#...#.#...#.####..##",
        "#####.#####.#####.#######.",
        "#####..####.#####.#######.",
        "..........#.........##....",
        "..........#..........#....",
    ),
    "Unequip": (
        "#...#..........................#......",
        "#...#..........................#......",
        "#...#.####...###...####.#...#.##.####.",
        "#...#.#####.#####.#####.#...#.##.#####",
        "#...#.#...#.#####.#...#.#...#..#.#...#",
        "#...#.#...#.#####.#...#.#...#..#.#...#",
        "#...#.#...#.#.....#####.#...#..#.#####",
        "#####.#...#.#####..####.#####..#.####.",
        ".###..#...#..####.....#..####..#.#....",
        "......................#..........#....",
    ),
}
# Additional exact native sampling phase from sw_tag_unequip_720.
TAG_NATIVE_TEMPLATES = {'Unequip': ('#...#.........................##......',
             '#...#.........................##......',
             '#...#.####..####..#####.#...#.#######.',
             '#...#.#####.#####.#####.#...#.########',
             '#...#.#...#.#####.#...#.#...#.####..##',
             '#...#.#...#.#####.#...#.#...#.####..##',
             '#...#.#...#.#.....#####.#...#.########',
             '#####.#...#.#####.#####.#####.#######.',
             '####..#...#.#####.....#.#####.####....',
             '......................#.........##....')}
# The Equip tap is real only once both tags read on real captures.
TAG_LEARNED = {"Equip", "Unequip"} <= set(TAG_TEMPLATES)
# At most this share of a template's pixels may differ.
TAG_MOST = 0.08


def _tag_ink(shot, box):
    """The tag's text as rows of "#" and ".", cropped to its ink; () when
    none."""
    left, top, right, bottom = _box(shot, box)
    ink = {(x, y) for y in range(top, bottom) for x in range(left, right) if min(_pixel(shot, x, y)) >= TAG_INK}
    if not ink:
        return ()
    xs, ys = [x for x, _ in ink], [y for _, y in ink]
    return tuple("".join("#" if (x, y) in ink else "." for x in range(min(xs), max(xs) + 1))
                 for y in range(min(ys), max(ys) + 1))


def _tag_distance(ink, template):
    """The share of differing pixels at the best shift of at most one pixel
    (1.0 when the sizes differ by more)."""
    if abs(len(ink) - len(template)) > 1 or abs(len(ink[0]) - len(template[0])) > 1:
        return 1.0
    height, width = max(len(ink), len(template)), max(len(ink[0]), len(template[0]))
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            wrong = 0
            for y in range(-1, height + 1):
                for x in range(-1, width + 1):
                    a = 0 <= y < len(ink) and 0 <= x < len(ink[0]) and ink[y][x] == "#"
                    ty, tx = y + dy, x + dx
                    b = 0 <= ty < len(template) and 0 <= tx < len(template[0]) and template[ty][tx] == "#"
                    wrong += a != b
            best = wrong if best is None else min(best, wrong)
    return best / max(1, sum(row.count("#") for row in template))


@calibrated
def tag(shot):
    """(text, box) of the one tag in the list: "Equip" or "Unequip" when
    its text matches that template (TAG_TEMPLATES); (None, box) when it
    matches none, (None, None) without exactly one tag."""
    found = tags(shot)
    if len(found) != 1:
        return None, None
    box = found[0]
    ink = _tag_ink(shot, box)
    if not ink:
        return None, box
    for text, template in (*TAG_TEMPLATES.items(), *TAG_NATIVE_TEMPLATES.items()):
        if _tag_distance(ink, template) <= TAG_MOST:
            return text, box
    return None, box


@calibrated
def tab(shot):
    """The Equipment panel's active tab ("weapon", "accessories", "relic",
    "spirit"): its text at least 1.4 times brighter than every other's."""
    width, height, _ = shot
    bright = {}
    for name, (a, b) in TABS.items():
        left, top, right, bottom = _box(shot, (a, TAB_Y[0], b, TAB_Y[1]))
        bright[name] = max((max(_pixel(shot, x, y)) for x in range(left, right) for y in range(top, bottom)),
                           default=0)
    best = max(bright, key=bright.get)
    others = [v for k, v in bright.items() if k != best]
    if bright[best] < 100 or any(bright[best] < 1.4 * v for v in others):
        return None
    return best


# An ordinary weapon's card (Enhance / Combine, its buttons Enhance MAX and
# Equip at the bottom): seen when the Soul Weapon icon's tap landed on the
# weapon list. Not captured: read by its left button's text.
DETAIL_BUTTON_AREA = (0.1, 0.8, 0.49, 0.87)


@calibrated
def weapon_detail(shot):
    """An ordinary weapon's card is open: its left button reads "Enhance
    MAX"."""
    for text, _, _ in font.read(shot, DETAIL_BUTTON_AREA, font=CARD_FONT):
        if font.close(text, ["EnhanceMAX", "Harvest", "Craft", "Breakdown"], most=0.3, margin=2) == "EnhanceMAX":
            return True
    return False


@calibrated
def equipped_badge(shot):
    """The card's sword badge is red (True), grey (False); None: neither."""
    left, top, right, bottom = _box(shot, BADGE_AREA)
    pixels = [_pixel(shot, x, y) for x in range(left, right) for y in range(top, bottom)]
    if not pixels:
        return None
    red = sum(1 for p in pixels if _red(p)) / len(pixels)
    grey = sum(1 for p in pixels if max(p) - min(p) < 16 and 40 <= max(p) <= 120) / len(pixels)
    if red >= 0.4:
        return True
    if grey >= 0.4:
        return False
    return None


def view(shot, names):
    """What the Soul Weapon screen shows, for soul_weapon_rules.plan:
    {open, selected, owned, tag, tag_box, tags, rows, badge}."""
    text, box = tag(shot)
    return {"open": title(shot), "selected": name(shot, names), "owned": owned(shot), "tag": text,
            "tag_box": box, "tags": tags(shot), "rows": rows(shot),
            "badge": equipped_badge(shot) if BADGE_TELLS else None}
