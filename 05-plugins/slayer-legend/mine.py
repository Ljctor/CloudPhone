"""What the Closed Mine's screens show, from a screenshot (width, height,
RGB bytes): the fight with its "Repeat entry" box, the floor list, the Area
and feathers pop-ups, and whether the gold scroll buff is on.

Positions are fractions of the screen, measured at 480x1040.
"""

import importlib.util
import os

# The stage reader's glyph matching, loaded beside this file (the gateway
# loads plugin files by path, not as a package).
_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_mine_stage", os.path.join(os.path.dirname(__file__), "stage.py"))
stage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage)

# Fight: "Repeat entry" (white text) and its tick box, top right.
REPEAT_TEXT = (0.79, 0.100, 0.93, 0.112)
REPEAT_BOX = (0.94, 0.104, 0.99, 0.125)
REPEAT_TAP = (0.9625, 0.1135)
# The buff icons under the avatar; the gold scroll has bright gold pixels
# (#ffbb33), which the other buffs (purple scroll, potion) do not.
BUFFS = (0.017, 0.054, 0.29, 0.079)
# Floor list: "Closed Mine" title, then rows of "<n> Floor" in yellow,
# 89 px apart at 480x1040.
LIST_TITLE = (0.38, 0.062, 0.62, 0.080)
FLOOR_LABELS = (0.30, 0.20, 0.70, 0.90)
ROW_HEIGHT = 89 / 1040
# Area pop-up: five grey buttons in a row; feathers pop-up: three orange.
AREA_ROW = (0.13, 0.870, 0.87, 0.890)
AREA_TAPS = [(x / 480, 914 / 1040) for x in (96, 167, 238, 309, 380)]
FEATHER_ROW = (0.10, 0.740, 0.90, 0.790)
FEATHER_TAPS = [(x / 480, 795 / 1040) for x in (98, 240, 370)]


def _share(shot, area, test, step=1):
    width, height, pixels = shot
    x0, y0 = int(area[0] * width), int(area[1] * height)
    x1, y1 = int(area[2] * width), int(area[3] * height)
    hits = total = 0
    for y in range(y0, y1, step):
        for x in range(x0, x1, step):
            i = (y * width + x) * 3
            hits += test(pixels[i], pixels[i + 1], pixels[i + 2])
            total += 1
    return hits / total if total else 0.0


def _white(r, g, b):
    return min(r, g, b) > 200


def _gold(r, g, b):
    return r > 230 and 150 < g < 215 and b < 90


def _yellow(r, g, b):
    return r > 180 and g > 140 and b < 160 and r - b > 70


def _orange(r, g, b):
    return r > 200 and 110 < g < 180 and b < 80


def _grey_button(r, g, b):
    return 20 <= r <= 70 and abs(r - g) < 8 and abs(g - b) < 8


def in_fight(shot):
    """The mine's fight screen: "Repeat entry" is shown."""
    return _share(shot, REPEAT_TEXT, _white) > 0.08


def repeat_ticked(shot):
    return _share(shot, REPEAT_BOX, _white) > 0.05


def gold_scroll(shot):
    """The gold scroll buff's icon is shown (only meaningful in the fight:
    pop-ups and the floor list cover it)."""
    return _share(shot, BUFFS, _gold) > 0.005


def area_popup(shot):
    # Grey buttons with white "Area n" labels (Power Saving Mode's grey
    # button sits at the same height, with grey text).
    return _share(shot, AREA_ROW, _grey_button, 2) > 0.25 and _share(shot, AREA_ROW, _white) > 0.02


def feather_popup(shot):
    return _share(shot, FEATHER_ROW, _orange, 2) > 0.25


def floors(shot):
    """The floor rows on screen as [(y fraction, number)], read from the
    yellow "<n> Floor" labels; rows cut by the list's edge are left out."""
    width, height, pixels = shot
    x0, x1 = int(FLOOR_LABELS[0] * width), int(FLOOR_LABELS[2] * width)

    def yellow_at(x, y):
        i = (y * width + x) * 3
        return _yellow(pixels[i], pixels[i + 1], pixels[i + 2])

    counts = [0] * height
    for y in range(int(FLOOR_LABELS[1] * height), int(FLOOR_LABELS[3] * height)):
        counts[y] = sum(yellow_at(x, y) for x in range(x0, x1))
    found = []
    y = int(FLOOR_LABELS[1] * height)
    while y < int(FLOOR_LABELS[3] * height):
        if counts[y] < 3:
            y += 1
            continue
        top = y
        while y < height and counts[y] >= 1:
            y += 1
        bottom = y - 1
        if bottom - top >= 0.008 * height:
            ink = [[yellow_at(x, row) for x in range(x0, x1)] for row in range(top, bottom + 1)]
            words = stage._words(ink)
            # "<digits> Floor": the first word is the number.
            if len(words) >= 2:
                text, worst = "", 0.0
                for glyph in words[0]:
                    name, distance = stage._best(ink, glyph, stage.DIGITS)
                    text += name
                    worst = max(worst, distance)
                if worst < 0.25 and text.isdigit():
                    found.append(((top + bottom) / 2 / height, int(text)))
        y += 1
    # Keep rows that agree with a neighbour (n-1 above or n+1 below): a
    # label half hidden by the list's edge reads as a wrong number.
    return [(fy, n) for i, (fy, n) in enumerate(found)
            if (i > 0 and found[i - 1][1] == n - 1) or (i + 1 < len(found) and found[i + 1][1] == n + 1)]


def floor_list(shot):
    """The Closed Mine's floor list (with no pop-up over it)."""
    return _share(shot, LIST_TITLE, _white) > 0.1 and len(floors(shot)) >= 2
