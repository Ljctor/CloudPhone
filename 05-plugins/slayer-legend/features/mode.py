"""What the game is set to do: farming mpw18 (the default), or for a time
farming mpw4, free play or the Closed Mine; back to mpw18 when the timer
ends (the mine ends its last entry first).

GET  /mode         {mode, default, until, stage18, stage4, highest, configured, state, message_t, setup, tone,
                    gold, mine, intention} (message_t: a status text, texts.py)
                   setup: true while the mode is being set up (its switch,
                   waiting for the lease or tried again), for the overlay;
                   intention: active destination/purpose, route null unless computed
                   tone: the overlay's colour, "ok", "hold", "setup" or
                   "error" (rules.tone)
POST /mode         {mode, default, until, stage18, stage4, highest, floor, area}: a number
                   absent or null keeps its value; until absent keeps the
                   timer, null clears it (no time limit)
POST /mode/setup   {mode, if_revision}: explicitly retry the accepted target; 202 queues
                   the existing leased pipeline, never an equipment success
POST /mode/timer   {add: minutes}: moves the end of the mode (and of the mine)
POST /mode/hold    {action: "free" | "resume"[, hold: id]}: a switch on hold
                   while the user plays: free play instead, or the switch
                   now (the user's 10 s not waited for); 409 when nothing
                   is on hold, the same action again changes nothing

Entering mpw18 or mpw4 farming brings the game there in the background
(features/stage_change.py): the mode's stage, its Battle settings preset,
then its soul weapon equipped, and it parks on the Soul Weapon screen
(AUTO is never tapped); a step that fails stops it with
one alert naming the step. Entering free play or the mine leaves that
screen, when the game shows it and the user is not playing. It
starts at once on its trigger (POST /mode, or the timer's end: the watch
wakes on it), within rules.SWITCH_BUDGET seconds; a switch that stops is
tried again on its own with a backoff (rules.retry_after) while within
that budget, and only then alerts once; a failed setup stays failed until
the complete requested configuration is verified (health alone is not
setup readiness). Once set up, one
notification says how long it took since the mode was chosen ("Farming
mpw18 ready in 34 s"), the slowest step named when over the budget. A
change of the running farming mode's loadout (engraving's on_change:
stage, preset, soul weapon) runs the same path at once (loadout_changed),
the soul weapon alone by its step alone (the stage change feature's
ensure_soul_weapon), notified "Loadout mpw18 applied in 21 s".
Each switch is one log line with its steps' seconds. While the user
played in the last 10 s with the game in front (the lease refused:
rules.USER_PLAYING; an input elsewhere, the game not running, is not
playing: the switch goes on), the
switch is on hold: one alert says so with the delay before its next try
("Switch to farming mpw18 on hold: you are playing. Next try in 10
s."), once per switch however long the wait; GET /mode's hold gives it
({id, mode, left}) for the page's two buttons, POST /mode/hold their
answer: « free » chooses free play, « resume » runs the switch now; with
no answer it goes on by itself once the 10 s are over. The ready
notification says the hold apart ("ready in 45 s (including 10 s waiting:
you were playing)"). While
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
import secrets
import copy



def mode(ports, rules, timer, values, mines, screens, scroll, loadouts, farming):
    """mines: the mine feature's api (start, stop, state, set_until, ended);
    scroll: gold_scroll.py; loadouts: the engraving feature's api (loadout,
    stage, set_stage, adopt_stage), which holds the mpw18 and mpw4 stages
    and presets; farming: the stage change feature's api (farm)."""
    t = ports.t
    status = {"mode": rules.DEFAULT, "default": rules.DEFAULT, "until": None, "highest": None,
              "configured": False, "state": "idle", "message": None, "task": None,
              "scroll": scroll.fresh(), "gold_look": None, "warned": None, "change": None,
              "switch": None, "switch_at": None,
              # hold: the switch on hold while the user plays ({id, mode,
              # until (monotonic), owner, action}), last_hold: the one that
              # ended last ({id, action}), wake: wakes the switch's wait.
              "hold": None, "last_hold": None, "wake": None,
              # watched(): the watchdog's last look ({mode, level}), once wired.
              "watched": None, "intention": None, "resource_refresh": None, "setup_result": None, "launch_epoch": 0}
    ports.store.register("mode", lambda: {key: status[key] for key in (
        "mode", "default", "until", "highest", "configured")})

    game = getattr(ports, "game", None)
    no_change = object()
    replacements = {"pending": no_change, "task": None}
    stopping = set()

    def highest():
        """The highest stage seen: the game's state (features/game.py)."""
        return game["value"]("highest") if game is not None else status["highest"]

    def stages():
        return {"stage18": loadouts["stage"]("mpw18"), "stage4": loadouts["stage"]("mpw4")}

    def report(state, message):
        """The mode's state and its message (a status text)."""
        if (status["state"], status["message"]) != (state, message):
            ports.log("error" if state == "failed" else "normal",
                      f"Mode {status['mode']}: {state}" + (f" ({ports.english(message)})" if message else ""))
        status["state"], status["message"] = state, message
        ports.store.save()

    def input_mark():
        latest = ports.last_input() if callable(getattr(ports, "last_input", None)) else None
        return (latest.get("wall"), latest.get("monotonic")) if isinstance(latest, dict) else None

    def setup_blocker():
        name = status["mode"]
        if name not in ("mpw18", "mpw4") or mines["state"]().get("enabled"):
            return None
        chosen = loadouts["loadout"](name).get("soul_weapon")
        if not chosen:
            return None
        switch = farming.get("soul_weapon_switch")
        if switch and switch() == "off":
            return t("Soul Weapon désactivée : configuration demandée non appliquée")
        capability = loadouts.get("applicability")
        support = capability(chosen) if capability else None
        if support and not support["supported"]:
            return support.get("reason_t")
        if (not support or support.get("engraving_required", True)) and engraving_off(name):
            # An off switch does not tell us whether it is the initial gate
            # or a later explicit stop. State the fact and supervision policy,
            # never invent a never-completed first-run history.
            return t("Gravure automatique désactivée · premier passage soumis à supervision")
        return None

    def current_setup_result():
        result = status["setup_result"]
        revision = loadouts.get("revision")
        if not result or not revision or result["mode"] != status["mode"] or mines["state"]().get("enabled"):
            return None
        age = ports.clock.wall() - result["at"]
        if (not 0 <= age <= 120 or result["revision"] != revision(result["mode"])
                or result["input_mark"] != input_mark() or result["launch_epoch"] != status["launch_epoch"]):
            return None
        return {key: value for key, value in result.items() if key not in ("input_mark", "launch_epoch")}

    def invalidate_setup_result(*_args):
        status["launch_epoch"] += 1

    if callable(getattr(ports, "on_relaunch", None)):
        ports.on_relaunch(invalidate_setup_result)

    def state():
        answer = {key: status[key] for key in ("mode", "default", "until", "configured", "state")}
        answer["highest"] = highest()
        answer["message_t"] = status["message"]
        answer["setup_blocker_t"] = setup_blocker()
        answer["setup_result"] = current_setup_result()
        answer["setup_request"] = setup_request()
        if status["state"] == "failed" and status["setup_result"] and answer["setup_result"] is None:
            answer["message_t"] = t("Configuration demandée non vérifiée")
        answer.update(stages())
        answer["setup"] = status["state"] in ("moving", "waiting")
        answer["intention"] = active_intention()
        hold = status["hold"]
        answer["hold"] = ({"id": hold["id"], "mode": hold["mode"],
                           "left": max(0, round(hold["until"] - ports.clock.monotonic()))} if hold else None)
        answer["gold"] = status["scroll"]["gold"] if status["mode"] == "mpw4" else None
        answer["mine"] = mines["state"]()
        answer["tone"] = tone(answer["mine"])
        if answer["tone"] == "error" and not answer["message_t"] and status["watched"]:
            look = status["watched"]()
            if look and look.get("mode") == answer["mode"]:
                answer["message_t"] = look.get("message_t")
        return answer

    def setup_request():
        """A current target receipt, not evidence that it has been applied."""
        name = status["mode"]
        change = status["change"]
        replacing = replacements["task"]
        revision = loadouts.get("revision")
        if (not ports.enabled() or not status["configured"] or name not in ("mpw18", "mpw4")
                or mines["state"]().get("enabled") or not loadouts["stage"](name)
                or not revision or setup_blocker()
                or change is not None and not change.done()
                or replacing is not None and not replacing.done()):
            return None
        return {"mode": name, "if_revision": revision(name)}

    def engraving_off(name):
        """The farming mode's loadout asks an engraving while the
        engraving's switch is off (features/soul_weapon.py)."""
        switch = farming.get("engraving_switch") if isinstance(farming, dict) else None
        if name not in ("mpw18", "mpw4") or switch is None or switch() != "off":
            return False
        weapon = loadouts["loadout"](name).get("soul_weapon") or {}
        variant = loadouts.get("variant")
        return bool(weapon.get("variant") and variant and variant(weapon.get("id"), weapon["variant"]))

    def tone(mine):
        """The overlay's colour (rules.tone)."""
        name = "mine" if mine.get("enabled") else status["mode"]
        look = status["watched"]() if status["watched"] else None
        playing = (ports.pause_left() or 0) > 0 if hasattr(ports, "pause_left") else False
        watched = look if look and look.get("mode") == name else None
        base = rules.tone(name, status["state"], status["hold"] is not None, playing,
                          watched, mine.get("state") if name == "mine" else None, engraving_off(name))
        if (name in ("mpw18", "mpw4") and setup_blocker() and not playing and not status["hold"]
                and status["state"] not in ("moving", "waiting") and not (watched or {}).get("repairing")):
            return "error"
        return base

    def watched_by(look):
        """look(): the watchdog's last look (its api's look)."""
        status["watched"] = look

    def switched(answer, since, waited, applied=False):
        """The switch's log line, and its alert when over budget: since,
        its trigger; waited, the seconds it waited for the lease (the
        user's or another holder's, not counted)."""
        before, after = status["switch"] or ("?", status["mode"])
        line, alert = rules.switch_report(before, after, ports.clock.monotonic() - since - waited,
                                          answer.get("timings") or {}, waited, applied)
        ports.log("warning" if alert else "normal", f"{line}, {answer['result']}", notify=bool(alert))
        return alert

    def end_hold(action):
        """The hold is over (action: "free", "resume", "timeout" once the
        lease was had, "ended" when the switch ended otherwise)."""
        hold = status["hold"]
        if hold is None:
            return
        status["hold"] = None
        status["last_hold"] = {"id": hold["id"], "action": action}
        # The alert's buttons are out of date.
        revoke = getattr(ports, "revoke_action", None)
        if revoke and hold.get("token"):
            revoke(hold["token"])
        ports.log("normal", f"Mode {hold['mode']}: hold {hold['id']} over ({action})")

    async def pause(seconds):
        """Sleeps seconds, or less when POST /mode/hold wakes it."""
        wake = status["wake"] = asyncio.Event()
        sleeper = asyncio.ensure_future(ports.clock.sleep(seconds))
        waker = asyncio.ensure_future(wake.wait())
        try:
            await asyncio.wait({sleeper, waker}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sleeper.cancel()
            waker.cancel()
            if status["wake"] is wake:
                status["wake"] = None

    async def on_hold(name, applied, owner, alerted):
        """The user played in the last 10 s: the switch is on hold until
        the 10 s are over (its hold made, or moved later), one alert the
        first time for this switch (alerted: it was sent). True once
        alerted."""
        left = ports.pause_left() or rules.BUSY_RETRY
        hold = status["hold"]
        if hold is None or hold["owner"] is not owner:
            hold = status["hold"] = {"id": secrets.token_hex(4), "mode": name, "owner": owner, "action": None,
                                     "applied": applied}
            ports.log("normal", f"Mode {name}: switch on hold {hold['id']}, the user plays "
                      f"({round(left)} s left)")
        hold["until"] = ports.clock.monotonic() + left
        report("waiting", rules.hold_message(name, left, applied))
        if not alerted:
            # Its two buttons: a one-time token, never the page's.
            issue = getattr(ports, "action_token", None)
            hold["token"] = issue("/mode/hold", rules.HOLD_TOKEN_SECONDS) if issue else None
            buttons = rules.hold_buttons(hold["id"], hold["token"])
            text = rules.hold_alert(name, left, applied)
            await (ports.notify(text, actions=buttons) if buttons else ports.notify(text))
        return left

    def active_intention():
        current = status["intention"]
        if current:
            return {key: value for key, value in current.items() if key != "owner"}
        getter = status["resource_refresh"]
        refresh = getter() if getter else None
        return refresh.get("intention") if refresh and refresh.get("active") else None

    def resource_refresh_by(getter):
        status["resource_refresh"] = getter

    async def set_stage(number, mpw, applied=False, step=None):
        name = f"mpw{mpw}"
        parked = farming.get("soul_weapon_switch", lambda: "off")() == "real"
        owner = object()
        revision = loadouts.get("revision")
        mark = input_mark()
        epoch = status["launch_epoch"]
        target_revision = revision(name) if revision else None
        target = copy.deepcopy(loadouts["loadout"](name))
        status["setup_result"] = None
        status["intention"] = {"owner": owner, "kind": "apply_loadout",
                               "destination": "soul_weapon" if parked or step else "battle",
                               "destination_t": t("Soul Weapon") if parked or step else t("Combat"),
                               "purpose_t": t("appliquer la configuration demandée de {mode}", mode=name),
                               "route": None, "route_known": False}
        try:
            completed = await apply_stage(number, mpw, applied, step)
            if (revision and status["mode"] == name and target_revision == revision(name)
                    and target.get("stage") == number and mark == input_mark() and epoch == status["launch_epoch"]):
                status["setup_result"] = {"mode": name, "revision": target_revision, "target": target,
                                          "at": ports.clock.wall(), "result": "done" if completed else status["state"],
                                          "message_t": status["message"], "input_mark": mark, "launch_epoch": epoch}
            return completed
        finally:
            if status["intention"] and status["intention"]["owner"] is owner:
                status["intention"] = None

    async def apply_stage(number, mpw, applied=False, step=None):
        """Brings the game to farming that stage with its loadout's preset.
        True once there; else one alert naming the step. While the
        shared lease cannot be had (the user played in the last 10 s,
        another holder), it waits for its next look (WATCH_EVERY), at most
        rules.LEASE_WAIT: then one alert, for the user. While the user
        plays it is on hold (on_hold: one alert, POST /mode/hold's choice).
        Set up: one notification with the seconds since the mode was chosen
        (applied: since its loadout changed), naming the slowest step when
        over rules.SWITCH_BUDGET. step: what runs in place of farm() (a
        coroutine function: the soul weapon step alone, taking force)."""
        name = f"mpw{mpw}"
        preset = loadouts["loadout"](name).get("preset")
        moving = t("Passage au stage {number} ({name})", number=number, name=name)
        report("moving", moving)
        since = status["switch_at"] if status["switch_at"] is not None else ports.clock.monotonic()
        waited, held, failures = 0.0, 0.0, 0
        # force: resumed at the user's request, the user's 10 s are not
        # waited for, retries included, until an input of theirs stops it.
        me, alerted, force = object(), False, False
        try:
            while True:
                began = ports.clock.monotonic()
                hold = status["hold"]
                if hold and hold["owner"] is me and hold["action"] == "resume":
                    force = True
                    end_hold("resume")
                    report("moving", t("{switch} : repris à ta demande", switch=moving))
                try:
                    forced = {"force": True} if force else {}
                    answer = await (step(**forced) if step
                                    else farming["farm"](number, preset, name, highest(), **forced))
                except ports.Busy as e:
                    if not ports.enabled():
                        # The plugin off: it waits for as long, no alert.
                        since = ports.clock.monotonic()
                    if ports.clock.monotonic() - since >= rules.LEASE_WAIT:
                        report("failed", t("{switch} : bail toujours pris après 30 min ({why})", switch=moving, why=e.t))
                        await ports.notify(f"Switch to stage {number} ({name}) failed: lease still taken after 30 min "
                                           f"({e})")
                        return False
                    if e.t["template"] == rules.USER_PLAYING:
                        force = False
                        left = await on_hold(name, applied, me, alerted)
                        alerted = True
                        await pause(min(rules.BUSY_RETRY, left))
                        held += ports.clock.monotonic() - began
                    else:
                        report("waiting", t("{switch} en attente : {why}", switch=moving, why=e.t))
                        await ports.clock.sleep(rules.BUSY_RETRY)
                    waited += ports.clock.monotonic() - began
                    continue
                if status["hold"] and status["hold"]["owner"] is me:
                    end_hold("timeout")
                if answer["result"] != "failed":
                    break
                failures += 1
                delay = rules.retry_after(failures, ports.clock.monotonic() - since - waited)
                if delay is None:
                    break
                ports.log("normal", f"Mode {name}: switch stopped ({ports.english(answer['text_t'])}), "
                          f"attempt {failures + 1} in {delay} s")
                report("moving", t("{switch} : nouvel essai dans {delay} s ({why})", switch=moving, delay=delay,
                                   why=answer["text_t"]))
                await ports.clock.sleep(delay)
        finally:
            if status["hold"] and status["hold"]["owner"] is me:
                end_hold("ended")
        alert = switched(answer, since, waited, applied)
        if answer["result"] == "done":
            await ports.notify(rules.ready_text(name, ports.clock.monotonic() - since, applied, alert, held))
        if answer["result"] == "failed":
            report("failed", t("{switch} arrêté : {why}", switch=moving, why=answer["text_t"]))
            await ports.notify(f"Switch to stage {number} ({name}) stopped: {ports.english(answer['text_t'])}")
            return False
        if answer["result"] == "plan":
            report("plan", t("{switch}, plan seul : {plan}", switch=moving, plan=answer["text_t"]))
            return False
        report("farming", farming_text(name, number, preset))
        return True

    def farming_text(name, number, preset):
        if preset:
            return t("Farming {name} au stage {number}, preset {preset}", name=name, number=number, preset=preset)
        return t("Farming {name} au stage {number}", name=name, number=number)

    def confirm(name, *, verified_setup=False):
        """Health alone cannot clear a failed loadout setup. Only a caller
        that verified the complete requested setup may resolve that failure."""
        if verified_setup and status["mode"] == name and status["state"] == "failed":
            ports.log("normal", f"Mode {name}: complete setup verified")
            report("farming", farming_text(name, loadouts["stage"](name), loadouts["loadout"](name).get("preset")))

    def replace_change(start):
        """One coordinator drains cancellation before starting its successor.
        Further requests replace only the queued command, never the draining
        task. Even a successor cancelled before its first turn cannot let a
        third request bypass its predecessor's unfinished cleanup."""
        task = replacements["task"]
        previous = status["change"]
        if (task is None or task.done()) and (previous is None or previous.done()):
            if previous is not None and not previous.cancelled():
                previous.exception()
            status["change"] = ports.spawn(start()) if start is not None else None
            return
        replacements["pending"] = start

        def stop(previous):
            if not previous.done() and previous not in stopping:
                stopping.add(previous)
                previous.add_done_callback(stopping.discard)
                previous.cancel()

        async def replace():
            while replacements["pending"] is not no_change:
                wanted = replacements["pending"]
                replacements["pending"] = no_change
                previous = status["change"]
                if previous is not None:
                    stop(previous)
                    if not previous.done():
                        terminal = asyncio.get_running_loop().create_future()

                        def finished(task):
                            if not terminal.done():
                                terminal.set_result(None)

                        previous.add_done_callback(finished)
                        try:
                            # Predecessor cancellation completes this future
                            # normally; coordinator cancellation still propagates.
                            # No Python3.11 Task.cancelling() dependency.
                            await asyncio.shield(terminal)
                        finally:
                            previous.remove_done_callback(finished)
                    if not previous.cancelled() and previous.exception() is not None:
                        ports.log("error", f"Previous mode transaction failed while stopping: {previous.exception()!r}")
                    status["change"] = None
                if replacements["pending"] is not no_change:
                    continue  # only the most recent request is still wanted
                if wanted is not None:
                    status["change"] = ports.spawn(wanted())

        if task is None or task.done():
            if previous is not None:
                stop(previous)
            replacements["task"] = ports.spawn(replace())

    async def enter(name, before=None):
        """What changing to mode name does (rules.entered): a stage change
        runs in the background at once, the one under way is dropped.
        before: the mode it leaves (the switch's log line), its trigger
        now."""
        status.update(switch=(before or "?", name), switch_at=ports.clock.monotonic())
        move = rules.entered(name, stages()["stage18"], stages()["stage4"])

        async def start():
            if move[0] == "stage":
                await set_stage(move[1], move[2])
            elif move[0] == "choose":
                report("idle", t("Farming {name} : choisis le stage", name=f"mpw{move[1]}"))
            elif move[0] in ("free", "agent"):
                report("free", free_text() if name == "free" else t("Agent mode : agent autorisé à jouer"))
            else:
                report("mine", t("Mine"))
            if move[0] in ("free", "agent", "mine") and "unpark" in farming:
                await leave_park(name)

        replace_change(start)

    async def leave_park(name):
        """Free play or the mine starts: the farming modes' parking (the
        Soul Weapon screen) is left, when the game shows it; while the
        user plays (the lease refused) nothing is touched."""
        owner = object()
        status["intention"] = {"owner": owner, "kind": "leave_farming", "destination": "battle",
                               "destination_t": t("Combat"),
                               "purpose_t": t("libérer le jeu pour {mode}", mode=name),
                               "route": None, "route_known": False}
        try:
            answer = await farming["unpark"](name)
        except ports.Busy as e:
            ports.log("normal", f"Mode {name}: the Soul Weapon screen not left: {ports.english(e.t)}")
            return
        finally:
            if status["intention"] and status["intention"]["owner"] is owner:
                status["intention"] = None
        if answer["result"] == "failed":
            ports.log("warning", f"Mode {name}: leaving the Soul Weapon screen stopped: "
                      f"{ports.english(answer['text_t'])}")

    def loadout_changed(name, before, after):
        """The engraving feature's on_change: a change of the running
        farming mode's loadout (its stage, preset or soul weapon) is
        applied at once, by the switch's own path (rules.SWITCH_BUDGET,
        retried, one notification « Configuration mpwN appliquée en N
        s »); the soul weapon alone by its step alone."""
        fields = rules.loadout_changes(before, after)
        if not status["configured"] or name != status["mode"] or name not in ("mpw18", "mpw4") or not fields:
            return
        ports.log("normal", f"Mode {name}: loadout changed ({', '.join(sorted(fields))}), applied now")
        status.update(switch=(name, name), switch_at=ports.clock.monotonic())
        if not after.get("stage"):
            async def idle():
                report("idle", t("Farming {name} : choisis le stage", name=name))
            replace_change(idle)
            return
        step = None
        if fields == {"soul_weapon"} and "ensure_soul_weapon" in farming:
            step = lambda **forced: farming["ensure_soul_weapon"](name, after, **forced)
        replace_change(lambda: set_stage(after["stage"], int(name[3:]), applied=True, step=step))

    def free_text():
        return (t("Jeu libre : rien n’est touché jusqu’à la fin du minuteur") if status["until"]
                else t("Jeu libre : rien n’est touché"))

    async def back_to_default(why):
        """A timed mode ended (why: rules.due's): back to the default mode
        (« Mode par défaut »), by the same switch; one alert says why."""
        before, default = status["mode"], status["default"]
        status.update(mode=default, until=None)
        stage = loadouts["stage"](default) if default in ("mpw18", "mpw4") else None
        detail = ports.english(mines["state"]().get("message_t"))
        await ports.notify(rules.back_text(why, default, stage, detail))
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
            ports.log("normal", f"Mode mpw4: gold scroll {news}")
            await ports.notify("Farming mpw4: " + ("no more gold scroll" if news == "gone" else "gold scroll back"))

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
                    await back_to_default(why)
                elif rules.warn_due(status["mode"], status["until"], status["warned"], ports.clock.wall()):
                    status["warned"] = status["until"]
                    ports.log("normal", "Mode free: 2 minutes left, user warned")
                    await ports.notify(rules.WARNING)
                elif status["mode"] == "mpw4" and rules.gold_due(status["gold_look"], ports.clock.monotonic()):
                    status["gold_look"] = ports.clock.monotonic()
                    await look_for_gold()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ports.exception("Mode failed")
            report("failed", t("Erreur : {error}", error=f"{e!r}"[:200]))

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
        asked, error = rules.request(body, {**stages(), "highest": highest(),
                                            "floor": mine["floor"], "area": mine["area"]}, status["default"])
        if error:
            return ports.respond({"error_t": error}, status=400)
        name, until, numbers, given = asked
        default, error = rules.default_request(body, numbers, status["default"])
        if error:
            return ports.respond({"error_t": error}, status=400)
        before = status["mode"]
        changed = name != before
        if default != status["default"]:
            ports.log("normal", f"Mode: default mode {status['default']} → {default}")
        until = rules.timer_for(name, until, given, status["mode"], status["until"], ports.clock.wall(), default)
        status.update(mode=name, default=default, until=until, configured=True)
        if game is not None and numbers["highest"]:
            game["note"]({"highest": numbers["highest"]}, "page")
        elif game is None:
            status["highest"] = numbers["highest"]
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
            return ports.respond({"error_t": t("Attendu : {expected}", expected="{add: minutes}")}, status=400)
        status["until"] = timer.moved(status["until"], add, ports.clock.wall())
        if status["mode"] == "mine":
            mines["set_until"](status["until"])
        ports.store.save()
        return ports.respond(state())

    async def go_free():
        """POST /mode/hold's « free »: free play, as its radio button
        chooses it (timed, unless it is the default mode)."""
        before = status["mode"]
        until = rules.timer_for("free", None, False, before, status["until"], ports.clock.wall(),
                                status["default"])
        status.update(mode="free", until=until, configured=True, scroll=scroll.fresh(), gold_look=None)
        mines["stop"]()
        await enter("free", before)
        watch_if_timed()
        ports.store.save()

    async def handle_hold(request):
        """{action: "free" | "resume"[, hold: id]}: the user's answer to a
        switch on hold (the page's buttons, the phone alert's)."""
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        action, error = rules.hold_request(body, status["hold"], status["last_hold"])
        if error:
            return ports.respond({"error_t": error[1]}, status=error[0])
        if action == "free":
            hold = status["hold"]
            ports.log("normal", f"Mode {hold['mode']}: on hold, free play asked")
            end_hold("free")
            await go_free()
        elif action == "resume":
            hold = status["hold"]
            hold["action"] = "resume"
            ports.log("normal", f"Mode {hold['mode']}: on hold, resumed now")
            if status["wake"] is not None:
                status["wake"].set()
        return ports.respond(state())

    async def handle_setup(request):
        """Explicitly recheck/apply the accepted target without changing it.
        No force: user activity still pauses the existing leased pipeline."""
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if (not isinstance(body, dict) or body.get("mode") not in ("mpw18", "mpw4")
                or not isinstance(body.get("if_revision"), str)):
            return ports.respond({"error_t": t("Attendu : {expected}",
                                 expected="{mode, if_revision}")}, status=400)
        expected = setup_request()
        if expected is None:
            reason = setup_blocker() or t("Configuration indisponible ou application déjà en cours")
            return ports.respond(dict(state(), error_t=reason), status=409)
        if any(body[key] != value for key, value in expected.items()):
            return ports.respond(dict(state(), error_t=t("Configuration modifiée ailleurs : recharge la cible avant d’appliquer")), status=409)
        name = expected["mode"]
        number = loadouts["stage"](name)
        status.update(switch=(name, name), switch_at=ports.clock.monotonic(), setup_result=None)
        report("moving", t("Application de la configuration {mode}", mode=name))
        replace_change(lambda: set_stage(number, int(name[3:]), applied=True))
        return ports.respond(state(), status=202)

    async def resume(app):
        """At the gateway's start: the timed mode state.json kept goes on."""
        if rules.watched(status["mode"], status["default"]):
            report(*{"free": ("free", free_text()), "agent": ("free", t("Agent mode : agent autorisé à jouer")),
                     "mine": ("mine", t("Mine"))}.get(status["mode"], ("idle", t("Farming {name}", name=status["mode"]))))
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
        ports.log("normal", f"Timer ended while the gateway was stopped ({', '.join(stopped)}): "
                  f"back to the default mode {status['default']}, mine off"
                  + (" once Repeat entry is unticked" if mines["state"]()["state"] == "stopping" else ""))

    # After the stages of an older state.json moved: not a change to apply.
    if "on_change" in loadouts:
        loadouts["on_change"](loadout_changed)

    return {
        "routes": [("GET", "/mode", handle_state), ("POST", "/mode", handle_mode), ("POST", "/mode/timer", handle_timer),
                   ("POST", "/mode/hold", handle_hold), ("POST", "/mode/setup", handle_setup)],
        "startup": [resume],
        # For the watchdog: the mode now (it runs only in the default one).
        "api": {"state": state, "confirm": confirm, "watched_by": watched_by,
                "resource_refresh_by": resource_refresh_by},
    }
