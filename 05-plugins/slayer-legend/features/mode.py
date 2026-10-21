"""What the game is set to do: farming mpw18 (the default), or for a time
farming mpw4, free play or the Closed Mine; back to mpw18 when the timer
ends (the mine ends its last entry first).

GET  /mode         {mode, default, until, stage18, stage4, highest, configured, state, message, setup, gold,
                    mine}
                   setup: true while the mode is being set up (its switch,
                   waiting for the lease or tried again), for the overlay
POST /mode         {mode, default, until, stage18, stage4, highest, floor, area}: a number
                   absent or null keeps its value; until absent keeps the
                   timer, null clears it (no time limit)
POST /mode/timer   {add: minutes}: moves the end of the mode (and of the mine)

Entering mpw18 or mpw4 farming brings the game there in the background
(features/stage_change.py): the mode's stage, its Battle settings preset,
AUTO on, then its soul weapon equipped; a step that fails stops it with
one alert naming the step. It
starts at once on its trigger (POST /mode, or the timer's end: the watch
wakes on it), within rules.SWITCH_BUDGET seconds; a switch that stops is
tried again on its own with a backoff (rules.retry_after) while within
that budget, and only then alerts once; a mode left failed is farming
again once the watchdog sees it farm (api confirm); once set up, one
notification says how long it took since the mode was chosen (« Farming
mpw18 prêt en 34 s »), the slowest step named when over the budget. A
change of the running farming mode's loadout (engraving's on_change:
stage, preset, soul weapon) runs the same path at once (loadout_changed),
the soul weapon alone by its step alone (the stage change feature's
ensure_soul_weapon), notified « Configuration mpw18 appliquée en 21 s ».
Each switch is one log line with its steps' seconds. While
farming mpw4 it looks for the
gold scroll every 30 s on the battle screen (gold: true, false once missing
for 2 looks, null unknown) and alerts once when it goes, then once when it
is back (gold_scroll.py, shared with the mine). Free play alerts once 2
minutes before its end, so that a user still playing can extend it. The
rules are in
mode_rules.py; the
mode and its timer are kept in state.json ("mode") and go on after a
gateway restart. The mpw18 and mpw4 stages are those of the modes'
loadouts (features/engraving.py, state.json "loadouts"): stage18 and
stage4 here are read from them and written to them.
"""

import asyncio
import logging

REASONS = {"mine done": "Mine terminée", "mine stopped": "Mine arrêtée", "timer": "Minuteur écoulé"}


