"""What the game is set to do, and when it goes back to the default. Pure.

The default mode (the user's « Mode par défaut »: "mpw18", farming a
stage with 18 monsters per wave, unless set to "mpw4" or "free") has no
timer; the others ("mpw4", "free": nothing is touched, "mine": the
Closed Mine) run until a time, then it goes back to it.

The State row's texts are status texts ({template, params}, t(): French
templates the page translates, features/texts.py); the phone alerts and
the log are English.
"""


def t(template, **params):
    """A status text (features/texts.py)."""
    return {"template": template, "params": params}


MODES = ("mpw18", "mpw4", "free", "agent", "mine")
DEFAULT = "mpw18"
# What the default mode may be (never the mine: it ends by itself).
DEFAULTS = ("mpw18", "mpw4", "free", "agent")
# "back to ..." once a timed mode ends, per default mode (its alert).
BACK_TO = {"mpw18": "back to farming mpw18", "mpw4": "back to farming mpw4",
           "free": "back to free play", "agent": "back to agent mode"}
# A timed mode chosen without an end time runs this long.
TIMED_MINUTES = 30
# Seconds between two checks of a timed mode.
WATCH_EVERY = 10
# A mode switch (the trigger: POST /mode, or a timer's end) reaches the
# battle screen on its stage and preset within this (seconds) of the
# plugin's own time: waiting for the lease (the user's 5 s after an
# input, another holder) is logged apart and never counted. Over it, the
# switch still completes, logged with one alert naming the slowest step.
SWITCH_BUDGET = 60
# While the lease cannot be had (the user played in the last 5 s,
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
WARNING = "The Cloud Phone takes over in 2 min: extend free play if you are still playing"


def next_look(until, now):
    """Seconds to the timed mode's next look: WATCH_EVERY, or less so as
    to wake right at the timer's end (until, Unix time; None: no limit)."""
    if until is None or until - now > WATCH_EVERY:
        return WATCH_EVERY
    return max(0.2, until - now + 0.1)


STEP_NAMES = {"stage": "stage change", "preset": "preset", "soul_weapon": "Soul Weapon",
              "park": "parking on Soul Weapon"}
# A farming mode's loadout fields whose change is applied at once.
LOADOUT_FIELDS = ("stage", "preset", "soul_weapon")


def loadout_changes(before, after):
    """The fields of LOADOUT_FIELDS that differ."""
    return {key for key in LOADOUT_FIELDS if (before or {}).get(key) != (after or {}).get(key)}


