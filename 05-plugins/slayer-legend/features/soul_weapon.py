"""Equips a farming mode's soul weapon (its loadout's soul_weapon id): the
last step of the stage change feature's farm(), after AUTO, and the step
the watchdog asks for after a relaunch (once the game is back). Never
periodic.

The sequence, every move through the navigation guard on a fresh capture
of that screen, under the stage change's lease:

- the battle screen with nothing over it (the stage change's to_battle);
- Equipment (the bottom tab); the Weapon tab must read active (the panel
  may open on Accessories, where the same top-right icon opens Black Orb:
  then the Weapon tab first);
- the Soul Weapon icon; its title must read "Soul Weapon";
- on the list, soul_weapon_rules.plan: select cells (read by the card's
  name), scroll, and Equip only when the target is selected, owned and its
  one tag reads Equip; afterwards the tag must read Unequip with the name
  unchanged. Unequip is never tapped (the guard refuses any tap on a tag
  read Unequip). At most MOST_MOVES moves, and a move that changes nothing
  stops it;
- closed with the red X, then the panel with its own tab (to_battle).

Fast: each wait polls for what the move should show (POLL, at most
WAIT_MOST), no fixed long sleeps. Skipped altogether when the last check
read the target equipped and neither a relaunch nor a user input came
since (the cache, in memory: a gateway restart reads again). Its duration
is logged.

The engraving (read only, phase 3b places it): once the target is
equipped, its engraving screen (the card's big icon) is read for whether
the grid's filled cells are the chosen variant's; one alert when not.
Only once the screen's readers are calibrated on a capture
(soul_weapon.ENGRAVING_CALIBRATED): until then not opened.
"""

import logging

EQUIPMENT_TAP = (0.41, 0.966)
WEAPON_TAB_TAP = (0.12, 0.414)
SOUL_WEAPON_TAP = (0.92, 0.446)
CLOSE_TAP = (0.5, 0.955)
ENGRAVING_TAP = (0.33, 0.636)
ENGRAVING_CLOSE_TAP = (0.11, 0.955)
# A list scroll: a slow drag (no fling).
SWIPE_MS = 700
# After a scroll the list may still glide: one more look this long after.
SETTLE = 0.4


