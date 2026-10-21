"""Reads the stage map's "Select Region" pop-up and the stage the battle
screen farms, off a screenshot (width, height, RGB bytes), with the
game's pixel font (pixel_font.py). Pure.

The pop-up (battle's stage_select): the title "Select Region", a banner
with the region's name between two arrows, and a scrolling list of the
region's 20 stages, one card each: "STAGE NNN" (too small to read), the
stage's name with its Roman numeral ("Giant's Glass XV"), and an orange
Move button on the right. A row is known by its name: the banner's region
and the numeral give the stage (stages.json: region k holds stages
20k+1 to 20k+20). Its Move button is found from the name, as the orange
block beside it.

The battle screen writes the stage's name, white with a dark outline, at
the top: read the same way. Areas are (left, top, right, bottom)
fractions of the screen, measured at 480x1040.
"""

import importlib.util
import os
import re

# The pixel font, loaded beside this file (the gateway loads plugin files
# by path, not as a package).
_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_stage_select_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

# The battle screen's stage map icon, the banner's arrows.
STAGE_MAP_TAP = (0.30, 0.07)
ARROW_TAPS = {"previous_region": (0.125, 0.345), "next_region": (0.875, 0.345)}
TITLE = (0.25, 0.235, 0.75, 0.28)
TITLE_CAP = (0.015, 0.022)
TITLE_TEXT = "Select Region"
BANNER = (0.25, 0.296, 0.75, 0.325)
BANNER_CAP = (0.009, 0.014)
LIST = (0.10, 0.405, 0.68, 0.815)
# The stage names' cap height (14 px at 1040): smaller lines (drop rates,
# "STAGE NNN") and the frame are not names.
NAME_CAP = (0.0115, 0.0160)
# Where the Move buttons are: x across, and from a name's top how far down.
MOVE_X = (0.70, 0.86)
MOVE_TAP_X = 0.78
MOVE_BELOW = (-0.012, 0.075)
MOVE_HEIGHT = 0.035
BATTLE_NAME = (0.315, 0.066, 0.655, 0.088)
BATTLE_CAP = (0.009, 0.014)
WHITE_TEXT = 200
PER_REGION = 20
# Edits by which the best region name must beat the second best.
REGION_MARGIN = 3


def regions(table):
    """The regions of stages.json, by index: k holds stages 20k+1 to 20k+20;
    its name when they all have it with I to XX after it, else None (the
    first regions, whose stages are named apart)."""
    stages = table["stages"]
    names = []
    for k in range(len(stages) // PER_REGION):
        block = [re.match(r"(.*) ([IVXL]+)$", row[0]) for row in stages[k * PER_REGION:(k + 1) * PER_REGION]]
        base = {m.group(1) for m in block if m}
        ok = (all(block) and len(base) == 1
              and [font.roman(m.group(2)) for m in block] == list(range(1, PER_REGION + 1)))
        names.append(base.pop() if ok else None)
    return names


def region_of(stage):
    return (stage - 1) // PER_REGION


def stage_of(region, numeral):
    return region * PER_REGION + numeral


def which(text, names):
    """The index of the region text reads as, against the closed list of
    regions with a margin of REGION_MARGIN edits over the second best; None
    (unknown: nothing is tapped on it) otherwise."""
    known = [name for name in names if name]
    name = font.close(text, known, margin=REGION_MARGIN)
    return names.index(name) if name else None


def _name(words, names):
    """(region index, numeral) of a stage name's words, or None."""
    if len(words) < 2:
        return None
    numeral = font.roman("".join(char or "?" for char, _, _ in words[-1]))
    region = which(font.text(words[:-1]), names)
    if numeral is None or region is None or not 1 <= numeral <= PER_REGION:
        return None
    return region, numeral


def orange(r, g, b):
    return r > 190 and 90 < g < 200 and b < 90


def _move_button(shot, top):
    """The y (fraction) of the middle of the Move button beside a name
    whose top is at top, or None when it is not all in the list (cut by the
    scroll) or not there."""
    width, height, pixels = shot
    x0, x1 = int(MOVE_X[0] * width), int(MOVE_X[1] * width)
    y0 = max(int(LIST[1] * height), int((top + MOVE_BELOW[0]) * height))
    y1 = min(int(LIST[3] * height), int((top + MOVE_BELOW[1]) * height))
    rows = []
    for y in range(y0, y1):
        hits = sum(1 for x in range(x0, x1, 2) if orange(*pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]))
        rows.append(hits / max(1, len(range(x0, x1, 2))) > 0.6)
    best, start = None, None
    for i, on in enumerate(rows + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    if best is None or (best[1] - best[0]) / height < MOVE_HEIGHT:
        return None
    if best[0] == 0 or best[1] == len(rows):
        return None  # runs past where it may be: cut by the list's edge, or not a button
    return (y0 + (best[0] + best[1]) / 2) / height


def popup(shot):
    """Whether the Select Region pop-up is open (its title reads so)."""
    return any(font.close(text, [TITLE_TEXT]) for text, _, _ in font.read(shot, TITLE, caps=TITLE_CAP))


def banner(shot, names):
    """The region index the banner names, or None."""
    for text, _, _ in font.read(shot, BANNER, caps=BANNER_CAP):
        region = which(text, names)
        if region is not None:
            return region
    return None


def rows(shot, names):
    """The stage rows the list shows, top to bottom: [{region, numeral,
    stage, y: the name's top, move: the Move button's y or None}]; a name
    that does not read is left out."""
    area = font.crop(shot, LIST)
    marks = font.ink(area)
    if not marks:
        return []
    height = shot[1]
    first = int(LIST[1] * height)
    found = []
    for top, bottom in font.lines(marks):
        _, cap = font.metrics(marks, top, bottom)
        if not NAME_CAP[0] <= cap / height <= NAME_CAP[1]:
            continue
        named = _name(font.read_line(marks, top, bottom), names)
        if not named:
            continue
        y = (first + top) / height
        found.append({"region": named[0], "numeral": named[1], "stage": stage_of(*named), "y": y,
                      "move": _move_button(shot, y)})
    return found


def view(shot, names):
    """What the pop-up shows: {popup, region, rows} (see rules.plan)."""
    if not popup(shot):
        return {"popup": False, "region": None, "rows": []}
    return {"popup": True, "region": banner(shot, names), "rows": rows(shot, names)}


def battle_stage(shot, names):
    """The stage the battle screen's top names, or None."""
    for text, _, _ in font.read(shot, BATTLE_NAME, level=WHITE_TEXT, channel=min, caps=BATTLE_CAP):
        words = text.split(" ")
        numeral = font.roman(words[-1]) if len(words) >= 2 else None
        region = which(" ".join(words[:-1]), names) if numeral else None
        if region is not None and 1 <= numeral <= PER_REGION:
            return region * PER_REGION + numeral
    return None
