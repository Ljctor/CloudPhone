"""Native 480px Cube counter, using independently observed glyph footprints.

Pink glyphs have ten body rows; commas descend below that baseline.
All ten digits are retained from real counter crops, not font guesses.
"""
from functools import lru_cache
import re

NATIVE_DIGITS_CALIBRATED = True
MAX_GLYPH_ERROR = .12
MAX_LINE_ERROR = .04
MIN_MARGIN = 10

PATTERNS = {
    '9': (
        ('0111110', '1111111', '1100011', '1100011', '1100011', '0111111', '0111111', '0000111', '0111110', '0111100', '0000000', '0000000', '0000000', '0000000'),
        ('0111110', '1111111', '1100011', '1100011', '1100011', '0111111', '0111111', '0001111', '0111110', '0111000', '0000000', '0000000', '0000000', '0000000'),
    ),
    ',': (
        ('000', '000', '000', '000', '000', '000', '000', '000', '011', '011', '110', '110', '000', '000'),
        ('000', '000', '000', '000', '000', '000', '000', '000', '111', '111', '100', '100', '000', '000'),
        ('000', '000', '000', '000', '000', '000', '000', '000', '011', '011', '110', '110', '000', '000'),
    ),
    '8': (
        ('0111110', '1111111', '1100011', '1111111', '0111110', '1100011', '1100011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
    ),
    '3': (
        ('0111110', '1111111', '1100011', '0001111', '0001110', '0000011', '0000011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
        ('0111110', '1111111', '1100011', '0011111', '0011110', '0000011', '0000011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
    ),
    '6': (
        ('0011110', '0111110', '1110000', '1111110', '1111110', '1100011', '1100011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
    ),
    '7': (
        ('1111111', '1111111', '0000011', '0000111', '0000110', '0000110', '0001110', '0001100', '0001100', '0001100', '0000000', '0000000', '0000000', '0000000'),
        ('1111111', '1111111', '0000011', '0000111', '0000110', '0000110', '0001110', '0001100', '0001100', '0001100', '0000000', '0000000', '0000000', '0000000'),
    ),
    '4': (
        ('00000110', '00011110', '00111110', '01110110', '01100110', '11000110', '11111111', '11111111', '00000110', '00000110', '00000000', '00000000', '00000000', '00000000'),
        ('000001100', '000011100', '000111100', '011111100', '011101100', '110001100', '111111111', '111111111', '000001100', '000001100', '000000000', '000000000', '000000000', '000000000'),
    ),
    '2': (
        ('0111110', '1111111', '1100011', '0001111', '0001110', '0011000', '0111000', '1110000', '1111111', '1111111', '0000000', '0000000', '0000000', '0000000'),
    ),
    '0': (
        ('0111110', '1111111', '1100011', '1100011', '1100011', '1100011', '1100011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
    ),
    '1': (
        ('0111', '1111', '1111', '0111', '0111', '0111', '0111', '0111', '1111', '1111', '0000', '0000', '0000', '0000'),
    ),
    '5': (
        ('1111111', '1111111', '1100000', '1111110', '1111110', '0000011', '0000011', '1100011', '1111111', '0111110', '0000000', '0000000', '0000000', '0000000'),
    ),
}
PATTERNS = {char: tuple(tuple(tuple(value == "1" for value in row) for row in pattern) for pattern in variants)
            for char, variants in PATTERNS.items()}
OWNERS = {}
for _char, _variants in PATTERNS.items():
    for _pattern in _variants:
        OWNERS.setdefault((len(_pattern[0]), tuple(value for row in _pattern for value in row)), set()).add(_char)

def _mask(shot):
    width, _, pixels = shot
    return [[_purple(pixels, (y * width + x) * 3) for x in range(357, 463)]
            for y in range(289, 303)]


def _purple(pixels, offset):
    red, green, blue = pixels[offset:offset + 3]
    return red > 95 and blue > green * 1.2 and red > green * 1.15


def _paths(mask, locks=None):
    """Amount alternatives; exact native cells can resolve only their own class.

    The second pass tracks every unresolved alternative separately. Changing
    segmentation, changing a noisy cell, or a tied fingerprint remains an
    ambiguity; an unrelated exact digit never clears it.
    """
    width = len(mask[0])
    @lru_cache(None)
    def score(x, char, cells):
        observed = tuple(value for row in mask for value in row[x:x + cells])
        exact = OWNERS.get((cells, observed)) == {char}
        distance = min(sum(mask[y][x + k] != pattern[y][min(len(pattern[0]) - 1,
                         int((k + .5) * len(pattern[0]) / cells))]
                         for y in range(14) for k in range(cells)) for pattern in PATTERNS[char])
        return distance, exact
    paths = {(0, True, 0, False): [(0, '', ())]}
    for x in range(width):
        for (at, first, count, unresolved), choices in list(paths.items()):
            if at != x:
                continue
            def add(key, cost, text, spans):
                target = paths.setdefault(key, [])
                previous = next((i for i, item in enumerate(target) if item[1] == text), None)
                candidate = (cost, text, spans)
                if previous is None:
                    target.append(candidate)
                elif cost < target[previous][0]:
                    target[previous] = candidate
                target.sort()
                del target[2:]
            if not any(row[x] for row in mask):
                for cost, text, spans in choices:
                    add((x + 1, first, count, unresolved), cost, text, spans)
            for char, variants in PATTERNS.items():
                comma = char == ','
                if comma and not (count > 0 and (first or count == 3)):
                    continue
                if not comma and count >= 3:
                    continue
                for cells in sorted({len(pattern[0]) + delta for pattern in variants for delta in (-1, 0, 1)}):
                    if cells < 1 or x + cells > width:
                        continue
                    distance, exact = score(x, char, cells)
                    if distance > cells * 14 * MAX_GLYPH_ERROR:
                        continue
                    uncertain = unresolved
                    if locks is not None:
                        expected = locks.get(x)
                        if expected is None or expected[:2] != (char, cells):
                            # Resolve only a different class on the SAME
                            # independently recorded, exact native footprint.
                            resolved = expected is not None and expected[1] == cells and expected[2] and distance >= 3
                            uncertain = uncertain or not resolved
                    key = (x + cells, False if comma else first, 0 if comma else count + 1, uncertain)
                    for cost, text, spans in choices:
                        if first and text == '0':
                            continue  # zero is a complete integer, never a prefix
                        add(key, cost + distance, text + char, spans + ((char, x, cells, exact),))
    return sorted((cost, text, spans, uncertain)
                  for (x, first, count, uncertain), choices in paths.items()
                  if x == width and (first and count > 0 or not first and count == 3)
                  for cost, text, spans in choices)


def decode(mask):
    used = [x for x in range(len(mask[0])) if any(row[x] for row in mask)]
    if not used:
        return None
    mask = [row[min(used):max(used) + 1] for row in mask]
    # Grammar must never turn an independently exact leading zero into an
    # eight merely to make a longer integer syntactically valid.
    for zero in PATTERNS['0']:
        cells = len(zero[0])
        if len(mask[0]) > cells and tuple(tuple(row[:cells]) for row in mask) == zero:
            return None
    candidates = _paths(mask)
    if not candidates:
        return None
    best, text, spans, _ = candidates[0]
    if best > len(mask[0]) * 14 * MAX_LINE_ERROR:
        return None
    alternatives = [item for item in candidates[1:] if item[1] != text]
    if alternatives and alternatives[0][0] - best < MIN_MARGIN:
        locks = {x: (char, cells, exact) for char, x, cells, exact in spans}
        unresolved = [item for item in _paths(mask, locks) if item[3] and item[1] != text]
        if unresolved and unresolved[0][0] - best < MIN_MARGIN:
            return None
    if not re.fullmatch(r'(?:0|[1-9]\d{0,2}(?:,\d{3})*)', text):
        return None
    return {'text': text, 'value': int(text.replace(',', ''))}


def read(shot):
    if not NATIVE_DIGITS_CALIBRATED or shot[:2] != (480, 1040):
        return None
    width, _, pixels = shot
    # The independently calibrated Cube icon is necessary. Its white rim
    # and purple centre reject coloured battle effects at these coordinates.
    purple = white = 0
    for y in range(284, 306):
        for x in range(331, 354):
            offset = (y * width + x) * 3
            purple += _purple(pixels, offset)
            white += min(pixels[offset:offset + 3]) > 180
    if purple < 50 or white < 20:
        return None
    return decode(_mask(shot))
