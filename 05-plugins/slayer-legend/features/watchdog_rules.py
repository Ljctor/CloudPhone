"""What the watchdog makes of each look at the game. Pure: what a look
saw, the selected mode's profile (its stage and loadout, see profile()),
what the watchdog remembers and the time go in; the symptom, the status
and the actions (records and alerts, a repair or its plan) come out. The
feature (watchdog.py beside this file) takes the looks and makes the
repairs, every move through the navigation guard, under the shared lease.

The watchdog checks that the game does what the selected mode says:
mpw18 and mpw4 farming, each with its own stage, Battle settings preset
and AUTO (the same symptoms and repairs); the Closed Mine, whose screens
are the mine feature's: the watchdog only owns its "game away" alert
(mine_away: the game gone, crashed or not in front for MINE_AWAY_LOOKS
looks, one alert, no repair). Free play suspends it, and so does a mode's
entry (paused(..., moving): the entry's sequence holds the lease). Every
text names the mode (MODE_NAMES). When a mode ends, the watchdog looks at
once, with no menu grace (still paused for a minute after a user input).
During free play the game may well be open on another device: nothing is
checked then. When it ends, the game here may show a "connected on another device"
screen or a choice of saves, whose layouts are not mapped yet: for
AFTER_MODE seconds after a mode ended, another screen is that
(after_mode_screen), alerted after ALERT_AFTER looks, for the user to do by
hand. The save notice and the title are start screens: the relaunch's
launch steps take the latest save.

Symptom → response, one look at a time (SYMPTOMS, REPAIRS):

| Symptom                                   | Response                              |
|-------------------------------------------|---------------------------------------|
| adb missing (the emulator or adb gone)    | error alert, no repair (part 03)      |
| Android's "isn't responding" dialog       | "Wait" once (the feature), then an    |
|                                           | alert; never "Close app" (a kill)     |
| game not running, not in front, a crash   | relaunch (phase 1b)                   |
| dialog, its title or save notice          |                                       |
| the sign-in screen (after a relaunch)     | relaunch: "Sign in with Google" once, |
|                                           | the chooser's one account (launch)    |
| a game menu 60 s with no user input       | back to battle, no relaunch           |
| battle on another stage than the profile's| stage change (phase 2)                |
| Power Saving Mode                         | well; the stage is unread there: only |
|                                           | a battle look can say "wrong stage"   |
| wrong Battle settings preset              | select the preset (phase 3)           |
| (mpw18's loadout, the engraving's store)  |                                       |
| AUTO read off (a still gear, on the       | AUTO on (stage_change.ensure_auto)    |
| controls' check)                          |                                       |
| wrong soul weapon or engraving            | loadout (phase 3)                     |
| another screen (a stage transition, a     | no tap: observed, an alert after      |
| loading screen, an unknown pop-up)        | ALERT_AFTER_OTHER looks               |
| another screen within AFTER_MODE of a     | no tap (TODO: map the disconnect      |
| mode's end (another device, saves)        | screen and the save choice): an alert |
|                                           | after ALERT_AFTER looks               |

The aim: after any disruption, the mode's farming is back within a minute. A
look every EVERY seconds; a user who plays (an input in the last
PAUSE_AFTER_INPUT seconds) is not a disruption.

Repairs apply only to what is recognised: the process, the focus, an
Android crash window, the title, sign-in and save screens, a game menu, the battle
screen (Power Saving Mode needs none).

- A symptom ALERT_AFTER looks in a row (ALERT_AFTER_OTHER for another
  screen) is one warning alert (an error one for adb), never repeated
  until the game has been well RECOVERED_AFTER looks in a row, or
  RECOVERY_FLOOR seconds when a repair was made since the problem began;
  then one normal "rétabli". A new alert of the same family (its repair,
  or the symptom without one) within QUIET_AFTER_ALERT of the last one
  notified is a warning record without phone alert, and no « rétabli »
  follows it; the backoff's escalations are always notified. A game menu inside its grace, or a look with no
  capture, changes nothing.
- A repair needs its symptom REPAIR_AFTER looks in a row (the same look
  as the alert), the repair learned (available) and, at the gateway's
  start, OBSERVE_FIRST looks seen first: a restored state never resumes a
  repair. One repair at a time; the next look verifies it. One that did
  not take is followed by a passive watch of WATCH_AFTER_FAILURE (looks
  and alerts, no repair of that kind), as the mine's stop pass is.
- Each kind of repair backs off on its own, and never stops for good:
  after its nth failure, no attempt of that kind for DELAYS[n] (1, 2, 4,
  8, 16 minutes, then 30 at most, each ±JITTER). Only a real failure
  counts: the repair ran and the next look still sees its symptom
  (failed), or its sequence stopped (stopped); a repair that worked is
  never one, even when its symptom comes back; a deferral (the lease, a
  user input) or a plan does not count either (not_run). The backoff of a kind starts
  over after a durable recovery: good looks for at least the last delay
  used, RECOVERY_FLOOR at least; a user input keeps it; the page's
  « Réessayer maintenant » clears it (retry). Its alerts: the first
  failure, the delay first reaching 8 minutes, then 30 (ESCALATE), then
  silence until « rétabli ». The next attempt's time is kept across
  gateway restarts (persisted()).
- The relaunch and the way back to battle always tap for real. The stage
  change, the preset and the loadout can be plan-only (until their screens
  are mapped and the user approves them): then the plan is said once per
  symptom.
- While another holder has the lease, the repair is deferred, said at
  normal level once per holder ("réparation différée : bail tenu par X").

The stage check reads the stage's name whole (region and numeral,
stage_select.py) when the stage change feature is there; else only the
numeral ending it, so that another region's stage with the same numeral
passes, and the status says "OK (numéral III)".

Texts are French templates with their parameters ({stage}, {holder}...),
for the page to translate (tr).
"""

