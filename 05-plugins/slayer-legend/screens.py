"""The game's main screens off a screenshot, and where the plugin's own
moves on them are.

look(shot) is the screen model: one pass per capture, its answer shared
by every feature, {screen, overlays, margin}: the one base screen of
screen_registry.json whose anchors hold, with a margin, else "unknown";
the overlays over it (the Soul Weapon screen over the battle is the
battle with the "soul_weapon" overlay: soul_weapon_over_battle()). See
the model's section at the end.

classify(shot) is the name the features know, from look(): title, save
(the "last save time" notice), sign_in (the game asks to sign in again:
"Sign in with Google" / "Sign in with Apple", seen after a relaunch),
battle, menu (one of the battle screen's panels over it), saver (Power
Saving Mode) or other. Areas are (left, top, right, bottom) fractions of
the screen, measured on a 360x780 screen (the page's device shapes keep
this ratio). A screenshot is (width, height, RGB888 bytes).

Another screen ("other") is named by its text: other_name(shot) reads
its title and buttons with the pixel font, as read, in English (the
game's), e.g. '"Connected on another device" [OK]'. A screen the
catalogue (other_screens.json) holds is named by its entry; one enters
the catalogue only once seen for real, its fixture a crop of its title
and buttons (nothing identifying). Nothing on another screen is ever
tapped: navigation.json refuses it by default. The "connected on another
device" screen and the choice between two saves have no catalogue entry
yet. Android's crash dialog is not the game's: ports.crashed() reads it
from dumpsys.
"""

import importlib.util
import json
import os

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_screens_font", os.path.join(os.path.dirname(__file__), "pixel_font.py"))
font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(font)

START_TEXT = (0.30, 0.80, 0.70, 0.87)   # "TAP TO START", white on dark
START_TAP = (0.50, 0.836)
CONFIRM_BUTTON = (0.26, 0.735, 0.37, 0.755)  # orange
EXIT_BUTTON = (0.62, 0.735, 0.73, 0.755)     # grey
CONFIRM_TAP = (0.314, 0.745)
SAVER_TAP = (0.50, 0.88)
# The game leaves Power Saving Mode only after a press held a few seconds.
SAVER_HOLD_MS = 4000
MENU_LABELS = (0.0, 0.975, 1.0, 0.995)
# The emerald in the top bar: the game's own screens (battle and its menus).
TOP_EMERALD = (0.377, 0.018, 0.402, 0.030)
# Power Saving Mode: black screen, orange "In battle . . .", grey button.
SAVER_BUTTON = (0.33, 0.83, 0.67, 0.92)
SAVER_TEXT = (0.40, 0.465, 0.60, 0.48)
SAVER_TOP = (0.10, 0.10, 0.90, 0.25)  # bottom menu names, white on dark
# The sign-in screen (measured on a real 480x1040 capture): two light grey
# buttons, "Sign in with Google" (the coloured G, grey text) above "Sign
# in with Apple" (a black apple, black text), the game's background
# between them.
SIGN_IN_GOOGLE = (0.255, 0.726, 0.745, 0.766)
SIGN_IN_APPLE = (0.255, 0.792, 0.745, 0.832)
SIGN_IN_GAP = (0.255, 0.774, 0.745, 0.785)
SIGN_IN_G = (0.275, 0.735, 0.335, 0.758)
SIGN_IN_GOOGLE_TEXT = (0.36, 0.735, 0.68, 0.758)
SIGN_IN_APPLE_LOGO = (0.275, 0.803, 0.325, 0.823)
SIGN_IN_GOOGLE_TAP = (0.50, 0.746)


def share(shot, area, test, step=2):
    """Fraction of the pixels in area (fractions of the screen) passing
    test(r, g, b), every step-th pixel of every step-th row."""
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    hits = total = 0
    for y in range(top, bottom, step):
        row = pixels[(y * width + left) * 3:(y * width + right) * 3]
        found = [test(r, g, b) for r, g, b in zip(row[0::3 * step], row[1::3 * step], row[2::3 * step])]
        total += len(found)
        hits += sum(1 for hit in found if hit)
    return hits / total if total else 0.0


