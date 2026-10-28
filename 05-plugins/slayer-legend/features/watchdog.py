"""The watchdog: it checks that the game does what the selected mode
says, looking at it every rules.EVERY seconds, and when it does not,
alerts and repairs: mpw18 and mpw4 farming each with its own loadout
(stage, Battle settings preset); the Closed Mine, whose screens are
the mine feature's: the game away (rules.mine_away) is relaunched, then
the mine re-entered by the mine feature (reenter); free play, nothing.

GET /watchdog   {mode, status: {template, params}, line: {template,
                 params}, symptom, paused_t, counters, waiting, lease,
                 repairing, profile, intention} (status, line, paused_t: status
                 texts, see texts.py; paused_t null unless paused)
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
change feature's farm() (under its own holder "stage_change", and
plan-only while its switch says so, see features/stage_change.py). On the
battle screen the stage is read whole (region and numeral); the preset and
AUTO are read on one unfold of the right edge's controls (the arrow's tap,
under the lease) at most every CONTROLS_EVERY seconds, whoever watches the
screen (only a user's input pauses it, 5 s). AUTO is never tapped
(the user's order, 2026-10-22): its reading is only said in the alerts.

The stage progress bar (stage.progress, under the stage's name) is read
at each look on the plain battle screen or the parking screen (the Soul
Weapon screen, where it is drawn too) while mpw18 or mpw4 farms; still
for rules.STALL_LOOKS readable looks in a row (rules.bar_look) it is the
symptom progress_stalled: an error alert, no repair, no tap. Not counted
while paused (free play, a mode's entry, a user input), in the mine, on
another screen (a menu: its own symptom) or within rules.BAR_SETTLE of a
relaunch: the count starts over. The way
back to battle from a game menu stays an alert (its close buttons differ
per panel); the soul weapon and its engraving wait for phase 3.

Parking (rules.park_wanted): while mpw18 or mpw4 farms, its idle place
is the Soul Weapon screen, the battle going on above it. The screen read
there (farming's parked: its title) counts as the battle: its stage,
preset and progress bar are read the same way (the bar is drawn there
too); the preset and AUTO are not unfolded there. The plain battle is
then the symptom unparked: the stage change feature's park() goes back,
through the soul weapon step's own moves (Equipment, the Weapon tab, the
Soul Weapon icon), never a tap inside the panel.

Free play suspends it, and so does a mode's entry while its sequence
runs (the mode feature's state "moving", under the lease): the watchdog
waits for it. A user input pauses it 5 s; another holder of the
lease defers its repair. At the gateway's start it only observes its first
looks; the repairs' hourly counts are kept in state.json ("watchdog").
"""

import asyncio
import random
import json

AVAILABLE = ("relaunch", "mine_relaunch")
# Repairs by the stage change feature, and the switch that makes each real.
FARMING = {"stage_change": "stage_change", "select_preset": "preset"}
# Seconds between two readings of the preset (each an unfold).
CONTROLS_EVERY = 300
# The farming modes (their own stage and preset).
FARMED = ("mpw18", "mpw4")