def switch_report(before, after, seconds, timings, waited=0.0, applied=False):
    """(log line, alert or None) of one mode switch: before → after in
    seconds of the plugin's own time (farm()'s run), timings {step:
    seconds} (farm()'s), waited: seconds waiting for the lease before it,
    said apart and never counted; the alert (English) when the plugin's
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
    why = (f": slowest step: {STEP_NAMES.get(slowest, slowest)} ({round(timings[slowest])} s)"
           if slowest else "")
    what = f"Loadout {after} applied" if applied else f"Switch {before} → {after}"
    return line, f"{what} in {round(seconds)} s (over {SWITCH_BUDGET} s){why}"


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
    ((mode, until, numbers, given), None) or (None, the error, a status
    text: the page shows it). A number absent or null keeps its stored value
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
        return None, t("Attendu : {expected}", expected="{mode, until, stage18, stage4, highest, floor, area}")
    if mode not in MODES:
        return None, t("{field} : un de {choices}", field="mode", choices=", ".join(MODES))
    numbers = {key: value if value is not None else (stored or {}).get(key) for key, value in numbers.items()}
    # A mode is chosen only once configured (the page greys it out until then).
    if mode == "mpw4" and not numbers["stage4"]:
        return None, t("Farming mpw4 : choisis d’abord son stage")
    if mode == "mine" and not (numbers["floor"] and 1 <= numbers["floor"] <= 9999
                               and numbers["area"] and 1 <= numbers["area"] <= 5):
        return None, t("Mine fermée : choisis d’abord l’étage (1 à 9999) et la zone (1 à 5)")
    if mode == (body.get("default") if body.get("default") in DEFAULTS else default):
        until = None
    return (mode, until, numbers, given), None


def default_request(body, numbers, current):
    """POST /mode's default (absent: current kept): (default, None) or
    (None, the error, a status text). mpw4 only once its stage is chosen, as
    its radio button."""
    default = body.get("default") if isinstance(body, dict) else None
    if default is None:
        return current, None
    if default not in DEFAULTS:
        return None, t("{field} : un de {choices}", field="default", choices=", ".join(DEFAULTS))
    if default == "mpw4" and not numbers.get("stage4"):
        return None, t("Farming mpw4 : choisis d’abord son stage")
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


def ready_text(name, seconds, applied=False, alert=None, held=0.0):
    """The one notification once a farming mode is set up: the seconds
    since it was chosen (applied: since its loadout changed), the lease's
    wait included; held: the part of it on hold while the user played,
    said apart; alert: the over-budget one, after it."""
    text = (f"Loadout {name} applied in {round(seconds)} s" if applied
            else f"Farming {name} ready in {round(seconds)} s")
    if round(held):
        text += f" (including {round(held)} s waiting: you were playing)"
    return f"{text}; {alert}" if alert else text


# The lease's refusal while the user played in the last 5 s (ports.Lease):
# the switch is on hold, said once, with a choice.
USER_PLAYING = "l’utilisateur joue"
HOLD_ACTIONS = ("free", "resume")
# The hold alert's buttons: their one-time token works this long at most
# (seconds), and not after the hold.
HOLD_TOKEN_SECONDS = 10 * 60
HOLD_BUTTONS = (("Switch to free play", "free"), ("Resume now", "resume"))


def hold_buttons(hold_id, token):
    """The hold alert's two buttons (ports.notify's actions), each posting
    its answer to POST /mode/hold with the hold's one-time token; none
    without a token (an older gateway)."""
    if not token:
        return None
    return [{"label": label, "path": "/mode/hold", "body": {"action": action, "hold": hold_id}, "token": token}
            for label, action in HOLD_BUTTONS]


def hold_alert(name, left, applied=False):
    """The one alert when a switch is put on hold because the user plays:
    left, the seconds before its next try."""
    what = f"Loadout {name}" if applied else f"Switch to farming {name}"
    return f"{what} on hold: you are playing. Next try in {max(1, round(left))} s."


def hold_message(name, left, applied=False):
    """The État row's text while on hold (a status text): « Passage au
    farming mpw18 », or « Configuration mpw18 » (applied), en attente."""
    what = t("Configuration {name}", name=name) if applied else t("Passage au farming {name}", name=name)
    return t("{what} en attente : tu joues · nouvel essai dans {seconds} s", what=what, seconds=max(1, round(left)))


def hold_request(body, hold, last):
    """POST /mode/hold {action: "free" | "resume"[, hold: id]}: (action,
    None) to do it, ("again", None) when it was already done for that hold
    (idempotent: nothing more to do), or (None, (status, error, a status
    text)): 400 a bad
    body, 409 nothing on hold (or another hold than the one named). hold:
    the hold now ({id, action}) or None; last: the hold that ended last
    ({id, action}) or None."""
    action = body.get("action") if isinstance(body, dict) else None
    if action not in HOLD_ACTIONS:
        return None, (400, t("Attendu : {expected}", expected='{action: "free" | "resume"}'))
    named = body.get("hold")
    if hold and (named is None or named == hold["id"]):
        return ("again" if hold.get("action") == action else action), None
    if last and last.get("action") == action and (named is None or named == last["id"]):
        return "again", None
    return None, (409, t("Aucun passage de mode en attente"))


REASONS = {"mine done": "Mine done", "mine stopped": "Mine stopped", "timer": "Timer ended",
           "mine no feather": "Closed Mine stopped: no feather left",
           "mine entry": "Closed Mine stopped: {detail}"}


def back_text(why, default, stage=None, detail=""):
    """The one alert once a timed mode ends: why (due's), back to the
    default mode (its stage, if a farming one); detail: the mine's message,
    in English. The mine's own ends say "Closed Mine stopped: no feather
    left, back to farming mpw18"."""
    reason = REASONS[why].replace("{detail}", detail)
    back = BACK_TO[default] + (f" (stage {stage})" if stage else "")
    return f"{reason}, {back}" if why in ("mine no feather", "mine entry") else f"{reason}: {back}"


# The colour of the mode's lines on the overlay (GET /mode's tone): "ok"
# (white mode name) while the mode runs and the watchdog sees nothing
# wrong, "hold" (blue) while the plugin holds its taps because the user
# plays (an input in the last 5 s with the game in front, ports.Lease),
# "setup" (orange) while returning to the instruction, "error" (red) when blocked.
TONES = ("ok", "hold", "setup", "error")
# The mode's states (features/mode.py) and the mine's (features/mine.py)
# that are an error, or a setup under way.
ERROR_STATES = ("failed", "blocked")
SETUP_STATES = ("moving", "waiting", "relaunching", "stopping")


def tone(mode, state, hold, playing, watched=None, mine=None, engraving_off=False):
    """The overlay's tone (TONES), from: mode, the selected mode's name;
    state, its state; hold, a switch on hold while the user plays; playing,
    the plugin holds its taps now because of the user's last input; watched, the
    watchdog's last look at this mode ({level: None, "warning" or
    "error"}) or None; mine, the mine's state while the mine is the mode;
    engraving_off, the farming mode's loadout asks an engraving while the
    engraving's switch is off. User input first, then an active repair,
    then a confirmed block, and finally recovery or the reached instruction."""
    watched = watched or {}
    level = watched.get("level")
    if playing:
        return "hold"
    if hold:
        return "setup"
    if watched.get("repairing"):
        return "setup"
    if state in ERROR_STATES or mine in ERROR_STATES or watched.get("blocked") is True:
        return "error"
    if state in SETUP_STATES or (mine in SETUP_STATES and mode == "mine") or level or engraving_off:
        return "setup"
    return "ok"
