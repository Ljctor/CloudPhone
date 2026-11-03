"""Native Gold decoding using the actual game's independently extracted font.

The active legacy Text uses Beantown, bold, best fit in a 486.84985-wide
rectangle, a .5 local scale and the 480/1080 canvas scale. Its source-pixel
width budget is therefore 216.3777. A single font size, origin and baseline
apply to the entire amount; overlapping bold tails share their pixels.

The source font is not distributed. legacy_font contains only independently
rasterized counter glyphs. A whole real Font18 counter replays with squared
four-level error 2 over 864 pixels using MONO bitmap bold in both axes,
rounded regular advances and bilinear half-size sampling. Other captured
amounts independently verify Font17 and Font18 without amount-specific cuts.
"""

import collections
from functools import lru_cache
import importlib.util
import math
import os


_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_legacy_font_gold",
    os.path.join(os.path.dirname(__file__), "legacy_font.py"))
_font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_font)
_BANK = _font.glyph_bank(vertical_bold=True, padding=2)
_WIDTH = 486.849853515625 * 480 / 1080


def _palettes():
    for horizontal in range(5, 50):
        a = horizontal / 100
        for vertical in range(horizontal, 50):
            b = vertical / 100
            weights = (a * b, a * (1 - b), (1 - a) * b, (1 - a) * (1 - b))
            yield a, b, tuple(sum(weights[k] for k in range(4) if mask >> k & 1)
                              for mask in range(16))


_PALETTES = tuple(_palettes())


@lru_cache(maxsize=128)
def _level_errors(value):
    """A gray level's losses are independent of the displayed digits/counts."""
    return tuple(min((value - expected) ** 2 for expected in palette)
                 for _, _, palette in _PALETTES)


@lru_cache(maxsize=128)
def _fit_axes(levels):
    columns = [(_level_errors(value), count) for value, count in levels]
    return min((sum(errors[index] * count for errors, count in columns), a, b)
               for index, (a, b, _) in enumerate(_PALETTES))[1:]