# Seconds between two looks; a capture this old is new enough.
EVERY = 15
MAX_AGE = 10
# A user input (touch, key) pauses the watchdog this long (seconds).
PAUSE_AFTER_INPUT = 60
# A game menu open this long (seconds) with no user input is a symptom.
MENU_GRACE = 60
ALERT_AFTER = 2
# Good looks in a row (battle or Power Saving Mode) before "rétabli".
RECOVERED_AFTER = 4
# Another screen may be a stage transition or a loading screen: 60 s.
ALERT_AFTER_OTHER = 4
# After a mode ended (free play, another device), seconds during which
# another screen is the disconnect screen or the save choice.
AFTER_MODE = 5 * 60
REPAIR_AFTER = 2
# Looks in a row with another app in front before it is "away" (a passing
# window, the focus said wrong once, is not).
AWAY_AFTER = 2
# Google's windows in front are the sign-in path, not another app.
GMS = "com.google.android.gms"
# The modes the watchdog checks, by the name its texts give them.
MODE_NAMES = {"mpw18": "Farming mpw18", "mpw4": "Farming mpw4", "mine": "Mine fermée"}
# The mine: the game gone or away this many looks (2 minutes) is its alert.
MINE_AWAY_LOOKS = 8
# Looks seen at the gateway's start before any repair.
OBSERVE_FIRST = 2
# After a repair that did not take: no repair of that kind this long.
WATCH_AFTER_FAILURE = 2 * 60
HOUR = 3600

SYMPTOMS = {
    "adb_missing": "adb ne répond pas : l’émulateur ou adb manque",
    "not_running": "le jeu ne tourne pas",
    "away": "une autre application est au premier plan : {window}",
    "crash": "le jeu a planté (fenêtre d’erreur d’Android)",
    "anr": "le jeu ne répond pas (fenêtre d’Android), « Attendre » sans effet : à faire à la main",
    "start_screen": "le jeu est revenu à son écran titre",
    "sign_in": "le jeu demande de se reconnecter (Sign in with Google)",
    "after_mode_screen": "écran inconnu après la fin du mode (connecté sur un autre appareil ? choix de "
                         "sauvegarde ?) : à faire à la main",
    "menu": "un menu du jeu est ouvert depuis plus d’une minute sans l’utilisateur",
    "wrong_stage": "mauvais stage, pas le {stage}",
    "wrong_battle_settings": "mauvais préréglage de combat : pas le {preset}",
    "wrong_loadout": "mauvais équipement : {what}",
    "auto_off": "AUTO est arrêté",
    "unexpected": "écran inattendu",
    "mine_away": "le jeu n’est plus au premier plan (plantage ?)",
}
# The repair of each symptom (None: alert only).
REPAIRS = {
    "adb_missing": None,
    "not_running": "relaunch",
    "away": "relaunch",
    "crash": "relaunch",
    "anr": None,
    "start_screen": "relaunch",
    # The relaunch signs in with Google, once per relaunch (launch_rules).
    "sign_in": "relaunch",
    "after_mode_screen": None,
    "menu": "back_to_battle",
    "wrong_stage": "stage_change",
    "wrong_battle_settings": "select_preset",
    "wrong_loadout": "loadout",
    "auto_off": "auto_on",
    "unexpected": None,
    # The relaunch, then the mine's own way back in (features/mine.py reenter).
    "mine_away": "mine_relaunch",
}
REPAIR_NAMES = {"relaunch": "relance du jeu", "mine_relaunch": "relance du jeu et retour dans la mine",
                "back_to_battle": "retour au combat",
                "stage_change": "changement de stage", "select_preset": "choix du préréglage de combat",
                "loadout": "rééquipement", "auto_on": "remise en marche d’AUTO"}
