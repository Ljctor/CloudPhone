"""Slayer Legend plugin, gateway side (loaded by the gateway's plugin loader).

GET  /api/v1/plugins/slayer-legend/emerald-mask[?counter=diamond]
     Where the emerald (or diamond) counter is, and the pixels of its digits after the
     comma, from an emulator screenshot: for browsers that cannot read the
     video's pixels.
GET  /api/v1/plugins/slayer-legend/screen
     The screen the game shows, {screen: title | save | battle | menu |
     saver | other | away (another app in front)}, and the farmed stage,
     {stage: {number, name, monsters_per_wave, drop, grade, soul_colour,
     soul_colour_confirmed, checked} or null}, from an emulator screenshot
     at most every 2 s. The number is read in Power Saving Mode; the
     battle screen only confirms it (checked: true when the numeral after
     the name still matches). ?known=N gives the number the page last saw,
     used while the gateway has not read one since it started. The rest
     comes from stages.json.
GET  /api/v1/plugins/slayer-legend/launch
     State of the last launch: {state, message}.
POST /api/v1/plugins/slayer-legend/launch
     Starts the game and brings it to the battle screen: taps "TAP TO START",
     then Confirm on the "last save time" notice (the latest save), or
     holds "Press here to finish Power Saving Mode" for 4 s. It never taps anything else;
     any other screen stops it and asks the user.

GET  /api/v1/plugins/slayer-legend/mine
     State of mine farming: {enabled, floor, area, until, state, message}.
POST /api/v1/plugins/slayer-legend/mine  {enabled, floor, area, until}
     Farms the Closed Mine: while the fight runs with "Repeat entry" ticked
     it only watches; when the game is back on the floor list (after 30
     entries) it taps the floor, the Area and 3 feathers again (always 3:
     the reward is multiplied by the feathers used). When the
     gold scroll buff is gone it unticks "Repeat entry" and stops: the
     entry under way ends, no more feathers are spent. It stops the same
     way at `until` (Unix seconds; null: no time limit); with a time limit,
     a missing gold scroll is only a warning. It leaves Power Saving Mode
     (4 s press) at most once a minute to see the buffs. With the Cloud
     Phone's phone alerts on (Options), it alerts when the gold scroll
     goes, when farming stops, and when the game has left the screen for 2
     minutes.
POST /api/v1/plugins/slayer-legend/mine/timer  {add: minutes}
     Moves the end of farming by that many minutes (may be negative).
GET  /api/v1/plugins/slayer-legend/gold-font
     The gold counter's pixel font, {height, glyphs: {char: rows of "#"
     and "."}}: digits, letters and the signs the page writes the rate with.
GET  /api/v1/plugins/slayer-legend/gold
     Gold earned per second: {text, value, rate, rate_text, span, read,
     box}; box is where the counter was last read ([left, top, right,
     bottom], fractions of the screen), for the page to write the rate
     after it.
     The first call starts reading the gold counter every 10 s while the
     game is in front (Power Saving Mode hides it: no reading then); a
     value counts once two readings in a row agree. The rate is the slope
     of the last 5 minutes of values (from the second value on, over the
     `span` seconds there are until then), all on the same stage. Where
     the game is gets checked at each reading, counter shown or not: the
     battle screen's stage name line must look the same, Power Saving
     Mode must show the same stage number; two checks in a row on another
     stage, another place, another screen or another app start the window
     again, as does spending gold. `read` is the time of the last reading.

POST /api/v1/plugins/slayer-legend/trace  {x, y, kind[, end: {x, y}]}
     A tap the user just made in the page (fractions of the screen; kind
     tap, long or swipe, end: where a swipe ended). If the game is in
     front, the screen before it (a screenshot at once: the game has not
     drawn its answer yet) and after it (2 s later, or just before the next
     tap) are kept as signatures (screen name and a grey thumbnail, see
     trace.py; never the screenshots) and the tap as an edge between them,
     in the plugin's data directory. Nothing is ever replayed. 202 at once.
GET  /api/v1/plugins/slayer-legend/trace
     {enabled (the gateway has a data directory to record into), nodes,
     edges, taps, last: {time, from, to, kind} or null}.
GET  /api/v1/plugins/slayer-legend/trace/graph
     The recorded graph: {nodes: [{id, screen, count, thumb}], edges:
     [{from, to, x, y, kind, count[, x2, y2]}]}.

The mode and its timer, the mine's floor, area, timer and on/off, and the
highest stage seen farmed are kept in the plugin's data directory
(state.json, written when they change) and restored when the gateway
starts: farming and a timed mode go on after a gateway restart.

Screens are recognised from a few pixel areas, as fractions of the screen,
measured on a 360x780 screen (the page's device shapes keep this ratio).
"""

