"""The game's state, scanned: the one producer of what the plugin knows of
the game. Every capture a feature takes (ports.capture) is looked at once
(screens.look) and the readers that match its screen and overlays run
(game_rules.readers_for: pure), only reading, never a tap; what they read
becomes the state, each field with its seen time, verified and source
(game_rules.py), kept in state.json ("game") and given by GET /game.
Features read the state and ask for a fresh scan when they need a value
newer than they have (api get, require, fresh).

GET /game   {screens: [{screen, fields: [{field, label, shown, pending,
            value, seen, verified, source}], example, examples, details}],
            playing, scans}

While the user plays (an input in the last minute with the game in
front) a capture is scanned every rules.PLAYING_EVERY seconds, so that
what the user changes in the game (a stage, a weapon, pieces moved) is
the new state; each change made while no feature of the plugin holds the
lease is logged « User changed <field> from A to B ». The game's process
is looked at every few seconds: gone, or another process (a relaunch,
Android restarted), every fact turns unverified and the features' own
caches (the soul weapon read equipped, the preset and AUTO read) are
dropped (ports.relaunched's listeners).

api: get(field, max_age) -> {value, seen, verified, source} or
{value: None, why}; require(fields, max_age) -> {field: the same};
fresh(max_age) -> (shot, readings): a capture at most max_age seconds
old and what its scan read; scan(shot) -> readings; note(readings,
source); value(field); relaunched(why).
"""

import asyncio

# The holders that are the plugin's own (a change made under them is not the user's).
PLUGIN = ("launch", "mine", "watchdog", "mode", "stage_change")


def reader_table(screens, stage, select, counter, souls, weapon, engraving, controls, screen_rules, table,
                 weapons, cubes=None):
    """{reader id: fn(shot, base, overlays, plain) -> {field: value}}: the
    plugin's existing readers (stage.py, stage_select.py, gold.py,
    soul_counters.py, soul_weapon.py, engraving_screen.py,
    battle_controls.py), wired. table: stages.json; weapons: the soul
    weapons' table (engravings.json)."""
    names = select.regions(table)
    weapon_names = weapon.names_of(weapons) if weapons else []

    def shades(overlays):
        # Under the Soul Weapon screen the battle is shaded.
        return (screens.PARKED_SHADE, 1.0) if screens.SOUL_WEAPON in overlays else (1.0, screens.PARKED_SHADE)

    def battle_stage(shot, base, overlays, plain):
        number = None
        for shade in shades(overlays):
            number = select.battle_stage(shot, names, shade)
            if number:
                break
        return {"stage": number, "stage_numeral": stage.read_battle(shot)}

    def progress(shot, base, overlays, plain):
        return {"progress": stage.progress(shot)}

    def gold(shot, base, overlays, plain):
        reading = counter.read(shot, (1.0, screens.PARKED_SHADE) if screens.SOUL_WEAPON in overlays or base == "battle"
                               and "panel" in overlays else (1.0,))
        if base == "saver":
            place = ("saver", stage.read_saver(shot)[0])
        else:
            place = ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME)))
        return {"gold": {"text": reading["text"], "value": reading["value"]} if reading else None,
                "gold_reading": reading, "gold_place": place}

    def cube_row(shot, base, overlays, plain):
        return {"cubes": cubes.read(shot) if cubes else None}

    def saver_stage(shot, base, overlays, plain):
        _, number = screen_rules.answer(table, stage, "saver", stage.read_saver(shot), None)
        return {"stage": number}

    def badge(shot, base, overlays, plain):
        return {"preset": controls.badge(shot)}

    def battle_settings(shot, base, overlays, plain):
        return {"preset": controls.selected(shot)}

    def souls_row(shot, base, overlays, plain):
        row = souls.read(shot) if souls else None
        shown = {colour: {"text": count["text"], "value": count["value"]}
                 for colour, count in (row or {}).items() if count} or None
        return {"souls": shown, "souls_reading": row}

    def soul_weapon(shot, base, overlays, plain):
        selected = weapon.name(shot, weapon_names) if weapon_names else None
        tag, _ = weapon.tag(shot)
        equipped = selected if selected and tag == "Unequip" else None
        return {"soul_weapon_selected": selected, "soul_weapon_equipped": equipped}

    def region(shot, base, overlays, plain):
        view = select.view(shot, names)
        # A Move button means selectable, not cleared. Only an observed
        # battle stage can raise the highest-stage lower bound.
        return {"region": names[view["region"]] if view["region"] is not None else None}

    def engraving_grid(shot, base, overlays, plain):
        selected = engraving.weapon(shot, weapon_names, weapon.CARD_FONT) if engraving else None
        matching = [entry for entry in weapons["weapons"] if entry["name"] == selected] if selected else []
        if len(matching) != 1 or matching[0].get("grid") != 5:
            return {"engraving": None}
        read = engraving.grid(shot, 5) if engraving else None
        # No cell of the grid seen (another screen's pixels): nothing read.
        if not read or all(state == "none" for state in read["cells"].values()):
            return {"engraving": None}
        active = {tuple(cell) for cell in matching[0]["cells"]}
        visible = {cell for cell, state in read["cells"].items() if state != "none"}
        if visible != active:
            return {"engraving": None}
        cells = [[read["cells"][(row, col)] if (row, col) in active else "none"
                  for col in range(5)] for row in range(5)]
        return {"engraving": {"weapon": selected, "cells": cells,
                              "pieces": [[list(cell) for cell in piece] for piece in read["pieces"]]}}

    return {"battle_stage": battle_stage, "progress": progress, "gold": gold, "cubes": cube_row,
            "saver_stage": saver_stage,
            "badge": badge, "battle_settings": battle_settings, "souls": souls_row, "soul_weapon": soul_weapon,
            "region": region, "engraving": engraving_grid}


