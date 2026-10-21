"""Sets the equipped soul weapon's engraving up as its loadout's variant:
the step after Equip in the soul weapon feature, on the Soul Weapon screen
with the weapon selected. Every move goes through the navigation guard on
a fresh capture of that screen.

- the card's big icon opens Soul Weapon Engraving: its title, then the
  weapon's name must read the target's;
- the grid and the 8 cards read twice alike (the screen may still draw);
- FIRST the padlocks: every card whose padlock reads open is tapped once,
  and must then read closed. A padlock read neither way is never tapped (a
  misread would unlock it). No drag unless all 8 read locked;
- then the drags engraving_setup_rules.check plans (the highest-level cards
  onto empty cells, base orientation only), each from a fresh capture: the
  card must still read unplaced and the cells empty; afterwards the cells
  must form that piece, the card read E, and nothing else of the grid
  change (rules.dragged). A drag that does not stops the drags. At most
  rules.MOST_DRAGS;
- read once more: ready only when check finds nothing left, every card
  locked included, the unplaced ones too;
- closed with the red X, back on Soul Weapon.

Never touched: Change, the gear, %, an unlock. Turning a piece and taking
one out of the grid are not learnt: what only they would fix stays in the
answer's problems, for the one alert.
"""

import logging

ENGRAVING_TAP = (0.33, 0.636)
ENGRAVING_CLOSE_TAP = (0.11, 0.955)
# A drag: held and moved slowly, so the game takes it as a drag, not a
# swipe.
DRAG_MS = 1200
# The budget the user gave a mode switch.
BUDGET = 60


def engraving_setup(ports, screen, rules, helpers, wait_for, back_on):
    """screen: engraving_screen.py; rules: engraving_setup_rules.py;
    helpers: the soul weapon's (look, tap, front, Stop); wait_for(test,
    most): the soul weapon's polled wait; back_on(shot): the Soul Weapon
    screen is shown (its title)."""
    Stop = helpers.Stop

    def read(shot, size, shapes):
        return {"grid": screen.grid(shot, size), "cards": screen.cards(shot, shapes)}

    def signature(reading):
        if reading["grid"] is None:
            return None
        return (sorted(reading["grid"]["cells"].items()),
                [(c["shape"], c["level"], c["locked"], c["placed"]) for c in reading["cards"]])

    async def steady(size, shapes, most=3.0):
        """(shot, reading) once two looks in a row read alike, or the last
        one after most seconds."""
        last, end = None, ports.clock.monotonic() + most
        while True:
            await ports.clock.sleep(0.25)
            shot = await helpers.look()
            reading = await ports.analyse(read, shot, size, shapes)
            if last is not None and signature(reading) is not None and signature(reading) == signature(last):
                return shot, reading
            last = reading
            if ports.clock.monotonic() >= end:
                return shot, reading

    async def setup(shot, entry, variant_name, variant, names, card_font, shapes):
        """(shot back on Soul Weapon, {ok, problems, locked, dragged, seconds})."""
        since = ports.clock.monotonic()
        size = entry.get("grid")
        await helpers.tap(shot, "soul_weapon", "engraving", ENGRAVING_TAP)
        shot, opened = await wait_for(screen.title)
        if not opened:
            raise Stop("ouverture de la gravure")
        locked, dragged, problems = [], [], []
        try:
            named = await ports.analyse(screen.weapon, shot, names, card_font)
            if named != entry["name"]:
                problems.append(f"l’écran montre {named or 'un nom illisible'}, pas {entry['name']}")
            elif size != 5:
                problems.append(f"grille {size}x{size} pas encore calibrée")
            else:
                shot, reading = await steady(size, shapes)
                result = rules.check(reading["grid"], reading["cards"], variant, entry["cells"],
                                     entry["name"], variant_name)
                for index in result["locks"]:
                    shot, reading = await steady(size, shapes)
                    if reading["cards"][index]["locked"] is not False:
                        continue
                    await helpers.tap(shot, "soul_weapon_engraving", "lock", screen.lock_point(index), verified=True)
                    shot, closed = await wait_for(lambda s: screen.locked(s, index) is True)
                    if not closed:
                        break
                    locked.append(index)
                shot, reading = await steady(size, shapes)
                result = rules.check(reading["grid"], reading["cards"], variant, entry["cells"],
                                     entry["name"], variant_name)
                all_locked = all(card["locked"] is True for card in reading["cards"])
                for move in result["moves"] if all_locked else []:
                    if len(dragged) >= rules.MOST_DRAGS:
                        break
                    shot, before = await steady(size, shapes)
                    card = before["cards"][move["card"]]
                    if card["placed"] or card["locked"] is not True or before["grid"] is None or any(
                            before["grid"]["cells"].get(cell) != "empty" for cell in move["cells"]):
                        break
                    start = screen.drag_point(move["card"])
                    end = rules.drop_point(move["cells"], screen.cell_centre)
                    await helpers.front()
                    await ports.swipe(shot, "soul_weapon_engraving", "drag_piece", start, end, DRAG_MS,
                                      verified=True)
                    shot, after = await steady(size, shapes)
                    if not rules.dragged(before, after, move):
                        problems.append(f"glisser {card['shape']} Lv.{card['level']} (n°{move['card'] + 1}) "
                                        f"n’a pas donné les cases attendues")
                        break
                    dragged.append(move["card"])
                shot, reading = await steady(size, shapes)
                result = rules.check(reading["grid"], reading["cards"], variant, entry["cells"],
                                     entry["name"], variant_name)
                problems = problems + result["problems"]
        finally:
            await helpers.tap(shot, "soul_weapon_engraving", "close", ENGRAVING_CLOSE_TAP)
        shot, back = await wait_for(back_on)
        if not back:
            raise Stop("retour de la gravure à l’écran Soul Weapon")
        seconds = round(ports.clock.monotonic() - since, 1)
        logging.info(f"Slayer Legend engraving: {entry['name']} {variant_name} "
                     f"{'ready' if not problems else 'not ready'} in {seconds} s, "
                     f"{len(locked)} locked, {len(dragged)} dragged")
        return shot, {"ok": not problems, "problems": problems, "locked": locked, "dragged": dragged,
                      "seconds": seconds}

    return setup
