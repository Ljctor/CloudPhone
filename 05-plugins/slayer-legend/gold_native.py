"""Strict native 480x1040 full-digit Gold OCR, calibrated on real crops.

Seven body rows plus comma descenders; actual four-level native glyphs,
including antialiasing phases. No scaled 13-row font authorizes a reading.
"""
NATIVE_FULL_DIGITS_CALIBRATED = True
MAX_GLYPH_ERROR = .065
MAX_LINE_ERROR = .025
MIN_MARGIN = 10

# Digit cells from reviewed bright/parked native captures; see
# fixtures/gold_native_480*.txt and test_gold_native.py.
_PATTERNS = {
    '1': (
        ('030', '230', '230', '030', '030', '030', '233', '000'),
        ('0230', '0330', '0330', '0230', '0230', '0330', '0333', '0000'),
        ('230', '330', '330', '230', '230', '330', '333', '000'),
        ('0200', '3310', '0310', '0310', '0310', '0320', '2330', '0000'),
        ('020', '330', '030', '030', '030', '232', '233', '000'),
        ('020', '230', '030', '030', '030', '032', '233', '000'),
        ('020', '330', '030', '030', '030', '032', '233', '000'),
        ('020', '330', '330', '230', '230', '332', '333', '000'),
        ('0200', '2310', '0310', '0310', '0310', '0320', '2332', '0000'),
        ('020', '230', '030', '030', '030', '232', '233', '000'),
    ),
    '3': (
        ('03330', '23233', '22133', '00333', '00023', '23133', '23332', '00000'),
        ('0220', '3333', '0223', '0233', '0003', '3223', '3332', '0000'),
        ('02220', '23333', '01233', '00333', '00023', '23233', '03330', '00000'),
        ('02220', '33333', '01233', '00333', '00023', '33233', '03330', '00000'),
        ('02220', '33333', '01233', '00333', '00023', '23233', '03330', '00000'),
    ),
    ',': (
        ('00', '00', '00', '00', '00', '00', '03', '23'),
        ('00', '00', '00', '00', '00', '00', '33', '30'),
        ('00', '00', '00', '00', '00', '02', '33', '30'),
        ('00', '00', '00', '00', '00', '02', '23', '23'),
        ('00', '00', '00', '00', '00', '20', '30', '30'),
    ),
    '7': (
        ('03333', '02223', '00013', '00030', '00230', '00230', '00230', '00000'),
        ('23333', '22233', '00133', '00230', '00330', '00310', '00310', '00000'),
        ('2222', '3333', '0023', '0032', '0230', '0230', '0230', '0000'),
        ('02222', '23333', '00133', '00230', '00330', '00310', '00310', '00000'),
        ('22222', '33333', '00133', '00230', '00330', '00310', '00310', '00000'),
        ('02222', '03333', '00023', '00032', '00230', '00230', '00230', '00000'),
        ('02222', '33333', '00133', '00230', '00330', '00310', '00310', '00000'),
    ),
    '2': (
        ('03330', '23233', '22133', '00330', '03310', '23110', '23333', '00000'),
        ('02220', '23333', '01133', '00330', '03310', '23222', '23333', '00000'),
        ('01220', '03333', '01023', '00132', '02330', '03322', '03333', '00000'),
        ('0220', '3333', '0023', '0132', '2330', '3322', '3333', '0000'),
    ),
    '4': (
        ('000230', '003330', '013330', '231230', '233333', '222332', '000230', '000000'),
        ('000030', '001330', '013330', '033030', '033333', '022232', '000030', '000000'),
        ('000230', '003330', '013330', '231230', '333333', '222332', '000230', '000000'),
        ('000120', '002330', '023330', '232330', '333330', '011330', '000230', '000000'),
        ('000120', '002330', '023330', '232330', '233330', '011330', '000230', '000000'),
        ('000120', '002330', '023330', '032330', '233330', '011330', '000230', '000000'),
        ('00020', '00330', '03330', '33130', '33333', '01132', '00030', '00000'),
        ('000020', '000330', '013330', '033130', '033333', '011132', '000030', '000000'),
    ),
    '9': (
        ('23310', '32230', '31030', '33330', '23330', '01320', '23300', '00000'),
        ('02330', '03223', '03103', '03333', '02333', '01132', '02330', '00000'),
        ('02220', '33333', '33023', '23233', '03333', '02330', '03320', '00000'),
        ('01220', '03333', '03103', '03223', '02333', '01232', '02330', '00000'),
        ('02220', '33333', '33023', '33233', '03333', '02330', '03320', '00000'),
        ('02220', '23333', '23023', '23233', '03333', '02330', '03320', '00000'),
        ('0220', '3333', '3103', '3223', '2333', '0232', '2330', '0000'),
    ),
    '8': (
        ('03330', '23233', '23133', '23333', '23023', '23133', '23332', '00000'),
        ('02200', '33333', '32233', '33333', '31033', '32233', '33320', '00000'),
        ('2220', '3333', '3233', '3333', '3023', '3233', '3330', '0000'),
        ('02220', '23333', '23233', '23333', '23023', '23233', '03330', '00000'),
        ('0220', '3333', '3223', '3333', '3103', '3223', '3332', '0000'),
        ('02220', '33333', '33233', '33333', '33023', '33233', '03330', '00000'),
    ),
    '0': (
        ('02330', '03223', '03103', '03103', '03103', '03113', '03332', '00000'),
        ('0220', '3333', '3103', '3103', '3103', '3223', '3332', '0000'),
        ('0222', '2333', '2302', '2302', '2302', '2323', '0333', '0000'),
        ('02220', '23333', '23023', '23023', '23023', '23233', '03330', '00000'),
        ('02220', '33333', '33023', '33023', '33023', '23233', '03330', '00000'),
        ('01220', '03333', '03103', '03103', '03103', '03223', '03332', '00000'),
    ),
    '6': (
        ('00220', '03330', '23220', '23332', '23023', '23233', '03330', '00000'),
        ('00220', '03330', '33220', '33332', '33023', '33233', '03330', '00000'),
        ('00120', '32330', '33320', '33332', '33103', '33223', '03332', '00000'),
        ('00220', '03330', '33220', '33332', '33023', '23233', '03330', '00000'),
        ('0120', '2330', '3320', '3332', '3103', '3223', '3332', '0000'),
        ('00220', '03330', '23220', '23332', '33023', '33233', '03330', '00000'),
        ('00120', '02330', '03320', '03332', '03103', '03223', '03332', '00000'),
    ),
    '5': (
        ('02222', '23333', '23220', '23332', '00023', '23233', '03330', '00000'),
        ('2222', '3333', '3220', '3332', '0003', '3223', '3332', '0000'),
        ('02222', '33333', '33220', '33332', '00023', '33233', '03330', '00000'),
        ('02222', '03333', '03220', '03332', '00003', '03223', '03332', '00000'),
    ),
}

