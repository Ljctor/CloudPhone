"""What the mpw18 watchdog makes of each look at the game. Pure: what a
look saw, the farming profile (the mpw18 stage and mpw18's loadout), what
the watchdog remembers and the time go in; the symptom, the status and the actions (records and alerts, a repair
or its plan) come out. The feature (watchdog.py beside this file) takes
the looks and makes the repairs, every move through the navigation guard,
under the shared lease.

The watchdog runs only while the mode is the default one, mpw18: free
play, the timed modes and the mine (with or without a time limit) suspend
it. So the mine's own "jeu absent" alert and the watchdog's never overlap:
each absence has one owner. When a mode ends, the watchdog looks at once,
with no menu grace (still paused for a minute after a user input). During
free play the game may well be open on another device: nothing is checked
then. When it ends, the game here may show a "connected on another device"
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

The aim: after any disruption, mpw18 farming is back within a minute. A
look every EVERY seconds; a user who plays (an input in the last
PAUSE_AFTER_INPUT seconds) is not a disruption.

Repairs apply only to what is recognised: the process, the focus, an
Android crash window, the title, sign-in and save screens, a game menu, the battle
screen (Power Saving Mode needs none).

- A symptom ALERT_AFTER looks in a row (ALERT_AFTER_OTHER for another
  screen) is one warning alert (an error one for adb), never repeated
  until the game has been well RECOVERED_AFTER looks in a row; then one
  normal "rétabli". A game menu inside its grace, or a look with no
  capture, changes nothing.
- A repair needs its symptom REPAIR_AFTER looks in a row (the same look
  as the alert), the repair learned (available) and, at the gateway's
  start, OBSERVE_FIRST looks seen first: a restored state never resumes a
  repair. One repair at a time; the next look verifies it. One that did
  not take is followed by a passive watch of WATCH_AFTER_FAILURE (looks
  and alerts, no repair of that kind), as the mine's stop pass is.
- Each kind of repair has an hourly cap (CAPS, counted on Unix time and
  kept across gateway restarts: persisted()), then is blocked with one
  warning alert (blocked again within the hour: no new alert). Blocked
  clears on a user input or once the hourly window frees a slot.
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
# Looks seen at the gateway's start before any repair.
OBSERVE_FIRST = 2
# After a repair that did not take: no repair of that kind this long.
WATCH_AFTER_FAILURE = 2 * 60
HOUR = 3600

SYMPTOMS = {
    "adb_missing": "adb ne répond pas : l’émulateur ou adb manque",
    "not_running": "le jeu ne tourne pas",
    "away": "une autre application est au premier plan",
    "crash": "le jeu a planté (fenêtre d’erreur d’Android)",
    "anr": "le jeu ne répond pas (fenêtre d’Android), « Attendre » sans effet : à faire à la main",
    "start_screen": "le jeu est revenu à son écran titre",
    "sign_in": "le jeu demande de se reconnecter (Sign in with Google)",
    "after_mode_screen": "écran inconnu après la fin du mode (connecté sur un autre appareil ? choix de "
                         "sauvegarde ?) : à faire à la main",
    "menu": "un menu du jeu est ouvert depuis plus d’une minute sans l’utilisateur",
    "wrong_stage": "mauvais stage : pas le stage {stage}",
    "wrong_battle_settings": "mauvais préréglage de combat : pas le {preset}",
    "wrong_loadout": "mauvais équipement : {what}",
    "auto_off": "AUTO est arrêté",
    "unexpected": "écran inattendu",
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
}
REPAIR_NAMES = {"relaunch": "relance du jeu", "back_to_battle": "retour au combat",
                "stage_change": "changement de stage", "select_preset": "choix du préréglage de combat",
                "loadout": "rééquipement", "auto_on": "remise en marche d’AUTO"}
# Repairs of each kind at most per hour.
CAPS = {"relaunch": 3, "back_to_battle": 10, "stage_change": 3, "select_preset": 3, "loadout": 3, "auto_on": 3}
ERRORS = ("adb_missing",)
# Repairs that are never plan-only.
ALWAYS_REAL = ("relaunch", "back_to_battle")


def fresh(kept=None):
    """What the watchdog remembers when it starts (kept: persisted() of
    the last run, from state.json), or when a mode suspended it."""
    kept = kept or {}
    repairs = {kind: [float(t) for t in kept.get("repairs", {}).get(kind, []) if isinstance(t, (int, float))]
               for kind in CAPS}
    return {"looks": 0, "streak": 0, "since_repair": 0, "good": 0, "symptom": None, "alerted": False,
            "alerts": 0, "repairs": repairs, "blocked": {}, "block_notified": {}, "watch": {},
            "verifying": None, "menu_since": None, "planned": None, "deferred": None}


def persisted(memory):
    """What a gateway restart keeps: the repairs' times (for the caps)."""
    return {"repairs": {kind: list(times) for kind, times in memory["repairs"].items()}}


