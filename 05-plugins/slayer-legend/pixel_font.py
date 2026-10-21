"""Reads the text Slayer Legend writes in its pixel font, off a screenshot
(width, height, RGB bytes). Pure, stdlib only.

The game writes its titles, region and stage names, buttons and labels in
one pixel font, scaled: a capital is CAP font pixels high, a descender
goes 2 below (ROWS in all). A line of text is cut into glyphs (columns of
ink), each glyph's box runs from the line's top over ROWS font pixels, so
that a glyph's height and place in the line count (a "." is not an "I"),
and is matched, as ink coverage on each shape's grid, against the shapes
below: the closest wins, None (unread) when even it is too far.

The shapes were cut out of screenshots at 480x1040 (title, region banner,
stage rows, labels) and averaged; those marked "drawn" are drawn in the
same style for letters not seen yet. A letter missing from FONT reads as
the closest shape: compare words with close() rather than ==.

Kept separate so that any screen reader may use it (stage names, the
Battle settings badge, soul weapon names, the engraving).
"""

CAP = 7
ROWS = 9
# How much a glyph's width (in font pixels) off its shape's counts.
WIDTH_WEIGHT = 0.02
# Beyond this distance a glyph is unread.
UNREAD = 0.12

# The shapes, ROWS rows each (CAP for a capital, 2 more for descenders).
FONT = {
    "'": ['#', '#', '#', '.', '.', '.', '.', '.', '.'],
    'G': ['.####', '#....', '#....', '#..##', '#...#', '#...#', '#####', '.....', '.....'],
    'I': ['##', '##', '##', '##', '##', '##', '##', '..', '..'],
    'M': ['##...##', '##...##', '#.###.#', '#.....#', '#.....#', '#.....#', '#.....#', '.......', '.......'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.####', '.....', '.....'],
    'R': ['###.', '####', '#..#', '####', '###.', '#.#.', '#..#', '....', '....'],
    'S': ['.###', '####', '#...', '.###', '...#', '#..#', '####', '....', '....'],
    'V': ['#..#', '#..#', '#..#', '#.##', '###.', '.##.', '.#..', '....', '....'],
    'X': ['#..#', '#..#', '###.', '.#..', '.##.', '#.##', '#..#', '....', '....'],
    'a': ['....', '....', '.###', '.###', '####', '#..#', '####', '....', '....'],
    'c': ['....', '....', '.###', '#...', '#...', '#...', '.###', '....', '....'],
    'd': ['....#', '....#', '..###', '#..##', '#...#', '#...#', '.####', '.....', '.....'],
    'e': ['....', '....', '.##.', '####', '####', '#...', '####', '....', '....'],
    'g': ['....', '....', '####', '#..#', '#..#', '####', '.###', '.##.', '....'],
    'i': ['.#', '..', '##', '.#', '.#', '.#', '.#', '..', '..'],
    'l': ['#', '#', '#', '#', '#', '#', '#', '.', '.'],
    'n': ['....', '....', '####', '#..#', '#..#', '#..#', '#..#', '....', '....'],
    'o': ['.....', '.....', '.###.', '#...#', '#...#', '#...#', '.###.', '.....', '.....'],
    's': ['....', '....', '####', '###.', '.###', '#..#', '####', '....', '....'],
    't': ['.#..', '.#..', '####', '.#..', '.#..', '.#..', '.###', '....', '....'],
    'v': ['.....', '.....', '#...#', '.#.#.', '.#.#.', '.##..', '.##..', '.....', '.....'],
    'w': ['......', '......', '#....#', '#.##.#', '####.#', '##..##', '....#.', '......', '......'],
}

# Drawn in the same style: capitals not seen yet (the "AUTO" label, the
# Battle settings title).
DRAWN = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#", ".....", "....."],
    "B": ["####.", "#...#", "#...#", "####.", "#...#", "#...#", "####.", ".....", "....."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####.", ".....", "....."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####", ".....", "....."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#..", ".....", "....."],
    "r": ["....", "....", "#.##", "##..", "#...", "#...", "#...", "....", "...."],
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###.", ".....", "....."],
}
FONT.update({char: shape for char, shape in DRAWN.items() if char not in FONT})


def crop(shot, area, channel=max):
    """Grey levels of an area ((left, top, right, bottom) fractions) of the
    screenshot, as rows of ints; channel(r, g, b) makes the grey (max: a
    white text and a coloured one alike)."""
    width, height, pixels = shot
    left, top = max(0, int(area[0] * width)), max(0, int(area[1] * height))
    right, bottom = min(width, int(area[2] * width)), min(height, int(area[3] * height))
    rows = []
    for y in range(top, bottom):
        base = y * width * 3
        rows.append([channel(pixels[base + 3 * x], pixels[base + 3 * x + 1], pixels[base + 3 * x + 2])
                     for x in range(left, right)])
    return rows


def ink(rows, level=None, share=0.6, contrast=40):
    """Binary ink: brighter than level, or than share of the way from the
    area's darkest to its brightest pixel. None when the area has no
    contrast (no text)."""
    flat = [v for row in rows for v in row]
    if not flat:
        return None
    low, high = min(flat), max(flat)
    if high - low < contrast:
        return None
    if level is None:
        level = low + (high - low) * share
    return [[v > level for v in row] for row in rows]


def lines(ink, least=4):
    """The text lines of an ink area, as (top, bottom) rows: runs of rows
    with ink, at least least rows high."""
    found, top = [], None
    for y, row in enumerate(ink + [[]]):
        if any(row):
            top = y if top is None else top
        elif top is not None:
            if y - top >= least:
                found.append((top, y - 1))
            top = None
    return found


def _runs(ink, top, bottom):
    """Columns of ink between rows top and bottom, as (left, right)."""
    width = len(ink[0])
    used = [any(ink[y][x] for y in range(top, bottom + 1)) for x in range(width)]
    runs, x = [], 0
    while x < width:
        if used[x]:
            right = x
            while right + 1 < width and used[right + 1]:
                right += 1
            runs.append((x, right))
            x = right + 1
        else:
            x += 1
    return runs


def _bottom(ink, top, bottom, run):
    left, right = run
    return max(y for y in range(top, bottom + 1) if any(ink[y][left:right + 1]))


def metrics(ink, top, bottom):
    """(glyph columns, cap height in pixels) of a line: the cap height runs
    from the line's top to the bottom most glyphs stand on (glyphs at
    least half the line's height: not an apostrophe; the higher on a tie:
    not a descender)."""
    runs = _runs(ink, top, bottom)
    if not runs:
        return [], 0
    bottoms = [_bottom(ink, top, bottom, run) for run in runs]
    tall = [b for b in bottoms if b - top + 1 >= (bottom - top + 1) / 2] or bottoms
    base = max(set(tall), key=lambda b: (tall.count(b), -b))
    return runs, base - top + 1


def _grid(ink, box, cols, rows):
    """Ink coverage of a box (left, right, top, bottom; rows past the ink
    are empty) on a cols x rows grid."""
    left, right, top, bottom = box
    height = len(ink)
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
                    if y < height and ink[y][x]:
                        covered += fx * fy
            row.append(covered / total if total else 0.0)
        grid.append(row)
    return grid


def match(ink, box, cap, font=None, only=None):
    """(the closest character, its distance) for a glyph box (left, right,
    top, bottom) on a line of cap height cap; only: the characters allowed."""
    font = font or FONT
    left, right, top, bottom = box
    width = (right - left + 1) * CAP / cap
    best, distance = None, None
    for char, shape in font.items():
        if only is not None and char not in only:
            continue
        cols = len(shape[0])
        grid = _grid(ink, box, cols, ROWS)
        d = sum((grid[y][x] - (shape[y][x] == "#")) ** 2 for y in range(ROWS) for x in range(cols)) / (cols * ROWS)
        d += WIDTH_WEIGHT * (width - cols) ** 2
        if distance is None or d < distance:
            best, distance = char, d
    return best, distance


def _split(ink, run, top, box_bottom, cap, font, only):
    """The glyphs of one column run, as [(character, distance, (left,
    right))]: one glyph, or, when it reads badly or is too wide for one
    (letters a fractional scale made touch), the cut into glyphs that reads
    best."""
    left, right = run
    chars = [char for char in font if only is None or char in only]
    widest = max(len(font[char][0]) for char in chars)
    width = (right - left + 1) * CAP / cap
    if width > 4 * (widest + 1):
        return [(None, 1.0, run)]  # a bar or a border, not text
    char, d = match(ink, (left, right, top, box_bottom), cap, font, only)
    if d <= UNREAD and width <= widest + 1:
        return [(char, d, run)]
    # Each character only at about its own width.
    widths = {}
    for c in chars:
        size = len(font[c][0]) * cap / CAP
        for w in range(max(1, int(size) - 1), int(size) + 3):
            widths.setdefault(w, []).append(c)
    best = {left: (0.0, [])}
    for end in range(left, right + 1):
        options = []
        for w, candidates in widths.items():
            start = end - w + 1
            if start not in best:
                continue
            c, dist = match(ink, (start, end, top, box_bottom), cap, font, candidates)
            options.append((best[start][0] + dist, best[start][1] + [(c, dist, (start, end))]))
        if options:
            best[end + 1] = min(options, key=lambda option: option[0])
    if right + 1 not in best:
        return [(None, 1.0, run)]
    return best[right + 1][1]


def read_line(ink, top, bottom, font=None, only=None, space=0.3):
    """The words of a line, as lists of (character or None, distance,
    (left, right)); a gap wider than space times the cap height parts two
    words."""
    font = font or FONT
    runs, cap = metrics(ink, top, bottom)
    if not runs or cap < 4:
        return []
    box_bottom = top + round(cap * ROWS / CAP) - 1
    words, word, last = [], [], None
    for run in runs:
        if word and run[0] - last - 1 > space * cap:
            words.append(word)
            word = []
        for char, distance, cut in _split(ink, run, top, box_bottom, cap, font, only):
            word.append((char if distance <= UNREAD else None, distance, cut))
        last = run[1]
    if word:
        words.append(word)
    return words


def text(words):
    """A line's words as a string, "?" for an unread glyph."""
    return " ".join("".join(char or "?" for char, _, _ in word) for word in words)


def read(shot, area, level=None, font=None, only=None, channel=max, caps=None, most=40):
    """[(text, top, bottom)] of every line in area; top and bottom are
    fractions of the screen. channel and level: see crop and ink (min with
    a high level keeps a white text only, off a bright background). caps:
    (lowest, highest) cap height as fractions of the screen height, the
    other lines are skipped; so is a line of more than most glyph columns
    (not text: reading it would only cost time)."""
    rows = crop(shot, area, channel)
    marks = ink(rows, level)
    if not marks:
        return []
    height = shot[1]
    first = int(area[1] * height)
    found = []
    for top, bottom in lines(marks):
        runs, cap = metrics(marks, top, bottom)
        if len(runs) > most or caps and not caps[0] <= cap / height <= caps[1]:
            continue
        found.append((text(read_line(marks, top, bottom, font, only)), (first + top) / height,
                      (first + bottom + 1) / height))
    return found


def distance(a, b):
    """Edit distance between two strings ("?" matches anything)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            same = ca == cb or "?" in (ca, cb)
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (0 if same else 1)))
        previous = current
    return previous[-1]


def close(read_text, names, most=0.25, margin=1):
    """The name read_text reads as: the closest of a closed list of names,
    when it is within most edits per character and every other is at
    least margin edits further. None otherwise (unknown)."""
    if not read_text:
        return None
    key = read_text.replace(" ", "").lower()
    scored = sorted((distance(key, name.replace(" ", "").lower()), name) for name in names)
    if not scored or scored[0][0] > most * max(len(key), 1):
        return None
    if len(scored) > 1 and scored[1][0] - scored[0][0] < max(1, margin):
        return None
    return scored[0][1]


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def roman(letters):
    """The value of a Roman numeral ("XIV": 14), None if it is not one."""
    if not letters or any(c not in ROMAN for c in letters):
        return None
    total, previous = 0, 0
    for c in reversed(letters):
        value = ROMAN[c]
        total = total - value if value < previous else total + value
        previous = max(previous, value)
    return total


def render(string, scale=2, font=None, gap=1, space=3):
    """A synthetic line of text: rows of 0/1, string drawn from font at
    scale (tests and calibration checks)."""
    font = font or FONT
    columns = []
    for i, char in enumerate(string):
        if char == " ":
            columns.extend([[0] * ROWS] * space)
            continue
        shape = font[char]
        for x in range(len(shape[0])):
            columns.append([1 if shape[y][x] == "#" else 0 for y in range(ROWS)])
        if i + 1 < len(string) and string[i + 1] != " ":
            columns.extend([[0] * ROWS] * gap)
    rows = [[columns[x][y] for x in range(len(columns))] for y in range(ROWS)]
    return [[v for v in row for _ in range(scale)] for row in rows for _ in range(scale)]


def numeral(ink):
    """The Roman numeral I to V alone in an ink area, by its strokes, in
    any font (the serif buttons and badge of Battle settings too): the
    strokes cut by a row a third down and by one three quarters down (a V
    has two at the top, one at the bottom; an I one in both). None
    otherwise."""
    if not ink:
        return None
    ys = [y for y, row in enumerate(ink) if any(row)]
    if len(ys) < 5:
        return None
    top, height = ys[0], ys[-1] - ys[0] + 1

    def strokes(fraction):
        row = ink[top + int(height * fraction)]
        return sum(1 for x, v in enumerate(row) if v and (x == 0 or not row[x - 1]))

    return {(1, 1): 1, (2, 2): 2, (3, 3): 3, (3, 2): 4, (2, 1): 5}.get((strokes(1 / 3), strokes(3 / 4)))
