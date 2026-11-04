"""Strict native numeric OCR for the measured companion-stone controls.

Independent legacy-font glyphs and calibrated control geometry reproduce the
entire observed line. No expected amount or balance lookup enters decoding.
Only the measured native font size is accepted; other sizes stay unread.
"""
import importlib.util
import math
import re
from functools import lru_cache
from pathlib import Path
_spec = importlib.util.spec_from_file_location('slayer_resource_font', str(Path(__file__).with_name('legacy_font.py')))
_font = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_font)
BANK = {26: _font.glyph_bank(vertical_bold=False)[26]}
font = _font
MAX_PIXEL_ERROR = 2
MIN_MARGIN = 4


def paths(rows, baseline, phase):
    """Blind grouped-number paths with source advances and preceding-glyph overlap."""
    width, height = (len(rows[0]), len(rows))
    max_advance = width * 2
    obs = bytes((v for row in rows for v in row))
    used = [(x, y) for y, row in enumerate(rows) for x, v in enumerate(row) if v]
    if not used:
        return []
    top, bottom = (min((y for x, y in used)), max((y for x, y in used)))
    if bottom - top < 4:
        return []
    first = min((x for x, y in used if y < bottom - 2))
    runs = []
    for x, v in enumerate(rows[bottom]):
        if v:
            if runs and runs[-1][1] == x - 1:
                runs[-1] = (runs[-1][0], x)
            else:
                runs.append((x, x))
    # Separate the body from sparse comma descenders at every font size.
    # Counting groups from the actual raster avoids an amount-length limit.
    counts = [sum(row) for row in rows]
    body_bottom = max(y for y, count in enumerate(counts) if count >= max(counts) * .3)
    commas = runs if bottom > body_bottom else []
    if any((b - a > 3 for a, b in commas)):
        return []

    @lru_cache(None)
    def patch(left, right):
        return bytes((obs[y * width + x] for y in range(height) for x in range(left, right)))
    poses = []
    for n, glyphs in BANK.items():
        if abs(glyphs['0'][1] * 0.5 - 2 - (bottom - top)) > 3:
            continue
        for origin in [first + v / 4 for v in range(-6, 2) if (v / 4) % .5 == phase]:
            error = 1000000000.0
            for char in '0123456789':
                right = math.ceil(origin + glyphs[char][4] * 0.5 - 0.5)
                left = max(0, math.ceil(origin - 0.5))
                alpha = font.raster(glyphs[char], origin, baseline, 0, left, right, height)
                score = sum(((a >= 100) != b for a, b in zip(alpha, patch(left, right))))
                error = min(error, score)
            poses.append((error, n, origin, baseline))
    # The first cell proposes physical poses; grouped-number DP is blind.
    found = []
    for _, n, origin, baseline in sorted(poses)[:4]:
        glyphs = BANK[n]

        # A preceding glyph may bleed across its advance; retain that ink.
        @lru_cache(None)
        def composed(parity, char, previous):
            left = math.ceil(origin + parity * 0.5 - 0.5)
            right = math.ceil(origin + (parity + glyphs[char][4]) * 0.5 - 0.5)
            alpha = font.raster(glyphs[char], origin, baseline, parity, left, right, height)
            if previous:
                prior = font.raster(glyphs[previous], origin, baseline, parity - glyphs[previous][4], left, right, height)
                alpha = font.screen(prior, alpha)
            binary = bytes((v >= 100 for v in alpha))
            centre = None
            if char == ',':
                xs = [x for x, v in enumerate(binary[bottom * (right - left):(bottom + 1) * (right - left)]) if v]
                if xs:
                    centre = (min(xs) + max(xs)) / 2
            return (binary, right - left, centre)

        @lru_cache(None)
        def cell(pen, char, previous):
            binary, cells, centre = composed(pen % 2, char, previous)
            left = math.ceil(origin + pen * 0.5 - 0.5)
            right = left + cells
            if left < 0 or right > width:
                return (1000000000.0, None)
            error = sum((a != b for a, b in zip(binary, patch(left, right))))
            return (error, left + centre if centre is not None else None)
        for leading in (1, 2, 3):
            roles = ['d'] * leading
            for k in range(len(commas)):
                roles += [k] + ['d'] * 3
            states = {(0, ''): [(0, '')]}
            for role in roles:
                following = {}
                for (pen, previous), choices in states.items():
                    chars = '0123456789' if role == 'd' else ','
                    for char in chars:
                        if previous == '0' and pen == glyphs['0'][4]:
                            continue
                        end = pen + glyphs[char][4]
                        if end > max_advance + 1:
                            continue
                        error, centre = cell(pen, char, previous)
                        if char == ',' and (centre is None or abs(centre - sum(commas[role]) / 2) > 1):
                            continue
                        following.setdefault((end, char), []).extend(((cost + error, text + char) for cost, text in choices))
                states = {key: sorted(set(values))[:2] for key, values in following.items()}
            for (pen, last), choices in states.items():
                for cost, text in choices:
                    # The complete source advance must fit the measured crop.
                    if pen > max_advance:
                        continue
                    right = min(width, math.ceil(origin + pen * 0.5 - 0.5))
                    left = max(0, math.ceil(origin - 0.5))
                    outside = sum((obs[y * width + x] for y in range(height) for x in range(left)))
                    tail = font.raster(glyphs[last], origin, baseline, pen - glyphs[last][4], right, width, height)
                    outside += sum(((a >= 100) != b for a, b in zip(tail, patch(right, width))))
                    found.append((cost + outside, text, n, origin, baseline))
    best = {}
    for row in found:
        if row[1] not in best or row < best[row[1]]:
            best[row[1]] = row
    return sorted(best.values())[:5]


def valid(text):
    return re.fullmatch(r'(?:0|[1-9]\d{0,2}(?:,\d{3})*)', text) is not None


@lru_cache(maxsize=64)
def decode(rows, baseline=14.75, phase=.25):
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        return None
    alternatives = paths(rows, baseline, phase)
    if not alternatives:
        return None
    error, text, *_ = alternatives[0]
    if error > MAX_PIXEL_ERROR or not valid(text):
        return None
    if len(alternatives) > 1 and alternatives[1][0] - error < MIN_MARGIN:
        return None
    return {'text': text, 'value': int(text.replace(',', ''))}
