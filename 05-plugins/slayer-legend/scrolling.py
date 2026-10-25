"""Scroll areas: one way to scroll a list until an item is read, and to
tell its start and its end, for every screen whose scroll area
screen_registry.json's tree records (rect, direction, content, the
navigation.json move that scrolls it).

A swipe is the move's own (navigation.json, through ports.swipe and its
guard), slow (SWIPE_MS: a drag, never read as a tap on an item), forward
as the move says it or back the other way. After each swipe a fresh
capture: the end (or the start, going back) is two frames alike in the
area, nothing moved.

Features with their own scroll code, kept (each scrolls towards its
target from what it reads, which this blind helper cannot do, and each is
tested on a scripted game): stage_change (Select Region's stages,
stage_change_rules.plan), soul_weapon (the list, off its orange tags,
soul_weapon_rules.plan) and mine (the floor list, mine_rules.scroll_towards).
"""

SWIPE_MS = 900
SETTLE = 0.8
# Grey cells of the area compared between two frames, and how far a cell
# must change to count; under MOVED of the cells changed, nothing moved.
COLUMNS, ROWS = 16, 24
CHANGE = 45
MOVED = 0.04


def cells(shot, rect):
    """The area's downscaled grey grid."""
    width, height, pixels = shot
    left, top, right, bottom = rect
    grid = []
    for row in range(ROWS):
        y = min(height - 1, int((top + (bottom - top) * (row + 0.5) / ROWS) * height))
        for column in range(COLUMNS):
            x = min(width - 1, int((left + (right - left) * (column + 0.5) / COLUMNS) * width))
            i = (y * width + x) * 3
            grid.append(pixels[i] + pixels[i + 1] + pixels[i + 2])
    return grid


def moved(before, after, rect):
    """The share of the area's cells that changed from before to after."""
    a, b = cells(before, rect), cells(after, rect)
    return sum(1 for x, y in zip(a, b) if abs(x - y) > CHANGE) / len(a)


def swipe_of(move, back=False):
    """(start, end) of a swipe move, reversed going back."""
    x1, y1, x2, y2 = move["swipe"]
    return ((x2, y2), (x1, y1)) if back else ((x1, y1), (x2, y2))


async def scroll_until(ports, shot, screen, move, rect, found, most=40, back=False, seen_of=None):
    """Swipes screen's move over rect until found(shot) reads the item.
    Returns (shot, what found returned), or (shot, None) at the list's end
    (start, going back) or after most swipes. seen_of(shot): what the
    guard checks the swipe against (the Soul Weapon list's tags)."""
    start, end = swipe_of(move, back)
    for _ in range(most + 1):
        value = found(shot)
        if value:
            return shot, value
        seen = seen_of(shot) if seen_of else None
        await ports.swipe(shot, screen, move["id"], start, end, SWIPE_MS, verified=seen is not None, seen=seen)
        await ports.clock.sleep(SETTLE)
        after = await ports.capture(max_age=0)
        if not after:
            return shot, None
        if moved(shot, after, rect) < MOVED:
            return after, None
        shot = after
    return shot, None


async def to_start(ports, shot, screen, move, rect, most=40, seen_of=None):
    """Back to the list's start: swipes back until nothing moves."""
    shot, _ = await scroll_until(ports, shot, screen, move, rect, lambda shot: None, most, back=True, seen_of=seen_of)
    return shot
