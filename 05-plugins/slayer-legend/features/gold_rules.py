"""Gold per second: which readings of the gold counter count, and the rate
over the window. Pure: the window and a reading go in, the new window
comes out (nothing is changed in place).

The window is {samples: [(time, value)], pending, text, place, number,
odd}: samples are the values that count (a value counts once two readings
in a row agree, pending is the last reading), all on the same stage;
place is the battle screen's stage name line (its ink) where they were
read, number the stage number Power Saving Mode showed meanwhile, odd the
checks in a row somewhere else.
"""

# Readings every SECONDS; the slope over WINDOW; the readings stop IDLE
# seconds after the last page asked.
SECONDS = 10
WINDOW = 300
IDLE = 600


def empty():
    return {"samples": [], "pending": None, "text": None, "place": None, "number": None, "odd": 0}


def trimmed(samples, now):
    """The samples of the last WINDOW seconds."""
    kept = list(samples)
    while kept and now - kept[0][0] > WINDOW:
        kept.pop(0)
    return kept


def rate(samples, now):
    """(gold per second, the samples kept): the least-squares slope of the
    window's values (the counter moves by steps of its last digit), from
    the second value on (over what there is until the window is full: the
    page marks it as provisional); None without two values over some time."""
    samples = trimmed(samples, now)
    if len(samples) < 2 or samples[-1][0] - samples[0][0] <= 0:
        return None, samples
    n = len(samples)
    mean_t = sum(t for t, _ in samples) / n
    mean_v = sum(v for _, v in samples) / n
    spread = sum((t - mean_t) ** 2 for t, _ in samples)
    if not spread:
        return None, samples
    return max(0.0, sum((t - mean_t) * (v - mean_v) for t, v in samples) / spread), samples


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
    return {**window, "place": place, "number": None, "odd": 0, "pending": None, "samples": []}


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


def counted(window, reading, now):
    """A reading on the window's stage: its value counts when the reading
    before agreed; spending gold starts the samples again."""
    if window["pending"] == reading["value"]:
        samples = list(window["samples"])
        if samples and reading["value"] < samples[-1][1]:
            samples = []  # gold was spent
        samples.append((now, reading["value"]))
        window = {**window, "samples": trimmed(samples, now), "text": reading["text"]}
    return {**window, "pending": reading["value"]}
