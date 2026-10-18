"""What the fake emulator shows: a synthetic Android screen.

A test pattern at the configured size, with what a black-box test can look
for in the video or in a screenshot:

- a frame counter (top left, below the status area) and a bar sweeping down
  the middle of the screen, so every frame differs;
- the size Android runs at, written in the middle;
- the last touch: a filled white disc while the finger is down, a white ring
  once it is up, centred on the touch's Android coordinates;
- the last key received, written near the bottom.

Nothing game-specific: game plugins are tested against the real game.
"""

import numpy as np

# 5×7 glyphs, '#' = lit. Enough for numbers, sizes and key names.
GLYPHS = {
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "J": ["  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "#   #", "##  #", "# # #", "#  ##", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "# # #", " # # "],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    " ": ["     "] * 7,
    ":": ["     ", "  #  ", "  #  ", "     ", "  #  ", "  #  ", "     "],
    "-": ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
}
_MASKS = {c: np.array([[ch == "#" for ch in row] for row in rows], dtype=bool) for c, rows in GLYPHS.items()}

def draw_text(image, text, x, y, scale, colour):
    """Draws `text` with its top-left corner at (x, y), each glyph pixel a
    scale×scale square; clipped to the image."""
    height, width = image.shape[:2]
    for i, char in enumerate(text.upper()):
        mask = _MASKS.get(char, _MASKS[" "])
        big = np.kron(mask, np.ones((scale, scale), dtype=bool))
        gx = x + i * 6 * scale
        x0, y0 = max(gx, 0), max(y, 0)
        x1, y1 = min(gx + big.shape[1], width), min(y + big.shape[0], height)
        if x1 <= x0 or y1 <= y0:
            continue
        region = image[y0:y1, x0:x1]
        region[big[y0 - y:y1 - y, x0 - gx:x1 - gx]] = colour


def disc(image, cx, cy, radius, colour, ring=0):
    """A filled disc, or a ring `ring` pixels thick."""
    height, width = image.shape[:2]
    y0, y1 = max(cy - radius, 0), min(cy + radius + 1, height)
    x0, x1 = max(cx - radius, 0), min(cx + radius + 1, width)
    if y1 <= y0 or x1 <= x0:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    d2 = (yy - cy) ** 2 + (xx - cx) ** 2
    inside = d2 <= radius * radius
    if ring:
        inside &= d2 >= (radius - ring) ** 2
    image[y0:y1, x0:x1][inside] = colour


class Screen:
    """Renders frames of the fake Android screen (RGB, uint8)."""

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.scale = max(1, round(width / 360))
        background = np.zeros((height, width, 3), dtype=np.uint8)
        # Vertical gradient, dark blue to dark purple.
        ramp = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        background[..., 0] = (20 + 50 * ramp).astype(np.uint8)
        background[..., 1] = 24
        background[..., 2] = (70 - 20 * ramp).astype(np.uint8)
        # Colour bars along the bottom fifth.
        bars = [(200, 200, 200), (200, 200, 0), (0, 200, 200), (0, 200, 0), (200, 0, 200), (200, 0, 0), (0, 0, 200)]
        top = height * 4 // 5
        for i, colour in enumerate(bars):
            background[top:height - 40 * self.scale, i * width // len(bars):(i + 1) * width // len(bars)] = colour
        draw_text(background, f"{width}X{height}", width // 2 - 9 * 6 * self.scale // 2 * 2 // 2,
                  height // 2 - 40 * self.scale, 2 * self.scale, (230, 230, 230))
        draw_text(background, "FAKE ANDROID", 10 * self.scale, height // 2 + 20 * self.scale, 2 * self.scale, (150, 150, 255))
        self.background = background

    def render(self, number, booted=True, touch=None, key=None):
        """touch: (x, y, pressed) in Android pixels, or None."""
        s = self.scale
        if not booted:
            image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
            draw_text(image, "BOOTING", self.width // 2 - 21 * 2 * s, self.height // 2, 2 * s, (200, 200, 200))
            return image
        image = self.background.copy()
        # The sweeping bar: in the middle three fifths of the screen.
        span = self.height * 3 // 5
        y = self.height // 5 + (number * 6 * s) % span
        image[y:y + 6 * s, :] = (120, 120, 120)
        draw_text(image, f"{number:06d}", 10 * s, 50 * s, 3 * s, (255, 255, 255))
        if key:
            draw_text(image, f"KEY {key}", 10 * s, self.height - 30 * s, 2 * s, (255, 255, 0))
        if touch is not None:
            x, y, pressed = touch
            if pressed:
                disc(image, x, y, 14 * s, (255, 255, 255))
            else:
                disc(image, x, y, 14 * s, (255, 255, 255), ring=3 * s)
        return image
