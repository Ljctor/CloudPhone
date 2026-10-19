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

MINE_SECONDS = 10
# What the game is set to do. "mpw18" (farming a stage with 18 monsters per
# wave) is the default; the others run until a time, then it goes back to it.
MODES = ("mpw18", "mpw4", "free", "mine")
MODE = {"mode": "mpw18", "until": None, "stage18": None, "stage4": None, "highest": None,
        "configured": False, "state": "idle", "message": "", "task": None}


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
        feature("trace").trace(ports, screens, load_sibling(context.directory, "trace")),
        feature("gold").gold(ports, screens, stage, load_sibling(context.directory, "gold"), feature("gold_rules")),
        feature("mine").mine(ports, screens, load_sibling(context.directory, "mine"), feature("mine_rules"),
                             feature("timer_rules"), values),
    ]
    mines = features[-1]["api"]
    mine_state = mines["state"]

    # What a gateway restart must not lose, so that farming meant to run
    # with the page closed goes on: the mode and its timer (state.json, see
    # ports.State).
    ports.store.register("mode", lambda: {key: MODE[key] for key in (
        "mode", "until", "stage18", "stage4", "highest", "configured")})
    save_state = ports.store.save
    alert = ports.notify
    number_or_none, time_or_none = values.number_or_none, values.time_or_none

    def restore_state():
        saved = ports.store.saved
        mode = saved.get("mode") or {}
        MODE.update(mode=mode.get("mode") if mode.get("mode") in MODES else "mpw18",
                    until=time_or_none(mode.get("until")), configured=mode.get("configured") is True,
                    **{key: number_or_none(mode.get(key), 99999) for key in ("stage18", "stage4", "highest")})
        # A timer that ended while the gateway was down: that mode or the
        # mine is over, not resumed.
        now = time.time()
        ended = []
        if MODE["mode"] != "mpw18" and MODE["until"] is not None and MODE["until"] <= now:
            ended.append(f"mode {MODE['mode']}")
            MODE.update(mode="mpw18", until=None)
        if mines["ended"]:
            ended.append("mine")
        if MODE["mode"] == "mine" and not mine_state()["enabled"]:
            MODE.update(mode="mpw18", until=None)
        if ended:
            logging.info(f"Slayer Legend: timer ended while the gateway was stopped ({', '.join(ended)}): "
                         "back to mpw18 farming, mine off"
                         + (" once Repeat entry is unticked" if mine_state()["state"] == "stopping" else ""))

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

    async def watch_mode():
        """Ends a timed mode: back to mpw18 farming once its time is up (the
        mine ends its last entry first)."""
        try:
            while MODE["mode"] != "mpw18":
                await asyncio.sleep(MINE_SECONDS)
                if MODE["mode"] == "mine":
                    if not mine_state()["enabled"]:
                        await back_to_default("Mine terminée" if mine_state()["state"] == "stopped" else "Mine arrêtée")
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
            mines["start"](numbers["floor"], numbers["area"], until)
        else:
            mines["stop"]()
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
            mines["set_until"](MODE["until"])
        save_state()
        return context.json(mode_state())

    async def resume(app):
        """At the gateway's start: the timed mode state.json kept goes on."""
        loop = asyncio.get_running_loop()
        if MODE["mode"] != "mpw18":
            mode_report(*{"free": ("free", "Jeu libre : rien n’est touché jusqu’à la fin du minuteur"),
                          "mine": ("mine", "Mine")}.get(MODE["mode"], ("idle", f"Farming {MODE['mode']}")))
            MODE["task"] = loop.create_task(watch_mode())

    ports.store.flush()
    for part in features:
        context.app.on_startup.extend(part.get("startup", []))
    context.app.on_startup.append(resume)
    for part in features:
        for method, path, handler in part["routes"]:
            (context.add_get if method == "GET" else context.add_post)(path, handler)
    context.add_get("/mode", handle_mode_state)
    context.add_post("/mode", handle_mode)
    context.add_post("/mode/timer", handle_mode_timer)