import asyncio
import importlib.util
import json
import logging
import os
import time

MINE = {"enabled": False, "floor": None, "area": None, "until": None, "gold": None,
        "state": "off", "message": "", "task": None, "stopper": None}
# A mine whose timer ended while the gateway was down, in a fight: how long
# its stop pass looks for the fight to untick "Repeat entry", then how long
# and how often it still watches for it, without touching anything else.
MINE_STOP_SECONDS = 180
MINE_WATCH_SECONDS = 15 * 60
MINE_WATCH_EVERY = 30
MINE_FEATHERS = 3
MINE_SECONDS = 10
# What the game is set to do. "mpw18" (farming a stage with 18 monsters per
# wave) is the default; the others run until a time, then it goes back to it.
MODES = ("mpw18", "mpw4", "free", "mine")
MODE = {"mode": "mpw18", "until": None, "stage18": None, "stage4": None, "highest": None,
        "configured": False, "state": "idle", "message": "", "task": None}
# Checks in a row without the gold scroll before stopping (an animation
# can hide it for a moment).
MINE_NO_GOLD = 2
# Gold per second: readings every GOLD_SECONDS, the slope over GOLD_WINDOW.
GOLD_SECONDS = 10
GOLD_WINDOW = 300
GOLD = {"samples": [], "pending": None, "text": None, "read": None, "box": None, "asked": 0.0, "task": None,
        "place": None, "number": None, "odd": 0}
# Navigation trace: the graph (trace.py), the tap waiting for its "after"
# screen {tap, before, task}, and the lock that keeps taps in order.
TRACE = {"graph": None, "path": None, "pending": None, "lock": None}
TRACE_AFTER_SECONDS = 2.0