def white(r, g, b):
    return r > 200 and g > 200 and b > 200


def orange(r, g, b):
    return r > 190 and 90 < g < 200 and b < 80


def grey(r, g, b):
    return max(r, g, b) - min(r, g, b) < 25 and 50 < r < 170


def dim_grey(r, g, b):
    return max(r, g, b) - min(r, g, b) < 20 and 35 < r < 110


def black(r, g, b):
    return r < 20 and g < 20 and b < 20


def light(r, g, b):
    # The bottom menu's names: light grey, darker under a panel.
    return min(r, g, b) > 150


def green(r, g, b):
    # Relative, so that it also holds when a panel darkens the screen.
    return g >= 64 and g > 1.3 * r and g > 2 * b


def dark(r, g, b):
    return max(r, g, b) < 45


def coloured(r, g, b):
    return max(r, g, b) - min(r, g, b) > 80


def sign_in(shot):
    """Both sign-in buttons where they were measured, Google's above
    Apple's (told apart by their logos and text colours)."""
    return (share(shot, SIGN_IN_GOOGLE, light) > 0.6 and share(shot, SIGN_IN_APPLE, light) > 0.6
            and share(shot, SIGN_IN_GAP, light) < 0.1
            and share(shot, SIGN_IN_G, coloured) > 0.1 and share(shot, SIGN_IN_G, dark) < 0.02
            and share(shot, SIGN_IN_GOOGLE_TEXT, grey) > 0.05 and share(shot, SIGN_IN_GOOGLE_TEXT, dark) < 0.02
            and share(shot, SIGN_IN_APPLE_LOGO, dark) > 0.2)


def classify(shot):
    """The screen's name as the features know it: look()'s screen, "menu"
    for the battle screen under a panel, "other" for any screen without
    a name of its own here (unknown, or the engraving screen)."""
    seen = look(shot)
    name = REGISTRY[seen["screen"]].get("legacy", "other") if seen["screen"] in REGISTRY else "other"
    if name == "battle" and "panel" in seen["overlays"]:
        return "menu"
    return name


# The bottom menu's tabs, and with a panel open the one it is: its label
# is lit, orange (seen on Adventure; assumed alike for the others) or
# white, when the others stay grey (138 at 480x1040) or go dark.
TABS = ((0.073, "character_enhance"), (0.24, "skill"), (0.41, "equipment_weapon"), (0.585, "companion"),
        (0.755, "adventure_map"), (0.925, "shop_summon"))
TAB_HALF = 0.06
TAB_TAP_Y = 0.966


def lit(r, g, b):
    return (r > 180 and g > 90 and b < 110 and r - b > 90) or min(r, g, b) > 200


def open_tab(shot):
    """(x, the navigation screen whose close move it is) of the bottom tab
    whose panel is open: the one tab whose label is lit; None when no tab
    or more than one is."""
    shares = [share(shot, (x - TAB_HALF, MENU_LABELS[1], x + TAB_HALF, MENU_LABELS[3]), lit) for x, _ in TABS]
    best = max(range(len(TABS)), key=lambda i: shares[i])
    if shares[best] < 0.05 or sorted(shares)[-2] > shares[best] / 3:
        return None
    return TABS[best]


# The game's « Better Soul Weapon / Equip » toast at the right of the
# battle (real captures, 2026-10-21): the weapon's icon on dark, then two
# white lines. A known overlay: never tapped (navigation.json
# forbids its area on the battle screen and the panels), and it covers none
# of the areas the screens are told by.
TOAST_AREA = (0.70, 0.315, 1.0, 0.375)
TOAST_ICON = (0.725, 0.33, 0.785, 0.36)
TOAST_TEXT = (0.81, 0.33, 0.99, 0.34)


def better_weapon_toast(shot):
    """The « Better Soul Weapon / Equip » toast shows (nothing to do: never tapped)."""
    return "better_weapon_toast" in look(shot)["overlays"]


# The battle screen with no panel or pop-up over it shows the skill bar:
# its blue mana bar (the start of it, filled unless the mana is spent).
MANA_BAR = (0.12, 0.546, 0.30, 0.551)
# The engraving screen's piece preview: its red cancel in this area
# (engraving_screen.BAR_AREA; its bar() then finds where).
PREVIEW_AREA = (60 / 480, 200 / 1040, 420 / 480, 600 / 1040)


