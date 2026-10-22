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

The engraving (features/engraving_setup.py), once the target is equipped:
its engraving screen (the card's big icon) is set up as the loadout's
variant: every card locked first, the highest-level cards placed, all 8
read locked at the end. Only then is the step done ("ready"); otherwise it
stops with one alert naming what is left. It may take longer than the
60 s budget: then said in the log and in the ready notice. The cache is
set only once the engraving read ready.
"""


EQUIPMENT_TAP = (0.41, 0.966)
WEAPON_TAB_TAP = (0.12, 0.414)
SOUL_WEAPON_TAP = (0.92, 0.445)
CLOSE_TAP = (0.5, 0.955)
# A mode switch's budget, seconds (the engraving may take longer: said).
BUDGET = 60
# A list scroll: a slow drag (no fling).
SWIPE_MS = 700
# After a scroll the list may still glide: one more look this long after.
SETTLE = 0.4


def soul_weapon(ports, screens, reader, rules, table, helpers, engraving=None):
    """reader: soul_weapon.py; rules: soul_weapon_rules.py; table:
    engravings.json; helpers: the stage change's look, tap (front first),
    front, to_battle and Stop; engraving: {setup (engraving_setup.py's
    engraving_setup), screen (engraving_screen.py), rules
    (engraving_setup_rules.py), variant(id, name): the variant's {pieces}
    (the engraving feature's)}; None: the engraving is not set up."""
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
            raise Stop("onglet Weapon de l’équipement pas actif (lu : {seen})", seen=tab or ports.t("rien"))
        await helpers.tap(shot, "equipment_weapon", "soul_weapon", SOUL_WEAPON_TAP)
        shot, opened = await wait_for(lambda s: reader.title(s) or reader.weapon_detail(s))
        if opened and not reader.title(shot):
            # The tap opened an ordinary weapon's card (the list scrolled
            # under the icon): closed, nothing else touched there.
            await helpers.tap(shot, "weapon_detail", "close", CLOSE_TAP)
            await wait_for(lambda s: reader.tab(s) == "weapon")
            raise Stop("la fiche d’une arme s’est ouverte au lieu de Soul Weapon (fermée)")
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

    setup = None
    if engraving:
        setup = engraving["setup"](ports, engraving["screen"], engraving["rules"], helpers, wait_for, reader.title)

    async def engrave(shot, entry, variant):
        """On the Soul Weapon screen with the target equipped: its engraving
        set up as the variant. (shot back on Soul Weapon, the alert's text
        (a status text) or None when ready or not asked, the setup's answer
        or None)."""
        if not (setup and variant and entry.get("grid")):
            return shot, None, None
        pieces = engraving["variant"](entry["id"], variant)
        if pieces is None:
            return shot, ports.t("Gravure de {name} : variante {variant} inconnue", name=entry["name"], variant=variant), None
        shot, done = await setup(shot, entry, variant, pieces, names, reader.CARD_FONT, table["shapes"])
        if not done["ok"]:
            return shot, engraving["rules"].alert(entry["name"], variant, done["problems"]), done
        return shot, None, done

    async def ensure(target_id, variant=None):
        """The weapon target_id equipped and its engraving set up as variant:
        "cached", "equipped" (it already was) or "done" (Equip tapped); else
        Stop with the step (an engraving not ready: its alert)."""
        since = ports.clock.monotonic()
        entry = by_id.get(target_id)
        if entry is None:
            raise Stop("arme {id} inconnue", id=target_id)
        target = entry["name"]
        if rules.shared(target, table):
            raise Stop("{weapon} : deux armes portent ce nom, le nom lu ne suffit pas à choisir", weapon=target)
        cache = status["cache"]
        last_input = (ports.last_input() or {}).get("wall") if hasattr(ports, "last_input") else None
        if cache and cache["id"] == target_id and cache.get("variant") == variant \
                and rules.fresh_cache(cache, ports.clock.wall(), last_input, status["relaunched"]):
            ports.log("normal", f"Soul weapon: {target} equipped (last read), skipped in 0.0 s")
            status["last"] = {"result": "cached", "weapon": target, "seconds": 0.0}
            return "cached"
        status["cache"] = None
        shot = await open_screen()
        memory = rules.fresh_memory(status["direction"])
        view = await ports.analyse(view_of, shot)
        result, moves = "equipped", 0
        while True:
            memory = rules.observe(memory, view, order)
            step = rules.plan(view, target, memory, order, reader.TAG_LEARNED)
            if step[0] == "done":
                break
            if step[0] == "fail":
                raise Stop(step[1])
            if moves >= rules.MOST_MOVES:
                raise Stop("{weapon} pas atteinte en {moves} gestes", weapon=target, moves=rules.MOST_MOVES)
            moves += 1
            await move(shot, view, step, target)
            if step[0] == "scroll":
                memory = rules.scrolled(memory)
            shot, after = await settled(view)
            if after is None:
                raise Stop({"select": "choix dans la liste sans effet", "scroll": "défilement de la liste sans effet",
                            "equip": "Equip sans effet"}[step[0]])
            if step[0] == "equip":
                if after["selected"] != target or after["tag"] != "Unequip":
                    raise Stop("vérification après Equip (lu : {name}, {tag})",
                               name=after["selected"] or ports.t("nom illisible"),
                               tag=after["tag"] or ports.t("étiquette illisible"))
                result = "done"
            view = after
        if memory["direction"] in (1, -1) and memory["direction"] != status["direction"]:
            status["direction"] = memory["direction"]
            ports.store.save()
        began = ports.clock.monotonic()
        shot, mismatch, done = await engrave(shot, entry, variant)
        engraved = round(ports.clock.monotonic() - began, 1)
        if done:
            logging.info(f"Slayer Legend soul weapon: engraving step took {engraved} s ({done['gestures']} gestures)")
        await close_screen(shot)
        seconds = round(ports.clock.monotonic() - since, 1)
        over = seconds > BUDGET
        ports.log("warning" if over else "normal",
                  f"Soul weapon: {target} {result} in {seconds} s, {moves} moves"
                  + (f", engraving {'not ready' if mismatch else 'ready'} in {done['seconds']} s" if done else "")
                  + (f" (over the {BUDGET} s budget)" if over else ""))
        status["last"] = {"result": result, "weapon": target, "seconds": seconds, "engraving_t": mismatch}
        if mismatch:
            raise Stop(mismatch)
        status["cache"] = {"id": target_id, "variant": variant, "at": ports.clock.wall()}
        if done and (done["locked"] or done["placed"] or done["removed"]):
            await ports.notify(f"Soul Weapon {target} ({variant}) ready: {len(done['removed'])} removed, "
                               f"{len(done['placed'])} placed, {len(done['locked'])} locked, in {seconds} s "
                               f"(engraving {engraved} s, {done['gestures']} gestures)"
                               + (f" (over the {BUDGET} s budget)" if over else ""))
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
            ports.log("normal", f"Soul weapon: switched to {value}")
            status["switch"] = value
            ports.store.save()

    return {"ensure": ensure, "relaunched": relaunched, "forget": forget, "set_switch": set_switch,
            "switch": lambda: status["switch"],
            "state": lambda: {"switch": status["switch"], "direction": status["direction"], "last": status["last"],
                              "cached": (status["cache"] or {}).get("id")}}
