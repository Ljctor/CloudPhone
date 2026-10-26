"""Gold per second, and the souls' per colour: which readings of a
counter count, and the rate over the window. Pure: the window and a
reading go in, the new window comes out (nothing is changed in place).

The window is {samples: [(time, value)], pending, text, step, offset,
place, number, odd}: samples are the values that count (a value counts
once two readings in a row agree, pending is the last reading), all on
the same stage; step is the last reading's resolution (one unit of its
last digit, gold.parse), offset what was spent and left out (souls);
place is the battle screen's stage name line (its ink) where they were
read, number the stage number Power Saving Mode showed meanwhile, odd the
checks in a row somewhere else.

The window's length follows the resolution read (window_for): WINDOW
while the counter is abbreviated (its last digit moves by coarse steps),
SHORT once it reads full digits.
"""

# Readings every SECONDS; the slope over WINDOW (SHORT in full digits);
# the readings stop IDLE seconds after the last page asked.
SECONDS = 10
WINDOW = 300
SHORT = 60
IDLE = 600
# The souls' counters move by one step of « 94.6C » every few minutes:
# their abbreviated window is longer.
SOULS_WINDOW = 1800


def empty():
    return {"samples": [], "pending": None, "text": None, "step": None, "offset": 0, "place": None,
            "number": None, "odd": 0}


def window_for(step, long=WINDOW):
    """Seconds of the window for a counter read at step (one unit of its
    last digit, None: not read yet): SHORT in full digits, else long."""
    return SHORT if step is not None and step <= 1 else long


def trimmed(samples, now, seconds=WINDOW):
    """The samples of the last seconds."""
    kept = list(samples)
    while kept and now - kept[0][0] > seconds:
        kept.pop(0)
    return kept


def rate(samples, now, seconds=WINDOW):
    """(per second, the samples kept): the least-squares slope of the
    window's values (the counter moves by steps of its last digit), from
    the second value on (over what there is until the window is full: the
    page marks it as provisional); None without two values over some time."""
    samples = trimmed(samples, now, seconds)
    if len(samples) < 2 or samples[-1][0] - samples[0][0] <= 0:
        return None, samples
    n = len(samples)
    mean_t = sum(t for t, _ in samples) / n
    origin = samples[0][1]
    relative = [v - origin for _, v in samples]
    mean_v = sum(relative) / n
    spread = sum((t - mean_t) ** 2 for t, _ in samples)
    if not spread:
        return None, samples
    return max(0.0, sum((t - mean_t) * (v - mean_v) for (t, _), v in zip(samples, relative)) / spread), samples


def same_place(a, b):
    """Two inks of the battle screen's stage name line are the same stage (a
    few pixels differ with what moves behind it)."""
    if len(a) != len(b) or len(a[0]) != len(b[0]):
        return False
    differ = sum(x != y for row_a, row_b in zip(a, b) for x, y in zip(row_a, row_b))
    ink = max(1, sum(map(sum, a)), sum(map(sum, b)))
    return differ / ink < 0.2


def restarted(window, place=None):
    """The window starts again, at place if known."""
    return {**window, "place": place, "number": None, "odd": 0, "pending": None, "samples": [], "offset": 0}


def elsewhere(window, place=None):
    """Not on the window's stage, or not known where: twice in a row (an
    effect can hide the stage name for a moment), the window starts again
    (at place if known)."""
    window = {**window, "odd": window["odd"] + 1}
    return restarted(window, place) if window["odd"] >= 2 else window


def where(window, kind, here):
    """Follows where the game is at a reading: ("saver", stage number) or
    ("battle", ink of the stage name line). (window, counts): counts when
    the reading was on the window's stage (its gold may be counted)."""
    if kind == "saver":
        # Power Saving Mode farms the same stage and writes its number.
        number = here
        if number is None:
            return elsewhere(window), False
        if window["number"] is None and window["place"] is not None and window["odd"] == 0:
            return {**window, "number": number}, False
        if number != window["number"]:
            return elsewhere(window), False
        return {**window, "odd": 0}, False
    if here is None:
        return elsewhere(window), False
    if window["place"] is None:
        return restarted(window, here), True
    if same_place(here, window["place"]):
        return {**window, "odd": 0}, True
    return elsewhere(window, here), False


def counted(window, reading, now, long=WINDOW, spent="restart"):
    """A reading on the window's stage: its value counts when the reading
    before agreed. A drop is spending: "restart" starts the samples again
    (gold), "skip" leaves it out (souls: the samples go on from the last
    value, the drop kept in offset). long: the abbreviated window
    (window_for)."""
    if window["pending"] == reading["value"]:
        samples = list(window["samples"])
        offset = window.get("offset", 0)
        value = reading["value"] + offset
        if samples and value < samples[-1][1]:
            if spent == "skip":
                offset += samples[-1][1] - value
                value = samples[-1][1]
            else:
                samples, offset, value = [], 0, reading["value"]
        samples.append((now, value))
        step = reading.get("step")
        window = {**window, "samples": trimmed(samples, now, window_for(step, long)), "text": reading["text"],
                  "step": step, "offset": offset}
    return {**window, "pending": reading["value"]}