# Seconds without attempt of a kind after its nth failure (DELAYS[n],
# the last one for any later), each ±JITTER of it.
DELAYS = (0, 60, 120, 240, 480, 960, 1800)
JITTER = 0.1
# A durable recovery: good looks for the last delay used, this long at least.
RECOVERY_FLOOR = 5 * 60
# Seconds after a notified alert during which another of its family is not.
QUIET_AFTER_ALERT = 30 * 60
# Delays (seconds) whose first reach is a phone alert.
ESCALATE = (480, 1800)
KINDS = tuple(REPAIR_NAMES)
ERRORS = ("adb_missing",)
# Repairs that are never plan-only.
ALWAYS_REAL = ("relaunch", "mine_relaunch", "back_to_battle")


def kept_backoff(saved):
    """The backoff kept in state.json, checked: {kind: {failures, next
    (Unix time of the next attempt allowed), delay (the last one, seconds),
    said (the ESCALATE delays alerted)}}."""
    kept = {}
    for kind, state in (saved if isinstance(saved, dict) else {}).items():
        try:
            if kind in KINDS:
                kept[kind] = {"failures": int(state["failures"]), "next": float(state["next"]),
                              "delay": float(state["delay"]),
                              "said": [int(d) for d in state.get("said", []) if d in ESCALATE]}
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return kept


def fresh(kept=None):
    """What the watchdog remembers when it starts (kept: persisted() of
    the last run, from state.json), or when a mode suspended it."""
    kept = kept or {}
    return {"looks": 0, "streak": 0, "since_repair": 0, "good": 0, "symptom": None, "alerted": False,
            "alerts": 0, "backoff": kept_backoff(kept.get("backoff")), "good_since": None, "watch": {},
            "repaired": False, "notified": {}, "alert_notified": False,
            "verifying": None, "menu_since": None, "planned": None, "deferred": None,
            "away": 0}


def persisted(memory):
    """What a gateway restart keeps: each kind's backoff."""
    return {"backoff": {kind: {**state, "said": list(state["said"])} for kind, state in memory["backoff"].items()}}


def suspended(memory):
    """A mode suspended the watchdog: it starts over, with its backoff."""
    return {**fresh(persisted(memory)), "looks": memory["looks"]}


def paused(mode, last_input, now, moving=False):
    """Why the watchdog does not look now (a template, its parameter
    {mode} the mode's MODE_NAMES name), or None. mode: the mode's name;
    last_input: monotonic time of the last user input, or None; moving:
    the mode's entry sequence runs (it holds the lease)."""
    if mode not in MODE_NAMES:
        return "Jeu libre : rien n’est surveillé"
    if moving:
        return "En pause : entrée dans le mode {mode}"
    if last_input is not None and now - last_input < PAUSE_AFTER_INPUT:
        return "En pause : l’utilisateur joue"
    return None


def roman(number):
    """1-39 as the game writes stage numerals (I, II, ... XXXIX)."""
    text = ""
    for value, letters in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while number >= value:
            text += letters
            number -= value
    return text


