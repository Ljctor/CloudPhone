"""Finds the decimals of Slayer Legend's emerald counter on a screenshot.

Python twin of emerald_mask.js (same directory), for browsers that cannot read
the video's pixels (Firefox on Android with hardware decoding): the page then
asks the gateway, which takes the screenshot from the emulator. Keep the two
in step.
"""

import math

# Search area, in 360-wide Android pixels.
AREA = {"x": 148, "y": 10, "width": 47, "height": 20}

BRIGHT = 0.55
EDGE = 0.3
DARK = 0.2
MIN_CONTRAST = 40


def js_round(value):
    """Math.round: halves go up (Python's round() goes to even)."""
    return math.floor(value + 0.5)


def find_emerald_mask(pixels, width, height, scale, channels=4):
    """pixels: bytes of the search area, `channels` bytes per pixel (RGB
    first), `width` x `height` pixels, scaled by `scale` (screen width / 360).

    Returns (mask, reason): mask is {x, y, width, height, color} in 360-wide
    Android pixels relative to the screen, or None with the failed step as
    reason ('flat', 'text', 'comma', 'digits', 'colour')."""

    def luminance(x, y):
        i = (y * width + x) * channels
        return (pixels[i] * 299 + pixels[i + 1] * 587 + pixels[i + 2] * 114) / 1000

    values = [luminance(x, y) for y in range(height) for x in range(width)]
    low, high = min(values), max(values)
    if high - low < MIN_CONTRAST:
        return None, "flat"
    bright_level = low + (high - low) * BRIGHT
    edge_level = low + (high - low) * EDGE
    dark_level = low + (high - low) * DARK

    def bright(x, y):
        return values[y * width + x] > bright_level

    def edge(x, y):
        return values[y * width + x] > edge_level

    row_counts = [sum(1 for x in range(width) if bright(x, y)) for y in range(height)]
    # The digits: the tallest band of rows with many bright pixels.
    busy = max(4, js_round(6 * scale))
    best = None
    y = 0
    while y < height:
        if row_counts[y] >= busy:
            end = y
            while end + 1 < height and row_counts[end + 1] >= busy:
                end += 1
            if best is None or end - y > best[1] - best[0]:
                best = (y, end)
            y = end
        y += 1
    if best is None:
        return None, "text"
    top, bottom = best
    text_height = bottom - top + 1
    if text_height < 4 * scale or text_height > 10 * scale:
        return None, "text"

    # The comma's tail: bright pixels just below the digits. Keep the last one.
    tail_rows = max(1, js_round(scale))
    comma = -1
    for x in range(width - 1, -1, -1):
        if any(bright(x, y) for y in range(bottom + 1, min(height - 1, bottom + tail_rows) + 1)):
            comma = x
            break
    if comma < 0:
        return None, "comma"
    while comma > 0 and bottom + 1 < height and bright(comma - 1, bottom + 1):
        comma -= 1

    # End of the number: last bright column after the comma, stopping at a
    # gap wider than a digit spacing (the next icon).
    gap = max(3, js_round(3 * scale))
    right = comma
    empty = 0
    x = comma + 1
    while x < width and empty <= gap:
        if any(edge(x, y) for y in range(top, bottom + 1)):
            right = x
            empty = 0
        else:
            empty += 1
        x += 1
    if right - comma < 3 * scale:
        return None, "digits"
    # The digits after the comma: skip the comma's own columns and the gap
    # after it. When the comma touches the next digit, assume a 2 px comma.
    def column(x):
        return any(edge(x, y) for y in range(top, bottom + 1))

    after = comma
    while after <= right and column(after):
        after += 1
    while after <= right and not column(after):
        after += 1
    if after > right - 2 * scale:
        after = min(right, comma + js_round(2 * scale))
    # Start of the number: first glyph column left of the comma, stopping at
    # the same kind of gap (the emerald icon) or at the area's edge.
    start = comma
    empty = 0
    x = comma - 1
    while x >= 0 and empty <= gap:
        if any(edge(x, y) for y in range(top, bottom + 1)):
            start = x
            empty = 0
        else:
            empty += 1
        x -= 1

    # Colour: the bar just right of the number.
    r = g = b = n = 0
    for y in range(top, bottom + 1):
        for x in range(right + 2, min(width - 1, right + 1 + gap) + 1):
            if values[y * width + x] < dark_level:
                i = (y * width + x) * channels
                r += pixels[i]
                g += pixels[i + 1]
                b += pixels[i + 2]
                n += 1
    if n == 0:
        return None, "colour"
    pad = 1
    return {
        "x": AREA["x"] + comma / scale,
        "y": AREA["y"] + top / scale - pad,
        "width": (right - comma + 1) / scale + pad,
        "height": (bottom - top + 1 + tail_rows) / scale + 2 * pad,
        "color": f"rgb({js_round(r / n)}, {js_round(g / n)}, {js_round(b / n)})",
        # The whole number, and the digits' height without the comma's tail.
        "number": {
            "x": AREA["x"] + start / scale - pad,
            "y": AREA["y"] + top / scale - pad,
            "width": (right - start + 1) / scale + 2 * pad,
            "height": (bottom - top + 1 + tail_rows) / scale + 2 * pad,
            "digitHeight": (bottom - top + 1) / scale,
        },
        # The digits after the comma: where they are on screen, and the same
        # box in the search area's pixels (to copy them), one row of margin.
        "decimals": {
            "x": AREA["x"] + after / scale,
            "width": (right - after + 1) / scale,
            "pixels": {
                "x": after,
                "y": max(0, top - 1),
                "width": right - after + 1,
                "height": min(height - 1, bottom + 1) - max(0, top - 1) + 1,
            },
        },
    }, None
