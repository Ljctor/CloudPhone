"""Farms the Closed Mine from the gateway, so it goes on with the page
closed.

GET  /mine         {enabled, floor, area, until, gold, state, message}
POST /mine         {enabled, floor, area, until}
POST /mine/timer   {add: minutes}: moves the end of farming (may be negative)

While a fight runs with "Repeat entry" ticked it only watches. Back on
the floor list (after 30 entries) it taps the floor, the Area and 3
feathers again. When the gold scroll is gone, or at `until`, it unticks
"Repeat entry": the entry under way is the last. A mine whose timer ended
while the gateway was down gets a stop pass at the gateway's start. When
to do what is in mine_rules.py; every tap, hold and swipe goes through the
navigation guard (ports). The mine's floor, area, timer and on/off are
kept in state.json ("mine").
"""

import asyncio
import logging


def mine(ports, screens, readers, rules, timer, values):
    """readers: mine.py (the mine's screens off a screenshot)."""
    status = {"enabled": False, "floor": None, "area": None, "until": None, "gold": None,
              "state": "off", "message": "", "task": None, "stopper": None}
    ports.store.register("mine", lambda: {key: status[key] for key in ("enabled", "floor", "area", "until",
                                                                        "state")})

    def report(state, message):
        if (status["state"], status["message"]) != (state, message):
            logging.info(f"Slayer Legend mine: {state} {message}")
        status["state"], status["message"] = state, message
        ports.store.save()

    async def alert(text):
        """The Cloud Phone's phone alerts (ntfy), when the user turned them on."""
        await ports.notify(text)

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
            report("blocked", f"Étage {floor} introuvable dans la liste")
            return False
        shot = await step(shot, "mine_list", "floor", (0.5, row))
        if not shot or not await ports.analyse(readers.area_popup, shot):
            return False
        shot = await step(shot, "mine_area", "area", readers.AREA_TAPS[status["area"] - 1])
        if not shot or not await ports.analyse(readers.feather_popup, shot):
            return False
        shot = await step(shot, "mine_feathers", "feathers", readers.FEATHER_TAPS[rules.FEATHERS - 1], 6)
        return bool(shot) and await ports.analyse(readers.in_fight, shot)

    async def untick(shot, reason):
        """Unticks "Repeat entry" so that the entry under way is the last.
        True once it is unticked and farming is off."""
        if await ports.analyse(readers.repeat_ticked, shot):
            shot = await step(shot, "mine_fight", "repeat", readers.REPEAT_TAP)
            if not shot or await ports.analyse(readers.repeat_ticked, shot):
                report("blocked", f"{reason}, mais « Repeat entry » ne se décoche pas")
                await alert(status["message"])
                return False
        status["enabled"] = False
        report("stopped", f"{reason} : « Repeat entry » décoché, la mine s’arrête après cette entrée")
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
        memory = rules.fresh()
        away_since = None
        place = f"étage {status['floor']}, zone {status['area']}"

        async def look_again():
            """Before a tap: a screenshot taken now, or None unless it shows
            what the loop's look (up to rules.SECONDS old) saw."""
            fresh = await ports.capture(max_age=0)
            if fresh and await ports.analyse(mine_facts, fresh) == facts:
                return fresh
            return None

        async def finish(state, message):
            status["enabled"] = False
            report(state, message)
            await alert(f"Mine arrêtée ({place}) : {message}")

        try:
            while status["enabled"]:
                await ports.clock.sleep(rules.SECONDS)
                if not await ports.focused():
                    report("waiting", "Le jeu n’est pas au premier plan")
                    away_since, late = rules.away(away_since, ports.clock.monotonic())
                    if late:
                        await alert("Le jeu n’est plus au premier plan depuis 2 minutes (plantage ?)")
                    continue
                away_since = None
                shot = await ports.capture(max_age=rules.SECONDS)
                if not shot:
                    continue
                facts = await ports.analyse(mine_facts, shot)
                move, memory, status["gold"], gone = rules.step(
                    facts, memory, ports.clock.monotonic(), ports.clock.wall(), status["until"], status["gold"])
                if move == "leave_saver":
                    shot = await look_again()
                    if shot:
                        memory["last_hold"] = ports.clock.monotonic()
                        await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                elif move == "stop_timer":
                    shot = await look_again()
                    if shot and await untick(shot, "Durée écoulée"):
                        await alert(f"Durée écoulée ({place}) : « Repeat entry » décoché, la mine s’arrête après "
                                    "cette entrée")
                        return
                elif move == "gold":
                    report("farming", "Combat en cours, parchemin doré actif")
                elif move in ("warn_no_gold", "stop_no_gold"):
                    timed = move == "warn_no_gold"
                    if gone:
                        await alert(f"Plus de parchemin doré ({place})"
                                    + (" : la mine continue jusqu’à la fin du minuteur" if timed else ""))
                    if timed:
                        report("farming", "Combat en cours, sans parchemin doré")
                        continue
                    shot = await look_again()
                    if shot and await untick(shot, "Plus de parchemin doré"):
                        return
                elif move == "other":
                    report("waiting", "Écran autre que la mine : rien à faire")
                elif move == "finish_timer":
                    await finish("stopped", "Durée écoulée : pas de relance")
                    return
                elif move == "finish_no_gold":
                    await finish("stopped", "Parchemin doré pas vu depuis 5 minutes : pas de relance")
                    return
                elif move == "wait_no_gold":
                    report("waiting", "Parchemin doré pas vu depuis 5 minutes : pas de relance")
                elif move == "finish_failures":
                    await finish("blocked", "La relance a échoué 3 fois : relance la mine à la main")
                    return
                elif move == "relaunch":
                    shot = await look_again()
                    if not shot:
                        continue
                    report("relaunching", f"Relance : étage {status['floor']}, zone {status['area']}")
                    ok = await relaunch(shot)
                    if not ok and status["state"] == "blocked":
                        await finish("blocked", status["message"])
                        return
                    memory = rules.relaunched(memory, ok)
                    if ok:
                        report("farming", "Mine relancée")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mine failed")
            await finish("failed", f"Erreur : {e!r}"[:200])

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
        reason = "Durée écoulée pendant un redémarrage de la passerelle"
        report("stopping", "Durée écoulée pendant un redémarrage : décoche « Repeat entry »")
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
                    report("stopped", f"{reason} : le jeu n’est plus en combat, rien à décocher")
                    logging.info(f"Slayer Legend mine: timer ended during a restart, game {why}: nothing to untick")
                    return
                shot = await ports.capture(max_age=0)
                if not shot:
                    continue
                screen, facts = await ports.analyse(stop_facts, shot)
                move = rules.stop_look(screen, facts, last_hold, ports.clock.monotonic())
                if move == "restarted":
                    report("stopped", f"{reason} : le jeu a redémarré, rien à décocher")
                    logging.info(f"Slayer Legend mine: timer ended during a restart, game on its {screen} "
                                 "screen: nothing to untick")
                    return
                if move == "leave_saver":
                    last_hold = ports.clock.monotonic()
                    await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                elif move == "untick":
                    if await untick(shot, reason):
                        logging.info("Slayer Legend mine: timer ended during a restart, Repeat entry unticked")
                    return
            report("blocked", "Durée écoulée pendant un redémarrage, combat de la mine pas vu en "
                   f"{rules.STOP_SECONDS // 60} minutes : « Repeat entry » est peut-être encore coché")
            logging.warning("Slayer Legend mine: timer ended during a restart, fight not seen: "
                            "Repeat entry may still be ticked")
            await alert(status["message"])
            await watch_after_blocked(reason)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mine stop failed")
            report("failed", f"Erreur : {e!r}"[:200])

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
                if await untick(shot, reason):
                    logging.info("Slayer Legend mine: fight seen after giving up, Repeat entry unticked")
                return
        logging.warning(f"Slayer Legend mine: fight still not seen after {rules.WATCH_SECONDS // 60} more minutes")
        await alert(f"Mine : combat toujours pas vu après {(rules.STOP_SECONDS + rules.WATCH_SECONDS) // 60} "
                    "minutes, « Repeat entry » est peut-être encore coché : vérifie à la main")

    def cancel_stopper():
        """The user starts the mine: no stop pass any more."""
        stopper = status["stopper"]
        if stopper is not None and not stopper.done():
            stopper.cancel()

    def state():
        return {key: status[key] for key in ("enabled", "floor", "area", "until", "gold", "state", "message")}

    def begin():
        cancel_stopper()
        status["enabled"] = True
        status["gold"] = None
        report("waiting", "Surveillance de la mine")
        task = status["task"]
        if task is None or task.done():
            status["task"] = ports.spawn(farm())

    def end():
        status["enabled"] = False
        task = status["task"]
        if task is not None and not task.done():
            task.cancel()
        report("off", "")

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
            return ports.respond({"error": error}, status=400)
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
            return ports.respond({"error": "Expected {add: minutes}"}, status=400)
        status["until"] = timer.moved(status["until"], add, ports.clock.wall())
        ports.store.save()
        return ports.respond(state())

    async def resume(app):
        """At the gateway's start: the farming state.json kept goes on, or
        the stop pass of a mine that ended meanwhile."""
        if status["state"] == "stopping":
            status["stopper"] = ports.spawn(stop_after_restart())
        if status["enabled"]:
            report("waiting", "Surveillance de la mine (reprise après un redémarrage de la passerelle)")
            status["task"] = ports.spawn(farm())

    saved = ports.store.saved.get("mine") or {}
    restored, ended = rules.restored({
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
        "api": {"start": start, "stop": stop, "state": state, "set_until": set_until, "ended": ended},
    }