def watchdog(ports, screens, stage, rules, numeral_of, modes, mines, launches, loadout, farming=None, gold=None):
    """numeral_of(number): the numeral ending stage number's name; modes,
    mines, launches: the mode, mine and launch features' api; loadout(mode):
    the engraving feature's loadout of a farming mode ({stage, preset,
    soul_weapon}), read only; farming: the stage change feature's api (None:
    the relaunch only); gold: the gold feature's api (current: gold/s), whose
    rate at 0 raises an alert once confirmed (rules.gold_zero)."""
    memory = rules.fresh(ports.store.saved.get("watchdog"))
    status = {"text": ports.t("Démarrage"), "symptom": None, "paused": None, "repairing": None,
              "mode": None, "ended_at": None, "resumed": False, "anr_waited": False, "controls": None,
              "intention": None, "redirect_episode": None, "input_stamp": None, "gold": rules.gold_fresh(),
              "bar": rules.bar_fresh(), "relaunched_at": None}
    parking = bool(farming) and "park" in farming
    available = AVAILABLE + (tuple(FARMING) if farming else ()) + (("park",) if parking else ())
    ports.store.register("watchdog", lambda: rules.persisted(memory))

    def forget_controls(why):
        """The game relaunched: the preset is read again."""
        status["controls"] = None

    if hasattr(ports, "on_relaunch"):
        ports.on_relaunch(forget_controls)

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
        state = modes["state"]()
        park = parking and rules.park_wanted(name, farming["soul_weapon_switch"](), state.get("state"),
                                             state.get("hold"))
        return rules.profile(part, part.get("stage"), name, park)

    game = getattr(ports, "game", None)

    def naming(shot):
        """The screen the look names (its stage and progress bar are the
        scan's: features/game.py), and whether the battle shows plain."""
        name = screens.classify(shot)
        known = screens.known_name(shot) if name == "other" else None
        if known:
            return "known", known, False
        if name == "menu" and farming and screens.plain_battle(shot):
            name = "battle"
        elif name == "menu" and parking and farming["parked"](shot):
            name = "parked"
        plain = name == "battle" and screens.plain_battle(shot)
        return name, screens.other_name(shot) if name == "other" else None, plain

    async def scanned_facts(shot):
        """facts() with the stage, its numeral and the bar from the game's
        scan of the same capture."""
        name, named, plain = await ports.analyse(naming, shot)
        if name == "known":
            return "known", None, None, None, named
        readings = await game["scan"](shot, ("battle_stage", "progress"))
        battle = name in ("battle", "parked")
        return (name, readings.get("stage_numeral") if battle else None,
                readings.get("stage") if battle and farming else None,
                readings.get("progress") if name == "parked" or plain else None, named)

    def facts(shot):
        name = screens.classify(shot)
        known = screens.known_name(shot) if name == "other" else None
        if known:
            return "known", None, None, None, known
        if name == "menu" and farming and screens.plain_battle(shot):
            name = "battle"  # the skill bar shows: no panel over the battle
        elif name == "menu" and parking and farming["parked"](shot):
            name = "parked"  # the Soul Weapon screen, the battle above it
        battle = name in ("battle", "parked")
        return (name, stage.read_battle(shot) if battle else None,
                farming["battle_stage"](shot, *((screens.PARKED_SHADE,) if name == "parked" else ()))
                if battle and farming else None,
                stage.progress(shot) if name == "parked" or battle and screens.plain_battle(shot) else None,
                screens.other_name(shot) if name == "other" else None)

    async def look():
        """What one look sees (watchdog_rules.judge's seen)."""
        running = await ports.running()
        seen = {"adb": running is not None, "running": bool(running), "crash": False, "anr": False,
                "focused": False, "screen": None, "numeral": None, "stage": None, "bar": None}
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
                seen["screen"], seen["numeral"], seen["stage"], seen["bar"], seen["named"] = \
                    await (scanned_facts(shot) if game is not None else ports.analyse(facts, shot))
        return seen

    async def read_controls(seen):
        """Read the preset periodically; report confirmed zero gold/s
        without inspecting AUTO or unfolding controls for that alert."""
        if not farming or seen["screen"] != "battle" or status["mode"] not in FARMED:
            return
        now = ports.clock.monotonic()
        if gold:
            status["gold"], trigger = rules.gold_zero(status["gold"], gold["current"](), ports.clock.wall())
            if trigger:
                status["gold"], alert = rules.gold_alert(status["gold"])
                if alert:
                    await ports.notify(say("warning", rules.GOLD_ALERT, {}, notify=True))
        kept = status["controls"]
        if kept is None or now - kept[1] >= CONTROLS_EVERY:
            reading = await farming["read_controls"]()
            kept = status["controls"] = (reading, now) if reading else None
            if reading and game is not None:
                game["note"]({"preset": reading["preset"]})
        if kept:
            seen["battle_settings"] = kept[0]["preset"]

    async def notify_all(actions):
        for _, level, text, values, notify in actions:
            said = say(level, text, values, notify)
            if notify:
                await ports.notify(said)

    async def farm_repair(kind):
        """A stage change repair: farm() for the stage and the preset, park()
        back to the parking screen; read again at the next look. Deferred
        or a plan: not a failure (rules.not_run); stopped: one
        (rules.stopped)."""
        nonlocal memory
        status["controls"] = None
        part = profile()
        name = part["mode"]
        status["repairing"] = kind
        status["intention"] = rules.redirect_intention(kind, profile())
        show(ports.t("Vers {destination} : {purpose}", destination=status["intention"]["destination_t"],
                     purpose=status["intention"]["purpose_t"]))
        try:
            answer = await (farming["park"](name) if kind == "park" else
                            farming["farm"](part["stage"], part["preset"], name, modes["state"]().get("highest")))
        except ports.Busy as e:
            memory = rules.not_run(memory, kind)
            say("normal", "Action waiting: {repair}; {why}", {"repair": rules.REPAIR_NAMES[kind], "why": e.t})
            return
        finally:
            status["repairing"] = None
            status["intention"] = None
        if answer["result"] == "failed":
            memory, actions = rules.stopped(memory, kind, ports.clock.wall(), random.uniform(-1.0, 1.0), name)
            # Why it stopped, with the backoff's alert (if it is one).
            notify = any(action[4] for action in actions)
            text = say("warning", "Action stopped: {repair}; {why}",
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
        status["intention"] = rules.redirect_intention(kind, profile())
        show(ports.t("Vers {destination} : {purpose}", destination=status["intention"]["destination_t"],
                     purpose=status["intention"]["purpose_t"]))
        try:
            await task
        finally:
            status["repairing"] = None
            status["intention"] = None
        ended = launches["state"]()
        status["relaunched_at"] = ports.clock.monotonic()
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
            status["intention"] = rules.redirect_intention(kind, profile())
            try:
                answer = await mines["reenter"]()
            finally:
                status["repairing"] = None
                status["intention"] = None
            say("normal", "Back into the mine: {result} {text}", {"result": answer["result"],
                                                                  "text": answer["text_t"]})

    async def tick():
        nonlocal memory
        name = mode_now()
        now, wall = ports.clock.monotonic(), ports.clock.wall()
        last = await ports.user_input()  # only an input with the game in front
        stamp = last.get("monotonic") if last else None
        if stamp is not None and stamp != status["input_stamp"]:
            status["input_stamp"] = stamp
            status["redirect_episode"] = None
        if name != status["mode"]:
            status["redirect_episode"] = None
            if status["mode"] is not None:
                # Another mode: its own symptoms, from scratch (the backoff
                # kept). Look at once, no menu grace; after free play,
                # another screen for a while may be the disconnect screen
                # or the saves.
                memory = rules.suspended(memory)
                status.update(resumed=True, controls=None,
                              ended_at=now if status["mode"] == "free" else status["ended_at"])
            status["mode"] = name
        mode_state = modes["state"]()
        moving = mode_state.get("state") == "moving"
        why = rules.paused(name, last["monotonic"] if last else None, now, moving)
        if not why and (mode_state.get("intention") or {}).get("kind") == "resource_refresh":
            why = "Actualisation des ressources en cours"
        if not ports.enabled():
            # Off: no look at all, from scratch once back on.
            why = "Plugin désactivé"
            memory = rules.suspended(memory)
            status["resumed"] = True
        status["paused"] = why
        if why or launches["running"]():
            status["bar"] = rules.bar_fresh()
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
        settled = status["relaunched_at"] is None or now - status["relaunched_at"] >= rules.BAR_SETTLE
        if name in FARMED and seen["screen"] in ("battle", "parked") and settled:
            status["bar"], seen["stalled"] = rules.bar_look(status["bar"], seen["bar"], now)
        else:
            status["bar"] = rules.bar_fresh()
        after_mode = status["ended_at"] is not None and now - status["ended_at"] < rules.AFTER_MODE
        symptom, text, params, memory = rules.judge(
            seen, profile(), numeral_of, last["monotonic"] if last else None, status["resumed"], memory, now,
            after_mode)
        status["resumed"] = False
        status["symptom"] = symptom
        if symptom is None:
            # The next observed healthy screen completes this redirect
            # episode. Retries before that observation share one notice.
            status["redirect_episode"] = None
        held = ports.lease.state()
        context = {"input_wall": last["wall"] if last else None,
                   "lease": held["holder"] if held and held["holder"] != "watchdog" else None,
                   "act": {kind: farming["switches"]()[switch] == "real" for kind, switch in FARMING.items()}
                   if farming else {}, "available": available, "jitter": random.uniform(-1.0, 1.0),
                   "mode": name}
        if symptom in (None, "unparked") and name in FARMED:
            modes["confirm"](name)
        memory, actions = rules.decide(memory, symptom, text, params, context, wall)
        ports.store.save()
        minutes = rules.waiting(memory, symptom, wall)
        if minutes is not None:
            show(ports.t("{what} ; prochain essai dans {minutes} min", what=ports.t(text, **params), minutes=minutes))
        else:
            show(ports.t(text, **params))
        observed = ports.t(text, **params)
        redirect = next((action[1] for action in actions if action[0] == "repair"), None)
        intention = rules.redirect_intention(redirect, profile()) if redirect else None
        redirect_key = json.dumps(intention, sort_keys=True) if intention else None
        new_redirect = bool(redirect and status["redirect_episode"] != redirect_key)
        redirect_notified = False

        async def announce_redirect():
            nonlocal redirect_notified
            if new_redirect and not redirect_notified:
                notice = rules.redirect_notice(intention, observed)
                said = say("normal", notice, notify=True)
                await ports.notify(said)
                status["redirect_episode"] = redirect_key
                memory["notified"] = {**memory["notified"], redirect: wall}
                redirect_notified = True

        repaired = False
        for action in actions:
            if action[0] == "record":
                _, level, text, values, notify = action
                if notify and new_redirect and not redirect_notified:
                    text = rules.redirect_notice(rules.redirect_intention(redirect, profile()), ports.t(text, **values) if not ports.is_t(text) else text)
                    values = None
                    redirect_notified = True
                    status["redirect_episode"] = redirect_key
                said = say(level, text, values, notify)
                if notify:
                    await ports.notify(said)
            elif action[0] == "repair" and action[1] in ("relaunch", "mine_relaunch"):
                await announce_redirect()
                ports.store.save()
                await relaunch(action[1])
                repaired = True
            elif action[0] == "repair" and (action[1] in FARMING or action[1] == "park"):
                await announce_redirect()
                ports.store.save()
                await farm_repair(action[1])
                repaired = True
            elif action[0] == "plan":
                say("normal", "Plan only (switch on plan): {repair}", {"repair": rules.REPAIR_NAMES[action[1]]})
        return repaired

    async def watch():
        # Poll only the input timestamp between regular looks. A fresh input
        # is reflected at once, then the first look after the 5 s pause is
        # scheduled at its expiry. Full game checks keep their 15 s cadence.
        input_stamp = None
        resume_at = None
        next_look = ports.clock.monotonic() + rules.EVERY
        monitor_input = callable(getattr(ports.lease, "last_input", None))
        while True:
            try:
                if not monitor_input:
                    await ports.clock.sleep(rules.EVERY)
                    await tick()
                    continue
                now = ports.clock.monotonic()
                last = ports.last_input()
                stamp = last["monotonic"] if last else None
                if stamp != input_stamp:
                    input_stamp = stamp
                    if stamp is not None and now - stamp < rules.PAUSE_AFTER_INPUT:
                        resume_at = stamp + rules.PAUSE_AFTER_INPUT
                        await tick()
                        next_look = ports.clock.monotonic() + rules.EVERY
                now = ports.clock.monotonic()
                if resume_at is not None and now >= resume_at:
                    resume_at = None
                    await tick()
                    next_look = ports.clock.monotonic() + rules.EVERY
                elif now >= next_look:
                    await tick()
                    next_look = ports.clock.monotonic() + rules.EVERY
                now = ports.clock.monotonic()
                await ports.clock.sleep(rules.input_wake_delay(now, next_look, resume_at))
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
        return {"mode": status["mode"], "status": status["text"], "line": line(),
                "waiting": sorted(kind for kind, kept in memory["backoff"].items() if kept["next"] > wall),
                "symptom": status["symptom"], "paused_t": status["text"] if status["paused"] else None,
                "repairing": status["repairing"], "intention": status["intention"],
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
            return ports.respond({"error_t": ports.t("{field} : un de {choices}", field="kind",
                                                     choices=", ".join(rules.REPAIR_NAMES))}, status=400)
        memory = rules.retry(memory, kind)
        ports.store.save()
        say("normal", "Retry now: {repair}", {"repair": rules.REPAIR_NAMES[kind]})
        return ports.respond(state())

    def last_look():
        """Its last look, for the mode's overlay tone: {mode, level}."""
        symptom = status["symptom"]
        return {"mode": status["mode"], "level": rules.level(symptom),
                "message_t": status["text"],
                "repairing": status["repairing"], "intention": status["intention"],
                "blocked": bool(memory["alerted"] and symptom in rules.ERRORS
                                and not status["repairing"])}

    return {"routes": [("GET", "/watchdog", handle_state), ("POST", "/watchdog/retry", handle_retry)],
            "startup": [start], "api": {"look": last_look}}