def red(r, g, b):
    return r > 200 and g < 60 and b < 60


def blue(r, g, b):
    return b > 200 and g > 100 and r < 120


# The Soul Weapon screen (the farming modes' parking) shades the battle
# above it: its whites read 159 (real captures at 480x1040, 2026-10-22).
PARKED_SHADE = 159 / 255


def plain_battle(shot):
    """The battle screen with nothing over it (its skill bar shows)."""
    return look(shot)["plain"]


# Another screen's text: the lines read in the middle of the screen, of a
# title's or a button's size (cap height as a fraction of the screen
# height), at most OTHER_LINES, each with at least OTHER_LETTERS letters
# read and at most a third of its glyphs unread (not a picture's edges).
OTHER_AREA = (0.04, 0.04, 0.96, 0.96)
OTHER_CAPS = (0.007, 0.03)
OTHER_LINES = 6
OTHER_LETTERS = 2
# A line this many words or fewer after the title is a button.
BUTTON_WORDS = 3


def _catalogue():
    with open(os.path.join(os.path.dirname(__file__), "other_screens.json"), encoding="utf-8") as f:
        return json.load(f)["screens"]


CATALOGUE = _catalogue()


# Words further apart than this many cap heights are two phrases (two
# buttons side by side).
PHRASE_GAP = 1.5


def _inverted(r, g, b):
    return 255 - min(r, g, b)


def other_lines(shot):
    """The text read on another screen, top to bottom: each line as its
    phrases (two buttons on one row are two phrases). Light text on dark
    and dark text on light (a grey button) alike."""
    found = sorted(_lines(shot, max) + _lines(shot, _inverted))
    return [phrases for _, phrases in found][:OTHER_LINES]


def _lines(shot, channel):
    """[(top, phrases)] of the lines read with channel (see other_lines)."""
    marks = font.ink(font.crop(shot, OTHER_AREA, channel))
    if not marks:
        return []
    height, found = shot[1], []
    for top, bottom in font.lines(marks):
        runs, cap = font.metrics(marks, top, bottom)
        if len(runs) > 40 or not OTHER_CAPS[0] <= cap / height <= OTHER_CAPS[1]:
            continue
        phrases, last = [], None
        for word in font.read_line(marks, top, bottom):
            text = font.text([word])
            if last is not None and word[0][2][0] - last > PHRASE_GAP * cap:
                phrases.append(text)
            elif phrases:
                phrases[-1] += " " + text
            else:
                phrases.append(text)
            last = word[-1][2][1]
        whole = "".join(phrases).replace(" ", "")
        letters = sum(c.isalnum() for c in whole)
        if letters >= OTHER_LETTERS and whole.count("?") * 3 <= len(whole):
            found.append((top, phrases))
    return found


def describe(lines):
    """'"title" [button] [button]': the first line is the title, the short
    phrases after it buttons, the longer ones more of the title's text."""
    if not lines:
        return "no text read"
    title, buttons = [" ".join(lines[0])], []
    for line in lines[1:]:
        for phrase in line:
            (buttons if len(phrase.split()) <= BUTTON_WORDS else title).append(phrase)
    return " ".join([f'"{" ".join(title)}"'] + [f"[{b}]" for b in buttons])


def other_name(shot, catalogue=None):
    """Another screen's name: its catalogue entry's when its title reads as
    one (close, with a margin), else its text as read (describe). A screen
    look() knows is named by known_name instead."""
    lines = other_lines(shot)
    entries = CATALOGUE if catalogue is None else catalogue
    titles = [entry["title"] for entry in entries]
    for line in lines[:2]:
        title = font.close(" ".join(line), titles, most=0.3, margin=2) if titles else None
        if title:
            return next(entry["name"] for entry in entries if entry["title"] == title)
    return describe(lines)