def judge(seen, profile, numeral_of, last_input, resumed, memory, now, after_mode=False):
    """(symptom, text, params, memory) for one look.

    seen: {adb (False: adb does not answer), running, focused (None:
    cannot tell, see ports.focus; False AWAY_AFTER looks in a row: away, or
    sign_in for a Google window), window (the one in front), crash (an
    Android error window in front), anr (its "not responding" one), screen (None: no capture), numeral
    (battle: the numeral ending the stage's name, None: unread),
    battle_settings (the preset's name read, None: not read), loadout
    (None: not checked; else what is wrong, "" when nothing), stage (battle:
    the stage number its name reads as, region and numeral, None: unread),
    auto ("on", "off", None: not read)}.
    profile: see profile(); numeral_of(number): the numeral the stage's
    name ends with in the table, or None. resumed: a mode just ended (no
    menu grace); after_mode: one ended less than AFTER_MODE ago (another
    screen is after_mode_screen).

    symptom None: well (battle or Power Saving Mode); "unknown": the look
    cannot tell (no capture); "pending": a game menu inside its grace.
    Neither unknown nor pending changes anything the watchdog remembers
    but the count of looks.

    The stage check compares only the numeral ending the stage's name:
    another region's stage with the same numeral passes. The region's
    banner is read in phase 2; until then the status says "numéral III",
    never a stage number."""
    memory = {**memory, "looks": memory["looks"] + 1}
    away, memory["away"] = memory.get("away", 0), 0
    if seen["adb"] and seen.get("running") and seen.get("focused") and not seen.get("crash") \
            and not seen.get("anr") \
            and seen.get("screen") is None:
        return "unknown", "pas de vérification (pas de capture d’écran)", {}, memory
    menu_since, memory["menu_since"] = memory["menu_since"], None
    if not seen["adb"]:
        return "adb_missing", SYMPTOMS["adb_missing"], {}, memory
    if seen.get("anr"):
        return "anr", SYMPTOMS["anr"], {}, memory
    if profile.get("mode") == "mine":
        return _mine(seen, away, memory)
    if seen.get("crash"):
        return "crash", SYMPTOMS["crash"], {}, memory
    if not seen["running"]:
        return "not_running", SYMPTOMS["not_running"], {}, memory
    if seen["focused"] is None:
        # A passing window over the game (the keyboard, a toast, a pop-up)
        # or the focus moving: nothing to judge.
        return "unknown", "pas de vérification (fenêtre de passage au premier plan)", {}, memory
    if not seen["focused"]:
        memory["away"] = away + 1
        if memory["away"] < AWAY_AFTER:
            return "unknown", "pas de vérification (autre fenêtre au premier plan, à confirmer)", {}, memory
        window = seen.get("window") or "?"
        if GMS in window:
            # Google's own window (its account chooser, the Play Games
            # prompt): the sign-in path, the relaunch's (launch_rules).
            return "sign_in", SYMPTOMS["sign_in"], {}, memory
        return "away", SYMPTOMS["away"], {"window": window}, memory
    screen = seen["screen"]
    if screen in ("title", "save"):
        return "start_screen", SYMPTOMS["start_screen"], {}, memory
    if screen == "sign_in":
        return "sign_in", SYMPTOMS["sign_in"], {}, memory
    if screen == "menu":
        since = now if menu_since is None else menu_since
        memory["menu_since"] = since
        quiet = now - max(since, last_input if last_input is not None else since)
        if resumed or quiet >= MENU_GRACE:
            return "menu", SYMPTOMS["menu"], {}, memory
        return "pending", "menu du jeu ouvert", {}, memory
    if screen == "saver":
        # The stage is not read here: unknown is not wrong.
        return None, "OK (économie d’énergie)", {}, memory
    if screen == "battle":
        wanted = profile.get("stage")
        numeral, expected = seen.get("numeral"), numeral_of(wanted) if wanted else None
        number = seen.get("stage")
        if wanted and (number is not None and number != wanted
                       or number is None and numeral is not None and expected is not None and numeral != expected):
            return "wrong_stage", SYMPTOMS["wrong_stage"], {"stage": wanted}, memory
        preset = profile.get("preset")
        if preset and seen.get("battle_settings") is not None and seen["battle_settings"] != preset:
            return "wrong_battle_settings", SYMPTOMS["wrong_battle_settings"], {"preset": preset}, memory
        if seen.get("loadout"):
            return "wrong_loadout", SYMPTOMS["wrong_loadout"], {"what": seen["loadout"]}, memory
        if seen.get("auto") == "off":
            return "auto_off", SYMPTOMS["auto_off"], {}, memory
        if number is not None and number == wanted:
            return None, "OK (stage {stage})", {"stage": wanted}, memory
        if numeral is not None and numeral == expected:
            return None, "OK (numéral {numeral})", {"numeral": roman(numeral)}, memory
        return None, "OK", {}, memory
    if after_mode:
        return "after_mode_screen", SYMPTOMS["after_mode_screen"], {}, memory
    return "unexpected", SYMPTOMS["unexpected"], {}, memory