def load_sibling(directory, name):
    """A module beside this file ("mine") or in features/ ("features/mine")."""
    spec = importlib.util.spec_from_file_location(f"cloudphone_plugin_slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(directory, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(context):
    def feature(name):
        return load_sibling(context.directory, f"features/{name}")

    nav = load_sibling(context.directory, "nav")
    ports = feature("ports").build(context, nav)
    screens = load_sibling(context.directory, "screens")
    stage = load_sibling(context.directory, "stage")
    values = feature("values")
    with open(os.path.join(context.directory, "stages.json"), encoding="utf-8") as f:
        table = json.load(f)
    features = [
        feature("counters").counters(ports, load_sibling(context.directory, "emerald_mask")),
        feature("screen").screen(ports, screens, stage, feature("screen_rules"), values, table),
        feature("launch").launch(ports, screens, feature("launch_rules")),
    ]

    tap, hold, in_focus = ports.tap, ports.hold, ports.focused
    mine = load_sibling(context.directory, "mine")

    def mine_report(state, message):
        if (MINE["state"], MINE["message"]) != (state, message):
            logging.info(f"Slayer Legend mine: {state} {message}")
        MINE["state"], MINE["message"] = state, message
        save_state()

    async def mine_step(shot, screen, move, point, wait=2.5):
        """Taps point (move of screen) if the game is still in front; the
        next screenshot."""
        if not await in_focus():
            return None
        await tap(shot, screen, move, point)
        await asyncio.sleep(wait)
        return await context.screenshot()

    async def mine_relaunch(shot):
        """From the floor list: floor, Area, feathers. True once the fight
        shows again."""
        floor = MINE["floor"]
        for _ in range(12):
            rows = await context.analyse(mine.floors, shot)
            row = next((y for y, n in rows if n == floor), None)
            if row is not None:
                break
            if not rows:
                return False
            # Scroll by about three rows towards the floor.
            up = rows[0][1] > floor
            a, b = (0.40, 0.65) if up else (0.65, 0.40)
            await ports.swipe(shot, "mine_list", "scroll", (0.5, a), (0.5, b), 600)
            await asyncio.sleep(1.5)
            shot = await context.screenshot()
            if not shot or not await context.analyse(mine.floor_list, shot):
                return False
        else:
            mine_report("blocked", f"Étage {floor} introuvable dans la liste")
            return False
        shot = await mine_step(shot, "mine_list", "floor", (0.5, row))
        if not shot or not await context.analyse(mine.area_popup, shot):
            return False
        shot = await mine_step(shot, "mine_area", "area", mine.AREA_TAPS[MINE["area"] - 1])
        if not shot or not await context.analyse(mine.feather_popup, shot):
            return False
        shot = await mine_step(shot, "mine_feathers", "feathers", mine.FEATHER_TAPS[MINE_FEATHERS - 1], 6)
        return bool(shot) and await context.analyse(mine.in_fight, shot)

    async def mine_stop(shot, reason):
        """Unticks "Repeat entry" so that the entry under way is the last.
        True once it is unticked and farming is off."""
        if await context.analyse(mine.repeat_ticked, shot):
            shot = await mine_step(shot, "mine_fight", "repeat", mine.REPEAT_TAP)
            if not shot or await context.analyse(mine.repeat_ticked, shot):
                mine_report("blocked", f"{reason}, mais « Repeat entry » ne se décoche pas")
                await alert(MINE["message"])
                return False
        MINE["enabled"] = False
        mine_report("stopped", f"{reason} : « Repeat entry » décoché, la mine s’arrête après cette entrée")
        return True

    async def alert(text):
        """The Cloud Phone's phone alerts (ntfy), when the user turned them on."""
        await context.notify(text)

    def mine_facts(shot):
        """What farm_mine checks on a screenshot: saver, fight, gold (the
        gold scroll, in a fight), other (a pop-up or a screen that is not
        the floor list)."""
        if screens.classify(shot) == "saver":
            return {"saver": True}
        if mine.in_fight(shot):
            return {"saver": False, "fight": True, "gold": mine.gold_scroll(shot)}
        other = mine.area_popup(shot) or mine.feather_popup(shot) or not mine.floor_list(shot)
        return {"saver": False, "fight": False, "other": other}

    async def farm_mine():
        no_gold = 0
        gold_seen = 0.0
        last_hold = 0.0
        failures = 0
        away_since = None
        timer_alerted = False
        place = f"étage {MINE['floor']}, zone {MINE['area']}"

        async def look_again():
            """Before a tap: a screenshot taken now, or None unless it shows
            what the loop's look (up to MINE_SECONDS old) saw."""
            fresh = await context.screenshot(max_age=0)
            if fresh and await context.analyse(mine_facts, fresh) == facts:
                return fresh
            return None

        async def finish(state, message):
            MINE["enabled"] = False
            mine_report(state, message)
            await alert(f"Mine arrêtée ({place}) : {message}")

        try:
            while MINE["enabled"]:
                await asyncio.sleep(MINE_SECONDS)
                if not await in_focus():
                    mine_report("waiting", "Le jeu n’est pas au premier plan")
                    away_since = away_since or time.monotonic()
                    if time.monotonic() - away_since > 120 and away_since > 0:
                        away_since = -1.0
                        await alert("Le jeu n’est plus au premier plan depuis 2 minutes (plantage ?)")
                    continue
                away_since = None
                shot = await context.screenshot(max_age=MINE_SECONDS)
                if not shot:
                    continue
                facts = await context.analyse(mine_facts, shot)
                if facts["saver"]:
                    # The buffs are hidden: leave Power Saving Mode to see them.
                    if time.monotonic() - last_hold > 60:
                        shot = await look_again()
                        if shot:
                            last_hold = time.monotonic()
                            await hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                    continue
                timed = MINE["until"] is not None
                over = timed and time.time() >= MINE["until"]
                if over and facts["fight"]:
                    shot = await look_again()
                    if not shot:
                        continue
                    if await mine_stop(shot, "Durée écoulée"):
                        await alert(f"Durée écoulée ({place}) : « Repeat entry » décoché, la mine s’arrête après cette entrée")
                        return
                    continue
                if facts["fight"]:
                    failures = 0
                    if facts["gold"]:
                        no_gold, gold_seen = 0, time.monotonic()
                        MINE["gold"] = True
                        mine_report("farming", "Combat en cours, parchemin doré actif")
                        continue
                    no_gold += 1
                    if no_gold < MINE_NO_GOLD:
                        continue
                    if MINE["gold"] is not False:
                        MINE["gold"] = False
                        await alert(f"Plus de parchemin doré ({place})"
                                    + (" : la mine continue jusqu’à la fin du minuteur" if timed else ""))
                    if timed:
                        # With a timer, the user chose how long: only warn.
                        mine_report("farming", "Combat en cours, sans parchemin doré")
                        continue
                    shot = await look_again()
                    if not shot:
                        continue
                    if await mine_stop(shot, "Plus de parchemin doré"):
                        return
                    continue
                if facts["other"]:
                    # The user's own taps, or a screen this does not know.
                    mine_report("waiting", "Écran autre que la mine : rien à faire")
                    continue
                # The floor list: the 30 entries are done.
                if over:
                    await finish("stopped", "Durée écoulée : pas de relance")
                    return
                if not timed and time.monotonic() - gold_seen > 5 * 60:
                    if gold_seen:
                        await finish("stopped", "Parchemin doré pas vu depuis 5 minutes : pas de relance")
                        return
                    mine_report("waiting", "Parchemin doré pas vu depuis 5 minutes : pas de relance")
                    continue
                if failures >= 3:
                    await finish("blocked", "La relance a échoué 3 fois : relance la mine à la main")
                    return
                shot = await look_again()
                if not shot:
                    continue
                mine_report("relaunching", f"Relance : étage {MINE['floor']}, zone {MINE['area']}")
                if await mine_relaunch(shot):
                    failures = 0
                    mine_report("farming", "Mine relancée")
                elif MINE["state"] == "blocked":
                    await finish("blocked", MINE["message"])
                    return
                else:
                    failures += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mine failed")
            await finish("failed", f"Erreur : {e!r}"[:200])

    def mine_state():
        return {key: MINE[key] for key in ("enabled", "floor", "area", "until", "gold", "state", "message")}

    async def handle_mine_state(request):
        return context.json(mine_state())

    async def handle_mine(request):
        try:
            body = await request.json()
            enabled = bool(body.get("enabled"))
            floor, area = int(body.get("floor") or 0), int(body.get("area") or 0)
            until = float(body["until"]) if body.get("until") is not None else None
        except (ValueError, TypeError, AttributeError):
            return context.json({"error": "Expected {enabled, floor, area, until}"}, status=400)
        if enabled and not (1 <= floor <= 9999 and 1 <= area <= 5):
            return context.json({"error": "floor 1-9999, area 1-5"}, status=400)
        MINE.update(floor=floor or None, area=area or None, until=until)
        task = MINE["task"]
        if enabled and not MINE["enabled"]:
            cancel_stopper()
            MINE["enabled"] = True
            MINE["gold"] = None
            mine_report("waiting", "Surveillance de la mine")
            if task is None or task.done():
                MINE["task"] = asyncio.get_running_loop().create_task(farm_mine())
        elif not enabled and MINE["enabled"]:
            MINE["enabled"] = False
            if task is not None and not task.done():
                task.cancel()
            mine_report("off", "")
        save_state()
        return context.json(mine_state())

    async def handle_mine_timer(request):
        """{add: minutes, may be negative}: moves the end of farming; at or
        before now there is no time limit any more."""
        try:
            add = float((await request.json()).get("add"))
        except (ValueError, TypeError, AttributeError):
            return context.json({"error": "Expected {add: minutes}"}, status=400)
        now = time.time()
        until = max(MINE["until"] or now, now) + add * 60
        MINE["until"] = until if until > now + 30 else None
        save_state()
        return context.json(mine_state())

    # What a gateway restart must not lose, so that farming meant to run
    # with the page closed goes on: the mode and its timer, the mine's
    # floor, area and timer (state.json, see ports.State).
    ports.store.register("mode", lambda: {key: MODE[key] for key in (
        "mode", "until", "stage18", "stage4", "highest", "configured")})
    ports.store.register("mine", lambda: {key: MINE[key] for key in ("enabled", "floor", "area", "until", "state")})
    save_state = ports.store.save
    number_or_none, time_or_none = values.number_or_none, values.time_or_none

    def restore_state():
        saved = ports.store.saved
        mode, mined = saved.get("mode") or {}, saved.get("mine") or {}
        MODE.update(mode=mode.get("mode") if mode.get("mode") in MODES else "mpw18",
                    until=time_or_none(mode.get("until")), configured=mode.get("configured") is True,
                    **{key: number_or_none(mode.get(key), 99999) for key in ("stage18", "stage4", "highest")})
        floor, area = number_or_none(mined.get("floor"), 9999), number_or_none(mined.get("area"), 5)
        MINE.update(enabled=mined.get("enabled") is True and bool(floor and area), floor=floor, area=area,
                    until=time_or_none(mined.get("until")))
        # A timer that ended while the gateway was down: that mode or the
        # mine is over, not resumed.
        now = time.time()
        ended = []
        if MODE["mode"] != "mpw18" and MODE["until"] is not None and MODE["until"] <= now:
            ended.append(f"mode {MODE['mode']}")
            MODE.update(mode="mpw18", until=None)
        if MINE["enabled"] and MINE["until"] is not None and MINE["until"] <= now:
            ended.append("mine")
            MINE["enabled"] = False
            # In a fight, "Repeat entry" goes on spending feathers: a stop
            # pass unticks it first (resume).
            MINE["state"] = "stopping" if mined.get("state") == "farming" else "off"
        elif mined.get("state") == "stopping":
            MINE["state"] = "stopping"  # restarted during a stop pass
        if MODE["mode"] == "mine" and not MINE["enabled"]:
            MODE.update(mode="mpw18", until=None)
        if ended:
            logging.info(f"Slayer Legend: timer ended while the gateway was stopped ({', '.join(ended)}): "
                         "back to mpw18 farming, mine off"
                         + (" once Repeat entry is unticked" if MINE["state"] == "stopping" else ""))

    restore_state()

    def mode_report(state, message):
        if (MODE["state"], MODE["message"]) != (state, message):
            logging.info(f"Slayer Legend mode {MODE['mode']}: {state} {message}")
        MODE["state"], MODE["message"] = state, message
        save_state()

    def mode_state():
        state = {key: MODE[key] for key in ("mode", "until", "stage18", "stage4", "highest", "configured",
                                             "state", "message")}
        state["mine"] = mine_state()
        return state

    async def set_stage(number, mpw):
        """Brings the game to farming that stage with its loadout. The
        screens for it are not learned yet: says so instead of tapping."""
        mode_report("todo", f"Passage au stage {number} (mpw{mpw}) : navigation pas encore apprise, fais-le à la main")
        await alert(f"À faire à la main : passer au stage {number} (mpw{mpw})")
        return False

    async def back_to_default(reason):
        MODE.update(mode="mpw18", until=None)
        await alert(f"{reason} : retour au farming mpw18" + (f" (stage {MODE['stage18']})" if MODE["stage18"] else ""))
        if MODE["stage18"]:
            await set_stage(MODE["stage18"], 18)
        else:
            mode_report("idle", "Farming mpw18 : choisis le stage")

    def start_mine(floor, area, until):
        MINE.update(floor=floor, area=area, until=until)
        if not MINE["enabled"]:
            cancel_stopper()
            MINE["enabled"] = True
            MINE["gold"] = None
            mine_report("waiting", "Surveillance de la mine")
            task = MINE["task"]
            if task is None or task.done():
                MINE["task"] = asyncio.get_running_loop().create_task(farm_mine())

    def stop_mine():
        if MINE["enabled"]:
            MINE["enabled"] = False
            task = MINE["task"]
            if task is not None and not task.done():
                task.cancel()
            mine_report("off", "")

    async def watch_mode():
        """Ends a timed mode: back to mpw18 farming once its time is up (the
        mine ends its last entry first)."""
        try:
            while MODE["mode"] != "mpw18":
                await asyncio.sleep(MINE_SECONDS)
                if MODE["mode"] == "mine":
                    if not MINE["enabled"]:
                        await back_to_default("Mine terminée" if MINE["state"] == "stopped" else "Mine arrêtée")
                    continue
                if MODE["until"] is not None and time.time() >= MODE["until"]:
                    await back_to_default("Minuteur écoulé")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mode failed")
            mode_report("failed", f"Erreur : {e!r}"[:200])

    async def handle_mode_state(request):
        return context.json(mode_state())

    async def handle_mode(request):
        """POST /mode {mode, until, stage18, stage4, highest, floor, area}."""
        try:
            body = await request.json()
            mode = body.get("mode") or "mpw18"
            until = float(body["until"]) if body.get("until") is not None else None
            numbers = {key: int(body.get(key) or 0) or None for key in ("stage18", "stage4", "highest", "floor", "area")}
        except (ValueError, TypeError, AttributeError):
            return context.json({"error": "Expected {mode, until, stage18, stage4, highest, floor, area}"}, status=400)
        if mode not in MODES:
            return context.json({"error": f"mode: one of {', '.join(MODES)}"}, status=400)
        if mode == "mine" and not (numbers["floor"] and 1 <= numbers["floor"] <= 9999
                                   and numbers["area"] and 1 <= numbers["area"] <= 5):
            return context.json({"error": "The mine needs floor 1-9999 and area 1-5"}, status=400)
        if mode == "mpw18":
            until = None
        changed = mode != MODE["mode"]
        MODE.update(mode=mode, until=until, configured=True,
                    **{key: numbers[key] for key in ("stage18", "stage4", "highest")})
        if mode == "mine":
            start_mine(numbers["floor"], numbers["area"], until)
        else:
            stop_mine()
        if changed:
            if mode == "mpw18":
                if MODE["stage18"]:
                    await set_stage(MODE["stage18"], 18)
                else:
                    mode_report("idle", "Farming mpw18 : choisis le stage")
            elif mode == "mpw4":
                if MODE["stage4"]:
                    await set_stage(MODE["stage4"], 4)
                else:
                    mode_report("idle", "Farming mpw4 : choisis le stage")
            elif mode == "free":
                mode_report("free", "Jeu libre : rien n’est touché jusqu’à la fin du minuteur")
            else:
                mode_report("mine", "Mine")
        task = MODE["task"]
        if mode != "mpw18" and (task is None or task.done()):
            MODE["task"] = asyncio.get_running_loop().create_task(watch_mode())
        save_state()
        return context.json(mode_state())

    async def handle_mode_timer(request):
        """{add: minutes, may be negative}: moves the end of the timed mode
        (and of the mine); at or before now there is no time limit."""
        try:
            add = float((await request.json()).get("add"))
        except (ValueError, TypeError, AttributeError):
            return context.json({"error": "Expected {add: minutes}"}, status=400)
        now = time.time()
        until = max(MODE["until"] or now, now) + add * 60
        MODE["until"] = until if until > now + 30 else None
        if MODE["mode"] == "mine":
            MINE["until"] = MODE["until"]
        save_state()
        return context.json(mode_state())

    game_running = ports.running

    def stop_facts(shot):
        return screens.classify(shot), mine_facts(shot)

    async def stop_after_restart():
        """The stop pass of a mine whose timer ended while the gateway was
        down, during a fight. It only looks (a screenshot at once each time)
        and, on the mine fight, unticks "Repeat entry" through the guard as
        mine_stop does; Power Saving Mode is left as the mine loop leaves
        it. When the game cannot be in a fight (its process gone, another
        app in front, the title or save screen: Android or the game
        restarted), it ends at once: nothing to untick. Without seeing the
        fight for MINE_STOP_SECONDS it is "blocked" (alert), then watches
        for MINE_WATCH_SECONDS more (watch_after_blocked)."""
        reason = "Durée écoulée pendant un redémarrage de la passerelle"
        mine_report("stopping", "Durée écoulée pendant un redémarrage : décoche « Repeat entry »")
        deadline = time.monotonic() + MINE_STOP_SECONDS
        last_hold = 0.0
        looks = 0
        try:
            while time.monotonic() < deadline:
                # The first look at once: a game that cannot be in a fight ends it.
                if looks:
                    await asyncio.sleep(MINE_SECONDS)
                looks += 1
                gone = await game_running() is False
                if gone or not await in_focus():
                    mine_report("stopped", f"{reason} : le jeu n’est plus en combat, rien à décocher")
                    logging.info("Slayer Legend mine: timer ended during a restart, game "
                                 + ("not running" if gone else "not in front") + ": nothing to untick")
                    return
                shot = await context.screenshot(max_age=0)
                if not shot:
                    continue
                screen, facts = await context.analyse(stop_facts, shot)
                if screen in ("title", "save"):
                    mine_report("stopped", f"{reason} : le jeu a redémarré, rien à décocher")
                    logging.info(f"Slayer Legend mine: timer ended during a restart, game on its {screen} "
                                 "screen: nothing to untick")
                    return
                if facts["saver"] and time.monotonic() - last_hold > 60:
                    last_hold = time.monotonic()
                    await hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                elif facts.get("fight"):
                    if await mine_stop(shot, reason):
                        logging.info("Slayer Legend mine: timer ended during a restart, Repeat entry unticked")
                    return
            mine_report("blocked", "Durée écoulée pendant un redémarrage, combat de la mine pas vu en "
                        f"{MINE_STOP_SECONDS // 60} minutes : « Repeat entry » est peut-être encore coché")
            logging.warning("Slayer Legend mine: timer ended during a restart, fight not seen: "
                            "Repeat entry may still be ticked")
            await alert(MINE["message"])
            await watch_after_blocked(reason)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mine stop failed")
            mine_report("failed", f"Erreur : {e!r}"[:200])

    async def watch_after_blocked(reason):
        """After a stop pass gave up: one look every MINE_WATCH_EVERY with
        the shared screenshot, no tap and no Power Saving hold, except
        unticking "Repeat entry" (mine_stop, after a screenshot at once
        still shows the fight) if the mine fight appears. One more alert if
        it is still blocked at the end."""
        deadline = time.monotonic() + MINE_WATCH_SECONDS
        while time.monotonic() < deadline:
            await asyncio.sleep(MINE_WATCH_EVERY)
            if not await in_focus():
                continue
            shot = await context.screenshot(max_age=MINE_WATCH_EVERY)
            if not shot or not (await context.analyse(mine_facts, shot)).get("fight"):
                continue
            shot = await context.screenshot(max_age=0)
            if shot and (await context.analyse(mine_facts, shot)).get("fight"):
                if await mine_stop(shot, reason):
                    logging.info("Slayer Legend mine: fight seen after giving up, Repeat entry unticked")
                return
        logging.warning(f"Slayer Legend mine: fight still not seen after {MINE_WATCH_SECONDS // 60} more minutes")
        await alert(f"Mine : combat toujours pas vu après {(MINE_STOP_SECONDS + MINE_WATCH_SECONDS) // 60} "
                    "minutes, « Repeat entry » est peut-être encore coché : vérifie à la main")

    def cancel_stopper():
        """The user starts the mine: no stop pass any more."""
        stopper = MINE["stopper"]
        if stopper is not None and not stopper.done():
            stopper.cancel()

    async def resume(app):
        """At the gateway's start: the farming and timed mode state.json
        kept go on, or the stop pass of a mine that ended meanwhile."""
        loop = asyncio.get_running_loop()
        if MINE["state"] == "stopping":
            MINE["stopper"] = loop.create_task(stop_after_restart())
        if MINE["enabled"]:
            mine_report("waiting", "Surveillance de la mine (reprise après un redémarrage de la passerelle)")
            MINE["task"] = loop.create_task(farm_mine())
        if MODE["mode"] != "mpw18":
            mode_report(*{"free": ("free", "Jeu libre : rien n’est touché jusqu’à la fin du minuteur"),
                          "mine": ("mine", "Mine")}.get(MODE["mode"], ("idle", f"Farming {MODE['mode']}")))
            MODE["task"] = loop.create_task(watch_mode())

    gold = load_sibling(context.directory, "gold")

    def gold_rate():
        samples = GOLD["samples"]
        while samples and time.time() - samples[0][0] > GOLD_WINDOW:
            samples.pop(0)
        # From the second value on: over what there is until the window
        # is full (the page marks it as provisional).
        if len(samples) < 2 or samples[-1][0] - samples[0][0] <= 0:
            return None
        # Least squares: the counter moves by steps of its last digit.
        n = len(samples)
        mean_t = sum(t for t, _ in samples) / n
        mean_v = sum(v for _, v in samples) / n
        spread = sum((t - mean_t) ** 2 for t, _ in samples)
        if not spread:
            return None
        return max(0.0, sum((t - mean_t) * (v - mean_v) for t, v in samples) / spread)

    def same_place(a, b):
        """Two inks of the battle screen's stage name line are the same
        stage (a few pixels differ with what moves behind it)."""
        if len(a) != len(b) or len(a[0]) != len(b[0]):
            return False
        differ = sum(x != y for row_a, row_b in zip(a, b) for x, y in zip(row_a, row_b))
        ink = max(1, sum(map(sum, a)), sum(map(sum, b)))
        return differ / ink < 0.2

    def gold_restart(place=None):
        GOLD.update(place=place, number=None, odd=0, pending=None)
        GOLD["samples"].clear()

    def gold_elsewhere(place=None):
        """Not on the window's stage, or not known where: twice in a row
        (an effect can hide the stage name for a moment), the window starts
        again (at `place` if known)."""
        GOLD["odd"] += 1
        if GOLD["odd"] >= 2:
            gold_restart(place)

    def gold_facts(shot):
        """The gold counter's reading and where the game is: ("saver",
        stage number) or ("battle", ink of the stage name line)."""
        reading = gold.read(shot)
        if screens.classify(shot) == "saver":
            return reading, ("saver", stage.read_saver(shot)[0])
        return reading, ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME)))

    def gold_where(where):
        """Follows where the game is at each reading; True when the shot
        was on the window's stage (its gold may be counted)."""
        kind, here = where
        if kind == "saver":
            # Power Saving Mode farms the same stage and writes its number.
            number = here
            if number is None:
                gold_elsewhere()
            elif GOLD["number"] is None and GOLD["place"] is not None and GOLD["odd"] == 0:
                GOLD["number"] = number
            elif number != GOLD["number"]:
                gold_elsewhere()
            else:
                GOLD["odd"] = 0
            return False
        if here is None:
            gold_elsewhere()
            return False
        if GOLD["place"] is None:
            gold_restart(here)
            return True
        if same_place(here, GOLD["place"]):
            GOLD["odd"] = 0
            return True
        gold_elsewhere(here)
        return False

    async def watch_gold():
        # Stops 10 minutes after the last page asked.
        while time.monotonic() - GOLD["asked"] < 600:
            try:
                shot = await context.screenshot(max_age=GOLD_SECONDS) if await in_focus() else None
                if not shot:
                    gold_elsewhere()  # another app in front: the game stops
                else:
                    reading, where = await context.analyse(gold_facts, shot)
                    if reading:
                        GOLD["read"] = time.time()
                        GOLD["box"] = reading["box"]
                    if gold_where(where) and reading:
                        now = time.time()
                        if GOLD["pending"] == reading["value"]:
                            samples = GOLD["samples"]
                            if samples and reading["value"] < samples[-1][1]:
                                samples.clear()  # gold was spent
                            samples.append((now, reading["value"]))
                            while samples and now - samples[0][0] > GOLD_WINDOW:
                                samples.pop(0)
                            GOLD["text"] = reading["text"]
                        GOLD["pending"] = reading["value"]
            except Exception as e:
                logging.warning(f"Gold reading failed: {e!r}")
            await asyncio.sleep(GOLD_SECONDS)
        GOLD["task"] = None

    async def handle_gold(request):
        GOLD["asked"] = time.monotonic()
        if GOLD["task"] is None:
            GOLD["task"] = asyncio.get_running_loop().create_task(watch_gold())
        rate = gold_rate()
        samples = GOLD["samples"]
        return context.json({
            "text": GOLD["text"],
            "value": samples[-1][1] if samples else None,
            "rate": rate,
            "rate_text": gold.rate_text(rate),
            "span": samples[-1][0] - samples[0][0] if samples else 0,
            "read": GOLD["read"],
            "box": GOLD["box"],
        })

    trace = load_sibling(context.directory, "trace")
    # Older gateways give plugins no data directory: then nothing is recorded.
    data_dir = getattr(context, "data_dir", None)
    if data_dir:
        TRACE["path"] = os.path.join(data_dir, "trace.json")
        TRACE["graph"] = trace.load(TRACE["path"])

    async def trace_signature():
        """(screen name, thumbnail) of the screen now, or None when the game
        is not in front."""
        # Taken at once: a tap's screen, never one from before it.
        shot, focus = await asyncio.gather(context.screenshot(max_age=0), in_focus())
        if not shot or not focus:
            return None
        return await context.analyse(signature, shot)

    def signature(shot):
        return screens.classify(shot), trace.thumbnail(shot)

    def trace_finish(pending, after):
        """Records the pending tap with its after screen and saves."""
        if TRACE["pending"] is pending:
            TRACE["pending"] = None
        # A tap that took the game out of the front (home, another app) is
        # not an edge of the game's graph: dropped.
        if pending["before"] is None or after is None:
            return
        if TRACE["graph"].record(pending["before"], after, pending["tap"], time.time()):
            try:
                trace.save(TRACE["graph"], TRACE["path"])
            except OSError as e:
                logging.warning(f"Slayer Legend trace not saved: {e!r}")

    async def trace_after(pending):
        await asyncio.sleep(TRACE_AFTER_SECONDS)
        async with TRACE["lock"]:
            # A newer tap may have finished it already.
            if TRACE["pending"] is pending:
                try:
                    trace_finish(pending, await trace_signature())
                except Exception as e:
                    TRACE["pending"] = None
                    logging.warning(f"Slayer Legend trace failed: {e!r}")

    async def trace_tap(tap):
        """Takes the screen at once. It is this tap's "before" and also the
        "after" of a tap still waiting for its 2 s (the screen just before
        the next tap is what the previous one led to); that earlier tap is
        recorded now, so taps quicker than 2 s apart chain without a second
        screenshot. Under a lock: taps are handled one at a time, in
        order."""
        async with TRACE["lock"]:
            try:
                now = await trace_signature()
                previous = TRACE["pending"]
                if previous is not None:
                    previous["task"].cancel()
                    trace_finish(previous, now)
                pending = {"tap": tap, "before": now, "task": None}
                TRACE["pending"] = pending
                pending["task"] = asyncio.get_running_loop().create_task(trace_after(pending))
            except Exception as e:
                logging.warning(f"Slayer Legend trace failed: {e!r}")

    async def handle_trace(request):
        if TRACE["graph"] is None:
            return context.json({"error": "No data directory: nothing is recorded"}, status=503)
        try:
            tap = trace.parse_tap(await request.json())
        except ValueError:
            tap = None
        if tap is None:
            return context.json({"error": "Expected {x, y, kind: tap|long|swipe[, end: {x, y}]}, fractions 0-1"},
                                status=400)
        if TRACE["lock"] is None:
            TRACE["lock"] = asyncio.Lock()
        asyncio.get_running_loop().create_task(trace_tap(tap))
        return context.json({"queued": True}, status=202)

    async def handle_trace_state(request):
        graph = TRACE["graph"]
        return context.json({
            "enabled": graph is not None,
            "nodes": len(graph.nodes) if graph else 0,
            "edges": len(graph.edges) if graph else 0,
            "taps": graph.taps() if graph else 0,
            "last": graph.last if graph else None,
        })

    async def handle_trace_graph(request):
        graph = TRACE["graph"]
        return context.json(graph.public() if graph else {"nodes": [], "edges": []})

    ports.store.flush()
    context.app.on_startup.append(resume)
    for part in features:
        for method, path, handler in part["routes"]:
            (context.add_get if method == "GET" else context.add_post)(path, handler)
    async def handle_gold_font(request):
        return context.json({"height": len(gold.DIGITS["0"]),
                             "glyphs": {**gold.DIGITS, **gold.LETTERS, **gold.SIGNS}})

    context.add_get("/gold", handle_gold)
    context.add_get("/gold-font", handle_gold_font)
    context.add_get("/mine", handle_mine_state)
    context.add_post("/mine", handle_mine)
    context.add_post("/mine/timer", handle_mine_timer)
    context.add_get("/mode", handle_mode_state)
    context.add_post("/mode", handle_mode)
    context.add_post("/mode/timer", handle_mode_timer)
    context.add_post("/trace", handle_trace)
    context.add_get("/trace", handle_trace_state)
    context.add_get("/trace/graph", handle_trace_graph)
