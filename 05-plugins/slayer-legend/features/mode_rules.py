"""What the game is set to do, and when it goes back to the default. Pure.

The default mode (the user's « Mode par défaut »: "mpw18", farming a
stage with 18 monsters per wave, unless set to "mpw4" or "free") has no
timer; the others ("mpw4", "free": nothing is touched, "mine": the
Closed Mine) run until a time, then it goes back to it.
"""

MODES = ("mpw18", "mpw4", "free", "mine")
DEFAULT = "mpw18"
# What the default mode may be (never the mine: it ends by itself).
DEFAULTS = ("mpw18", "mpw4", "free")
# « retour … » once a timed mode ends, per default mode.
BACK_TO = {"mpw18": "retour au farming mpw18", "mpw4": "retour au farming mpw4", "free": "retour au jeu libre"}
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


STEP_NAMES = {"stage": "changement de stage", "preset": "préréglage", "auto": "AUTO",
              "soul_weapon": "Soul Weapon"}
# A farming mode's loadout fields whose change is applied at once.
LOADOUT_FIELDS = ("stage", "preset", "soul_weapon")


def loadout_changes(before, after):
    """The fields of LOADOUT_FIELDS that differ."""
    return {key for key in LOADOUT_FIELDS if (before or {}).get(key) != (after or {}).get(key)}


def switch_report(before, after, seconds, timings, waited=0.0, applied=False):
    """(log line, alert or None) of one mode switch: before → after in
    seconds of the plugin's own time (farm()'s run), timings {step:
    seconds} (farm()'s), waited: seconds waiting for the lease before it,
    said apart and never counted; the alert (French) when the plugin's
    time is over SWITCH_BUDGET, naming the slowest step. applied: the
    running mode's loadout changed (after: the mode), not a switch."""
    steps = ", ".join(f"{name} {round(value)} s" for name, value in timings.items())
    line = (f"loadout {after} changed → applied in {round(seconds)} s" if applied
            else f"switch {before}→{after} in {round(seconds)} s") + (f" ({steps})" if steps else "")
    if round(waited):
        line += f" (+{round(waited)} s waiting for the lease)"
    if seconds <= SWITCH_BUDGET:
        return line, None
    slowest = max(timings, key=timings.get) if timings else None
    why = (f" : étape la plus lente : {STEP_NAMES.get(slowest, slowest)} ({round(timings[slowest])} s)"
           if slowest else "")
    what = f"Configuration {after} appliquée" if applied else f"Passage {before} → {after}"
    return line, f"{what} en {round(seconds)} s (plus de {SWITCH_BUDGET} s){why}"


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


def request(body, stored=None, default=DEFAULT):
    """POST /mode's {mode, until, stage18, stage4, highest, floor, area}:
    ((mode, until, numbers, given), None) or (None, the error, in French:
    the page shows it). A number absent or null keeps its stored value
    (stored: the numbers as they are, e.g. after a gateway restart a
    browser that does not know one). given: whether the body has until (a
    null one clears the timer; an absent one keeps it, see timer_for). The
    default mode (default: the body's, else the one kept) has no timer."""
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
    if mode == (body.get("default") if body.get("default") in DEFAULTS else default):
        until = None
    return (mode, until, numbers, given), None


def default_request(body, numbers, current):
    """POST /mode's default (absent: current kept): (default, None) or
    (None, the error, in French). mpw4 only once its stage is chosen, as
    its radio button."""
    default = body.get("default") if isinstance(body, dict) else None
    if default is None:
        return current, None
    if default not in DEFAULTS:
        return None, f"default: one of {', '.join(DEFAULTS)}"
    if default == "mpw4" and not numbers.get("stage4"):
        return None, "Farming mpw4 : choisis d’abord son stage"
    return default, None


def timer_for(mode, until, given, current, current_until, now, default=DEFAULT):
    """The end of mode once POST /mode chose it: until when the body gave
    one (null: no time limit, e.g. the mine farming until stopped); else
    the timer running when the mode stays the same, or TIMED_MINUTES from
    now for a timed mode just chosen. The default mode has none."""
    if mode == default:
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
        return {"stopped": "mine done", "no_feather": "mine no feather",
                "entry_failed": "mine entry"}.get(mine["state"], "mine stopped")
    if until is not None and now >= until:
        return "timer"
    return None


def restored(mode, until, mine_enabled, now, default=DEFAULT):
    """(mode, until, ended) from state.json after a gateway restart: a
    timer that ended while the gateway was down ends its mode (ended), back
    to the default; so does the mine's mode when the mine is not farming
    any more."""
    ended = mode != default and until is not None and until <= now
    if ended:
        mode, until = default, None
    if mode == "mine" and not mine_enabled:
        mode, until = default, None
    if mode == default:
        until = None
    return mode, until, ended


def watched(mode, default):
    """The mode feature's watch runs: a timed mode (its end), or mpw4
    farming (its gold scroll looks), even as the default."""
    return mode != default or mode == "mpw4"


def retry_after(failures, elapsed):
    """Seconds before the next attempt of a switch that stopped failures
    times, elapsed seconds (its own, the lease's wait apart) after its
    trigger; None: no time left in SWITCH_BUDGET, it stays failed."""
    delay = min(RETRY_FIRST * 2 ** (failures - 1), RETRY_MOST)
    return delay if elapsed + delay < SWITCH_BUDGET else None


def ready_text(name, seconds, applied=False, alert=None):
    """The one notification once a farming mode is set up: the seconds
    since it was chosen (applied: since its loadout changed), the lease's
    wait included; alert: the over-budget one, after it."""
    text = (f"Configuration {name} appliquée en {round(seconds)} s" if applied
            else f"Farming {name} prêt en {round(seconds)} s")
    return f"{text} ; {alert}" if alert else text


REASONS = {"mine done": "Mine terminée", "mine stopped": "Mine arrêtée", "timer": "Minuteur écoulé",
           "mine no feather": "Mine fermée arrêtée : plus de plume",
           "mine entry": "Mine fermée arrêtée : {detail}"}


def back_text(why, default, stage=None, detail=""):
    """The one alert once a timed mode ends: why (due's), back to the
    default mode (its stage, if a farming one). The mine's own ends say
    « Mine fermée arrêtée : plus de plume, retour au farming mpw18 »."""
    reason = REASONS[why].format(detail=detail)
    back = BACK_TO[default] + (f" (stage {stage})" if stage else "")
    return f"{reason}, {back}" if why in ("mine no feather", "mine entry") else f"{reason} : {back}"
