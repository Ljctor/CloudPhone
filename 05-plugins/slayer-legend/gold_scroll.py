"""The gold scroll buff, off a screenshot (width, height, RGB bytes), and
when its absence counts. Pure. The one owner of both: the Closed Mine
(mine.py's reader and features/mine_rules.py) and mpw4 farming
(features/mode.py) use them.

shown(shot) only means something on a fight screen (the mine's fight, the
battle screen): pop-ups, panels, the floor list and Power Saving Mode
cover the buffs. seen(fight, shot) says so: None (unknown) elsewhere.

The warning record, {gold, misses, warned}: the scroll as last told (None
unknown, True, False once missing), the fight looks in a row without it,
and whether its absence was told (one alert per absence).
"""

# The buff icons under the avatar, top left, on the mine's fight and on the
# battle screen; the gold scroll has bright gold pixels (#ffbb33), which
# the other buffs (purple scroll, potion) do not. Fractions of the screen,
# measured at 480x1040 on the mine's fight.
BUFFS = (0.017, 0.054, 0.29, 0.079)
# Fight looks in a row without the scroll before it counts as missing (an
# animation can hide it for a moment).
LOOKS = 2


def _gold(r, g, b):
    return r > 230 and 150 < g < 215 and b < 90


def shown(shot):
    """The gold scroll buff's icon is shown."""
    width, height, pixels = shot
    x0, y0 = int(BUFFS[0] * width), int(BUFFS[1] * height)
    x1, y1 = int(BUFFS[2] * width), int(BUFFS[3] * height)
    hits = total = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * width + x) * 3
            hits += _gold(pixels[i], pixels[i + 1], pixels[i + 2])
            total += 1
    return bool(total) and hits / total > 0.005


def seen(fight, shot):
    """What one look tells: True or False on a fight screen, None elsewhere."""
    return shown(shot) if fight else None


def fresh():
    return {"gold": None, "misses": 0, "warned": False}


def look(record, seen, looks=LOOKS):
    """(record, news) after one look that saw seen (True, False or None).
    news: "gone" the first time the scroll is missing for looks fight looks
    in a row (alert), "back" when it is seen again after that, else None.
    Until then a miss keeps the scroll as last told; an unknown look
    changes nothing but gold (None)."""
    record = dict(record)
    if seen is None:
        record["gold"] = None
        return record, None
    if seen:
        news = "back" if record["warned"] else None
        record.update(gold=True, misses=0, warned=False)
        return record, news
    record["misses"] += 1
    if record["misses"] < looks:
        return record, None
    news = None if record["warned"] else "gone"
    record.update(gold=False, warned=True)
    return record, news
