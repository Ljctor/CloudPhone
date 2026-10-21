"""The game's main screens off a screenshot, and where the plugin's own
moves on them are.

classify(shot) is one of: title, save (the "last save time" notice),
sign_in (the game asks to sign in again: "Sign in with Google" / "Sign in
with Apple", seen after a relaunch), battle, menu (one of the battle
screen's panels over it), saver (Power Saving Mode) or other. Screens are recognised from a few pixel areas, as
(left, top, right, bottom) fractions of the screen, measured on a 360x780
screen (the page's device shapes keep this ratio). A screenshot is
(width, height, RGB888 bytes).

TODO: the "connected on another device" screen (after free play on
another phone) and the choice between two saves have no known layout yet:
they are "other" (the watchdog alerts on them, for the user). Android's
crash dialog is not the game's: ports.crashed() reads it from dumpsys.
"""

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


def share(shot, area, test):
    """Fraction of the pixels in area (fractions of the screen) passing test(r, g, b)."""
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    hits = total = 0
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            i = (y * width + x) * 3
            total += 1
            hits += bool(test(pixels[i], pixels[i + 1], pixels[i + 2]))
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
    if share(shot, CONFIRM_BUTTON, orange) > 0.6 and share(shot, EXIT_BUTTON, grey) > 0.6:
        return "save"
    if sign_in(shot):
        return "sign_in"
    # The top bar's emerald: the battle screen, or one of its panels over it
    # (the bottom menu names then go dark or are covered).
    if share(shot, TOP_EMERALD, green) > 0.15:
        return "battle" if share(shot, MENU_LABELS, light) > 0.01 else "menu"
    if (share(shot, SAVER_BUTTON, dim_grey) > 0.8 and share(shot, SAVER_TOP, black) > 0.95
            and share(shot, SAVER_TEXT, orange) > 0.08):
        return "saver"
    if 0.02 < share(shot, START_TEXT, white) < 0.4:
        return "title"
    return "other"


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


# The battle screen with no panel or pop-up over it shows the skill bar:
# its blue mana bar (the start of it, filled unless the mana is spent).
MANA_BAR = (0.12, 0.546, 0.30, 0.551)


def blue(r, g, b):
    return b > 200 and g > 100 and r < 120


def plain_battle(shot):
    """The battle screen with nothing over it (its skill bar shows)."""
    return share(shot, TOP_EMERALD, green) > 0.15 and share(shot, MANA_BAR, blue) > 0.5
