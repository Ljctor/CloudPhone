"""The watchdog: it checks that the game does what the selected mode
says, looking at it every rules.EVERY seconds, and when it does not,
alerts and repairs: mpw18 and mpw4 farming each with its own loadout
(stage, Battle settings preset, AUTO); the Closed Mine, whose screens are
the mine feature's: the game away (rules.mine_away) is relaunched, then
the mine re-entered by the mine feature (reenter); free play, nothing.

GET /watchdog   {mode, status: {template, params}, text, line: {template,
                 params}, symptom, paused, counters, waiting, lease,
                 repairing, profile}
POST /watchdog/retry   {kind}: « Réessayer », that repair's backoff starts
                 over (needs the page token)

line: the watchdog's part of the mode's État row ("OK", the symptom,
"relance du jeu dans 4 min" while a repair backs off); waiting: the kinds
backing off now (each its next attempt still ahead), for « Réessayer ».

Each look checks that adb answers, that Android's crash dialog is not in
front, that the game's process runs and is in front, then the screen
(the shared capture, at most rules.MAX_AGE seconds old): the battle screen
or Power Saving Mode is farming; on the battle screen the numeral ending
the stage's name is compared with the mpw18 stage's. What it makes of a
look is watchdog_rules.py's (judge, decide); its profile is the selected
mode's (rules.profile).

The repairs: the relaunch (the launch feature's, holder "watchdog" of the
shared lease, stopped by a user input): it never kills the game, closes
Android's crash dialog by its button, takes the latest save, and leaves
Power Saving Mode. A wrong stage or Battle settings preset: the stage
change feature's farm(); AUTO read off: its ensure_auto (each under its
own holder "stage_change", and plan-only while its switch says so, see
features/stage_change.py). On the battle screen the stage is read whole
(region and numeral); the preset and AUTO are read on one unfold of the
right edge's controls (a tap, under the lease) at most every
CONTROLS_EVERY seconds, whoever watches the screen (only a user's input
pauses it, a minute). The way
back to battle from a game menu stays an alert (its close buttons differ
per panel); the soul weapon and its engraving wait for phase 3.

Free play suspends it, and so does a mode's entry while its sequence
runs (the mode feature's state "moving", under the lease): the watchdog
waits for it. A user input pauses it a minute; another holder of the
lease defers its repair. At the gateway's start it only observes its first
looks; the repairs' hourly counts are kept in state.json ("watchdog").
"""

import asyncio
import random

AVAILABLE = ("relaunch", "mine_relaunch")
# Repairs by the stage change feature, and the switch that makes each real.
FARMING = {"stage_change": "stage_change", "select_preset": "preset", "auto_on": "auto"}
# Seconds between two readings of the preset and AUTO (each an unfold).
CONTROLS_EVERY = 300
# The farming modes (their own stage, preset and AUTO).
FARMED = ("mpw18", "mpw4")