def _cell(rows, char):
    """Ignore adjacent glyph antialiasing and enclosed background pockets.

    Native digits occupy seven rows; comma ink occupies the last three.
    Weak boundary pixels and isolated upper flecks cannot identify a digit.
    These masks are shared by calibration and observation, never by labels.
    """
    values = [list(row) for row in rows]
    width = len(values[0])
    for y, row in enumerate(values):
        for x, value in enumerate(row):
            if char == ',' and y < 5 or char != ',' and y == 7 or value == 1 and x in (0, width - 1):
                row[x] = 0
    if char != ',':
        remaining = {(x, y) for y, row in enumerate(values) for x, value in enumerate(row) if value >= 2}
        while remaining:
            point = remaining.pop(); component = [point]
            for x, y in component:
                for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if neighbor in remaining:
                        remaining.remove(neighbor); component.append(neighbor)
            if len(component) <= 3 and all(y < 5 for x, y in component):
                for x, y in component:
                    values[y][x] = 0
    return tuple(value for row in values for value in row)

_GLYPHS = {}
for _char, _variants in _PATTERNS.items():
    _GLYPHS[_char] = {}
    for _rows in _variants:
        _GLYPHS[_char].setdefault(len(_rows[0]), []).append(_cell([tuple(int(v) for v in row) for row in _rows], _char))