def soul_weapon(ports, screens, reader, rules, table, helpers, expected_cells=None):
    """reader: soul_weapon.py; rules: soul_weapon_rules.py; table:
    engravings.json; helpers: the stage change's look, tap (front first),
    front, to_battle and Stop; expected_cells(id, variant): the cells the
    variant fills (the engraving feature's), for the engraving check."""
    names = reader.names_of(table)
    order = rules.order_names(table)
    by_id = {entry["id"]: entry for entry in table["weapons"]}
    saved = ports.store.saved.get("soul_weapon") or {}
    status = {"direction": saved.get("direction") if saved.get("direction") in (1, -1) else None,
              "switch": "off" if saved.get("switch") == "off" else "real",
              "cache": None, "relaunched": None, "last": None}
    ports.store.register("soul_weapon", lambda: {"direction": status["direction"], "switch": status["switch"]})
    Stop = helpers.Stop

    async def wait_for(test, most=None):
        """(shot, value) of the first fresh look where test(shot) is true
        (polled every POLL), or (the last shot, None) after most seconds."""
        end = ports.clock.monotonic() + (rules.WAIT_MOST if most is None else most)
        while True:
            await ports.clock.sleep(rules.POLL)
            shot = await helpers.look()
            value = await ports.analyse(test, shot)
            if value or ports.clock.monotonic() >= end:
                return shot, value

    def view_of(shot):
        return reader.view(shot, names)

    async def settled(before):
        """The first view that differs from before and reads the same on
        the next look (the card's name follows the frame a moment later):
        (shot, view) or (shot, None)."""
        end = ports.clock.monotonic() + rules.WAIT_MOST
        last = None
        while True:
            await ports.clock.sleep(rules.POLL)
            shot = await helpers.look()
            seen = await ports.analyse(view_of, shot)
            if rules.progressed(before, seen):
                if last is not None and rules.signature(last) == rules.signature(seen):
                    return shot, seen
                last = seen
            else:
                last = None
            if ports.clock.monotonic() >= end:
                return shot, None

    async def open_screen():
        shot = await helpers.to_battle()
        await helpers.tap(shot, "battle", "menu_equipment", EQUIPMENT_TAP)
        shot, tab = await wait_for(reader.tab)
        if tab == "accessories":
            await helpers.tap(shot, "equipment_accessories", "weapon", WEAPON_TAB_TAP)
            shot, tab = await wait_for(lambda s: reader.tab(s) == "weapon" and "weapon")
        if tab != "weapon":
            raise Stop(f"onglet Weapon de l’équipement pas actif (lu : {tab or 'rien'})")
        await helpers.tap(shot, "equipment_weapon", "soul_weapon", SOUL_WEAPON_TAP)
        shot, opened = await wait_for(reader.title)
        if not opened:
            raise Stop("ouverture de l’écran Soul Weapon")
        return shot

    async def close_screen(shot):
        await helpers.tap(shot, "soul_weapon", "close", CLOSE_TAP)
        shot, closed = await wait_for(lambda s: not reader.title(s) and reader.tab(s) == "weapon")
        if not closed:
            raise Stop("fermeture de l’écran Soul Weapon")
        await helpers.to_battle()

    async def move(shot, view, step, target):
        seen = rules.seen(view, target)
        if step[0] == "select":
            await helpers.tap(shot, "soul_weapon", "select", reader.select_point(view["rows"][step[1]]),
                              verified=True, seen=seen)
        elif step[0] == "scroll":
            rows = view["rows"]
            # From the last whole cell to the first (or back): the list moves
            # by about its height less a cell, each in its upper part.
            first, last = reader.select_point(rows[0]), reader.select_point(rows[-1])
            start, end = (last, first) if step[1] == "down" else (first, last)
            await helpers.front()
            await ports.swipe(shot, "soul_weapon", "scroll", start, end, SWIPE_MS, verified=True, seen=seen)
            await ports.clock.sleep(SETTLE)
        else:
            await helpers.tap(shot, "soul_weapon", "equip", rules.tag_point(view), verified=True, seen=seen)

    async def check_engraving(shot, entry, variant):
        """On the Soul Weapon screen with the target selected: its
        engraving read against the variant's cells; the alert's text when
        they differ, else None. Back on the Soul Weapon screen."""
        if not (reader.ENGRAVING_CALIBRATED and expected_cells and variant and entry.get("grid")):
            return shot, None
        want = expected_cells(entry["id"], variant)
        if want is None:
            return shot, None
        await helpers.tap(shot, "soul_weapon", "engraving", ENGRAVING_TAP)
        shot, opened = await wait_for(lambda s: reader.engraving_title(s, names)[0])
        if not opened:
            raise Stop("ouverture de la gravure")
        named = (await ports.analyse(reader.engraving_title, shot, names))[1]
        cells = await ports.analyse(reader.engraving_cells, shot, entry["grid"])
        await helpers.tap(shot, "soul_weapon_engraving", "close", ENGRAVING_CLOSE_TAP)
        shot, back = await wait_for(reader.title)
        if not back:
            raise Stop("retour de la gravure à l’écran Soul Weapon")
        if named not in (None, entry["name"]):
            return shot, f"Gravure : l’écran montre {named}, pas {entry['name']}"
        if cells is not None and cells != set(map(tuple, want)):
            return shot, f"Gravure de {entry['name']} : la grille ne correspond pas à la variante {variant}"
        return shot, None

    async def ensure(target_id, variant=None):
        """The weapon target_id equipped: "cached", "equipped" (it already
        was) or "done" (Equip tapped); else Stop with the step, in French.
        The engraving's mismatch, if read, in status["engraving"]."""
        since = ports.clock.monotonic()
        entry = by_id.get(target_id)
        if entry is None:
            raise Stop(f"arme {target_id} inconnue")
        target = entry["name"]
        if rules.shared(target, table):
            raise Stop(f"{target} : deux armes portent ce nom, à équiper à la main")
        cache = status["cache"]
        last_input = (ports.last_input() or {}).get("wall") if hasattr(ports, "last_input") else None
        if cache and cache["id"] == target_id and rules.fresh_cache(cache, ports.clock.wall(), last_input,
                                                                    status["relaunched"]):
            logging.info(f"Slayer Legend soul weapon: {target} equipped (last read), skipped in 0.0 s")
            status["last"] = {"result": "cached", "weapon": target, "seconds": 0.0}
            return "cached"
        status["cache"] = None
        shot = await open_screen()
        memory = rules.fresh_memory(status["direction"])
        view = await ports.analyse(view_of, shot)
        result, moves = "equipped", 0
        while True:
            memory = rules.observe(memory, view, order)
            step = rules.plan(view, target, memory, order)
            if step[0] == "done":
                break
            if step[0] == "fail":
                raise Stop(step[1])
            if moves >= rules.MOST_MOVES:
                raise Stop(f"{target} pas atteinte en {rules.MOST_MOVES} gestes")
            moves += 1
            await move(shot, view, step, target)
            if step[0] == "scroll":
                memory = rules.scrolled(memory)
            shot, after = await settled(view)
            if after is None:
                raise Stop({"select": "choix dans la liste", "scroll": "défilement de la liste",
                            "equip": "Equip"}[step[0]] + " sans effet")
            if step[0] == "equip":
                if after["selected"] != target or after["tag"] != "Unequip":
                    raise Stop(f"vérification après Equip (lu : {after['selected'] or 'nom illisible'}, "
                               f"{after['tag'] or 'étiquette illisible'})")
                result = "done"
            view = after
        if memory["direction"] in (1, -1) and memory["direction"] != status["direction"]:
            status["direction"] = memory["direction"]
            ports.store.save()
        status["cache"] = {"id": target_id, "at": ports.clock.wall()}
        shot, mismatch = await check_engraving(shot, entry, variant)
        await close_screen(shot)
        seconds = round(ports.clock.monotonic() - since, 1)
        logging.info(f"Slayer Legend soul weapon: {target} {result} in {seconds} s, {moves} moves")
        status["last"] = {"result": result, "weapon": target, "seconds": seconds, "engraving": mismatch}
        return result

    def relaunched():
        """The game was relaunched: the next ensure reads again."""
        status["relaunched"] = ports.clock.wall()
        status["cache"] = None

    def forget():
        status["cache"] = None

    def set_switch(value):
        """"real" (the default: the user's choice, no plan mode) or "off"
        (the emergency stop: nothing is read or tapped for the soul weapon)."""
        if value != status["switch"]:
            logging.info(f"Slayer Legend soul weapon: switched to {value}")
            status["switch"] = value
            ports.store.save()

    return {"ensure": ensure, "relaunched": relaunched, "forget": forget, "set_switch": set_switch,
            "switch": lambda: status["switch"],
            "state": lambda: {"switch": status["switch"], "direction": status["direction"], "last": status["last"],
                              "cached": (status["cache"] or {}).get("id")}}
