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

While enabled with the game in front, one server task captures continuously,
even with the browser closed: every 0.5 seconds after recent input, otherwise
every 1.5 seconds. Detection publishes before independent bounded readers;
each reader keeps its own poll interval. Thus what the user changes in the
game (a stage, a weapon, pieces moved) becomes the new state; each change made while no feature of the plugin holds the
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
import math
import time

# The holders that are the plugin's own (a change made under them is not the user's).
# Server-side observer cadence: active gestures need prompt recognition;
# stable foreground remains observed with no connected browser. Process/focus
# probes stay slower than captures to avoid an adb probe for every frame.
OBSERVE_ACTIVE = 0.5
OBSERVE_STABLE = 1.5
OBSERVE_PROBE = 5.0

PLUGIN = ("launch", "mine", "watchdog", "mode", "stage_change", "resource_refresh")


def reader_table(screens, stage, select, counter, souls, weapon, engraving, controls, screen_rules, table,
                 weapons, cubes=None, currencies=None, equipment=None):
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

    def currency_bar(shot, base, overlays, plain):
        return {field: currencies.read(shot, field) if currencies else None
                for field in ("emerald", "diamond")}

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

    def equipment_row(shot, base, overlays, plain):
        if not equipment:
            return {}
        tab = weapon.tab(shot)
        if tab == "weapon":
            return {"weapon_l3": equipment.read(shot)}
        if tab == "accessories":
            return {"accessory_l3": equipment.read(shot)}
        return {}

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
            "currencies": currency_bar,
            "saver_stage": saver_stage,
            "badge": badge, "battle_settings": battle_settings, "souls": souls_row, "soul_weapon": soul_weapon,
            "equipment_l3": equipment_row,
            "region": region, "engraving": engraving_grid}


