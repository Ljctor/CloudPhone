"""Read the Enhance Cube balance above an ordinary weapon's detail card.

Calibrated from a real 720x1560 capture (fixtures/cube_balance_720.txt).
The reader is deliberately narrow: other screens and unreadable digits
return None, so a stale balance is never silently replaced by a guess.
"""

import re


# Pixel-font shapes from two real counter captures. Each row is about two
# screen pixels high. All ten digits have now been observed.
SHAPES = {
    "0": ("..########.", "###########", "###......##", "###......##", "###......##", "###......##", "###......##", "###......##", "..########."),
    "1": ("..###..", "#####..", "#####..", "..###..", "..###..", "..###..", "..###..", "#######", "#######"),
    "2": ("..#######..", "###########", "###.....###", "......#####", "....#####..", "..#####....", "#####......", "###########", "###########"),
    "3": ("..#######..", "###########", "###.....###", "....#######", "....#######", "........###", "###.....###", "###########", "..#######.."),
    "4": ("........###..", "......#####..", "....#######..", "..#####.###..", "#####...###..", "#############", "#############", "........###..", "........###.."),
    "5": ("###########", "###########", "####.......", "#########..", "###########", "........###", "####....###", "####....###", "..#######.."),
    "6": ("....#####..", "..#######..", "#####......", "#########..", "###########", "###.....###", "###.....###", "###########", "..#######.."),
    "7": ("###########", "###########", "........###", "......#####", "......###..", "....#####..", "....###....", "....###....", "....###...."),
    "8": ("..#######..", "###########", "###.....###", "###########", "###########", "###.....###", "###.....###", "###########", "..#######.."),
    "9": ("..########.", "###########", "###......##", "###......##", "###########", "..#########", ".......####", ".......###.", "..######..."),
}


def _purple(pixels, offset):
    red, green, blue = pixels[offset:offset + 3]
    return red > 95 and blue > green * 1.2 and red > green * 1.15


def _core(pixels, offset):
    red, green, blue = pixels[offset:offset + 3]
    return red >= 230 and blue > green * 1.2 and red > green * 1.1


def _runs(columns):
    result, start = [], None
    for index, used in enumerate(columns + [False]):
        if used and start is None:
            start = index
        if not used and start is not None:
            result.append((start, index))
            start = None
    return result


def _digit(mask):
    """Closest observed glyph; reject uncertain or ambiguous shapes."""
    width, height = len(mask[0]), len(mask)
    if not 6 <= width <= 15 or height < 15:
        return None
    scores = []
    for character, shape in SHAPES.items():
        target_width = len(shape[0])
        difference = 0
        for row in range(9):
            source_y = min(height - 1, (row * 2 * height + 9) // 18)
            for col in range(target_width):
                source_x = min(width - 1, (col * width + target_width // 2) // target_width)
                difference += mask[source_y][source_x] != (shape[row][col] == "#")
        score = difference / (9 * target_width)
        scores.append((score, character))
    scores.sort()
    if scores[0][0] > 0.17 or scores[1][0] - scores[0][0] < 0.035:
        return None
    return scores[0][1]


def read(shot):
    """{text, value} or None. Only the weapon-detail counter at 720x1560+."""
    width, height, pixels = shot
    if width < 700 or height < 1500:
        return None
    sx, sy = width / 720, height / 1560
    # The small cube at the left is a necessary screen signature.
    left, top, right, bottom = (round(v * scale) for v, scale in
                                zip((497, 427, 528, 457), (sx, sy, sx, sy)))
    icon_pixels = sum(_purple(pixels, (y * width + x) * 3)
                      for y in range(top, bottom) for x in range(left, right))
    if icon_pixels < 90 * sx * sy:
        return None
    x0, y0, x1, y1 = (round(v * scale) for v, scale in
                      zip((535, 430, 695, 452), (sx, sy, sx, sy)))
    mask = [[_purple(pixels, (y * width + x) * 3) for x in range(x0, x1)]
            for y in range(y0, y1)]
    # Pale antialiased edges can join neighbours. The bright core leaves a
    # one-pixel gap even when two digits touch at their pink edges.
    core = [[_core(pixels, (y * width + x) * 3) for x in range(x0, x1)]
            for y in range(y0, y1)]
    runs = _runs([any(row[x] for row in core) for x in range(x1 - x0)])
    if not 1 <= len(runs) <= 20:
        return None
    characters = []
    for left, right in runs:
        glyph = [row[left:right] for row in mask]
        used_y = [y for y, row in enumerate(glyph) if any(row)]
        if not used_y:
            return None
        core_y = [y for y, row in enumerate(core) if any(row[left:right])]
        if len(core_y) < 9 * sy and right - left <= 7 * sx:
            characters.append(",")
            continue
        digit = _digit(glyph[used_y[0]:used_y[-1] + 1])
        if digit is None:
            return None
        characters.append(digit)
    text = "".join(characters)
    if not re.fullmatch(r"[1-9]\d{0,2}(?:,\d{3})*", text):
        return None
    return {"text": text, "value": int(text.replace(",", ""))}