def mode(ports, rules, timer, values, mines, screens, scroll, loadouts, farming):
    """mines: the mine feature's api (start, stop, state, set_until, ended);
    scroll: gold_scroll.py; loadouts: the engraving feature's api (loadout,
    stage, set_stage, adopt_stage), which holds the mpw18 and mpw4 stages
    and presets; farming: the stage change feature's api (farm)."""
    status = {"mode": rules.DEFAULT, "default": rules.DEFAULT, "until": None, "highest": None,
              "configured": False, "state": "idle", "message": "", "task": None,
              "scroll": scroll.fresh(), "gold_look": None, "warned": None, "change": None,
              "switch": None, "switch_at": None}
    ports.store.register("mode", lambda: {key: status[key] for key in (
        "mode", "default", "until", "highest", "configured")})

    def stages():
        return {"stage18": loadouts["stage"]("mpw18"), "stage4": loadouts["stage"]("mpw4")}

    def report(state, message):
        if (status["state"], status["message"]) != (state, message):
            logging.info(f"Slayer Legend mode {status['mode']}: {state} {message}")
        status["state"], status["message"] = state, message
        ports.store.save()

    def state():
        answer = {key: status[key] for key in ("mode", "default", "until", "highest", "configured", "state",
                                               "message")}
        answer.update(stages())
        answer["setup"] = status["state"] in ("moving", "waiting")
        answer["gold"] = status["scroll"]["gold"] if status["mode"] == "mpw4" else None
        answer["mine"] = mines["state"]()
        return answer

    def switched(answer, since, waited, applied=False):
        """The switch's log line, and its alert when over budget: since,
        its trigger; waited, the seconds it waited for the lease (the
        user's or another holder's, not counted)."""
        before, after = status["switch"] or ("?", status["mode"])
        line, alert = rules.switch_report(before, after, ports.clock.monotonic() - since - waited,
                                          answer.get("timings") or {}, waited, applied)
        logging.getLogger("cloudphone.slayer-legend").log(
            logging.WARNING if alert else logging.INFO, f"{line}, {answer['result']}",
            extra={"source": "slayer-legend", "notify": bool(alert)})
        return alert

    async def set_stage(number, mpw, applied=False, step=None):
        """Brings the game to farming that stage with its loadout's preset,
        AUTO on. True once there; else one alert naming the step. While the
        shared lease cannot be had (the user played in the last minute,
        another holder), it waits for its next look (WATCH_EVERY), at most
        rules.LEASE_WAIT: then one alert, for the user. Set up: one
        notification with the seconds since the mode was chosen (applied:
        since its loadout changed), naming the slowest step when over
        rules.SWITCH_BUDGET. step: what runs in place of farm() (a
        coroutine function: the soul weapon step alone)."""
        name = f"mpw{mpw}"
        preset = loadouts["loadout"](name).get("preset")
        report("moving", f"Passage au stage {number} ({name})")
        since = status["switch_at"] if status["switch_at"] is not None else ports.clock.monotonic()
        waited, failures = 0.0, 0
        while True:
            began = ports.clock.monotonic()
            try:
                answer = await (step() if step else farming["farm"](number, preset, name, status["highest"]))
            except ports.Busy as e:
                if ports.clock.monotonic() - since >= rules.LEASE_WAIT:
                    text = f"Passage au stage {number} ({name}) : bail toujours pris après 30 min ({e}), à faire à la main"
                    report("failed", text[:200])
                    await ports.notify(text)
                    return False
                report("waiting", f"Passage au stage {number} ({name}) en attente : {e}")
                await ports.clock.sleep(rules.BUSY_RETRY)
                waited += ports.clock.monotonic() - began
                continue
            if answer["result"] != "failed":
                break
            failures += 1
            delay = rules.retry_after(failures, ports.clock.monotonic() - since - waited)
            if delay is None:
                break
            logging.info(f"Slayer Legend mode {name}: switch stopped ({answer['text']}), "
                         f"attempt {failures + 1} in {delay} s")
            report("moving", f"Passage au stage {number} ({name}) : nouvel essai dans {delay} s ({answer['text']})"[:200])
            await ports.clock.sleep(delay)
        alert = switched(answer, since, waited, applied)
        if answer["result"] == "done":
            await ports.notify(rules.ready_text(name, ports.clock.monotonic() - since, applied, alert))
        if answer["result"] == "failed":
            text = f"Passage au stage {number} ({name}) arrêté : {answer['text']}"
            report("failed", text[:200])
            await ports.notify(text)
            return False
        if answer["result"] == "plan":
            report("plan", f"Passage au stage {number} ({name}), plan seul : {answer['text']}"[:200])
            return False
        report("farming", farming_text(name, number, preset))
        return True

    def farming_text(name, number, preset):
        return f"Farming {name} au stage {number}" + (f", preset {preset}" if preset else "")

    def confirm(name):
        """The watchdog saw mode name farm as its loadout says (a look, or
        its repair done): a switch left failed is over."""
        if status["mode"] == name and status["state"] == "failed":
            logging.info(f"Slayer Legend mode {name}: farming, as the watchdog sees it")
            report("farming", farming_text(name, loadouts["stage"](name), loadouts["loadout"](name).get("preset")))

    async def enter(name, before=None):
        """What changing to mode name does (rules.entered): a stage change
        runs in the background at once, the one under way is dropped.
        before: the mode it leaves (the switch's log line), its trigger
        now."""
        status.update(switch=(before or "?", name), switch_at=ports.clock.monotonic())
        change = status["change"]
        if change is not None and not change.done():
            change.cancel()
        status["change"] = None
        move = rules.entered(name, stages()["stage18"], stages()["stage4"])
        if move[0] == "stage":
            status["change"] = ports.spawn(set_stage(move[1], move[2]))
        elif move[0] == "choose":
            report("idle", f"Farming mpw{move[1]} : choisis le stage")
        elif move[0] == "free":
            report("free", free_text())
        else:
            report("mine", "Mine")

    def loadout_changed(name, before, after):
        """The engraving feature's on_change: a change of the running
        farming mode's loadout (its stage, preset or soul weapon) is
        applied at once, by the switch's own path (rules.SWITCH_BUDGET,
        retried, one notification « Configuration mpwN appliquée en N
        s »); the soul weapon alone by its step alone."""
        fields = rules.loadout_changes(before, after)
        if not status["configured"] or name != status["mode"] or name not in ("mpw18", "mpw4") or not fields:
            return
        logging.info(f"Slayer Legend mode {name}: loadout changed ({', '.join(sorted(fields))}), applied now")
        status.update(switch=(name, name), switch_at=ports.clock.monotonic())
        change = status["change"]
        if change is not None and not change.done():
            change.cancel()
        status["change"] = None
        if not after.get("stage"):
            report("idle", f"Farming {name} : choisis le stage")
            return
        step = None
        if fields == {"soul_weapon"} and "ensure_soul_weapon" in farming:
            step = lambda: farming["ensure_soul_weapon"](name, after)
        status["change"] = ports.spawn(set_stage(after["stage"], int(name[3:]), applied=True, step=step))

    def free_text():
        return ("Jeu libre : rien n’est touché jusqu’à la fin du minuteur" if status["until"]
                else "Jeu libre : rien n’est touché")

    async def back_to_default(reason):
        """A timed mode ended: back to the default mode (« Mode par
        défaut »), by the same switch."""
        before, default = status["mode"], status["default"]
        status.update(mode=default, until=None)
        stage = loadouts["stage"](default) if default in ("mpw18", "mpw4") else None
        await ports.notify(f"{reason} : {rules.BACK_TO[default]}" + (f" (stage {stage})" if stage else ""))
        await enter(default, before)

    def gold_facts(shot):
        return scroll.seen(screens.classify(shot) == "battle", shot)

    async def look_for_gold():
        """mpw4 farming: one look for the gold scroll, with the shared
        screenshot; one alert when it goes, one when it is back."""
        shot = await ports.capture(max_age=rules.WATCH_EVERY)
        if not shot:
            return
        status["scroll"], news = scroll.look(status["scroll"], await ports.analyse(gold_facts, shot))
        if news:
            logging.info(f"Slayer Legend mode mpw4: gold scroll {news}")
            await ports.notify("Farming mpw4 : " + ("plus de parchemin doré" if news == "gone"
                                                    else "parchemin doré rétabli"))

    async def watch():
        """Ends a timed mode: back to the default mode once its time is up
        (the mine ends its last entry first). While farming mpw4, looks for
        the gold scroll."""
        try:
            while rules.watched(status["mode"], status["default"]):
                # Awake right at the timer's end: the switch back starts then.
                await ports.clock.sleep(rules.next_look(status["until"], ports.clock.wall()))
                why = rules.due(status["mode"], status["until"], mines["state"](), ports.clock.wall())
                if why:
                    await back_to_default(REASONS[why])
                elif rules.warn_due(status["mode"], status["until"], status["warned"], ports.clock.wall()):
                    status["warned"] = status["until"]
                    logging.info("Slayer Legend mode free: 2 minutes left, user warned")
                    await ports.notify(rules.WARNING)
                elif status["mode"] == "mpw4" and rules.gold_due(status["gold_look"], ports.clock.monotonic()):
                    status["gold_look"] = ports.clock.monotonic()
                    await look_for_gold()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mode failed")
            report("failed", f"Erreur : {e!r}"[:200])

    def watch_if_timed():
        task = status["task"]
        if rules.watched(status["mode"], status["default"]) and (task is None or task.done()):
            status["task"] = ports.spawn(watch())

    async def handle_state(request):
        return ports.respond(state())

    async def handle_mode(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        mine = mines["state"]()
        asked, error = rules.request(body, {**stages(), "highest": status["highest"],
                                            "floor": mine["floor"], "area": mine["area"]}, status["default"])
        if error:
            return ports.respond({"error": error}, status=400)
        name, until, numbers, given = asked
        default, error = rules.default_request(body, numbers, status["default"])
        if error:
            return ports.respond({"error": error}, status=400)
        before = status["mode"]
        changed = name != before
        if default != status["default"]:
            logging.info(f"Slayer Legend mode: default mode {status['default']} → {default}")
        until = rules.timer_for(name, until, given, status["mode"], status["until"], ports.clock.wall(), default)
        status.update(mode=name, default=default, until=until, configured=True, highest=numbers["highest"])
        loadouts["set_stage"]("mpw18", numbers["stage18"])
        loadouts["set_stage"]("mpw4", numbers["stage4"])
        if name == "mine":
            mines["start"](numbers["floor"], numbers["area"], until)
        else:
            mines["stop"]()
        if changed:
            status.update(scroll=scroll.fresh(), gold_look=None)
            await enter(name, before)
        watch_if_timed()
        ports.store.save()
        return ports.respond(state())

    async def handle_timer(request):
        """{add: minutes, may be negative}: moves the end of the timed mode
        (and of the mine); at or before now there is no time limit."""
        try:
            add = float((await request.json()).get("add"))
        except (ValueError, TypeError, AttributeError):
            return ports.respond({"error": "Expected {add: minutes}"}, status=400)
        status["until"] = timer.moved(status["until"], add, ports.clock.wall())
        if status["mode"] == "mine":
            mines["set_until"](status["until"])
        ports.store.save()
        return ports.respond(state())

    async def resume(app):
        """At the gateway's start: the timed mode state.json kept goes on."""
        if rules.watched(status["mode"], status["default"]):
            report(*{"free": ("free", free_text()),
                     "mine": ("mine", "Mine")}.get(status["mode"], ("idle", f"Farming {status['mode']}")))
            status["task"] = ports.spawn(watch())

    saved = ports.store.saved.get("mode") or {}
    status.update(mode=saved.get("mode") if saved.get("mode") in rules.MODES else rules.DEFAULT,
                  default=saved.get("default") if saved.get("default") in rules.DEFAULTS else rules.DEFAULT,
                  until=values.time_or_none(saved.get("until")), configured=saved.get("configured") is True,
                  highest=values.number_or_none(saved.get("highest"), 99999))
    # Earlier versions kept the stages here: they move to the loadouts.
    for key, name in (("stage18", "mpw18"), ("stage4", "mpw4")):
        loadouts["adopt_stage"](name, values.number_or_none(saved.get(key), 99999))
    before = status["mode"]
    status["mode"], status["until"], ended = rules.restored(status["mode"], status["until"],
                                                            mines["state"]()["enabled"], ports.clock.wall(),
                                                            status["default"])
    stopped = [f"mode {before}"] if ended else []
    if mines["ended"]:
        stopped.append("mine")
    if stopped:
        logging.info(f"Slayer Legend: timer ended while the gateway was stopped ({', '.join(stopped)}): "
                     f"back to the default mode {status['default']}, mine off"
                     + (" once Repeat entry is unticked" if mines["state"]()["state"] == "stopping" else ""))

    # After the stages of an older state.json moved: not a change to apply.
    if "on_change" in loadouts:
        loadouts["on_change"](loadout_changed)

    return {
        "routes": [("GET", "/mode", handle_state), ("POST", "/mode", handle_mode), ("POST", "/mode/timer", handle_timer)],
        "startup": [resume],
        # For the watchdog: the mode now (it runs only in the default one).
        "api": {"state": state, "confirm": confirm},
    }