def watchdog(ports, screens, stage, rules, numeral_of, modes, mines, launches, loadout, farming=None, gold=None):
    """numeral_of(number): the numeral ending stage number's name; modes,
    mines, launches: the mode, mine and launch features' api; loadout(mode):
    the engraving feature's loadout of a farming mode ({stage, preset,
    soul_weapon}), read only; farming: the stage change feature's api (None:
    the relaunch only); gold: the gold feature's api (current: gold/s), whose
    rate at 0 reads AUTO at once (rules.gold_zero)."""
    memory = rules.fresh(ports.store.saved.get("watchdog"))
    status = {"text": ports.t("Démarrage"), "symptom": None, "paused": None, "repairing": None,
              "mode": None, "ended_at": None, "resumed": False, "anr_waited": False, "controls": None,
              "gold": rules.gold_fresh(),
              "gold_due": False}
    available = AVAILABLE + (tuple(FARMING) if farming else ())
    ports.store.register("watchdog", lambda: rules.persisted(memory))

    def say(level, text, params=None, notify=False):
        """One record for the gateway's log (and the page), in English: an
        English template filled with params, or a status text (rules.record);
        notify: also a phone alert. Its text."""
        said = ports.english(text) if ports.is_t(text) else ports.fill(text, params)
        ports.log(level, said, notify)
        return said

    def show(text):
        """The status: a status text."""
        status["text"] = text

    def mode_now():
        """The mode's name ("mine" while the mine farms)."""
        return "mine" if mines["state"]()["enabled"] else modes["state"]()["mode"]

    def profile():
        """The selected mode's stage and loadout (none for the mine)."""
        name = status["mode"] or mode_now()
        if name not in FARMED:
            return rules.profile(None, None, name)
        part = loadout(name) or {}
        return rules.profile(part, part.get("stage"), name)

    def facts(shot):
        name = screens.classify(shot)
        if name == "menu" and farming and screens.plain_battle(shot):
            name = "battle"  # the skill bar shows: no panel over the battle
        battle = name == "battle"
        return (name, stage.read_battle(shot) if battle else None,
                farming["battle_stage"](shot) if battle and farming else None)

    async def look():
        """What one look sees (watchdog_rules.judge's seen)."""
        running = await ports.running()
        seen = {"adb": running is not None, "running": bool(running), "crash": False, "anr": False,
                "focused": False, "screen": None, "numeral": None, "stage": None}
        if running is None:
            return seen
        dialog = await ports.dialog()
        seen["crash"], seen["anr"] = dialog == "crash", dialog == "anr"
        if running and not dialog:
            focus = await ports.focus()
            seen["focused"], seen["window"] = focus["game"], focus["window"]
            if not focus["game"]:
                # Which window, for the diagnosis (a launcher, a system
                # dialog, Google's; never the account's).
                ports.log("normal", f"Watchdog: the game is not in front: {focus['window']}")
        if seen["focused"]:
            shot = await ports.capture(max_age=rules.MAX_AGE)
            if shot:
                seen["screen"], seen["numeral"], seen["stage"] = await ports.analyse(facts, shot)
        return seen

    async def read_controls(seen):
        """The preset and AUTO, read on one unfold at most every
        CONTROLS_EVERY seconds on the battle screen (kept in between), or
        at once when gold/s reads 0 (a trigger: AUTO may be off), viewers
        or not. AUTO read on while gold/s stays at 0: one alert."""
        if not farming or seen["screen"] != "battle" or status["mode"] not in FARMED:
            return
        now = ports.clock.monotonic()
        if gold:
            status["gold"], trigger = rules.gold_zero(status["gold"], gold["current"](), ports.clock.wall())
            if trigger:
                ports.log("normal", "Watchdog: gold/s at 0, AUTO read at once")
                status["gold_due"] = True
        triggered, status["gold_due"] = status["gold_due"], False
        kept = status["controls"]
        if kept is None or triggered or now - kept[1] >= CONTROLS_EVERY:
            reading = await farming["read_controls"]()
            kept = status["controls"] = (reading, now) if reading else None
            if triggered:
                status["gold"], alert = rules.gold_alert(status["gold"], reading and reading["auto"])
                if alert:
                    await ports.notify(say("warning", rules.GOLD_ALERT, {}, notify=True))
        if kept:
            seen["battle_settings"], seen["auto"] = kept[0]["preset"], kept[0]["auto"]

    async def notify_all(actions):
        for _, level, text, values, notify in actions:
            said = say(level, text, values, notify)
            if notify:
                await ports.notify(said)

    async def farm_repair(kind):
        """A stage change repair: farm() for the stage and the preset,
        ensure_auto for AUTO; read again at the next look. Deferred or a
        plan: not a failure (rules.not_run); stopped: one (rules.stopped)."""
        nonlocal memory
        status["controls"] = None
        part = profile()
        name = part["mode"]
        status["repairing"] = kind
        show(ports.t("Réparation en cours : {repair}", repair=rules.REPAIR_NAMES[kind]))
        try:
            if kind == "auto_on":
                answer = await farming["ensure_auto"](name)
            else:
                answer = await farming["farm"](part["stage"], part["preset"], name,
                                               modes["state"]().get("highest"))
        except ports.Busy as e:
            memory = rules.not_run(memory, kind)
            say("normal", "Repair deferred: {repair} ({why})", {"repair": rules.REPAIR_NAMES[kind], "why": e.t})
            return
        finally:
            status["repairing"] = None
        if answer["result"] == "failed":
            memory, actions = rules.stopped(memory, kind, ports.clock.wall(), random.uniform(-1.0, 1.0), name)
            # Why it stopped, with the backoff's alert (if it is one).
            notify = any(action[4] for action in actions)
            text = say("warning", "Repair stopped: {repair}: {why}",
                       {"repair": rules.REPAIR_NAMES[kind], "why": answer["text_t"]}, notify=notify)
            if notify:
                await ports.notify(text)
            await notify_all([(*action[:4], False) for action in actions])
        elif answer["result"] == "done":
            modes["confirm"](name)
        elif answer["result"] == "plan":
            memory = rules.not_run(memory, kind)
            say("normal", "Plan only: {repair}: {plan}", {"repair": rules.REPAIR_NAMES[kind], "plan": answer["text_t"]})

    async def wait_anr():
        """Android says the game is not responding: "Wait", once per
        dialog (its "Close app" would kill the game). Still there at the
        next look, it is the alert's."""
        if status["anr_waited"]:
            return
        status["anr_waited"] = True
        shot = await ports.capture(max_age=rules.MAX_AGE)
        if not shot:
            # No capture: Wait is tried again at the next look.
            status["anr_waited"] = False
            return
        try:
            async with ports.leased("watchdog", "Wait on the not responding dialog", 60):
                pressed = await ports.wait_anr(shot)
        except ports.Busy as e:
            ports.log("normal", f"Watchdog: Wait on the ANR dialog deferred: {e}")
            status["anr_waited"] = False
            return
        say("normal", "The game is not responding: Wait pressed" if pressed
            else "The game is not responding: Wait button not found")

    async def relaunch(kind="relaunch"):
        """The launch, holder "watchdog". Deferred (the lease, a user
        input) or the user's own launch: not a failure; stopped (blocked,
        failed): one. kind mine_relaunch: then the mine's way back in."""
        nonlocal memory
        task = launches["start"]("watchdog", False)
        if task is None:
            # The user's own launch runs: it is the repair.
            memory = rules.not_run(memory, kind)
            return
        status["repairing"] = kind
        show(ports.t("Réparation en cours : {repair}", repair=rules.REPAIR_NAMES[kind]))
        try:
            await task
        finally:
            status["repairing"] = None
        ended = launches["state"]()
        if ended["state"] == "done" and farming and "relaunched" in farming:
            # The game is back: its soul weapon read again (features/soul_weapon.py).
            farming["relaunched"](mode_now())
        if ended["state"] == "deferred":
            memory = rules.not_run(memory, kind)
        elif ended["state"] in ("blocked", "failed"):
            memory, actions = rules.stopped(memory, kind, ports.clock.wall(), random.uniform(-1.0, 1.0),
                                            status["mode"])
            await notify_all(actions)
        elif kind == "mine_relaunch" and "reenter" in mines:
            # Back in the mine by its own way; out of feathers or no way in,
            # the mine ends and the mode goes back to the default (its alert).
            status["repairing"] = kind
            try:
                answer = await mines["reenter"]()
            finally:
                status["repairing"] = None
            say("normal", "Back into the mine: {result} {text}", {"result": answer["result"],
                                                                  "text": answer["text_t"]})

    async def tick():
        nonlocal memory
        name = mode_now()
        now, wall = ports.clock.monotonic(), ports.clock.wall()
        last = await ports.user_input()  # only an input with the game in front
        if name != status["mode"]:
            if status["mode"] is not None:
                # Another mode: its own symptoms, from scratch (the backoff
                # kept). Look at once, no menu grace; after free play,
                # another screen for a while may be the disconnect screen
                # or the saves.
                memory = rules.suspended(memory)
                status.update(resumed=True, controls=None,
                              ended_at=now if status["mode"] == "free" else status["ended_at"])
            status["mode"] = name
        moving = modes["state"]().get("state") == "moving"
        why = rules.paused(name, last["monotonic"] if last else None, now, moving)
        if not ports.enabled():
            # Off: no look at all, from scratch once back on.
            why = "Plugin désactivé"
            memory = rules.suspended(memory)
            status["resumed"] = True
        status["paused"] = why
        if why:
            if name not in rules.MODE_NAMES or moving:
                memory = rules.suspended(memory)
                status["resumed"] = True
            status["symptom"] = None
            show(ports.t(why, mode=rules.MODE_NAMES.get(name, name)) if "{mode}" in why else ports.t(why))
            return False
        if launches["running"]():
            show(ports.t("Lancement du jeu en cours"))
            return False
        seen = await look()
        if seen["anr"]:
            await wait_anr()
        else:
            status["anr_waited"] = False
        await read_controls(seen)
        after_mode = status["ended_at"] is not None and now - status["ended_at"] < rules.AFTER_MODE
        symptom, text, params, memory = rules.judge(
            seen, profile(), numeral_of, last["monotonic"] if last else None, status["resumed"], memory, now,
            after_mode)
        status["resumed"] = False
        status["symptom"] = symptom
        held = ports.lease.state()
        context = {"input_wall": last["wall"] if last else None,
                   "lease": held["holder"] if held and held["holder"] != "watchdog" else None,
                   "act": {kind: farming["switches"]()[switch] == "real" for kind, switch in FARMING.items()}
                   if farming else {}, "available": available, "jitter": random.uniform(-1.0, 1.0),
                   "mode": name}
        if symptom is None and name in FARMED:
            modes["confirm"](name)
        memory, actions = rules.decide(memory, symptom, text, params, context, wall)
        ports.store.save()
        minutes = rules.waiting(memory, symptom, wall)
        if minutes is not None:
            show(ports.t("{what} ; prochain essai dans {minutes} min", what=ports.t(text, **params), minutes=minutes))
        else:
            show(ports.t(text, **params))
        repaired = False
        for action in actions:
            if action[0] == "record":
                _, level, text, values, notify = action
                said = say(level, text, values, notify)
                if notify:
                    await ports.notify(said)
            elif action[0] == "repair" and action[1] in ("relaunch", "mine_relaunch"):
                ports.store.save()
                await relaunch(action[1])
                repaired = True
            elif action[0] == "repair" and action[1] in FARMING:
                ports.store.save()
                await farm_repair(action[1])
                repaired = True
            elif action[0] == "plan":
                say("normal", "Plan only (switch on plan): {repair}", {"repair": rules.REPAIR_NAMES[action[1]]})
        return repaired

    async def watch():
        while True:
            await ports.clock.sleep(rules.EVERY)
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                ports.exception("Watchdog failed")
                show(ports.t("Erreur : {error}", error=f"{e!r}"[:200]))

    async def start(app):
        ports.spawn(watch())

    def line():
        """The watchdog's part of the mode's État row: "OK", the pause, the
        repair under way, "{repair} dans {minutes} min" while the symptom's
        repair backs off, else the symptom (as the status)."""
        if status["paused"] or status["repairing"] or status["symptom"] in ("unknown", "pending"):
            return status["text"]
        if status["symptom"] is None:
            return ports.t("OK")
        minutes = rules.waiting(memory, status["symptom"], ports.clock.wall())
        kind = rules.REPAIRS.get(status["symptom"])
        if minutes is not None:
            return ports.t("{repair} dans {minutes} min", repair=rules.REPAIR_NAMES[kind], minutes=minutes)
        return status["text"]

    def state():
        held = ports.lease.state()
        wall = ports.clock.wall()
        return {"mode": status["mode"], "status": status["text"], "text": ports.french(status["text"]),
                "line": line(),
                "waiting": sorted(kind for kind, kept in memory["backoff"].items() if kept["next"] > wall),
                "symptom": status["symptom"], "paused": status["paused"], "repairing": status["repairing"],
                "counters": rules.counters(memory, wall), "lease": held,
                "profile": profile()}

    async def handle_state(request):
        return ports.respond(state())

    async def handle_retry(request):
        nonlocal memory
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        kind = body.get("kind") if isinstance(body, dict) else None
        if kind not in rules.REPAIR_NAMES:
            return ports.respond({"error": f"Expected {{kind}}: one of {', '.join(rules.REPAIR_NAMES)}"}, status=400)
        memory = rules.retry(memory, kind)
        ports.store.save()
        say("normal", "Retry now: {repair}", {"repair": rules.REPAIR_NAMES[kind]})
        return ports.respond(state())

    return {"routes": [("GET", "/watchdog", handle_state), ("POST", "/watchdog/retry", handle_retry)],
            "startup": [start]}