def read_all(screens, rules, readers, shot, last_runs=None, now=0.0, timings=None, force=(), done=(), previous_look=None):
    """One scan of shot, pure but for the readers' work: (look, readings,
    ran). Each reader its screen shows runs once when due (last_runs:
    {reader: when it last ran}, None: all due) or forced, unless it is in
    done (it ran on this shot already); readings {field: value} (None: read
    nothing there); timings, when given, gets each reader's seconds. A
    changed observed screen/overlay runs its visible readers immediately."""
    import time
    look = screens.look(shot)
    classified = screens.classify(shot) if look["screen"] == "unknown" else None
    base, overlays, plain = rules.seen_screen(look, classified)
    look = {**look, "classified": classified}
    # A reader shared by several panels (notably Weapon/Accessories)
    # must read the newly visible panel even inside its normal poll interval.
    def identity(view):
        return (rules.seen_screen(view, view.get("classified")), view.get("quest_tab"))
    changed_screen = previous_look is not None and identity(previous_look) != identity(look)
    readings, ran = {}, []
    for reader in rules.readers_for(look, classified):
        if reader in done:
            continue
        if last_runs is not None and not changed_screen and not rules.due(reader, last_runs.get(reader), now, force):
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
             "playing": False, "watcher": None, "epoch": 0, "relaunched_at": None, "input": None}
    observations = []
    frames = []  # Bounded identity cache; active jobs retain their own frame.
    lanes = {}   # At most one running and one latest pending job per reader.
    runtime = {"detected": 0, "discarded": 0, "errors": 0, "readers": {},
               "detection_seconds": None, "archive_seconds": None, "archive_errors": 0,
               "producer": {"captures": 0, "foreground": False, "interval_seconds": None}}
    applied = {}  # Includes unread observations, whose facts keep their historical seen time.
    archive_slot = {"pending": None, "task": None}
    detector_lock = None
    explicit_lock = None
    reader_limit = None

    def observed(shot):
        """Capture acquisition time, never OCR completion time. Older ports
        fall back to the first hook/scan entry, before queueing or analysis."""
        for pixels, size, at, epoch in observations:
            if pixels is shot[2] and size == shot[:2]:
                return at, epoch
        at = ports.capture_time(shot) if hasattr(ports, "capture_time") else None
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at):
            at = clock.wall()
        observations.insert(0, (shot[2], shot[:2], at, state["epoch"]))
        del observations[8:]
        return at, state["epoch"]
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

    def note(readings, source="scan", seen=None):
        """Notes readings ({field: value}); logs the user's changes. Written
        at once when a lasting value changed or a field is first seen,
        else at most every SAVE_EVERY seconds."""
        before = state["facts"]
        state["facts"], changes = rules.noted(before, readings, clock.wall() if seen is None else seen, source)
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

    def valid(frame):
        return (frame["epoch"] == state["epoch"] and
                (state["relaunched_at"] is None or frame["at"] >= state["relaunched_at"]))

    def identify(shot):
        look = screens.look(shot)
        return {**look, "classified": screens.classify(shot) if look["screen"] == "unknown" else None}

    async def archive_later():
        try:
            while archive_slot["pending"] is not None:
                frame, archive_slot["pending"] = archive_slot["pending"], None
                began = time.perf_counter()
                try:
                    await ports.analyse(archive, frame["look"], frame["shot"], frame["at"])
                except Exception as exc:
                    runtime["archive_errors"] += 1
                    ports.log("warning", f"Game archive failed: {exc!r}")
                finally:
                    runtime["archive_seconds"] = time.perf_counter() - began
        finally:
            archive_slot["task"] = None

    async def detect(shot):
        nonlocal detector_lock
        at, epoch = observed(shot)
        for frame in frames:
            if frame["pixels"] is shot[2]:
                return frame if valid(frame) else None
        if detector_lock is None:
            detector_lock = asyncio.Lock()
        async with detector_lock:
            for frame in frames:
                if frame["pixels"] is shot[2]:
                    return frame if valid(frame) else None
            frame = {"shot": shot, "pixels": shot[2], "size": [shot[0], shot[1]], "at": at,
                     "epoch": epoch, "readings": {}, "ran": set(), "jobs": {}}
            if not valid(frame):
                runtime["discarded"] += 1
                return None
            began = time.perf_counter()
            look = await getattr(ports, "detect", ports.analyse)(identify, shot)
            runtime["detection_seconds"] = time.perf_counter() - began
            if not valid(frame):
                runtime["discarded"] += 1
                return None
            previous = state["last"]
            changed = previous is not None and (
                rules.seen_screen(previous["look"], previous["look"].get("classified")),
                previous["look"].get("quest_tab")) != (
                rules.seen_screen(look, look.get("classified")), look.get("quest_tab"))
            user = ports.last_input() if hasattr(ports, "last_input") else None
            mark = user.get("monotonic") if user else None
            changed_input = (mark is not None and (state["input"] is None or mark > state["input"])
                             and isinstance(user.get("wall"), (int, float)) and user["wall"] <= at)
            if changed_input:
                state["input"] = mark
            frame.update(look=look, shows=set(rules.readers_for(look, look["classified"])),
                         changed=changed or changed_input)
            frames.insert(0, frame)
            del frames[8:]
            # Detection is visible immediately, independently of every resource reader.
            if previous is None or at >= previous["at"]:
                state["last"] = frame
            else:
                runtime["discarded"] += 1
            state["scans"] += 1
            runtime["detected"] += 1
            if archive:
                archive_slot["pending"] = frame
                if archive_slot["task"] is None:
                    archive_slot["task"] = ports.spawn(archive_later())
            return frame

    async def read(frame, reader):
        nonlocal reader_limit
        if reader_limit is None:
            reader_limit = asyncio.Semaphore(2)
        queued = time.perf_counter()
        metric = runtime["readers"].setdefault(reader, {"runs": 0, "errors": 0, "discarded": 0})
        metric["queued"] = metric.get("queued", 0) + 1
        try:
            await reader_limit.acquire()
        except BaseException:
            metric["queued"] -= 1
            raise
        metric["queued"] -= 1
        try:
            if not valid(frame):
                metric["discarded"] += 1
                return {}
            metric["queue_seconds"] = time.perf_counter() - queued
            metric["running"] = metric.get("running", 0) + 1
            began = time.perf_counter()
            try:
                values = await ports.analyse(readers[reader], frame["shot"],
                                            *rules.seen_screen(frame["look"], frame["look"]["classified"]))
                if not valid(frame):
                    metric["discarded"] += 1
                    return {}
                values = {field: value for field, value in values.items()
                          if value is not None or frame["readings"].get(field) is None}
                frame["readings"].update(values)
                frame["ran"].add(reader)
                state["last_runs"][reader] = max(state["last_runs"].get(reader, 0), frame["started"])
                # A newer unread result is evidence too: old OCR cannot reverify it.
                accepted = {field: value for field, value in values.items()
                            if frame["at"] >= applied.get(field, float("-inf"))}
                metric["discarded"] += len(values) - len(accepted)
                for field in accepted:
                    applied[field] = frame["at"]
                note(accepted, seen=frame["at"])
                metric["at"] = frame["at"]
                metric["runs"] += 1
                return values
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                metric["errors"] += 1
                metric["error"] = str(exc)
                runtime["errors"] += 1
                ports.log("warning", f"Game reader {reader} failed: {exc!r}")
                return {}
            finally:
                metric["running"] -= 1
                metric["seconds"] = time.perf_counter() - began
        finally:
            reader_limit.release()

    def due(frame, force=()):
        frame.setdefault("started", clock.monotonic())
        return [reader for reader in readers if reader in frame["shows"] and reader not in frame["ran"]
                and (frame["changed"] or rules.due(reader, state["last_runs"].get(reader),
                                                   frame["started"], force))]

    def reader_task(frame, reader):
        task = asyncio.create_task(read(frame, reader))
        return getattr(ports, "track_task", lambda task: task)(task)

    async def reader_later(reader, lane):
        try:
            while lane["pending"] is not None:
                frame, lane["pending"] = lane["pending"], None
                task = reader_task(frame, reader)
                frame["jobs"][reader] = task
                await task
        finally:
            lane["task"] = None

    def enqueue(frame):
        for reader in due(frame):
            lane = lanes.setdefault(reader, {"pending": None, "task": None})
            if reader in frame["jobs"]:
                continue
            if lane["pending"] is not None and lane["pending"] is not frame:
                runtime["discarded"] += 1
            lane["pending"] = frame
            if lane["task"] is None:
                lane["task"] = ports.spawn(reader_later(reader, lane))

    async def scan(shot, force=()):
        """Wait for this frame's due/forced readers. Background detection never waits for OCR."""
        nonlocal explicit_lock
        if not shot:
            return {}
        if explicit_lock is None:
            explicit_lock = asyncio.Lock()
        async with explicit_lock:
            frame = await detect(shot)
            if frame is None:
                return {}
            tasks = []
            for reader in due(frame, force):
                lane = lanes.get(reader)
                if lane and lane["pending"] is frame:
                    lane["pending"] = None
                task = frame["jobs"].get(reader)
                if task is None or task.done():
                    task = reader_task(frame, reader)
                    frame["jobs"][reader] = task
                tasks.append(task)
            if tasks:
                await asyncio.gather(*(asyncio.shield(task) for task in tasks))
            return dict(frame["readings"]) if valid(frame) else {}

    async def scan_later():
        try:
            while state["pending"] is not None:
                shot, state["pending"] = state["pending"], None
                try:
                    frame = await detect(shot)
                    if frame is not None:
                        enqueue(frame)
                except Exception as exc:
                    runtime["errors"] += 1
                    ports.log("warning", f"Game detection failed: {exc!r}")
        finally:
            state["task"] = None

    def saw(shot):
        """Capture hook: one detection in flight plus one latest pending frame."""
        if not shot or scanned(shot):
            return
        observed(shot)
        if state["pending"] is not None and state["pending"][2] is not shot[2]:
            runtime["discarded"] += 1
        state["pending"] = shot
        if state["task"] is None:
            state["task"] = ports.spawn(scan_later())

    async def fresh(max_age=0, force=()):
        """(shot, readings) of a capture at most max_age seconds old."""
        shot = await ports.capture(max_age=max_age)
        return shot, (await scan(shot, force) if shot else {})

    async def scan_visible(shot):
        """Read every calibrated reader shown by a user's final gesture frame."""
        return await scan(shot, tuple(readers))

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
            shot, readings = await fresh(min(max_age, 1.0) if max_age is not None else 0, wanted)
            here = readable_here()
            now = clock.wall()
            # Derived fields (highest, individual souls) count only when this
            # capture actually established their value. An unread new image
            # never falls back to a recent historical fact.
            confirmed, _ = rules.noted({}, readings, observed(shot)[0] if shot else now)
            for field in fields:
                if answer[field] is None:
                    fact = rules.fact_now(state["facts"], field, max(max_age, 1.0) if max_age is not None else None, now)
                    proof = confirmed.get(field)
                    if not proof or not fact or proof["value"] != fact["value"] or proof["seen"] != fact["seen"]:
                        fact = None
                    answer[field] = fact or {"value": None, "why": "unread" if field in here
                                             else "not readable on this screen"}
                else:
                    # A refresh for another field may have crossed a relaunch
                    # or disproved this cached reading while we awaited OCR.
                    answer[field] = rules.fact_now(state["facts"], field, max_age, now) or {
                        "value": None, "why": "unread" if field in here else "not readable on this screen"}
        return answer

    async def get(field, max_age=0):
        return (await require([field], max_age))[field]

    def value(field):
        fact = state["facts"].get(field)
        return fact["value"] if fact else None

    def relaunched(why):
        state["epoch"] += 1
        state["relaunched_at"] = clock.wall()
        state["last"] = None
        state["last_runs"] = {}
        applied.clear()
        state["pending"] = None
        for lane in lanes.values():
            lane["pending"] = None
        state["facts"] = rules.unverified(state["facts"])
        ports.log("normal", f"Game {why}: every game value unverified until read again")
        ports.store.save()

    async def watch():
        """One serial server capture producer, independent of browser activity."""
        foreground = False
        probe_at = float("-inf")
        while True:
            interval = rules.PROCESS_EVERY
            try:
                enabled = getattr(ports, "enabled", lambda: True)()
                if not enabled:
                    foreground = False
                    probe_at = float("-inf")
                elif clock.monotonic() >= probe_at:
                    running = await ports.running()
                    foreground = bool(running and await ports.focused())
                    probe_at = clock.monotonic() + (OBSERVE_PROBE if foreground else rules.PROCESS_EVERY)
                last = ports.last_input() if hasattr(ports, "last_input") else None
                state["playing"] = bool(last and foreground and
                                        clock.monotonic() - last["monotonic"] < rules.PLAYING)
                runtime["producer"]["foreground"] = foreground
                if enabled and foreground:
                    interval = OBSERVE_ACTIVE if state["playing"] else OBSERVE_STABLE
                    began = time.perf_counter()
                    shot = await ports.capture(max_age=0)
                    runtime["producer"]["capture_seconds"] = time.perf_counter() - began
                    if shot:
                        runtime["producer"]["captures"] += 1
                        runtime["producer"]["at"] = observed(shot)[0]
                        # New ports publish through the hook. Older ports need the same
                        # coalescing hook here; no explicit scan or reader await.
                        if not hasattr(ports, "on_capture"):
                            saw(shot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                runtime["errors"] += 1
                ports.log("warning", f"Game observer failed: {exc!r}")
            runtime["producer"]["interval_seconds"] = interval
            await clock.sleep(interval)

    async def start(app):
        if state["watcher"] is None or state["watcher"].done():
            state["watcher"] = ports.spawn(watch())

    async def handle_game(request):
        answer = {**rules.answer(state["facts"]), "playing": state["playing"], "scans": state["scans"]}
        last = state["last"]
        answer["observation"] = {**runtime,
            "readers": {reader: {**metric, "age_seconds": max(0, clock.wall() - metric["at"])
                                  if "at" in metric else None}
                        for reader, metric in runtime["readers"].items()},
            "reader_concurrency": 2,
            "reader_running": sum(metric.get("running", 0) for metric in runtime["readers"].values()),
            "reader_waiting": sum(metric.get("queued", 0) for metric in runtime["readers"].values()),
            "detection_queued": int(state["pending"] is not None),
            "reader_queued": sum(lane["pending"] is not None for lane in lanes.values()),
            "reader_workers": sum(lane["task"] is not None for lane in lanes.values()),
            "archive_queued": int(archive_slot["pending"] is not None),
            "age_seconds": max(0, clock.wall() - last["at"]) if last else None}
        answer["scan"] = ({"size": last["size"], "at": last["at"],
                          "screen": last["look"]["screen"],
                          "overlays": sorted(last["look"].get("overlays") or ()),
                          "expected": sorted(last["shows"]), "ran": sorted(last["ran"])} if last else None)
        if last and "quest_tab" in last["look"]:
            answer["scan"]["quest_tab"] = last["look"]["quest_tab"]
        return ports.respond(examples(answer) if examples else answer)

    if hasattr(ports, "on_capture"):
        ports.on_capture(saw)
    if hasattr(ports, "on_relaunch"):
        ports.on_relaunch(relaunched)
    api = {"get": get, "require": require, "fresh": fresh, "scan": scan, "scan_visible": scan_visible,
           "note": note, "value": value,
           "relaunched": relaunched, "facts": lambda: state["facts"],
           "view": lambda: ({"at": state["last"]["at"], "look": state["last"]["look"]}
                            if state["last"] else None)}
    return {"routes": [("GET", "/game", handle_game)], "startup": [start], "api": api}
