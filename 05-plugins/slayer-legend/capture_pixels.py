"""Sample immutable RGB captures onto the calibrated 480×1040 lattice.

Only pixel geometry changes; callers retain their confidence thresholds and
return positions as screen fractions. A smaller source loses information:
precision readers must refuse it rather than treating upsampling as evidence.
"""

from math import gcd
from threading import RLock

WIDTH, HEIGHT = 480, 1040

_normalised = []
_normalise_lock = RLock()


def canonical(shot):
    width, height, pixels = shot
    if (width, height) == (WIDTH, HEIGHT):
        return shot
    with _normalise_lock:
        for original, result in _normalised:
            if original[2] is pixels and original[:2] == (width, height):
                return result
    # Sample centres. An integer or 1.5× nearest-pixel enlargement preserves
    # every calibrated pixel exactly; no interpolated colour crosses a gate.
    divisor = gcd(width, WIDTH)
    period, source_period = WIDTH // divisor, width // divisor
    # RGB channel slices repeat every rational scaling period (two target
    # pixels per three source pixels at 720). Strided byte copies avoid a
    # Python loop over half a million pixels on every fresh screenshot.
    channels = [(phase * 3 + channel, int((phase + .5) * width / WIDTH) * 3 + channel)
                for phase in range(period) for channel in range(3)]
    rows = []
    for y in range(HEIGHT):
        start = min(height - 1, int((y + .5) * height / HEIGHT)) * width * 3
        source = pixels[start:start + width * 3]
        row = bytearray(WIDTH * 3)
        for target_channel, source_channel in channels:
            row[target_channel::period * 3] = source[source_channel::source_period * 3]
        rows.append(row)
    result = WIDTH, HEIGHT, b"".join(rows)
    with _normalise_lock:
        _normalised.insert(0, (shot, result))
        del _normalised[2:]
    return result
