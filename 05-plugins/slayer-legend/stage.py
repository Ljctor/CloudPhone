"""Reads the farmed stage off a Slayer Legend screenshot.

Power Saving Mode writes it big and sharp in the middle ("STAGE 920" over
"Giant's Glass XX"): the number is read there. The battle screen writes it
small and faint at the top, too small to read the number reliably, but the
Roman numeral after the name is readable: it confirms that the stage has
not changed since the number was read.

The game's fonts are pixel fonts. Each glyph is cut out, resampled to each shape's
grid of ink coverage and compared with the shapes below, drawn in the
game's style, close enough to tell them apart.
"""

# Power Saving Mode's digits, 10 rows high with 2 px strokes: 0, 2 and 9
# as the game draws them, the others drawn in the same style.
DIGITS = {
    "0": [".####..", "#######", "##...##", "##...##", "##...##", "##...##", "##...##", "##...##", "#######", ".####.."],
    "1": [".##.", "###.", ".##.", ".##.", ".##.", ".##.", ".##.", ".##.", "####", "####"],
    "2": [".####.", "######", "#....#", "...###", "...##.", "..###.", ".###..", "###...", "######", "######"],
    "3": [".####..", "#######", "##...##", "....##.", "...###.", ".....##", "##...##", "##...##", "#######", ".####.."],
    "4": ["....##.", "...###.", "..####.", ".##.##.", "##..##.", "#######", "#######", "....##.", "....##.", "....##."],
    "5": ["#######", "#######", "##.....", "######.", "#######", ".....##", "##...##", "##...##", "#######", ".####.."],
    "6": ["...###.", "..####.", "###....", "######.", "#######", "##...##", "##...##", "##...##", "#######", "..####."],
    "7": ["#######", "#######", "##...##", "....##.", "...##..", "..##...", "..##...", "..##...", "..##...", "..##..."],
    "8": [".####..", "#######", "##...##", "##...##", ".#####.", "#######", "##...##", "##...##", "#######", ".####.."],
    "9": [".####..", "#######", "##...##", "##...##", "##...##", "#######", ".######", "....###", ".####..", ".###..."],
}
NUMERALS = {
    "I": ["..#..", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "V": ["#...#", "#...#", "#...#", ".#.#.", ".#.#.", "..#..", "..#.."],
    # The game's X: straight legs, a narrow waist.
    "X": ["##.##", "##.##", ".###.", "..#..", ".###.", "##.##", "##.##"],
}
ROMAN = {"I": 1, "V": 5, "X": 10}

# Text lines, as (left, top, right, bottom) fractions of the screen.
SAVER_NUMBER = (0.20, 0.368, 0.80, 0.392)
SAVER_NAME = (0.10, 0.394, 0.90, 0.422)
BATTLE_NAME = (0.33, 0.068, 0.66, 0.084)


def _crop(shot, area):
    """Grey levels of an area of the screenshot, as rows of ints."""
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = int(area[2] * width), int(area[3] * height)
    rows = []
    for y in range(top, bottom):
        row = []
        for x in range(left, right):
            i = (y * width + x) * 3
            row.append(max(pixels[i], pixels[i + 1], pixels[i + 2]))
        rows.append(row)
    return rows


def _ink(rows):
    """Binary ink: brighter than 60 % of the way from the line's darkest to
    its brightest pixel (the anti-aliased edges stay out, so that letters
    stay apart). None when the line has no contrast (no text)."""
    flat = [v for row in rows for v in row]
    if not flat:
        return None
    low, high = min(flat), max(flat)
    if high - low < 40:
        return None
    level = low + (high - low) * 0.6
    return [[v > level for v in row] for row in rows]


def _words(ink):
    """Glyphs as (left, right, top, bottom), grouped in words by gaps wider
    than a quarter of the text's height."""
    height, width = len(ink), len(ink[0])
    used = [any(ink[y][x] for y in range(height)) for x in range(width)]
    rows = [y for y in range(height) if any(ink[y])]
    if not rows:
        return []
    text_height = rows[-1] - rows[0] + 1
    glyphs = []
    x = 0
    while x < width:
        if not used[x]:
            x += 1
            continue
        right = x
        while right + 1 < width and used[right + 1]:
            right += 1
        ys = [y for y in range(height) if any(ink[y][x:right + 1])]
        # Touching glyphs ("XX"): split a run much wider than a glyph.
        parts = max(1, round((right - x + 1) / (0.7 * text_height)))
        for k in range(parts):
            a = x + (right - x + 1) * k // parts
            b = x + (right - x + 1) * (k + 1) // parts - 1
            glyphs.append((a, b, ys[0], ys[-1]))
        x = right + 1
    words, word = [], []
    for glyph in glyphs:
        if word and glyph[0] - word[-1][1] - 1 > text_height / 4:
            words.append(word)
            word = []
        word.append(glyph)
    if word:
        words.append(word)
    return words


def _grid(ink, glyph, cols, rows):
    """Ink coverage of a glyph on a cols x rows grid."""
    left, right, top, bottom = glyph
    w, h = right - left + 1, bottom - top + 1
    grid = []
    for gy in range(rows):
        y0, y1 = top + gy * h / rows, top + (gy + 1) * h / rows
        row = []
        for gx in range(cols):
            x0, x1 = left + gx * w / cols, left + (gx + 1) * w / cols
            total = covered = 0.0
            for y in range(int(y0), min(bottom + 1, int(y1 + 0.999))):
                fy = min(y + 1, y1) - max(y, y0)
                for x in range(int(x0), min(right + 1, int(x1 + 0.999))):
                    fx = min(x + 1, x1) - max(x, x0)
                    total += fx * fy
                    covered += fx * fy * ink[y][x]
            row.append(covered / total if total else 0.0)
        grid.append(row)
    return grid


def _best(ink, glyph, shapes):
    """The shape closest to the glyph, and how far it is (0 is perfect)."""
    left, right, top, bottom = glyph
    # A glyph much narrower than high is a 1 or an I: one stroke.
    if (right - left + 1) < 0.3 * (bottom - top + 1):
        narrow = [name for name in shapes if name in ("1", "I")]
        if narrow:
            return narrow[0], 0.0
    best, distance = None, None
    for name, shape in shapes.items():
        cols, rows = len(shape[0]), len(shape)
        grid = _grid(ink, glyph, cols, rows)
        d = sum((grid[y][x] - (shape[y][x] == "#")) ** 2 for y in range(rows) for x in range(cols)) / (cols * rows)
        if distance is None or d < distance:
            best, distance = name, d
    return best, distance


def _roman(text):
    total, previous = 0, 0
    for c in reversed(text):
        value = ROMAN[c]
        total = total - value if value < previous else total + value
        previous = max(previous, value)
    return total


def _numeral(shot, area):
    """The Roman numeral ending the stage name in area, or None."""
    ink = _ink(_crop(shot, area))
    words = _words(ink) if ink else []
    if len(words) < 2:
        return None
    text = ""
    for glyph in words[-1]:
        name, distance = _best(ink, glyph, NUMERALS)
        if distance > 0.2:
            return None
        text += name
    return _roman(text) if text else None


def read_saver(shot):
    """(stage number or None, numeral or None) from Power Saving Mode."""
    ink = _ink(_crop(shot, SAVER_NUMBER))
    words = _words(ink) if ink else []
    number = None
    if len(words) >= 2:
        digits = ""
        for glyph in words[-1]:
            name, distance = _best(ink, glyph, DIGITS)
            if distance > 0.12:
                digits = ""
                break
            digits += name
        number = int(digits) if digits else None
    return number, _numeral(shot, SAVER_NAME)


def read_battle(shot):
    """The numeral ending the stage name on the battle screen, or None."""
    return _numeral(shot, BATTLE_NAME)


# The stage progress bar under the stage's name on the battle screen
# (measured on a real series at 480x1040, stage 920, 2026-10-22): its fill
# is one flat orange, PROGRESS_FILL, from the bar's left end rightwards,
# on PROGRESS (left, top, right, bottom fractions: x 121 to 334, 214 px,
# rows 129 to 133). Its "?" box right of it is brown inside
# (PROGRESS_BOX_COLOUR on PROGRESS_BOX): a white flash or a panel's shade
# shifts both colours, and then the bar is not read.
PROGRESS = (121 / 480, 129 / 1040, 335 / 480, 134 / 1040)
PROGRESS_FILL = (159, 89, 0)
PROGRESS_BOX = (340 / 480, 121 / 1040, 358 / 480, 125 / 1040)
PROGRESS_BOX_COLOUR = (89, 69, 45)
PROGRESS_MARGIN = 16
# Read only while calibrated on real captures of every state it tells
# apart (test_gates.py: fixtures/bar_empty, bar_partial, bar_full,
# bar_flash).
PROGRESS_CALIBRATED = True


def _near(pixels, i, colour):
    return all(abs(pixels[i + k] - colour[k]) <= PROGRESS_MARGIN for k in range(3))


def progress(shot):
    """The stage progress bar's fill, 0 (empty) to 1 (full), or None when
    it is not drawn as calibrated (its "?" box not read). Read on the plain
    battle screen only (the caller's check)."""
    if not PROGRESS_CALIBRATED:
        return None
    width, height, pixels = shot

    def box(area):
        return (round(area[0] * width), round(area[1] * height), round(area[2] * width), round(area[3] * height))

    left, top, right, bottom = box(PROGRESS_BOX)
    inside = [_near(pixels, (y * width + x) * 3, PROGRESS_BOX_COLOUR) for y in range(top, bottom)
              for x in range(left, right)]
    if not inside or sum(inside) < 0.8 * len(inside):
        return None
    left, top, right, bottom = box(PROGRESS)
    runs = []
    for y in range(top, bottom):
        run = 0
        while left + run < right and _near(pixels, (y * width + left + run) * 3, PROGRESS_FILL):
            run += 1
        runs.append(run)
    # The middle row's run of the sorted ones: an effect across one row
    # changes nothing.
    return sorted(runs)[len(runs) // 2] / (right - left)