def suspended(memory):
    """A mode suspended the watchdog: it starts over, with its caps."""
    return {**fresh(persisted(memory)), "looks": memory["looks"]}


def paused(mode, last_input, now):
    """Why the watchdog does not look now (a template), or None. mode: the
    mode's name; last_input: monotonic time of the last user input, or None."""
    if mode != "mpw18":
        return "En pause : mode {mode}"
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

    seen: {adb (False: adb does not answer), running, focused, crash (an
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
    if seen["adb"] and seen.get("running") and seen.get("focused") and not seen.get("crash") \
            and not seen.get("anr") \
            and seen.get("screen") is None:
        return "unknown", "pas de vérification (pas de capture d’écran)", {}, memory
    menu_since, memory["menu_since"] = memory["menu_since"], None
    if not seen["adb"]:
        return "adb_missing", SYMPTOMS["adb_missing"], {}, memory
    if seen.get("anr"):
        return "anr", SYMPTOMS["anr"], {}, memory
    if seen.get("crash"):
        return "crash", SYMPTOMS["crash"], {}, memory
    if not seen["running"]:
        return "not_running", SYMPTOMS["not_running"], {}, memory
    if not seen["focused"]:
        return "away", SYMPTOMS["away"], {}, memory
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


def status(text, params):
    """The status row's template and parameters: "Farming mpw18 : OK
    (numéral III)", or the symptom."""
    return "Farming mpw18 : " + text, params


def record(level, text, params=None, notify=False):
    return ("record", level, text, params or {}, notify)


def in_hour(times, wall):
    return [t for t in times if wall - t < HOUR]


def unblocked(memory, input_wall, wall):
    """Blocked kinds clear on a user input since they were blocked (with a
    new hourly count: the user took over) or once the hourly window frees
    a slot; never on a good look."""
    blocked, repairs = dict(memory["blocked"]), dict(memory["repairs"])
    for kind, since in memory["blocked"].items():
        if input_wall is not None and since < input_wall:
            repairs[kind] = [t for t in repairs.get(kind, []) if t > input_wall]
            del blocked[kind]
        elif len(in_hour(repairs.get(kind, []), wall)) < CAPS[kind]:
            del blocked[kind]
    return {**memory, "blocked": blocked, "repairs": repairs}


def decide(memory, symptom, text, params, context, wall):
    """(memory, actions) after a look. context: {input_wall (Unix time of
    the last user input, or None), lease (the lease's holder when it is not
    the watchdog, or None), act ({kind: True when that repair taps for
    real; else its plan; ALWAYS_REAL kinds always do}), available (the
    repairs learned)}.

    actions: ("record", level, template, params, notify) (level normal,
    warning or error; notify: also a phone alert), ("repair", kind),
    ("plan", kind).

    The problem's alert is said once until the game has been well
    RECOVERED_AFTER looks in a row (battle or Power Saving Mode); then
    once "rétabli". A good look in between (the battle screen between two
    pop-ups) resets the bad looks in a row, nothing else."""
    actions = []
    memory = unblocked(memory, context.get("input_wall"), wall)
    if symptom in ("unknown", "pending"):
        return memory, actions
    verifying, memory["verifying"] = memory["verifying"], None
    if symptom is None:
        if verifying:
            actions.append(record("normal", "Réparation réussie : {repair}", {"repair": REPAIR_NAMES[verifying]}))
        memory.update(streak=0, since_repair=0, symptom=None, good=memory["good"] + 1)
        if memory["good"] >= RECOVERED_AFTER:
            if memory["alerted"]:
                actions.append(record("normal", "Farming mpw18 : rétabli", notify=True))
            memory.update(alerted=False, watch={}, planned=None, deferred=None)
        return memory, actions
    memory["good"] = 0
    repair = REPAIRS[symptom]
    if verifying:
        if repair == verifying:
            # The repair did not take: watch this kind passively for a while.
            memory["watch"] = {**memory["watch"], verifying: wall + WATCH_AFTER_FAILURE}
            actions.append(record("warning", "Réparation sans effet : {repair}, surveillance seule 2 minutes",
                                  {"repair": REPAIR_NAMES[verifying]}))
        else:
            # It took; something else is wrong now (a pop-up after a relaunch).
            actions.append(record("normal", "Réparation réussie : {repair}", {"repair": REPAIR_NAMES[verifying]}))
    same = symptom == memory["symptom"] or (repair is not None and repair == REPAIRS.get(memory["symptom"]))
    memory["streak"] = memory["streak"] + 1 if same else 1
    memory["since_repair"] = memory["since_repair"] + 1 if same else 1
    memory["symptom"] = symptom
    if memory["streak"] >= (ALERT_AFTER_OTHER if symptom == "unexpected" else ALERT_AFTER) and not memory["alerted"]:
        memory["alerted"] = True
        memory["alerts"] += 1
        actions.append(record("error" if symptom in ERRORS else "warning", "Farming mpw18 : " + text, params,
                              notify=True))
    if (repair is None or memory["since_repair"] < REPAIR_AFTER or memory["looks"] <= OBSERVE_FIRST
            or repair not in context.get("available", ()) or repair in memory["blocked"]
            or memory["watch"].get(repair, 0) > wall):
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
    recent = in_hour(memory["repairs"].get(repair, []), wall)
    if len(recent) >= CAPS[repair]:
        memory["repairs"] = {**memory["repairs"], repair: recent}
        memory["blocked"] = {**memory["blocked"], repair: wall}
        # Blocked again within the hour: not said again.
        notify = wall - memory["block_notified"].get(repair, -HOUR) >= HOUR
        if notify:
            memory["block_notified"] = {**memory["block_notified"], repair: wall}
        actions.append(record("warning", "Réparation bloquée : {repair}, {cap} fois en une heure ; "
                                         "fais-le à la main", {"repair": REPAIR_NAMES[repair], "cap": CAPS[repair]},
                              notify=notify))
        return memory, actions
    memory["repairs"] = {**memory["repairs"], repair: recent + [wall]}
    memory["verifying"] = repair
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
    """The state details' counters, the repairs per kind."""
    return {"looks": memory["looks"], "bad_in_a_row": memory["streak"], "alerts": memory["alerts"],
            "repairs_this_hour": {kind: len(in_hour(times, wall)) for kind, times in memory["repairs"].items()},
            "blocked_since": dict(memory["blocked"])}


def profile(loadout, stage18):
    """The farming profile: the mpw18 stage (the mode's stage18) and
    mpw18's loadout, as the engraving feature keeps it per mode
    (its api loadout("mpw18"): {preset: "I"-"V", the Battle settings preset;
    soul_weapon: {id, variant}}, or None). Phase 1 uses only the stage; the
    preset and the soul weapon wait for phase 3 (the panels that show them
    are not mapped yet). The engraving's placement is the engraving's."""
    loadout = loadout if isinstance(loadout, dict) else {}
    preset = loadout.get("preset")
    weapon = loadout.get("soul_weapon")
    weapon_id = weapon.get("id") if isinstance(weapon, dict) else None
    variant = weapon.get("variant") if isinstance(weapon, dict) else None
    return {
        "stage": stage18 if isinstance(stage18, int) and not isinstance(stage18, bool) and stage18 > 0 else None,
        "preset": preset if preset in ("I", "II", "III", "IV", "V") else None,
        "soul_weapon": ({"id": weapon_id, "variant": variant if isinstance(variant, str) else None}
                        if isinstance(weapon_id, int) and not isinstance(weapon_id, bool) else None),
    }