# -- The screen model: one look per capture --------------------------------
#
# screen_registry.json holds every screen recognised, by navigation.json
# id, with its anchors and fixtures (see its "about"). look(shot) runs once
# per capture, its answer kept for the last few captures and shared by
# every feature: {screen, overlays, margin, plain, margins}. screen is the
# one base screen whose anchors all hold, "unknown" when none does or
# when its margin over the next one is under MARGIN; overlays the
# overlays over it whose anchors hold. Every navigation.json screen the
# registry does not hold is pending capture (pending()): never matched.
WIDTH, HEIGHT = 480, 1040
MARGIN = 0.05
# A patch is compared on about this many points (a downscaled signature).
SAMPLES = 256
CACHE = 4
# The Soul Weapon screen over the battle: the battle screen as the base,
# this overlay over it (and the Equipment tabs, equipment_weapon, under it).
SOUL_WEAPON = "soul_weapon"
HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


def fixture(name):
    """(screen width, height, left, top, width, height, rgb bytes) of fixtures/<name>.txt."""
    with open(os.path.join(HERE, "fixtures", f"{name}.txt"), encoding="ascii") as f:
        lines = [line.strip() for line in f if not line.startswith("#")]
    sw, sh, x, y, w, h = map(int, lines[0].split())
    return sw, sh, x, y, w, h, b"".join(bytes.fromhex(row) for row in lines[1:1 + h])


_REGISTRY = _load("screen_registry.json")
REGISTRY = _REGISTRY["screens"]
OUTSIDE = _REGISTRY["outside"]
NAMES = {key: node["name"] for key, node in _load("navigation.json")["screens"].items()}
# Every screen of the game known so far, recognised or not (see the registry's about).
TREE = _REGISTRY["tree"]
BASES = [key for key, entry in REGISTRY.items() if entry["kind"] == "screen"]
OVERLAYS = [key for key, entry in REGISTRY.items() if entry["kind"] == "overlay"]
TIERS = {"registered": 0, "measured": 1}


def pending():
    """The screens of navigation.json and of the tree with no anchors yet:
    pending capture."""
    keys = list(NAMES) + [key for key in TREE if key not in NAMES]
    return [key for key in keys if key not in REGISTRY and key not in OUTSIDE]


def _even(values):
    """values with their mean taken off and divided by their mean spread."""
    mean = sum(values) / len(values)
    spread = sum(abs(v - mean) for v in values) / len(values)
    return mean, spread


