"""What the game is set to do, and when it goes back to the default. Pure.

"mpw18" (farming a stage with 18 monsters per wave) is the default; the
others ("mpw4", "free": nothing is touched, "mine": the Closed Mine) run
until a time, then it goes back to it.
"""

MODES = ("mpw18", "mpw4", "free", "mine")
DEFAULT = "mpw18"
# A timed mode chosen without an end time runs this long.
TIMED_MINUTES = 30
# Seconds between two checks of a timed mode.
WATCH_EVERY = 10
# A mode switch (the trigger: POST /mode, or a timer's end) reaches the
# battle screen on its stage, preset and AUTO within this (seconds) of the
# plugin's own time: waiting for the lease (the user's minute after an
# input, another holder) is logged apart and never counted. Over it, the
# switch still completes, logged with one alert naming the slowest step.
SWITCH_BUDGET = 60
# While the lease cannot be had (the user played in the last minute,
# another holder), the switch tries again this often (seconds).
BUSY_RETRY = 2
# A stage change waits for the shared lease this long at most (seconds).
LEASE_WAIT = 30 * 60
# A switch that stopped (a screen passing by, a step missed) is tried
# again after 2, 4, 8 then every 16 seconds, while within SWITCH_BUDGET of
# its trigger; then one alert.
RETRY_FIRST, RETRY_MOST = 2, 16
# mpw4 farming: seconds between two looks for the gold scroll (on the
# battle screen, gold_scroll.py), with a screenshot at most WATCH_EVERY old.
GOLD_EVERY = 30
# Free play: one phone alert this long (seconds) before its end, so that a
# user still playing can extend it.
WARN_BEFORE = 2 * 60
WARNING = "Le Cloud Phone reprend la main dans 2 min, prolonge le jeu libre si tu joues encore"


def next_look(until, now):
    """Seconds to the timed mode's next look: WATCH_EVERY, or less so as
    to wake right at the timer's end (until, Unix time; None: no limit)."""
    if until is None or until - now > WATCH_EVERY:
        return WATCH_EVERY
    return max(0.2, until - now + 0.1)


STEP_NAMES = {"stage": "changement de stage", "preset": "préréglage", "auto": "AUTO"}


def switch_report(before, after, seconds, timings, waited=0.0):
    """(log line, alert or None) of one mode switch: before → after in
    seconds of the plugin's own time (farm()'s run), timings {step:
    seconds} (farm()'s), waited: seconds waiting for the lease before it,
    said apart and never counted; the alert (French) when the plugin's
    time is over SWITCH_BUDGET, naming the slowest step."""
    steps = ", ".join(f"{name} {round(value)} s" for name, value in timings.items())
    line = f"switch {before}→{after} in {round(seconds)} s" + (f" ({steps})" if steps else "")
    if round(waited):
        line += f" (+{round(waited)} s waiting for the lease)"
    if seconds <= SWITCH_BUDGET:
        return line, None
    slowest = max(timings, key=timings.get) if timings else None
    why = (f" : étape la plus lente : {STEP_NAMES.get(slowest, slowest)} ({round(timings[slowest])} s)"
           if slowest else "")
    return line, f"Passage {before} → {after} en {round(seconds)} s (plus de {SWITCH_BUDGET} s){why}"


def warn_due(mode, until, warned, now):
    """Free play says WARNING now: its end is at most WARN_BEFORE away and
    this end was not warned of yet (warned: the until last warned of, so
    that a timer moved later warns again near its new end)."""
    return mode == "free" and until is not None and until != warned and 0 < until - now <= WARN_BEFORE


def gold_due(last, now):
    """mpw4 farming looks for the gold scroll now: last is the monotonic
    time of its last look (None: none yet)."""
    return last is None or now - last >= GOLD_EVERY


NUMBERS = ("stage18", "stage4", "highest", "floor", "area")


def request(body, stored=None):
    """POST /mode's {mode, until, stage18, stage4, highest, floor, area}:
    ((mode, until, numbers, given), None) or (None, the error, in French:
    the page shows it). A number absent or null keeps its stored value
    (stored: the numbers as they are, e.g. after a gateway restart a
    browser that does not know one). given: whether the body has until (a
    null one clears the timer; an absent one keeps it, see timer_for). The
    default mode has no timer."""
    try:
        mode = body.get("mode") or DEFAULT
        given = "until" in body
        until = float(body["until"]) if body.get("until") is not None else None
        numbers = {key: int(body.get(key) or 0) or None for key in NUMBERS}
    except (ValueError, TypeError, AttributeError):
        return None, "Expected {mode, until, stage18, stage4, highest, floor, area}"
    if mode not in MODES:
        return None, f"mode: one of {', '.join(MODES)}"
    numbers = {key: value if value is not None else (stored or {}).get(key) for key, value in numbers.items()}
    # A mode is chosen only once configured (the page greys it out until then).
    if mode == "mpw4" and not numbers["stage4"]:
        return None, "Farming mpw4 : choisis d’abord son stage"
    if mode == "mine" and not (numbers["floor"] and 1 <= numbers["floor"] <= 9999
                               and numbers["area"] and 1 <= numbers["area"] <= 5):
        return None, "Mine fermée : choisis d’abord l’étage (1 à 9999) et la zone (1 à 5)"
    if mode == DEFAULT:
        until = None
    return (mode, until, numbers, given), None


def timer_for(mode, until, given, current, current_until, now):
    """The end of mode once POST /mode chose it: until when the body gave
    one (null: no time limit, e.g. the mine farming until stopped); else
    the timer running when the mode stays the same, or TIMED_MINUTES from
    now for a timed mode just chosen. The default mode has none."""
    if mode == DEFAULT:
        return None
    if given:
        return until
    if mode == current:
        return current_until
    return now + TIMED_MINUTES * 60


def entered(mode, stage18, stage4):
    """What changing to mode does: ("stage", number, mpw) brings the game
    to farming that stage, ("choose", mpw) asks the user to choose one,
    ("free",) touches nothing until the timer ends, ("mine",) farms the
    mine."""
    if mode == "mpw18":
        return ("stage", stage18, 18) if stage18 else ("choose", 18)
    if mode == "mpw4":
        return ("stage", stage4, 4) if stage4 else ("choose", 4)
    return (mode,)


def due(mode, until, mine, now):
    """Why a timed mode ends now, or None: "mine done" (its last entry
    ended), "mine stopped" (another reason), "timer" (its time is up). mine:
    the mine's state {enabled, state}."""
    if mode == "mine":
        if mine["enabled"]:
            return None
        return "mine done" if mine["state"] == "stopped" else "mine stopped"
    if until is not None and now >= until:
        return "timer"
    return None


def restored(mode, until, mine_enabled, now):
    """(mode, until, ended) from state.json after a gateway restart: a
    timer that ended while the gateway was down ends its mode (ended), back
    to the default; so does the mine's mode when the mine is not farming
    any more."""
    ended = mode != DEFAULT and until is not None and until <= now
    if ended:
        mode, until = DEFAULT, None
    if mode == "mine" and not mine_enabled:
        mode, until = DEFAULT, None
    return mode, until, ended


def retry_after(failures, elapsed):
    """Seconds before the next attempt of a switch that stopped failures
    times, elapsed seconds (its own, the lease's wait apart) after its
    trigger; None: no time left in SWITCH_BUDGET, it stays failed."""
    delay = min(RETRY_FIRST * 2 ** (failures - 1), RETRY_MOST)
    return delay if elapsed + delay < SWITCH_BUDGET else None
