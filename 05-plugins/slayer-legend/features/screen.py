"""The screen the game shows and the stage it farms, and the stages the
mode can choose from.

GET /screen[?known=N]   {screen, stage, panel}, from a screenshot at most every 250 ms;
                        panel: the bottom tab whose panel is open on the
                        battle screen (screens.TABS' names), else None
GET /stages[?known=N]   {highest, mpw18, mpw4}: every mpw18 and mpw4 stage,
                        those past highest too (the page marks them)

Read-only: it never touches the game. The stage and the highest stage
seen are the game's state (features/game.py: the scan of the capture,
kept in state.json "game"); without it (an older setup in the tests) the
highest is kept here, in state.json ("highest"). ?known=N: a stage a
page saw, noted as the highest when it is higher. What the answers say is
in screen_rules.py.
"""

import asyncio

# An answer this young is given again instead of a new screenshot.
SECONDS = 0.25


def screen(ports, screens, stage, rules, values, table):
    cache = {"time": 0.0, "value": None, "lock": None}
    quick_cache = {"time": 0.0, "value": None, "lock": None}
    # The last stage number read in Power Saving Mode.
    farmed = {"number": None}
    # The highest stage seen farmed: the game only farms unlocked stages.
    # None until one is read.
    highest = {"number": values.number_or_none(ports.store.saved.get("highest"), 99999)}
    game = getattr(ports, "game", None)
    if game is None:
        ports.store.register("highest", lambda: highest["number"])

    def note_highest(number, source="scan"):
        if game is not None:
            if number:
                game["note"]({"highest": number}, source)
            return
        higher = rules.higher(highest["number"], number)
        if higher:
            highest["number"] = higher
            ports.store.save()

    def highest_now():
        return game["value"]("highest") if game is not None else highest["number"]

    def screen_facts(shot):
        """The screen and what it says of the stage: (number, numeral) in
        Power Saving Mode, the name's numeral on the battle screen; and the
        panel open over the battle screen."""
        name = screens.classify(shot)
        if name == "saver":
            return name, stage.read_saver(shot), None
        if name in ("battle", "menu"):
            tab = screens.open_tab(shot) if name == "battle" else None
            return name, stage.read_battle(shot), tab[1] if tab else None
        return name, None, None

    def screen_name(shot):
        """The screen, and the panel open over the battle screen."""
        name = screens.classify(shot)
        tab = screens.open_tab(shot) if name == "battle" else None
        return name, tab[1] if tab else None

    async def read_screen(remembered):
        if not await ports.focused():
            return {"screen": "away", "stage": None}
        shot = await ports.capture(max_age=SECONDS)
        if not shot:
            return {"screen": None, "stage": None}
        if game is not None:
            # The stage as the scan of this capture read it.
            name, panel = await ports.analyse(screen_name, shot)
            readings = await game["scan"](shot, ("battle_stage", "saver_stage"))
            read = ((readings.get("stage"), None) if name == "saver"
                    else readings.get("stage_numeral") if name in ("battle", "menu") else None)
            known = game["value"]("stage") or remembered
        else:
            name, read, panel = await ports.analyse(screen_facts, shot)
            known = farmed["number"] or remembered
        answer, number = rules.answer(table, stage, name, read, known)
        answer = {**answer, "panel": panel}
        if number:
            farmed["number"] = number
            note_highest(number)
        return answer

    async def quick_screen():
        """Navigation geometry only, without waiting for numeric readers."""
        if quick_cache["lock"] is None:
            quick_cache["lock"] = asyncio.Lock()
        async with quick_cache["lock"]:
            if quick_cache["value"] is not None and ports.clock.monotonic() - quick_cache["time"] < SECONDS:
                return quick_cache["value"]
            shot, focused = await asyncio.gather(ports.capture(max_age=SECONDS), ports.focused())
            if shot and focused:
                seen = await ports.analyse(screens.look, shot)
                name, overlays = seen["screen"], seen["overlays"]
                plain = bool(seen.get("plain"))
            else:
                name, overlays = ("away" if not focused else "unknown"), []
                plain = False
            answer = {"screen": name, "panel": None,
                      "scan": {"screen": name, "overlays": overlays, "plain": plain,
                               "at": ports.clock.wall()}}
            quick_cache.update(time=ports.clock.monotonic(), value=answer)
            return answer

    async def handle_screen(request):
        if request.query.get("quick") == "1":
            return ports.respond(await quick_screen())
        remembered = rules.remembered(table, request.query.get("known", ""))
        if cache["lock"] is None:
            cache["lock"] = asyncio.Lock()
        async with cache["lock"]:
            if cache["value"] is None or ports.clock.monotonic() - cache["time"] > SECONDS:
                try:
                    cache["value"] = await read_screen(remembered)
                except Exception as e:
                    ports.log("warning", f"Screen: no screenshot: {e!r}")
                    cache["value"] = {"screen": None}
                cache["time"] = ports.clock.monotonic()
        return ports.respond(cache["value"])

    async def handle_stages(request):
        """Every mpw18 and mpw4 stage, and the highest one seen farmed (N:
        the highest the page saw): the stage change may reach one past it."""
        try:
            note_highest(int(request.query.get("known") or 0) or None, "page")
        except ValueError:
            pass
        number = highest_now()
        return ports.respond({"highest": number, "mpw18": rules.stage_list(table, 18, None),
                              "mpw4": rules.stage_list(table, 4, None)})

    return {"routes": [("GET", "/screen", handle_screen), ("GET", "/stages", handle_stages)]}
