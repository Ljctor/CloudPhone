"""Farms the Closed Mine from the gateway, so it goes on with the page
closed.

GET  /mine         {enabled, floor, area, until, gold, state, message_t}
POST /mine         {enabled, floor, area, until}
POST /mine/timer   {add: minutes}: moves the end of farming (may be negative)

While a fight runs with "Repeat entry" ticked it only watches. Back on
the floor list (after 30 entries) it taps the floor, the Area and 3
feathers again. When the gold scroll is gone, or at `until`, it unticks
"Repeat entry": the entry under way is the last; three tries in a row that
do not take leave it blocked (one alert), tapping nothing more. A mine
whose timer ended while the gateway was down gets a stop pass at the
gateway's start. When to do what is in mine_rules.py; every tap, hold and
swipe goes through the navigation guard (ports), each sequence of them
under the shared lease (holder "mine"): while another holder has it, or
for 5 s after a user input, the mine waits for its next look. The game not in front is the
watchdog's (mine_away): it relaunches the game, then calls reenter(),
the way back in from the battle screen (Adventure, Dungeon, Closed Mine,
then the floor, Area and feathers), tried again after 2, 4, 8 then 16 s
within rules.ENTRY_BUDGET; it stops before its first tap while those
screens are not calibrated (mine.py). Out of feathers (read on the
feathers pop-up, once calibrated), or no way back in, the mine ends with
no alert of its own: the mode goes back to the default one, with one. The mine's floor, area,
timer and on/off are kept in state.json ("mine").
"""

import asyncio