def _mine(seen, away, memory):
    """judge() while the mine farms: its screens are the mine feature's;
    the game gone, crashed, away or back on its title, save or sign-in
    screen is mine_away: its repair relaunches the game and goes back into
    the mine (mine_relaunch); its alert after MINE_AWAY_LOOKS looks in a
    row (see decide)."""
    if seen.get("crash") or not seen["running"]:
        return "mine_away", SYMPTOMS["mine_away"], {}, memory
    if seen.get("focused") and seen.get("screen") in ("title", "save", "sign_in"):
        return "mine_away", SYMPTOMS["mine_away"], {}, memory
    if seen["focused"] is None:
        return "unknown", "pas de vérification (fenêtre de passage au premier plan)", {}, memory
    if not seen["focused"]:
        memory["away"] = away + 1
        if memory["away"] < AWAY_AFTER:
            return "unknown", "pas de vérification (autre fenêtre au premier plan, à confirmer)", {}, memory
        return "mine_away", SYMPTOMS["mine_away"], {}, memory
    return None, "OK", {}, memory


def status(text, params, mode="mpw18"):
    """The status row's template and parameters: "{mode} : OK (numéral
    III)" with mode's MODE_NAMES name, or the symptom."""
    return "{mode} : " + text, {**params, "mode": MODE_NAMES.get(mode, mode)}


def record(level, text, params=None, notify=False):
    return ("record", level, text, params or {}, notify)


def delay(failures, jitter=0.0):
    """Seconds without attempt after the failures-th failure; jitter in
    [-1, 1] spreads it by JITTER."""
    return DELAYS[min(failures, len(DELAYS) - 1)] * (1 + JITTER * max(-1.0, min(1.0, jitter)))


def minutes(seconds):
    return max(1, round(seconds / 60))


def failure(memory, kind, wall, jitter=0.0, mode="mpw18"):
    """(memory, actions): one real failure of kind: its next delay, and
    its alert the first time and when the delay first reaches ESCALATE
    (naming mode)."""
    state = memory["backoff"].get(kind, {"failures": 0, "said": []})
    failures = state["failures"] + 1
    base = DELAYS[min(failures, len(DELAYS) - 1)]
    wait = delay(failures, jitter)
    said = list(state["said"])
    values = {"repair": REPAIR_NAMES[kind], "minutes": minutes(wait)}
    named = {**values, "mode": MODE_NAMES.get(mode, mode)}
    reached = next((d for d in ESCALATE if base >= d and d not in said), None)
    if failures == 1:
        action = record("warning", "Réparation sans effet : {repair}, prochain essai dans {minutes} min", values,
                        notify=True)
    elif reached is not None:
        action = record("warning", "{mode} : {repair} toujours en échec, prochaine tentative dans "
                                   "{minutes} min", named, notify=True)
    else:
        action = record("normal", "Réparation sans effet : {repair}, prochain essai dans {minutes} min", values)
    if reached is not None:
        said.append(reached)
    memory = {**memory, "backoff": {**memory["backoff"], kind: {
        "failures": failures, "next": wall + wait, "delay": wait, "said": said}}}
    return memory, [action]


def stopped(memory, kind, wall, jitter=0.0, mode="mpw18"):
    """(memory, actions): the repair under way stopped (its sequence
    answered failed): one real failure, not counted again at the next look."""
    if memory["verifying"] != kind:
        return memory, []
    memory = {**memory, "verifying": None, "watch": {**memory["watch"], kind: wall + WATCH_AFTER_FAILURE}}
    return failure(memory, kind, wall, jitter, mode)


def not_run(memory, kind):
    """The repair did not run (deferred: the lease, a user input; or a
    plan): no failure, nothing to verify."""
    return {**memory, "verifying": None} if memory["verifying"] == kind else memory


def retry(memory, kind):
    """« Réessayer maintenant »: that kind's backoff starts over."""
    return {**memory, "backoff": {k: v for k, v in memory["backoff"].items() if k != kind},
            "watch": {k: v for k, v in memory["watch"].items() if k != kind}}


