"""Sets the equipped soul weapon's engraving up as its loadout's variant:
the step after Equip in the soul weapon feature, on the Soul Weapon screen
with the weapon selected. Every move goes through the navigation guard on
a fresh capture of that screen (engraving_screen.py reads it).

- the card's big icon opens Soul Weapon Engraving: its title, then the
  weapon's name must read the target's;
- then one move at a time, each planned on a fresh reading
  (engraving_setup_rules.next_step), at most rules.MOST_STEPS:
  - lock: a card whose padlock reads open. Its padlock's corner is tapped
    (only on that fresh "open" reading: a tap on a closed one opens it);
    if a fresh capture shows no change, an error alert says the corner tap
    did nothing, and the piece popup is used instead: a tap on the card's
    middle, its padlock tapped only while it reads open, then closed by a
    tap above it. The card must then read closed.
  - remove: a slow drag (REMOVE_MS) from a cell of the piece to the
    inventory. The cells must read empty and exactly one card lose its E;
    taking a piece out unlocks it: that card is locked again at once.
  - place: a slow drag (DRAG_MS) from the card to where its preview lands
    on the cells (engraving_screen.hold_point); then, on the preview, its
    rotate button until its shape is the cells', a drag of one of its
    cubes by the offset left, and its confirm only once it lies on the
    cells and the check reads valid (rules.preview_step, at most
    rules.MOST_PREVIEW moves); else its cancel. Afterwards the cells must
    form that piece, the card read E and its padlock closed (else locked).
- before closing: a fresh capture must read all 8 padlocks closed; a card
  still open is locked; one that stays open is an error alert, never left
  silently;
- closed with the red X, back on Soul Weapon. Ready only when
  rules.check finds nothing left.

Never touched: Change, the gear, %. A bright (unlocked) card's drawing is
not read: each slot keeps the shape and level read while it was locked.
"""

import logging