def _candidates(shot, shade):
    width, height, pixels = shot
    left, top, right, bottom = round(width * .25), round(height * .10), round(width * .85), round(height * .30)
    w, h = right - left, bottom - top
    rgb = [[pixels[((y + top) * width + x + left) * 3:((y + top) * width + x + left) * 3 + 3]
            for x in range(w)] for y in range(h)]
    values = [[min(pixel) for pixel in row] for row in rgb]
    outside, queue = set(), []
    for y in range(h):
        for x in range(w):
            if (x in (0, w - 1) or y in (0, h - 1)) and values[y][x] >= 80 * shade:
                outside.add((x, y)); queue.append((x, y))
    # The white flash behind the outlined text must not become glyph ink.
    # Its bright region reaches the search boundary; enclosed letters do not.
    for x, y in queue:
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            a, b = x + dx, y + dy
            if 0 <= a < w and 0 <= b < h and (a, b) not in outside and values[b][a] >= 80 * shade:
                outside.add((a, b)); queue.append((a, b))
    for y in range(h):
        for x in range(w):
            if (x, y) in outside or max(rgb[y][x]) - min(rgb[y][x]) > 25 * shade:
                values[y][x] = 0
    active = [sum(value >= 100 * shade for value in row) >= 18 for row in values]
    start = None
    lines = []
    for y, on in enumerate(active + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start == 7:
                lines.append((start, y))
            start = None
    for y0, y1 in lines:
        peak = max(value for row in values[y0:y1] for value in row)
        if peak < 120 * shade or y1 >= h:
            continue
        ink = [[min(3, round(value / peak * 3)) for value in row] for row in values[y0:y1 + 1]]
        used = [any(row[x] for row in ink) for x in range(w)]
        groups, start = [], None
        for x, on in enumerate(used + [False]):
            if on and start is None:
                start = x
            elif not on and start is not None:
                if groups and start - groups[-1][1] <= 4:
                    groups[-1] = (groups[-1][0], x)
                else:
                    groups.append((start, x))
                start = None
        for x0, x1 in groups:
            if not 35 <= x1 - x0 <= 200:
                continue
            coin = sum(r > 220 * shade and 120 * shade < g < 215 * shade and b < 90 * shade
                       for y in range(max(0, y0 - 6), min(h, y1 + 7))
                       for r, g, b in rgb[y][max(0, x0 - 40):x0])
            if coin >= 15:
                yield [row[x0:x1] for row in ink], (left + x0, top + y0, left + x1, top + y1 + 1), peak


def _decode(ink):
    """Joint segmentation and digit recognition, with grouped-integer grammar.

    Commas can touch digits; connected components are not characters. Each
    edge consumes one actual native glyph variant, without resizing it.
    Keep alternative amounts through segmentation and reject close results.
    """
    width = len(ink[0])
    paths = {}
    for start in range(3):
        prefix = [value for row in ink for value in row[:start]]
        if prefix and max(prefix) > 1:
            continue
        paths[(start, True, 0, False)] = [(sum(v * v for v in prefix), '')]
    distances = {}
    for x in range(width):
        states = [(key, value) for key, value in paths.items() if key[0] == x]
        for (_, first, count, grouped), previous in states:
            for char, variants in _GLYPHS.items():
                comma = char == ','
                if comma and not (count > 0 and (first or count == 3)):
                    continue
                if not comma and (count >= 3 or first and count == 0 and char == '0'):
                    continue
                for cells, patterns in variants.items():
                    if x + cells > width:
                        continue
                    key = (char, x, cells)
                    if key not in distances:
                        pixels = _cell([row[x:x + cells] for row in ink], char)
                        distances[key] = min(sum((a - b) ** 2 for a, b in zip(pixels, pattern)) for pattern in patterns)
                    distance = distances[key]
                    if distance > MAX_GLYPH_ERROR * 9 * 8 * cells:
                        continue
                    target = (x + cells, False if comma else first, 0 if comma else count + 1, grouped or comma)
                    choices = paths.setdefault(target, [])
                    for cost, text in previous:
                        candidate = (cost + distance, text + char)
                        old = next((i for i, entry in enumerate(choices) if entry[1] == candidate[1]), None)
                        if old is None:
                            choices.append(candidate)
                        elif candidate[0] < choices[old][0]:
                            choices[old] = candidate
                    choices.sort()
                    del choices[2:]
    amounts = {}
    for (x, first, count, grouped), choices in paths.items():
        if not grouped or count != 3 or width - x not in (0, 1, 2):
            continue
        suffix = [value for row in ink for value in row[x:]]
        if suffix and max(suffix) > 1:
            continue
        for cost, text in choices:
            if len(text.replace(',', '')) < 7:
                continue
            score = cost + sum(value * value for value in suffix)
            amounts[text] = min(amounts.get(text, float('inf')), score)
    ordered = sorted((score, text) for text, score in amounts.items())
    if not ordered or ordered[0][0] > MAX_LINE_ERROR * 9 * 8 * width:
        return None
    if len(ordered) > 1 and ordered[1][0] - ordered[0][0] < MIN_MARGIN:
        return None
    return ordered[0][1]


def read(shot, shades=(1.0,)):
    if not NATIVE_FULL_DIGITS_CALIBRATED or shot[:2] != (480, 1040):
        return None
    found = {}
    for shade in shades:
        for ink, box, peak in _candidates(shot, shade):
            text = _decode(ink)
            if text:
                value = int(text.replace(',', ''))
                found[value] = {'text': text, 'value': value, 'step': 1, 'full': True,
                                'box': [box[0] / 480, box[1] / 1040, box[2] / 480, box[3] / 1040],
                                'shade': min(1.0, peak / 255)}
    return next(iter(found.values())) if len(found) == 1 else None