def _features(rows, char):
    """Normalize weak background and the body/descender scoring regions.

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


def _axes(shot, box, peak):
    """Infer bilinear phases from the gray palette, independently of digits.

    Four binary source texels produce the subset sums of four bilinear
    weights. Reflections and the exchange of x/y remain hypotheses for the
    complete-line decoder; no expected character selects the palette fit.
    """
    width, _, pixels = shot
    left, top, right, bottom = box
    counts = collections.Counter()
    for y in range(top, bottom):
        for x in range(left, right):
            pixel = pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]
            if max(pixel) - min(pixel) < 16 and 5 < min(pixel) < peak - 4:
                counts[min(pixel)] += 1
    levels = [(value / peak, min(count, 20))
              for value, count in counts.items() if count >= 2]
    if len(levels) < 3:
        return None
    return _fit_axes(tuple(levels))


def decode(shot, ink, box, peak, max_glyph_error, max_line_error, min_margin):
    axes = _axes(shot, box, peak)
    if axes is None:
        return None
    return _decode(tuple(tuple(row) for row in ink), axes,
                   max_glyph_error, max_line_error, min_margin)


@lru_cache(maxsize=96)
def _decode(ink, axes, max_glyph_error, max_line_error, min_margin):
    width, height = len(ink[0]), len(ink)
    a, b = axes
    amounts = {}

    @lru_cache(None)
    def actual(left, right, char):
        return _features([[ink[y][x] if 0 <= x < width else 0
                      for x in range(left, right)] for y in range(height)], char)

    # These source sizes cover the calibrated seven-body-row native font.
    for size in range(16, 21):
        glyphs = _BANK[size]
        zero_top = glyphs['0'][3] - 2  # Remove transparent atlas padding.
        for horizontal, vertical in ((a, b), (b, a)):
            for x_sign in (-1, 1):
                for y_sign in (-1, 1):
                    x_phase = .25 + x_sign * horizontal / 2
                    y_phase = .25 + y_sign * vertical / 2
                    # The candidate finder may retain up to two weak leading
                    # background columns, just as the original native reader.
                    for shift in (-1, -.5, 0, .5, 1, 1.5):
                        origin = x_phase + shift
                        for baseline_shift in (0, -.5):
                            baseline = zero_top * .5 + y_phase + baseline_shift
                            prefix = [value for row in ink
                                      for value in row[:max(0, math.ceil(origin - .5))]]
                            if prefix and max(prefix) > 1:
                                continue
                            prefix_cost = sum(value * value for value in prefix)

                            @lru_cache(None)
                            def pattern(parity, previous, char):
                                left = math.ceil(origin + parity * .5 - .5)
                                right = math.ceil(origin + (parity + glyphs[char][4]) * .5 - .5)
                                raw = _font.raster(glyphs[char], origin, baseline,
                                                   parity, left, right, height)
                                if previous:
                                    tail = _font.raster(
                                        glyphs[previous], origin, baseline,
                                        parity - glyphs[previous][4], left, right, height)
                                    raw = _font.screen(tail, raw)
                                values = [min(3, round(value / 255 * 3)) for value in raw]
                                rows = [values[y * (right - left):(y + 1) * (right - left)]
                                        for y in range(height)]
                                return _features(rows, char), right - left

                            @lru_cache(None)
                            def cost(pen, previous, char):
                                vector, columns = pattern(pen % 2, previous, char)
                                left = math.ceil(origin + pen * .5 - .5)
                                right = left + columns
                                if left < -1 or right > width + 1:
                                    return float('inf')
                                return math.dist(vector, actual(left, right, char)) ** 2

                            if not any(cost(0, '', char) <= max_glyph_error * 9 * height *
                                       pattern(0, '', char)[1] for char in '123456789'):
                                continue
                            # Source pen and previous character preserve native
                            # parity and bold overlap, rather than fitting each
                            # digit's position or phase independently.
                            paths = {(0, True, 0, False, ''): [(prefix_cost, '')]}
                            for pen in range(math.floor(_WIDTH) + 1):
                                states = [(key, value) for key, value in paths.items()
                                          if key[0] == pen]
                                for (_, first, count, grouped, previous), choices in states:
                                    for char in '0123456789,':
                                        comma = char == ','
                                        if comma and not (count > 0 and (first or count == 3)):
                                            continue
                                        if not comma and (count >= 3 or first and count == 0 and char == '0'):
                                            continue
                                        advance = glyphs[char][4]
                                        next_pen = pen + advance
                                        if next_pen > _WIDTH or origin + next_pen * .5 > width + 1:
                                            continue
                                        error = cost(pen, previous, char)
                                        columns = pattern(pen % 2, previous, char)[1]
                                        if error > max_glyph_error * 9 * height * columns:
                                            continue
                                        key = (next_pen, False if comma else first,
                                               0 if comma else count + 1, grouped or comma, char)
                                        following = paths.setdefault(key, [])
                                        following.extend((score + error, text + char)
                                                         for score, text in choices)
                                        following.sort()
                                        del following[4:]
                            for (pen, first, count, grouped, previous), choices in paths.items():
                                if not grouped or count != 3:
                                    continue
                                right = math.ceil(origin + pen * .5 - .5)
                                if abs(width - right) > 2:
                                    continue
                                suffix = [value for row in ink for value in row[max(0, right):]]
                                # Bold ink may overhang the final advance too.
                                # It is a glyph tail, rather than empty suffix.
                                tail = _font.raster(
                                    glyphs[previous], origin, baseline,
                                    pen - glyphs[previous][4], max(0, right), width, height)
                                terminal_error = sum(
                                    (value - min(3, round(alpha / 255 * 3))) ** 2
                                    for value, alpha in zip(suffix, tail))
                                for score, text in choices:
                                    if len(text.replace(',', '')) < 7:
                                        continue
                                    # Unity selects the largest fitting size.
                                    if size + 1 in _BANK and sum(_BANK[size + 1][char][4]
                                                                 for char in text) <= _WIDTH:
                                        continue
                                    error = score + terminal_error
                                    amounts[text] = min(amounts.get(text, float('inf')), error)
    ordered = sorted((score, text) for text, score in amounts.items())
    if not ordered or ordered[0][0] > max_line_error * 9 * height * width:
        return None
    if len(ordered) > 1 and ordered[1][0] - ordered[0][0] < min_margin:
        return None
    return ordered[0][1]