def waiting(memory, symptom, wall):
    """Minutes before the next attempt of symptom's repair, or None."""
    state = memory["backoff"].get(REPAIRS.get(symptom))
    return minutes(state["next"] - wall) if state and state["next"] > wall else None


def recovered(memory, wall):
    """Kinds whose good looks lasted their last delay (RECOVERY_FLOOR at
    least) start over; a repair that worked that long is done with."""
    since = memory["good_since"]
    if since is None:
        return memory

    return {**memory, "backoff": {kind: state for kind, state in memory["backoff"].items()
                                  if wall - since < max(state["delay"], RECOVERY_FLOOR)}}


def decide(memory, symptom, text, params, context, wall):
    """(memory, actions) after a look. context: {input_wall (Unix time of
    the last user input, or None), lease (the lease's holder when it is not
    the watchdog, or None), act ({kind: True when that repair taps for
    real; else its plan; ALWAYS_REAL kinds always do}), available (the
    repairs learned), mode (the mode checked, its texts' name; mpw18 when
    absent)}.

    actions: ("record", level, template, params, notify) (level normal,
    warning or error; notify: also a phone alert), ("repair", kind),
    ("plan", kind).

    The problem's alert is said once until the game has been well
    RECOVERED_AFTER looks in a row (battle or Power Saving Mode); then
    once "rétabli". A good look in between (the battle screen between two
    pop-ups) resets the bad looks in a row, nothing else."""
    actions = []
    if symptom in ("unknown", "pending"):
        return memory, actions
    mode = context.get("mode", "mpw18")
    named = MODE_NAMES.get(mode, mode)
    memory = dict(memory)
    verifying, memory["verifying"] = memory["verifying"], None
    if symptom is None:
        if verifying:
            actions.append(record("normal", "Réparation réussie : {repair}", {"repair": REPAIR_NAMES[verifying]}))
        if memory["good_since"] is None:
            memory["good_since"] = wall
        memory = recovered(memory, wall)
        memory.update(streak=0, since_repair=0, symptom=None, good=memory["good"] + 1)
        # After a repair, only a durable recovery is "rétabli".
        if memory["good"] >= RECOVERED_AFTER and (not memory["repaired"]
                                                  or wall - memory["good_since"] >= RECOVERY_FLOOR):
            if memory["alerted"] and memory["alert_notified"]:
                actions.append(record("normal", "{mode} : rétabli", {"mode": named}, notify=True))
            memory.update(alerted=False, alert_notified=False, repaired=False, watch={}, planned=None,
                          deferred=None)
        return memory, actions
    memory["good"] = 0
    memory["good_since"] = None
    repair = REPAIRS[symptom]
    if verifying:
        if repair == verifying:
            # The repair did not take: a real failure; watch this kind
            # passively for a while.
            memory["watch"] = {**memory["watch"], verifying: wall + WATCH_AFTER_FAILURE}
            memory, said = failure(memory, verifying, wall, context.get("jitter", 0.0), mode)
            actions += said
        else:
            # It took; something else is wrong now (a pop-up after a relaunch).
            actions.append(record("normal", "Réparation réussie : {repair}", {"repair": REPAIR_NAMES[verifying]}))
    same = symptom == memory["symptom"] or (repair is not None and repair == REPAIRS.get(memory["symptom"]))
    memory["streak"] = memory["streak"] + 1 if same else 1
    memory["since_repair"] = memory["since_repair"] + 1 if same else 1
    memory["symptom"] = symptom
    alert_after = {"unexpected": ALERT_AFTER_OTHER, "mine_away": MINE_AWAY_LOOKS}.get(symptom, ALERT_AFTER)
    if memory["streak"] >= alert_after and not memory["alerted"]:
        memory["alerted"] = True
        memory["alerts"] += 1
        family = repair or symptom
        quiet = wall - memory["notified"].get(family, -QUIET_AFTER_ALERT) < QUIET_AFTER_ALERT
        memory["alert_notified"] = not quiet
        if not quiet:
            memory["notified"] = {**memory["notified"], family: wall}
        actions.append(record("error" if symptom in ERRORS else "warning", "{mode} : " + text,
                              {**params, "mode": named}, notify=not quiet))
    if (repair is None or memory["since_repair"] < REPAIR_AFTER or memory["looks"] <= OBSERVE_FIRST
            or repair not in context.get("available", ())
            or memory["watch"].get(repair, 0) > wall
            or memory["backoff"].get(repair, {}).get("next", 0) > wall):
        return memory, actions
    holder = context.get("lease")
    if holder:
        if memory["deferred"] != holder:
            memory["deferred"] = holder
            actions.append(record("normal", "Réparation différée : bail tenu par {holder}", {"holder": holder}))
        return memory, actions
    memory["deferred"] = None
    if repair not in ALWAYS_REAL and not context.get("act", {}).get(repair):
        if memory["planned"] != symptom:
            memory["planned"] = symptom
            actions.append(("plan", repair))
        return memory, actions
    memory["verifying"] = repair
    memory["repaired"] = True
    memory["since_repair"] = 0
    actions.append(record("normal", "Réparation : {repair}", {"repair": REPAIR_NAMES[repair]}))
    actions.append(("repair", repair))
    return memory, actions


