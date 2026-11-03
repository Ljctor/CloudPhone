"""Strict native 480x1040 full-digit Gold OCR, calibrated on real crops.

Seven body rows plus comma descenders; actual four-level native glyphs,
including antialiasing phases. No scaled 13-row font authorizes a reading.
"""
import importlib.util
import os


NATIVE_FULL_DIGITS_CALIBRATED = True
MAX_GLYPH_ERROR = .065
MAX_LINE_ERROR = .025
MIN_MARGIN = 10

def _candidate_data(shot):
    width, height, pixels = shot
    left, top, right, bottom = round(width * .25), round(height * .10), round(width * .85), round(height * .30)
    w, h = right - left, bottom - top
    rgb = [[pixels[((y + top) * width + x + left) * 3:((y + top) * width + x + left) * 3 + 3]
            for x in range(w)] for y in range(h)]
    values = [[min(pixel) for pixel in row] for row in rgb]
    chroma = [[max(pixel) - min(pixel) for pixel in row] for row in rgb]
    return left, top, w, h, rgb, values, chroma


def _candidates(shot, shade, data=None):
    left, top, w, h, rgb, original, chroma = data or _candidate_data(shot)
    values = [row[:] for row in original]
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
            if (x, y) in outside or chroma[y][x] > 25 * shade:
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


_source = None


def _source_decoder():
    global _source
    if _source is None:
        spec = importlib.util.spec_from_file_location(
            "cloudphone_plugin_slayer_legend_gold_source",
            os.path.join(os.path.dirname(__file__), "gold_source.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _source = module
    return _source


def read(shot, shades=(1.0,)):
    if not NATIVE_FULL_DIGITS_CALIBRATED or shot[:2] != (480, 1040):
        return None
    found = {}
    data = _candidate_data(shot)
    for shade in shades:
        for ink, box, peak in _candidates(shot, shade, data):
            text = _source_decoder().decode(
                shot, ink, box, peak,
                MAX_GLYPH_ERROR, MAX_LINE_ERROR, MIN_MARGIN)
            if text:
                value = int(text.replace(',', ''))
                found[value] = {'text': text, 'value': value, 'step': 1, 'full': True,
                                'box': [box[0] / 480, box[1] / 1040, box[2] / 480, box[3] / 1040],
                                'shade': min(1.0, peak / 255)}
    return next(iter(found.values())) if len(found) == 1 else None