class Patch:
    """A fixture's area as a downscaled grey signature, its brightness and
    contrast evened out (a panel dimming the screen changes neither). Each
    point of the signature is a cell's grey: the sum of two runs of step
    pixels, step / 2 rows apart (one C-speed sum per run), so that thin
    strokes still count at another screen size."""

    def __init__(self, name, box=None, limit=0.6):
        _, _, x, y, w, h, data = fixture(name)
        bx, by, bw, bh = box or (0, 0, w, h)
        self.step = step = max(2, round((bw * bh / SAMPLES) ** 0.5))
        self.cells = [(x + px, y + py) for py in range(by, by + bh - step + 1, step)
                      for px in range(bx, bx + bw - step + 1, step)]
        grey = [self._grey(data, w, [((py - y) * w + (px - x)) * 3, ((py - y + step // 2) * w + (px - x)) * 3],
                           step * 3) for px, py in self.cells]
        mean, self.spread = _even(grey)
        self.signature = [(g - mean) / max(self.spread, 1) for g in grey]
        self.limit = limit
        self.offsets = {}

    @staticmethod
    def _grey(pixels, width, starts, run):
        return sum(sum(pixels[i:i + run]) for i in starts) / run

    def distance(self, shot):
        width, height, pixels = shot
        cached = self.offsets.get((width, height))
        if cached is None:
            sx, sy = width / WIDTH, height / HEIGHT
            run = max(1, round(self.step * sx)) * 3
            cached = self.offsets[(width, height)] = (run, [
                ((int(py * sy) * width + int(px * sx)) * 3, (int((py + self.step // 2) * sy) * width + int(px * sx)) * 3)
                for px, py in self.cells])
        run, offsets = cached
        grey = [(sum(pixels[i:i + run]) + sum(pixels[j:j + run])) / run for i, j in offsets]
        mean, spread = _even(grey)
        spread = max(spread, self.spread / 4, 1)
        return sum(abs((g - mean) / spread - s) for g, s in zip(grey, self.signature)) / len(grey)

    def margin(self, shot):
        return max(-1.0, 1 - self.distance(shot) / self.limit)


def _share_margin(value, level, above):
    """1 when the share is as far past its level as the level is from 0 or
    1 (the nearer), -1 as far short of it."""
    gap = (value - level) if above else (level - value)
    return max(-1.0, min(1.0, gap / max(min(level, 1 - level), 1e-6)))


_engraving = None
# The shares measured on the capture being looked at (two anchors may read one).
_shares = {}


def _reader(name):
    """A reader by name: one of this module's, or engraving_screen's."""
    global _engraving
    if not name.startswith("engraving_screen."):
        return globals()[name]
    if _engraving is None:
        spec = importlib.util.spec_from_file_location(
            "cloudphone_plugin_slayer_legend_screens_engraving", os.path.join(HERE, "engraving_screen.py"))
        _engraving = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_engraving)
    return getattr(_engraving, name.split(".", 1)[1])


def _anchor(spec):
    """A function shot -> margin for one registry anchor."""
    if "patch" in spec:
        return Patch(spec["patch"], spec.get("box"), spec.get("limit", 0.6)).margin
    if "share" in spec:
        area, test, step = globals()[spec["share"]], globals()[spec["test"]], spec.get("step", 2)
        above = "above" in spec
        level = spec["above"] if above else spec["below"]
        key = (spec["share"], spec["test"], step)

        def margin_of(shot):
            if key not in _shares:
                _shares[key] = share(shot, area, test, step)
            return _share_margin(_shares[key], level, above)
        return margin_of
    reader = spec["reader"]
    return lambda shot: 1.0 if _reader(reader)(shot) else -1.0


ANCHORS = {key: [_anchor(spec) for spec in entry["anchors"]] for key, entry in REGISTRY.items()}
SIGNATURES = {key: [Patch(spec["patch"], spec.get("box")).signature for spec in entry["anchors"] if "patch" in spec]
              for key, entry in REGISTRY.items()}


def margin(shot, key):
    """key's margin on shot: its anchors' lowest, or the first one under 0
    (the others are then not looked at)."""
    low = 1.0
    for anchor in ANCHORS[key]:
        low = min(low, anchor(shot))
        if low <= 0:
            break
    return low


_seen = []


def look(shot):
    """{screen, overlays, margin, plain, margins} of one capture (see above)."""
    width, height, pixels = shot
    for kept, answer in _seen:
        if kept is pixels and answer["size"] == (width, height):
            return answer
    _shares.clear()
    margins = {key: margin(shot, key) for key in BASES}
    found = sorted((TIERS[REGISTRY[key]["status"]], -value, key) for key, value in margins.items() if value > 0)
    if found:
        tier, best, screen = found[0]
        rivals = [-value for t, value, _ in found[1:] if t == tier]
        sure = min(-best, -best - max(rivals)) if rivals else -best
    else:
        screen, sure = "unknown", max(margins.values())
    if sure < MARGIN:
        screen = "unknown"
    overlays = []
    for key in OVERLAYS:
        if screen in REGISTRY[key]["over"]:
            margins[key] = margin(shot, key)
            if margins[key] > 0:
                overlays.append(key)
    plain = screen == "battle" and share(shot, MANA_BAR, blue) > 0.5
    answer = {"screen": screen, "overlays": overlays, "margin": round(sure, 3), "plain": plain,
              "margins": {key: round(value, 3) for key, value in margins.items()}, "size": (width, height)}
    _seen.insert(0, (pixels, answer))
    del _seen[CACHE:]
    return answer


def known_name(shot):
    """The navigation.json name of the screen look() recognises, e.g.
    "Soul Weapon Engraving"; None when it is unknown."""
    screen = look(shot)["screen"]
    return None if screen == "unknown" else NAMES.get(screen)


def soul_weapon_over_battle(shot):
    """The Soul Weapon screen is open over the battle."""
    seen = look(shot)
    return seen["screen"] == "battle" and SOUL_WEAPON in seen["overlays"]