def read_all(screens, rules, readers, shot, last_runs=None, now=0.0, timings=None, force=(), done=()):
    """One scan of shot, pure but for the readers' work: (look, readings,
    ran). Each reader its screen shows runs once when due (last_runs:
    {reader: when it last ran}, None: all due) or forced, unless it is in
    done (it ran on this shot already); readings {field: value} (None: read
    nothing there); timings, when given, gets each reader's seconds."""
    import time
    look = screens.look(shot)
    classified = screens.classify(shot) if look["screen"] == "unknown" else None
    base, overlays, plain = rules.seen_screen(look, classified)
    look = {**look, "classified": classified}
    readings, ran = {}, []
    for reader in rules.readers_for(look, classified):
        if reader in done:
            continue
        if last_runs is not None and not rules.due(reader, last_runs.get(reader), now, force):
            continue
        began = time.perf_counter()
        for field, value in readers[reader](shot, base, overlays, plain).items():
            if value is not None or field not in readings:
                readings[field] = value
        if timings is not None:
            timings[reader] = time.perf_counter() - began
        ran.append(reader)
    return look, readings, ran


def game(ports, screens, rules, readers, archive=None, examples=None):
    """readers: reader_table's."""
    clock = ports.clock
    state = {"facts": rules.fresh(ports.store.saved.get("game"), clock.wall()), "saved_at": clock.monotonic(),
             "last_runs": {}, "scans": 0, "last": None, "lock": None, "pending": None, "task": None,
             "playing": False}
    ports.store.register("game", lambda: rules.persisted(state["facts"]))
    # Earlier versions kept the highest stage apart: it becomes the state's.
    kept = [ports.store.saved.get("highest"), (ports.store.saved.get("mode") or {}).get("highest")]
    kept = [n for n in kept if isinstance(n, int) and not isinstance(n, bool) and n > 0]
    if kept and "highest" not in state["facts"]:
        state["facts"], _ = rules.noted(state["facts"], {"highest": max(kept)}, clock.wall(), "setup")
        state["facts"] = rules.unverified(state["facts"])

    def save(changed):
        if changed or clock.monotonic() - state["saved_at"] >= rules.SAVE_EVERY:
            state["saved_at"] = clock.monotonic()
            ports.store.save()

    def note(readings, source="scan"):
        """Notes readings ({field: value}); logs the user's changes. Written
        at once when a lasting value changed or a field is first seen,
        else at most every SAVE_EVERY seconds."""
        before = state["facts"]
        state["facts"], changes = rules.noted(before, readings, clock.wall(), source)
        held = ports.lease.state() if hasattr(ports, "lease") else None
        ours = bool(held and held.get("holder") in PLUGIN)
        lasting = [change for change in changes if rules.lasting(change[0])]
        if source == "scan" and not ours:
            for field, old, new in lasting:
                ports.log("normal", rules.change_line(field, old, new))
        save(bool(lasting) or any(field not in before and field in state["facts"] for field in readings))
        return changes

    def scanned(shot, force=()):
        """The last scan when it was of shot and ran every forced reader
        its screen shows."""
        last = state["last"]
        if not last or last["pixels"] is not shot[2]:
            return None
        if any(reader in last["shows"] and reader not in last["ran"] for reader in force):
            return None
        return last

    async def scan(shot, force=()):
        """The readings of shot, scanned once (the readers in force run on
        it even when their every seconds are not over), given again after."""
        if not shot:
            return {}
        done = scanned(shot, force)
        if done:
            return done["readings"]
        if state["lock"] is None:
            state["lock"] = asyncio.Lock()
        async with state["lock"]:
            done = scanned(shot, force)
            if done:
                return done["readings"]
            last = state["last"] if state["last"] and state["last"]["pixels"] is shot[2] else None
            now = clock.monotonic()
            look, readings, ran = await ports.analyse(read_all, screens, rules, readers, shot,
                                                      dict(state["last_runs"]), now, None, tuple(force),
                                                      tuple(last["ran"]) if last else ())
            if archive:
                await ports.analyse(archive, look, shot, clock.wall())
            for reader in ran:
                state["last_runs"][reader] = now
            state["scans"] += 1
            if last:
                readings = {**last["readings"], **{k: v for k, v in readings.items()
                                                   if v is not None or k not in last["readings"]}}
                ran = list(last["ran"]) + ran
            state["last"] = {"pixels": shot[2], "readings": readings, "ran": set(ran), "look": look,
                             "shows": set(rules.readers_for(look, look["classified"]))}
            note(readings)
            return readings

    async def scan_later():
        while state["pending"] is not None:
            shot, state["pending"] = state["pending"], None
            try:
                await scan(shot)
            except Exception as e:
                ports.log("warning", f"Game scan failed: {e!r}")
        state["task"] = None

    def saw(shot):
        """ports.capture's hook: every capture scanned once, in the
        background (the latest one when several came during a scan)."""
        if not shot or scanned(shot):
            return
        state["pending"] = shot
        if state["task"] is None:
            state["task"] = ports.spawn(scan_later())

    async def fresh(max_age=0, force=()):
        """(shot, readings) of a capture at most max_age seconds old."""
        shot = await ports.capture(max_age=max_age)
        return shot, (await scan(shot, force) if shot else {})

    def readable_here():
        last = state["last"]
        return rules.fields_of(last["shows"]) if last else set()

    async def require(fields, max_age=0):
        """{field: fact} for each field: the state's when seen within
        max_age seconds, else read on a fresh capture; {value: None, why}
        when this screen does not show it or it did not read."""
        now = clock.wall()
        answer = {field: rules.fact_now(state["facts"], field, max_age, now) for field in fields}
        if any(fact is None for fact in answer.values()):
            wanted = tuple(reader for reader, spec in rules.READERS.items()
                           if any(field in spec["fields"] for field in fields))
            await fresh(min(max_age, 1.0), wanted)
            here = readable_here()
            now = clock.wall()
            for field in fields:
                if answer[field] is None:
                    fact = rules.fact_now(state["facts"], field, max(max_age, 1.0), now)
                    answer[field] = fact or {"value": None, "why": "unread" if field in here
                                             else "not readable on this screen"}
        return answer

    async def get(field, max_age=0):
        return (await require([field], max_age))[field]

    def value(field):
        fact = state["facts"].get(field)
        return fact["value"] if fact else None

    def relaunched(why):
        state["facts"] = rules.unverified(state["facts"])
        ports.log("normal", f"Game {why}: every game value unverified until read again")
        ports.store.save()

    async def watch():
        """The user's play scanned every PLAYING_EVERY seconds; the game's
        process looked at (ports.running notices a relaunch)."""
        while True:
            last = ports.last_input() if hasattr(ports, "last_input") else None
            playing = bool(last) and clock.monotonic() - last["monotonic"] < rules.PLAYING
            state["playing"] = playing
            await clock.sleep(rules.PLAYING_EVERY if playing else rules.PROCESS_EVERY)
            try:
                running = await ports.running()
                if playing and running and await ports.focused():
                    await fresh(rules.PLAYING_EVERY)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                ports.log("warning", f"Game scan failed: {e!r}")

    async def start(app):
        ports.spawn(watch())

    async def handle_game(request):
        answer = {**rules.answer(state["facts"]), "playing": state["playing"], "scans": state["scans"]}
        return ports.respond(examples(answer) if examples else answer)

    if hasattr(ports, "on_capture"):
        ports.on_capture(saw)
    if hasattr(ports, "on_relaunch"):
        ports.on_relaunch(relaunched)
    api = {"get": get, "require": require, "fresh": fresh, "scan": scan, "note": note, "value": value,
           "relaunched": relaunched, "facts": lambda: state["facts"]}
    return {"routes": [("GET", "/game", handle_game)], "startup": [start], "api": api}
