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
  and tag(): the text of the one tag, "Equip" or "Unequip", read strictly
  (one tag, one line, the closest of the two by at least 2 edits), else
  None. Not calibrated on a capture yet (the tag was seen, not captured):
  until then it reads nothing it is not sure of.
- tab(): the Equipment panel's active tab, "weapon" or "accessories" (the
  Accessories tab has its own top-right icon, Black Orb), by which tab's
  text is clearly the brightest; None otherwise.
- equipped_badge(): the card's sword badge (top right) is red. Seen red
  on the equipped weapon and grey on one not owned; whether an owned
  weapon not equipped shows it grey is not known yet: see BADGE_TELLS.

The engraving screen (from the card's big icon): engraving_title() reads
"Soul Weapon Engraving" and the weapon's name above it; engraving_cells()
which cells of the 5x5 grid hold a piece. Neither is calibrated on a
capture (ENGRAVING_CALIBRATED).
"""

import importlib.util
import os

# The pixel font, loaded beside this file (the gateway loads plugin files
# by path, not as a package).
_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_soul_weapon_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

TITLE_AREA = (0.0, 0.515, 0.35, 0.55)
TITLE = "Soul Weapon"
NAME_AREA = (0.42, 0.59, 0.84, 0.625)
OWNED_AREA = (0.78, 0.558, 0.96, 0.58)
OWNED_LEVEL = 120
LIST_X = (0.025, 0.15)
LIST_Y = (0.55, 0.93)
# Where a cell is tapped to select it: in its upper part, above where its
# Equip / Unequip tag shows (the tag sits in the cell's lower half).
SELECT_X = 0.087
SELECT_DEPTH = 0.3
TAB_Y = (0.402, 0.423)
TABS = {"weapon": (0.03, 0.2), "accessories": (0.22, 0.4), "relic": (0.42, 0.58), "spirit": (0.6, 0.77)}
BADGE_AREA = (0.855, 0.59, 0.915, 0.62)
# The red badge is taken for "equipped" only once a capture of an owned,
# unequipped weapon shows it grey.
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


def title(shot):
    """The popup's title reads "Soul Weapon"."""
    return any(font.distance(text, TITLE) <= 1 for text, _, _ in
               font.read(shot, TITLE_AREA, font=TITLE_FONT, caps=(0.012, 0.02)))


def names_of(table):
    """The weapons' names, each once (two weapons share "Silence")."""
    return sorted({entry["name"] for entry in table["weapons"]})


def read_name(shot):
    """The card's name as read, "?" for an unread glyph; None without one."""
    lines = font.read(shot, NAME_AREA, font=CARD_FONT, caps=(0.009, 0.016))
    return max(lines, key=lambda line: len(line[0]))[0] if lines else None


def name(shot, names):
    """The selected weapon's name (one of names), None when it does not
    read clearly as one."""
    return font.close(read_name(shot), names, most=NAME_MOST, margin=NAME_MARGIN)


def _owned_ink(shot):
    rows = font.crop(shot, OWNED_AREA, min)
    return font.ink(rows, OWNED_LEVEL)


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


def rows(shot):
    """The list's whole cells, top to bottom: [{top, bottom, selected}]
    (fractions of the screen height)."""
    width, height, _ = shot
    left, top, right, bottom = _box(shot, (0.0, LIST_Y[0], 0.2, LIST_Y[1]))
    x0, x1 = int(0.02 * width), int(0.04 * width)
    inside = []
    for y in range(top, bottom):
        inside.append(any(_frame(_pixel(shot, x, y)) or _red(_pixel(shot, x, y)) for x in range(x0, x1)))
    cells, start = [], None
    for i, on in enumerate(inside + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            first, last = top + start, top + i - 1
            # Whole cells only: not touching the list's edges, 0.045 to
            # 0.07 of the screen high.
            if start > 0 and i < len(inside) and 0.045 <= (last - first + 1) / height <= 0.07:
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


def tags(shot):
    """The orange boxes in the list column, [left, top, right, bottom]
    (fractions), at least 0.04 wide and 0.008 high."""
    width, height, _ = shot
    left, top, right, bottom = _box(shot, (0.0, LIST_Y[0], 0.2, LIST_Y[1]))
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


def tag(shot):
    """(text, box) of the one tag in the list: text "Equip" or "Unequip",
    read strictly; (None, box) when it does not read clearly, (None,
    None) without exactly one tag."""
    found = tags(shot)
    if len(found) != 1:
        return None, None
    box = found[0]
    lines = font.read(shot, box, channel=min, font=CARD_FONT)
    if len(lines) != 1:
        return None, box
    text = lines[0][0]
    if "?" in text or " " in text:
        return None, box
    return font.close(text, ["Equip", "Unequip"], most=0.2, margin=2), box


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


def weapon_detail(shot):
    """An ordinary weapon's card is open: its left button reads "Enhance
    MAX"."""
    for text, _, _ in font.read(shot, DETAIL_BUTTON_AREA, font=CARD_FONT):
        if font.close(text, ["EnhanceMAX", "Harvest", "Craft", "Breakdown"], most=0.3, margin=2) == "EnhanceMAX":
            return True
    return False


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


# -- The engraving screen (not calibrated on a capture yet).
ENGRAVING_CALIBRATED = False
ENGRAVING_TITLE_AREA = (0.1, 0.1, 0.9, 0.2)
ENGRAVING_TITLE = "Soul Weapon Engraving"
# The 5x5 grid (x 0.22-0.78, y 0.24-0.50, the catalogue's); a 4x4 one is
# centred in it.
GRID_AREA = (0.22, 0.24, 0.78, 0.50)


def engraving_title(shot, names):
    """(title read as "Soul Weapon Engraving", the weapon's name above it
    or None)."""
    lines = font.read(shot, ENGRAVING_TITLE_AREA, font=CARD_FONT)
    is_title = any(font.distance(text, ENGRAVING_TITLE) <= 3 for text, _, _ in lines)
    named = [font.close(text, names, most=NAME_MOST, margin=NAME_MARGIN) for text, _, _ in lines]
    named = [n for n in named if n]
    return is_title, named[0] if len(named) == 1 else None


def engraving_cells(shot, size):
    """The cells of the size x size grid that hold a piece, as a set of
    (row, col), row 0 at the top; None until ENGRAVING_CALIBRATED. A piece
    is coloured (green, blue, red), an empty cell dark or outlined."""
    if not ENGRAVING_CALIBRATED or size not in (4, 5):
        return None
    left, top, right, bottom = _box(shot, GRID_AREA)
    cell_w, cell_h = (right - left) / 5, (bottom - top) / 5
    offset = (5 - size) / 2
    filled = set()
    for row in range(size):
        for col in range(size):
            cx = int(left + (col + offset + 0.5) * cell_w)
            cy = int(top + (row + offset + 0.5) * cell_h)
            samples = [_pixel(shot, cx + dx, cy + dy) for dx in (-3, 0, 3) for dy in (-3, 0, 3)]
            if sum(1 for r, g, b in samples if max(r, g, b) - min(r, g, b) > 60 and max(r, g, b) > 100) >= 6:
                filled.add((row, col))
    return filled