# Gold per second at 0 often means AUTO is off (the slayer does nothing): a
# trigger to read AUTO at once, never a proof (AUTO is tapped only on an
# OFF reading). It needs a full window (gold_rules.WINDOW, less one
# reading), a fresh sample (at most GOLD_FRESH seconds old, counted on the
# battle screen) and GOLD_ZEROS such readings in a row.
GOLD_FULL = 290
GOLD_FRESH = 30
GOLD_ZEROS = 2
GOLD_ALERT = "gold/s à 0 mais AUTO actif"


def gold_fresh():
    return {"last": None, "zeros": 0, "alerted": False}


def gold_zero(kept, gold, wall):
    """(kept, trigger): trigger once GOLD_ZEROS fresh readings in a row,
    each a new sample, read the rate at 0 over a full window. kept:
    gold_fresh() then what this returned; gold: the gold feature's current()
    ({rate, span, last}) or None. A rate above 0 clears it all (and the
    alert said, see gold_alert)."""
    if not gold or gold.get("last") is None or gold["last"] == kept["last"] or wall - gold["last"] > GOLD_FRESH:
        return kept, False
    kept = {**kept, "last": gold["last"]}
    if gold["rate"] is not None and gold["rate"] > 0:
        return gold_fresh() | {"last": gold["last"]}, False
    if gold["rate"] is None or gold["span"] < GOLD_FULL:
        return {**kept, "zeros": 0}, False
    zeros = kept["zeros"] + 1
    return {**kept, "zeros": zeros}, zeros == GOLD_ZEROS


def gold_alert(kept, auto):
    """(kept, alert): the AUTO reading after a trigger. ON while gold/s is
    at 0: one alert (GOLD_ALERT) until the rate is above 0 again."""
    if auto == "on" and kept["zeros"] >= GOLD_ZEROS and not kept["alerted"]:
        return {**kept, "alerted": True}, True
    return kept, False


def counters(memory, wall):
    """The state details' counters; next_attempt: each kind backing off,
    {repair (its French name), failures, next (Unix time of its next
    attempt allowed)}."""
    return {"looks": memory["looks"], "bad_in_a_row": memory["streak"], "alerts": memory["alerts"],
            "next_attempt": {kind: {"repair": REPAIR_NAMES[kind], "failures": state["failures"],
                                    "next": state["next"]} for kind, state in memory["backoff"].items()}}


def profile(loadout, stage18, mode="mpw18"):
    """The selected mode's profile: mode (mpw18, mpw4 or mine), its stage
    (stage18: the mode's stage, None for the mine) and its loadout, as the
    engraving feature keeps it per mode (its api loadout(mode): {preset:
    "I"-"V", the Battle settings preset; soul_weapon: {id, variant}}, or
    None). The soul weapon waits for phase 3 (the panels that show it are
    not mapped yet). The engraving's placement is the engraving's."""
    loadout = loadout if isinstance(loadout, dict) else {}
    preset = loadout.get("preset")
    weapon = loadout.get("soul_weapon")
    weapon_id = weapon.get("id") if isinstance(weapon, dict) else None
    variant = weapon.get("variant") if isinstance(weapon, dict) else None
    return {
        "mode": mode,
        "stage": stage18 if isinstance(stage18, int) and not isinstance(stage18, bool) and stage18 > 0 else None,
        "preset": preset if preset in ("I", "II", "III", "IV", "V") else None,
        "soul_weapon": ({"id": weapon_id, "variant": variant if isinstance(variant, str) else None}
                        if isinstance(weapon_id, int) and not isinstance(weapon_id, bool) else None),
    }