ENGRAVING_TAP = (0.33, 0.636)
ENGRAVING_CLOSE_TAP = (0.11, 0.955)
# Slow drags, so the game takes them as drags (eg5 to eg6: 800 ms; eg7:
# 1200 ms).
DRAG_MS = 1200
REMOVE_MS = 800
MOVE_MS = 800
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

    async def error(text):
        """An error alert for the developer (something did not work as
        calibrated), the setup going on."""
        logging.error(f"Slayer Legend engraving: {text}")
        await ports.notify(f"Engraving: {text}"[:200])

    async def setup(shot, entry, variant_name, variant, names, card_font, shapes):
        """(shot back on Soul Weapon, {ok, problems, locked, removed,
        placed, seconds})."""
        since = ports.clock.monotonic()
        size = entry.get("grid")
        gold = rules.gold_variant(variant_name)
        known = {}
        done = {"locked": [], "removed": [], "placed": [], "corner_failed": False}
        problems = []

        def remember(cards):
            """The cards with each bright one's shape, level and icon as
            read while it was locked."""
            out = []
            for card in cards:
                if card["shape"] is not None and card["level"] is not None and not card.get("bright"):
                    known[card["index"]] = {k: card[k] for k in ("shape", "level", "kind")}
                    out.append(card)
                else:
                    out.append(dict(card, **known.get(card["index"], {})))
            return out

        async def lock(index):
            """The card index locked: True once it reads closed."""
            shot, reading = await steady(size, shapes)
            if reading["cards"][index]["locked"] is not False:
                return reading["cards"][index]["locked"] is True
            if not done["corner_failed"]:
                await helpers.tap(shot, "soul_weapon_engraving", "lock", screen.lock_point(index), verified=True)
                shot, closed = await wait_for(lambda s: screen.locked(s, index) is True, 2.0)
                if closed:
                    done["locked"].append(index)
                    return True
                # Said once; the popup for the rest of this setup.
                done["corner_failed"] = True
                await error(f"the padlock corner tap of #{index + 1} did nothing, locked through its popup")
                shot = await helpers.look()
            if not await ports.analyse(screen.popup, shot):
                state = await ports.analyse(screen.locked, shot, index)
                if state is not False:
                    return state is True
                await helpers.tap(shot, "soul_weapon_engraving", "piece", screen.drag_point(index), verified=True)
            shot, state = await wait_for(screen.popup_padlock)
            if state == "open":
                await helpers.tap(shot, "soul_weapon_engraving_piece", "padlock", screen.POPUP_LOCK_TAP,
                                  verified=True)
                shot, state = await wait_for(lambda s: screen.popup_padlock(s) == "closed" and "closed")
            if await ports.analyse(screen.popup, shot):
                await helpers.tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
                await wait_for(lambda s: not screen.popup(s))
            shot = await helpers.look()
            if await ports.analyse(screen.locked, shot, index) is True:
                done["locked"].append(index)
                return True
            return False

        async def remove(cells, reading):
            shot, before = await steady(size, shapes)
            if any(before["grid"] is None or before["grid"]["cells"].get(cell) != "piece" for cell in cells):
                problems.append("the piece to take out moved")
                return False
            start = screen.cell_centre(*cells[0])
            await helpers.front()
            await ports.swipe(shot, "soul_weapon_engraving", "remove_piece", start, screen.INVENTORY_DROP,
                              REMOVE_MS, verified=True)
            shot, after = await steady(size, shapes)
            freed = [c["index"] for c, b in zip(after["cards"], before["cards"]) if b["placed"] and not c["placed"]]
            if after["grid"] is None or any(after["grid"]["cells"].get(cell) != "empty" for cell in cells) \
                    or len(freed) != 1:
                problems.append(f"taking out the piece at {cells[0]} did not free its cells and one card")
                for index in [c["index"] for c in after["cards"] if c["locked"] is False]:
                    await lock(index)
                return False
            done["removed"].append(freed[0])
            if not await lock(freed[0]):
                problems.append(f"#{freed[0] + 1} stays unlocked after its removal")
                await error(f"#{freed[0] + 1} stays unlocked after its removal")
                return False
            return True

        async def place(index, cells, card):
            shot, before = await steady(size, shapes)
            if before["cards"][index]["placed"] or any(before["grid"]["cells"].get(cell) != "empty" for cell in cells):
                problems.append(f"#{index + 1}: card or cells changed before the drag")
                return False
            under = set(await ports.analyse(screen.cubes, shot))
            base = rules.normalised([tuple(c) for c in shapes[card["shape"]]["cells"]])
            target = screen.hold_point(cells)
            await helpers.front()
            await ports.swipe(shot, "soul_weapon_engraving", "drag_piece", screen.drag_point(index), target,
                              DRAG_MS, verified=True)
            turns = 0
            for _ in range(rules.MOST_PREVIEW):
                shot, found = await wait_for(screen.bar)
                if not found:
                    problems.append(f"no preview after dragging #{index + 1}")
                    return False
                now = await ports.analyse(screen.cubes, shot)
                step = rules.preview_step(under, set(now), found["valid"], base, turns, cells)
                if step[0] == "rotate":
                    await helpers.tap(shot, "soul_weapon_engraving_preview", "rotate", found["rotate"], verified=True)
                    turns += 1
                    await ports.clock.sleep(0.3)
                elif step[0] == "move":
                    await helpers.front()
                    await ports.swipe(shot, "soul_weapon_engraving_preview", "move", screen.cell_centre(*step[1]),
                                      screen.cell_centre(*step[2]), MOVE_MS, verified=True)
                    await ports.clock.sleep(0.3)
                elif step[0] == "confirm":
                    await helpers.tap(shot, "soul_weapon_engraving_preview", "confirm", found["confirm"],
                                      verified=True)
                    shot, after = await steady(size, shapes)
                    if after["grid"] is None or sorted(cells) not in [sorted(map(tuple, p))
                                                                      for p in after["grid"]["pieces"]] \
                            or not after["cards"][index]["placed"]:
                        problems.append(f"#{index + 1} not read placed after its confirm")
                        return False
                    done["placed"].append(index)
                    if after["cards"][index]["locked"] is not True and not await lock(index):
                        problems.append(f"#{index + 1} stays unlocked after its placing")
                        await error(f"#{index + 1} stays unlocked after its placing")
                        return False
                    return True
                else:
                    break
            await helpers.tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
            await wait_for(lambda s: not screen.bar(s))
            problems.append(f"placing #{index + 1} cancelled ({step[1] if step[0] == 'cancel' else 'too many moves'})")
            return False

        await helpers.tap(shot, "soul_weapon", "engraving", ENGRAVING_TAP)
        shot, opened = await wait_for(screen.title)
        if not opened:
            raise Stop("engraving screen not opened")
        try:
            named = await ports.analyse(screen.weapon, shot, names, card_font)
            if named != entry["name"]:
                problems.append(f"the screen shows {named or 'an unreadable name'}, not {entry['name']}")
            elif size != 5:
                problems.append(f"{size}x{size} grid not calibrated")
            elif not all(getattr(screen, gate, False) for gate in ("PADLOCK_LEARNED", "POPUP_LEARNED",
                                                                   "PREVIEW_LEARNED")):
                problems.append("engraving readings not calibrated, nothing moved")
            else:
                probed = []
                for _ in range(rules.MOST_STEPS):
                    shot, reading = await steady(size, shapes)
                    cards = remember(reading["cards"])
                    step = rules.next_step(reading["grid"], cards, variant, shapes, gold, probed)
                    if step[0] in ("done", "fail"):
                        if step[0] == "fail":
                            problems.append(step[1])
                        break
                    if step[0] == "lock":
                        if not await lock(step[1]):
                            problems.append(f"#{step[1] + 1} stays unlocked")
                            await error(f"#{step[1] + 1} stays unlocked")
                            break
                    elif step[0] == "remove":
                        probed.append(step[1])
                        if not await remove(step[1], reading):
                            break
                    elif not await place(step[1], step[2], cards[step[1]]):
                        break
                else:
                    problems.append(f"not done in {rules.MOST_STEPS} moves")
            # Never left with a piece unlocked: all 8 read closed first.
            shot, reading = await steady(size, shapes)
            for card in reading["cards"]:
                if card["locked"] is False and not await lock(card["index"]):
                    await error(f"#{card['index'] + 1} left unlocked")
            shot, reading = await steady(size, shapes)
            if size == 5 and named == entry["name"]:
                problems = problems + [p for p in rules.check(reading["grid"], remember(reading["cards"]), variant,
                                                              entry["cells"], entry["name"], variant_name, gold)
                                       if p not in problems]
        finally:
            # Nothing left over the screen: a preview cancelled, a popup
            # closed, then the screen's red X.
            shot = await helpers.look()
            found = await ports.analyse(screen.bar, shot)
            if found:
                await helpers.tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
                shot, _ = await wait_for(lambda s: not screen.bar(s))
            if await ports.analyse(screen.popup, shot):
                await helpers.tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
                shot, _ = await wait_for(lambda s: not screen.popup(s))
            await helpers.tap(shot, "soul_weapon_engraving", "close", ENGRAVING_CLOSE_TAP)
        shot, back = await wait_for(back_on)
        if not back:
            raise Stop("back from the engraving to Soul Weapon")
        seconds = round(ports.clock.monotonic() - since, 1)
        logging.info(f"Slayer Legend engraving: {entry['name']} {variant_name} "
                     f"{'ready' if not problems else 'not ready'} in {seconds} s, {len(done['locked'])} locked, "
                     f"{len(done['removed'])} removed, {len(done['placed'])} placed")
        return shot, {"ok": not problems, "problems": problems, "locked": done["locked"],
                      "removed": done["removed"], "placed": done["placed"], "dragged": done["placed"],
                      "seconds": seconds}

    return setup