def mine(ports, screens, readers, rules, timer, values):
    """readers: mine.py (the mine's screens off a screenshot)."""
    t = ports.t
    status = {"enabled": False, "floor": None, "area": None, "until": None, "gold": None,
              "state": "off", "message": None, "task": None, "stopper": None, "entering": False,
              "no_feather": False}
    ports.store.register("mine", lambda: {key: status[key] for key in ("enabled", "floor", "area", "until",
                                                                        "state")})

    def report(state, message=None):
        """The mine's state and its message (a status text, or None)."""
        if (status["state"], status["message"]) != (state, message):
            ports.log("error" if state in ("blocked", "failed") else "normal",
                      f"Mine: {state}" + (f" ({ports.english(message)})" if message else ""))
        status["state"], status["message"] = state, message
        ports.store.save()

    async def alert(text):
        """The Cloud Phone's phone alerts (ntfy), when the user turned them on."""
        await ports.notify(text)

    async def leased(reason, sequence):
        """sequence() under the shared lease; None when the mine may not
        tap now (another holder has it, the user plays): said in its state,
        tried again at a next look."""
        try:
            async with ports.leased("mine", reason, rules.LEASE_SECONDS):
                return await sequence()
        except ports.Busy as e:
            report("waiting", t("En attente : {why}", why=e.t))
            return None

    async def hold_saver(shot):
        await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
        return True

    async def step(shot, screen, move, point, wait=2.5):
        """Taps point (move of screen) if the game is still in front; the
        next screenshot."""
        if not await ports.focused():
            return None
        await ports.tap(shot, screen, move, point)
        await ports.clock.sleep(wait)
        return await ports.capture()

    async def relaunch(shot):
        """From the floor list: floor, Area, feathers. True once the fight
        shows again."""
        floor = status["floor"]
        for _ in range(rules.SCROLL_TRIES):
            rows = await ports.analyse(readers.floors, shot)
            row = rules.floor_row(rows, floor)
            if row is not None:
                break
            if not rows:
                return False
            a, b = rules.scroll_towards(rows, floor)
            await ports.swipe(shot, "mine_list", "scroll", (0.5, a), (0.5, b), rules.SCROLL_MS)
            await ports.clock.sleep(1.5)
            shot = await ports.capture()
            if not shot or not await ports.analyse(readers.floor_list, shot):
                return False
        else:
            report("blocked", t("Étage {floor} introuvable dans la liste", floor=floor))
            return False
        shot = await step(shot, "mine_list", "floor", (0.5, row))
        if not shot or not await ports.analyse(readers.area_popup, shot):
            return False
        shot = await step(shot, "mine_area", "area", readers.AREA_TAPS[status["area"] - 1])
        if not shot or not await ports.analyse(readers.feather_popup, shot):
            return False
        if readers.feathers_left is not None and await ports.analyse(readers.feathers_left, shot) == 0:
            status["no_feather"] = True
            return False
        shot = await step(shot, "mine_feathers", "feathers", readers.FEATHER_TAPS[rules.FEATHERS - 1], 6)
        fighting = bool(shot) and await ports.analyse(readers.in_fight, shot)
        game = getattr(ports, "game", None)
        if fighting and game is not None:
            game["note"]({"mine_floor": floor, "mine_area": status["area"]}, "setup")
        return fighting

    async def unticked(shot):
        """Unticks "Repeat entry" if it is ticked, so that the entry under
        way is the last. True once it is unticked."""
        if await ports.analyse(readers.repeat_ticked, shot):
            shot = await step(shot, "mine_fight", "repeat", readers.REPEAT_TAP)
            if not shot or await ports.analyse(readers.repeat_ticked, shot):
                return False
        return True

    def ended(state, message):
        """The mine ends with no alert of its own (out of feathers, no way
        back in): the mode's back to default says it, once. message: a
        status text."""
        status["enabled"] = False
        report(state, message)

    async def poll(read, timeout):
        """A fresh screenshot every second until read(shot) is true, at most
        timeout seconds: the last one, or None."""
        deadline = ports.clock.monotonic() + timeout
        while True:
            shot = await ports.capture(max_age=0)
            if shot and await ports.analyse(read, shot):
                return shot
            if ports.clock.monotonic() >= deadline:
                return None
            await ports.clock.sleep(1)

    async def way_in():
        """From the battle screen to the mine's fight: "done", "no_feather",
        or the step that did not show (a status text)."""
        shot = await poll(screens.plain_battle, rules.ENTRY_SETTLE)
        if not shot:
            return t("écran de combat pas vu")
        for screen, move, point, read, name in (
                ("battle", "menu_adventure", readers.ADVENTURE_TAP, readers.adventure_open, "Adventure"),
                ("adventure_map", "dungeon", readers.DUNGEON_TAP, readers.dungeon_open, "Dungeon"),
                ("dungeon_map", "closed_mine", readers.CLOSED_MINE_TAP, readers.floor_list, t("liste des étages"))):
            if not await ports.focused():
                return t("le jeu n’est plus au premier plan")
            await ports.tap(shot, screen, move, point)
            shot = await poll(read, rules.ENTRY_SETTLE)
            if not shot:
                return t("écran {name} pas vu", name=name)
        if await relaunch(shot):
            return "done"
        return "no_feather" if status["no_feather"] else t("étage, zone ou plumes")

    async def reenter():
        """After the watchdog's relaunch: the way back in, tried again within
        rules.ENTRY_BUDGET; then (or out of feathers, or not calibrated) the
        mine ends. {result: "done", "no_feather", "failed" or
        "uncalibrated", text_t (a status text, or None)}."""
        if not status["enabled"]:
            return {"result": "failed", "text_t": t("la mine ne farme plus")}
        if readers.adventure_open is None or readers.dungeon_open is None:
            text = t("écrans Adventure et Dungeon pas encore reconnus")
            ended("entry_failed", t("retour dans la mine impossible ({why})", why=text))
            return {"result": "uncalibrated", "text_t": text}
        status.update(entering=True, no_feather=False)
        report("relaunching", t("Retour dans la mine : étage {floor}, zone {area}", floor=status["floor"],
                                area=status["area"]))
        began, failures, first = ports.clock.monotonic(), 0, None
        try:
            while True:
                why = await leased("Back into the mine", way_in)
                if why == "done":
                    report("farming", t("Mine relancée après un redémarrage du jeu"))
                    return {"result": "done", "text_t": None}
                if why == "no_feather":
                    ended("no_feather", t("plus de plume"))
                    return {"result": "no_feather", "text_t": t("plus de plume")}
                failures += 1
                # The first try's step names the cause: a later one may
                # start where it stopped (not the battle screen).
                first = first or why
                delay = rules.entry_retry(failures, ports.clock.monotonic() - began)
                if delay is None:
                    text = first or t("bail toujours pris")
                    ended("entry_failed", t("retour dans la mine impossible ({why})", why=text))
                    return {"result": "failed", "text_t": text}
                ports.log("normal", f"Mine: way back in stopped ({ports.english(why)}), again in {delay} s")
                await ports.clock.sleep(delay)
        finally:
            status["entering"] = False

    def stopped(reason):
        """reason: a status text."""
        status["enabled"] = False
        report("stopped", t("{reason} : « Repeat entry » décoché, la mine s’arrête après cette entrée", reason=reason))

    async def untick(shot, reason):
        """The stop pass's untick: True once it is unticked and farming is
        off; None when it may not tap now; else blocked, with an alert."""
        done = await leased("Untick Repeat entry", lambda: unticked(shot))
        if done is None:
            return None
        if not done:
            report("blocked", t("{reason}, mais « Repeat entry » ne se décoche pas", reason=reason))
            await alert(ports.fill("Mine: {reason}, but Repeat entry does not untick", {"reason": reason}))
            return False
        stopped(reason)
        return True

    def mine_facts(shot):
        """What the farming loop checks on a screenshot: saver, fight, gold
        (the gold scroll, in a fight), other (a pop-up or a screen that is
        not the floor list)."""
        if screens.classify(shot) == "saver":
            return {"saver": True}
        if readers.in_fight(shot):
            return {"saver": False, "fight": True, "gold": readers.gold_scroll(shot)}
        other = readers.area_popup(shot) or readers.feather_popup(shot) or not readers.floor_list(shot)
        return {"saver": False, "fight": False, "other": other}

    async def farm():
        # Only the loop begin() started last farms: one still ending (cancelled
        # by end(), or in its last alert) never takes another look.
        me = asyncio.current_task()
        memory = rules.fresh()
        place = t("étage {floor}, zone {area}", floor=status["floor"], area=status["area"])

        async def look_again():
            """Before a tap: a screenshot taken now, or None unless it shows
            what the loop's look (up to rules.SECONDS old) saw."""
            fresh = await ports.capture(max_age=0)
            if fresh and await ports.analyse(mine_facts, fresh) == facts:
                return fresh
            return None

        async def finish(state, message):
            """message: a status text, said in English in the alert."""
            status["enabled"] = False
            report(state, message)
            await alert(ports.fill("Mine stopped ({place}): {why}", {"place": place, "why": message}))

        async def untick_or_retry(shot, reason):
            """The farming loop's untick: "unticked" (farming is off),
            "retry" (it did not take, or may not tap now: the next look
            tries again) or, after rules.MAX_UNTICK_FAILURES tries in a row
            that did not take, "blocked" (farming is off, one alert, no more
            taps)."""
            nonlocal memory
            done = await leased("Untick Repeat entry", lambda: unticked(shot))
            if done is None:
                return "retry"
            if done:
                stopped(reason)
                return "unticked"
            memory, give_up = rules.untick_failed(memory)
            if give_up:
                await finish("blocked", t("{reason}, mais « Repeat entry » ne se décoche pas après {tries} essais : "
                                          "sa case se lit toujours cochée", reason=reason, tries=rules.MAX_UNTICK_FAILURES))
                return "blocked"
            report("blocked", t("{reason}, mais « Repeat entry » ne se décoche pas : nouvel essai", reason=reason))
            return "retry"

        try:
            while status["enabled"] and status["task"] is me:
                await ports.clock.sleep(rules.SECONDS)
                if status["task"] is not me:
                    return
                if not ports.enabled():
                    report("waiting", t("Plugin désactivé"))
                    continue
                if status["entering"]:
                    # The way back in runs (reenter, under the lease).
                    continue
                if not await ports.focused():
                    # The watchdog's (rules mine_away): its relaunch, then reenter().
                    report("waiting", t("Le jeu n’est pas au premier plan"))
                    continue
                shot = await ports.capture(max_age=rules.SECONDS)
                if not shot:
                    continue
                facts = await ports.analyse(mine_facts, shot)
                move, memory, status["gold"], gone = rules.step(
                    facts, memory, ports.clock.monotonic(), ports.clock.wall(), status["until"])
                if move == "leave_saver":
                    shot = await look_again()
                    if shot and await leased("Leave Power Saving Mode", lambda: hold_saver(shot)):
                        memory["last_hold"] = ports.clock.monotonic()
                elif move == "stop_timer":
                    shot = await look_again()
                    result = await untick_or_retry(shot, t("Durée écoulée")) if shot else "retry"
                    if result == "unticked":
                        await alert(ports.fill("Time is up ({place}): Repeat entry unticked, the mine stops after "
                                               "this entry", {"place": place}))
                    if result != "retry":
                        return
                elif move == "gold":
                    report("farming", t("Combat en cours, parchemin doré actif"))
                elif move in ("warn_no_gold", "stop_no_gold"):
                    timed = move == "warn_no_gold"
                    if gone:
                        await alert(ports.fill("No more gold scroll ({place})"
                                               + (": the mine goes on until the timer ends" if timed else ""),
                                               {"place": place}))
                    if timed:
                        report("farming", t("Combat en cours, sans parchemin doré"))
                        continue
                    shot = await look_again()
                    if shot and await untick_or_retry(shot, t("Plus de parchemin doré")) != "retry":
                        return
                elif move == "other":
                    report("waiting", t("Écran autre que la mine : rien à faire"))
                elif move == "finish_timer":
                    await finish("stopped", t("Durée écoulée : pas de relance"))
                    return
                elif move == "finish_no_gold":
                    await finish("stopped", t("Parchemin doré pas vu depuis 5 minutes : pas de relance"))
                    return
                elif move == "wait_no_gold":
                    report("waiting", t("Parchemin doré pas vu depuis 5 minutes : pas de relance"))
                elif move == "finish_failures":
                    await finish("blocked", t("La relance de la mine a échoué {tries} fois de suite : pas de combat vu "
                                                "après la relance", tries=rules.MAX_FAILURES))
                    return
                elif move == "relaunch":
                    shot = await look_again()
                    if not shot:
                        continue
                    report("relaunching", t("Relance : étage {floor}, zone {area}", floor=status["floor"],
                                            area=status["area"]))
                    ok = await leased("Mine relaunch", lambda: relaunch(shot))
                    if ok is None:
                        continue
                    if not ok and status["no_feather"]:
                        ended("no_feather", t("plus de plume"))
                        return
                    if not ok and status["state"] == "blocked":
                        await finish("blocked", status["message"])
                        return
                    memory = rules.relaunched(memory, ok)
                    if ok:
                        report("farming", t("Mine relancée"))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ports.exception("Mine failed")
            await finish("failed", t("Erreur : {error}", error=f"{e!r}"[:200]))

    def stop_facts(shot):
        return screens.classify(shot), mine_facts(shot)

    async def stop_after_restart():
        """The stop pass of a mine whose timer ended while the gateway was
        down, during a fight. It only looks (a screenshot at once each time)
        and, on the mine fight, unticks "Repeat entry" through the guard as
        untick() does; Power Saving Mode is left as the farming loop leaves
        it. When the game cannot be in a fight (its process gone, another
        app in front, the title or save screen: Android or the game
        restarted), it ends at once: nothing to untick. Without seeing the
        fight for rules.STOP_SECONDS it is "blocked" (alert), then watches
        for rules.WATCH_SECONDS more (watch_after_blocked)."""
        reason = t("Durée écoulée pendant un redémarrage du gateway")
        report("stopping", t("Durée écoulée pendant un redémarrage : décoche « Repeat entry »"))
        deadline = ports.clock.monotonic() + rules.STOP_SECONDS
        last_hold = 0.0
        looks = 0
        try:
            while ports.clock.monotonic() < deadline:
                # The first look at once: a game that cannot be in a fight ends it.
                if looks:
                    await ports.clock.sleep(rules.SECONDS)
                looks += 1
                gone = await ports.running() is False
                why = rules.stop_pass_ended(gone, False if gone else await ports.focused())
                if why:
                    report("stopped", t("{reason} : le jeu n’est plus en combat, rien à décocher", reason=reason))
                    ports.log("normal", f"Mine: timer ended during a restart, game {why}: nothing to untick")
                    return
                shot = await ports.capture(max_age=0)
                if not shot:
                    continue
                screen, facts = await ports.analyse(stop_facts, shot)
                move = rules.stop_look(screen, facts, last_hold, ports.clock.monotonic())
                if move == "restarted":
                    report("stopped", t("{reason} : le jeu a redémarré, rien à décocher", reason=reason))
                    ports.log("normal", f"Mine: timer ended during a restart, game on its {screen} "
                              "screen: nothing to untick")
                    return
                if move == "leave_saver":
                    if await leased("Leave Power Saving Mode", lambda: hold_saver(shot)):
                        last_hold = ports.clock.monotonic()
                elif move == "untick":
                    done = await untick(shot, reason)
                    if done is None:
                        continue
                    if done:
                        ports.log("normal", "Mine: timer ended during a restart, Repeat entry unticked")
                    return
            report("blocked", t("Durée écoulée pendant un redémarrage, combat de la mine pas vu en {minutes} minutes : "
                                "« Repeat entry » est peut-être encore coché", minutes=rules.STOP_SECONDS // 60))
            ports.log("warning", "Mine: timer ended during a restart, fight not seen: "
                      "Repeat entry may still be ticked")
            await alert(f"Mine: time ran out during a restart, the mine's fight not seen in {rules.STOP_SECONDS // 60} "
                        "minutes: Repeat entry may still be ticked")
            await watch_after_blocked(reason)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ports.exception("Mine stop failed")
            report("failed", t("Erreur : {error}", error=f"{e!r}"[:200]))

    async def watch_after_blocked(reason):
        """After a stop pass gave up: one look every rules.WATCH_EVERY with
        the shared screenshot, no tap and no Power Saving hold, except
        unticking "Repeat entry" (untick(), after a screenshot at once
        still shows the fight) if the mine fight appears. One more alert if
        it is still blocked at the end."""
        deadline = ports.clock.monotonic() + rules.WATCH_SECONDS
        while ports.clock.monotonic() < deadline:
            await ports.clock.sleep(rules.WATCH_EVERY)
            if not await ports.focused():
                continue
            shot = await ports.capture(max_age=rules.WATCH_EVERY)
            if not shot or not rules.in_fight(await ports.analyse(mine_facts, shot)):
                continue
            shot = await ports.capture(max_age=0)
            if shot and rules.in_fight(await ports.analyse(mine_facts, shot)):
                done = await untick(shot, reason)
                if done is None:
                    continue
                if done:
                    ports.log("normal", "Mine: fight seen after giving up, Repeat entry unticked")
                return
        ports.log("warning", f"Mine: fight still not seen after {rules.WATCH_SECONDS // 60} more minutes")
        await alert(f"Mine: fight still not seen after {(rules.STOP_SECONDS + rules.WATCH_SECONDS) // 60} "
                    "minutes: Repeat entry may still be ticked")

    def cancel_stopper():
        """The user starts the mine: no stop pass any more."""
        stopper = status["stopper"]
        if stopper is not None and not stopper.done():
            stopper.cancel()

    def state():
        answer = {key: status[key] for key in ("enabled", "floor", "area", "until", "gold", "state")}
        answer["message_t"] = status["message"]
        return answer

    def begin():
        cancel_stopper()
        status["enabled"] = True
        status["gold"] = None
        report("waiting", t("Surveillance de la mine"))
        # A fresh loop, even when the last one has not ended yet: begin()
        # only runs with farming off, so that one is ending (cancelled by
        # end() in the same tick, or in its last alert) and would not farm.
        status["task"] = ports.spawn(farm())

    def end():
        status["enabled"] = False
        task = status["task"]
        if task is not None and not task.done():
            task.cancel()
        report("off")

    def start(floor, area, until):
        """The mode's mine: farms floor and area until then."""
        status.update(floor=floor, area=area, until=until)
        if not status["enabled"]:
            begin()

    def stop():
        if status["enabled"]:
            end()

    def set_until(until):
        status["until"] = until

    async def handle_state(request):
        return ports.respond(state())

    async def handle_mine(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        asked, error = rules.request(body)
        if error:
            return ports.respond({"error_t": error}, status=400)
        enabled, floor, area, until = asked
        status.update(floor=floor or None, area=area or None, until=until)
        if enabled and not status["enabled"]:
            begin()
        elif not enabled and status["enabled"]:
            end()
        ports.store.save()
        return ports.respond(state())

    async def handle_timer(request):
        """{add: minutes, may be negative}: moves the end of farming; at or
        before now there is no time limit any more."""
        try:
            add = float((await request.json()).get("add"))
        except (ValueError, TypeError, AttributeError):
            return ports.respond({"error_t": t("Attendu : {expected}", expected="{add: minutes}")}, status=400)
        status["until"] = timer.moved(status["until"], add, ports.clock.wall())
        ports.store.save()
        return ports.respond(state())

    async def resume(app):
        """At the gateway's start: the farming state.json kept goes on, or
        the stop pass of a mine that ended meanwhile."""
        if status["state"] == "stopping":
            status["stopper"] = ports.spawn(stop_after_restart())
        if status["enabled"]:
            report("waiting", t("Surveillance de la mine (reprise après un redémarrage du gateway)"))
            status["task"] = ports.spawn(farm())

    saved = ports.store.saved.get("mine") or {}
    restored, was_ended = rules.restored({
        "enabled": saved.get("enabled"), "state": saved.get("state"),
        "floor": values.number_or_none(saved.get("floor"), 9999), "area": values.number_or_none(saved.get("area"), 5),
        "until": values.time_or_none(saved.get("until"))}, ports.clock.wall())
    status.update({key: value for key, value in restored.items() if key != "state"})
    if restored["state"]:
        status["state"] = restored["state"]

    return {
        "routes": [("GET", "/mine", handle_state), ("POST", "/mine", handle_mine), ("POST", "/mine/timer", handle_timer)],
        "startup": [resume],
        # For the mode: the mine it starts and stops, and whether its timer
        # ended while the gateway was down.
        "api": {"start": start, "stop": stop, "state": state, "set_until": set_until, "ended": was_ended,
                "reenter": reenter},
    }
