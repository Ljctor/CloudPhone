"""The screen the game shows and the stage it farms, and the stages the
mode can choose from.

GET /screen[?known=N]   {screen, stage, panel}, from a screenshot at most every 2 s;
                        panel: the bottom tab whose panel is open on the
                        battle screen (screens.TABS' names), else None
GET /stages[?known=N]   {highest, mpw18, mpw4}

Read-only: it never touches the game. The highest stage seen farmed is
kept in state.json ("highest"). What the answers say is in screen_rules.py.
"""

import asyncio
import logging

# An answer this young is given again instead of a new screenshot.
SECONDS = 2.0


def screen(ports, screens, stage, rules, values, table):
    cache = {"time": 0.0, "value": None, "lock": None}
    # The last stage number read in Power Saving Mode.
    farmed = {"number": None}
    # The highest stage seen farmed: the game only farms unlocked stages.
    # None until one is read.
    highest = {"number": values.number_or_none(ports.store.saved.get("highest"), 99999)}
    ports.store.register("highest", lambda: highest["number"])

    def note_highest(number):
        higher = rules.higher(highest["number"], number)
        if higher:
            highest["number"] = higher
            ports.store.save()

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

    async def read_screen(remembered):
        if not await ports.focused():
            return {"screen": "away", "stage": None}
        shot = await ports.capture(max_age=SECONDS)
        if not shot:
            return {"screen": None, "stage": None}
        name, read, panel = await ports.analyse(screen_facts, shot)
        answer, number = rules.answer(table, stage, name, read, farmed["number"] or remembered)
        answer = {**answer, "panel": panel}
        if number:
            farmed["number"] = number
            note_highest(number)
        return answer

    async def handle_screen(request):
        remembered = rules.remembered(table, request.query.get("known", ""))
        if cache["lock"] is None:
            cache["lock"] = asyncio.Lock()
        async with cache["lock"]:
            if cache["value"] is None or ports.clock.monotonic() - cache["time"] > SECONDS:
                try:
                    cache["value"] = await read_screen(remembered)
                except Exception as e:
                    logging.warning(f"Slayer Legend screen: no screenshot: {e!r}")
                    cache["value"] = {"screen": None}
                cache["time"] = ports.clock.monotonic()
        return ports.respond(cache["value"])

    async def handle_stages(request):
        """The mpw18 and mpw4 stages up to the highest one seen farmed (N:
        the highest the page saw), all of them when none is known."""
        try:
            note_highest(int(request.query.get("known") or 0) or None)
        except ValueError:
            pass
        number = highest["number"]
        return ports.respond({"highest": number, "mpw18": rules.stage_list(table, 18, number),
                              "mpw4": rules.stage_list(table, 4, number)})

    return {"routes": [("GET", "/screen", handle_screen), ("GET", "/stages", handle_stages)]}
