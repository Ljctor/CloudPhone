"""Reads the battle screen's preset and AUTO controls and the Battle
settings panel, off screenshots (width, height, RGB bytes). Pure.

On the battle screen's right edge a small arrow unfolds, for about 2 s, a
badge with the current Battle settings preset as a Roman numeral (white
on a light tile) and the AUTO tile: a gear over the label "AUTO". AUTO is
on while the gear spins: told from two screenshots a moment apart, where
the gear's pixels change while its tile does not (and the fight does, so
that the two are fresh frames). The skill icons are a hint: AUTO on, most
show a grey cooldown.

Battle settings: the title "Battle settings", the presets I to V in a
row, the chosen one in a white frame. Areas are (left, top, right, bottom)
fractions of the screen, measured at 480x1040 with no panel open.
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_battle_controls_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

NUMERALS = ("I", "II", "III", "IV", "V")
# The folded controls' arrow, and once unfolded the badge and the gear.
ARROW_TAP = (0.975, 0.444)
BADGE_TAP = (0.965, 0.405)
AUTO_TAP = (0.93, 0.447)
# Only the numeral's rows: what drops in the fight passes under the badge.
BADGE = (0.94, 0.399, 0.99, 0.4095)
GEAR = (0.906, 0.430, 0.963, 0.454)
AUTO_LABEL = (0.88, 0.453, 0.99, 0.466)
TILE_TOP = (0.88, 0.424, 0.995, 0.430)
FIGHT = (0.10, 0.30, 0.80, 0.47)
SKILLS = [(x, y, x + 0.145, y + 0.067) for y in (0.570, 0.655) for x in (0.08, 0.25, 0.425, 0.60, 0.775)]
WHITE = 200
# Mean change of a grey level (0-255) between the two screenshots.
SPINNING = 10
STILL = 4
FRESH = 4
# A skill icon greyed by its cooldown: hardly any colour.
GREY_ICON = 12
GREY_ICONS = 2

SETTINGS_TITLE = (0.02, 0.222, 0.42, 0.258)
SETTINGS_TITLE_CAP = (0.013, 0.022)
SETTINGS_TEXT = "Battle settings"
PRESET_X = (0.17, 0.32, 0.50, 0.66, 0.83)
PRESET_Y = 0.305
PRESET_HALF = (0.065, 0.032)
PRESET_NUMERAL = (0.04, 0.016)
FRAME = 0.06


def _greys(shot, area):
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    return [max(pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]) for y in range(top, bottom)
            for x in range(left, right)]


def _change(a, b, area):
    one, two = _greys(a, area), _greys(b, area)
    if len(one) != len(two) or not one:
        return None
    return sum(abs(x - y) for x, y in zip(one, two)) / len(one)


def _white_share(shot, area):
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    hits = total = 0
    for y in range(top, bottom):
        for x in range(left, right):
            i = (y * width + x) * 3
            total += 1
            hits += min(pixels[i], pixels[i + 1], pixels[i + 2]) > 235
    return hits / total if total else 0.0


def badge(shot):
    """The preset the unfolded badge shows ("III"), or None (folded, or
    unreadable)."""
    number = font.numeral(font.ink(font.crop(shot, BADGE, min), WHITE))
    return NUMERALS[number - 1] if number else None


def auto_label(shot):
    """Whether the AUTO tile is shown (its label reads AUTO)."""
    return any(font.close(text, ["AUTO"], most=0.5) for text, _, _ in
               font.read(shot, AUTO_LABEL, level=WHITE, channel=min))


def folded(shot):
    """The controls are folded: no badge, no AUTO tile. Then the arrow's
    spot is not the gear."""
    return badge(shot) is None and not auto_label(shot)


def grey_icons(shot):
    """How many skill icons are greyed (cooling down)."""
    width, height, pixels = shot
    count = 0
    for area in SKILLS:
        left, top, right, bottom = (int(area[0] * width), int(area[1] * height),
                                    int(area[2] * width), int(area[3] * height))
        colour = [max(pixels[i:i + 3]) - min(pixels[i:i + 3]) for y in range(top, bottom, 2)
                  for x in range(left, right, 2) for i in [(y * width + x) * 3]]
        count += bool(colour) and sum(colour) / len(colour) < GREY_ICON
    return count


def auto(first, second):
    """"on" (the gear spins), "off" (it stands still while the fight
    moves and no skill cools down), or None (cannot tell: the controls are
    not unfolded on both, the frames are not fresh, something crosses the
    tile, or the hints disagree). first and second: screenshots a moment
    apart, the controls unfolded."""
    if not (auto_label(first) and auto_label(second)):
        return None
    if (_change(first, second, FIGHT) or 0) < FRESH:
        return None  # the same frame twice: nothing can be told
    tile = max(_change(first, second, TILE_TOP) or 0, _change(first, second, AUTO_LABEL) or 0)
    if tile > STILL:
        return None
    gear = _change(first, second, GEAR) or 0
    if gear >= SPINNING:
        return "on"
    if gear <= STILL and grey_icons(second) < GREY_ICONS:
        return "off"
    return None


def settings_open(shot):
    """Whether the Battle settings panel is open (its title reads so)."""
    return any(font.close(text, [SETTINGS_TEXT]) for text, _, _ in
               font.read(shot, SETTINGS_TITLE, caps=SETTINGS_TITLE_CAP))


def preset_tap(name):
    return (PRESET_X[NUMERALS.index(name)], PRESET_Y)


def selected(shot):
    """The preset Battle settings shows as chosen: the one button in a
    white frame, whose numeral reads as its own. None otherwise."""
    framed = []
    for i, x in enumerate(PRESET_X):
        box = (x - PRESET_HALF[0], PRESET_Y - PRESET_HALF[1], x + PRESET_HALF[0], PRESET_Y + PRESET_HALF[1])
        framed.append(_white_share(shot, box))
    best = max(range(len(framed)), key=lambda i: framed[i])
    if framed[best] < FRAME or sorted(framed)[-2] > framed[best] / 3:
        return None
    x = PRESET_X[best]
    inside = (x - PRESET_NUMERAL[0], PRESET_Y - PRESET_NUMERAL[1], x + PRESET_NUMERAL[0], PRESET_Y + PRESET_NUMERAL[1])
    number = font.numeral(font.ink(font.crop(shot, inside, min), WHITE))
    return NUMERALS[best] if number == best + 1 else None
