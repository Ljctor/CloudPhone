"""What the game is set to do, and when it goes back to the default. Pure.

"mpw18" (farming a stage with 18 monsters per wave) is the default; the
others ("mpw4", "free": nothing is touched, "mine": the Closed Mine) run
until a time, then it goes back to it.
"""

MODES = ("mpw18", "mpw4", "free", "mine")
DEFAULT = "mpw18"
# Seconds between two checks of a timed mode.
WATCH_EVERY = 10


def request(body):
    """POST /mode's {mode, until, stage18, stage4, highest, floor, area}:
    ((mode, until, numbers), None) or (None, the error). The default mode
    has no timer."""
    try:
        mode = body.get("mode") or DEFAULT
        until = float(body["until"]) if body.get("until") is not None else None
        numbers = {key: int(body.get(key) or 0) or None for key in ("stage18", "stage4", "highest", "floor", "area")}
    except (ValueError, TypeError, AttributeError):
        return None, "Expected {mode, until, stage18, stage4, highest, floor, area}"
    if mode not in MODES:
        return None, f"mode: one of {', '.join(MODES)}"
    if mode == "mine" and not (numbers["floor"] and 1 <= numbers["floor"] <= 9999
                               and numbers["area"] and 1 <= numbers["area"] <= 5):
        return None, "The mine needs floor 1-9999 and area 1-5"
    if mode == DEFAULT:
        until = None
    return (mode, until, numbers), None


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
