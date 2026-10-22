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
  still open is locked; one that stays open, or whose padlock stays
  unreadable (never tapped), is an error alert and a problem, never left
  silently;
- closed with the red X, back on Soul Weapon. Ready only when
  rules.check finds nothing left.

Nothing at all while the engraving switch (switch()) is not "real": no
gesture, one error log, and the setup not ready (rules.NOT_SET_UP).

Never touched: Change, the gear, %. A bright (unlocked) card's drawing is
not read: each slot keeps the shape and level read while it was locked.
"""


ENGRAVING_TAP = (0.33, 0.636)
ENGRAVING_CLOSE_TAP = (0.11, 0.955)
# Slow drags, so the game takes them as drags (eg5 to eg6: 800 ms; eg7:
# 1200 ms).
DRAG_MS = 1200
REMOVE_MS = 800
MOVE_MS = 800
# The budget the user gave a mode switch.
BUDGET = 60


def engraving_setup(ports, screen, rules, helpers, wait_for, back_on, switch=lambda: "off"):
    """screen: engraving_screen.py; rules: engraving_setup_rules.py;
    helpers: the soul weapon's (look, tap, front, Stop); wait_for(test,
    most): the soul weapon's polled wait; back_on(shot): the Soul Weapon
    screen is shown (its title); switch(): the engraving switch, "real"
    or "off"."""
    Stop = helpers.Stop
    # The gestures of the setup running (taps and drags).
    gestures = [0]

    async def tap(*args, **kwargs):
        gestures[0] += 1
        await helpers.tap(*args, **kwargs)

    async def swipe(*args, **kwargs):
        gestures[0] += 1
        await ports.swipe(*args, **kwargs)

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
        ports.log("error", f"Engraving: {text}")
        await ports.notify(f"Engraving: {text}"[:200])

    async def setup(shot, entry, variant_name, variant, names, card_font, shapes):
        """(shot back on Soul Weapon, {ok, problems, locked, removed,
        placed, seconds, gestures})."""
        since = ports.clock.monotonic()
        gestures[0] = 0
        if switch() != "real":
            ports.log("error", f"Engraving: {ports.english(ports.t(rules.NOT_SET_UP))}")
            return shot, {"ok": False, "problems": [ports.t(rules.NOT_SET_UP)], "locked": [], "removed": [],
                          "placed": [], "dragged": [], "seconds": 0.0, "gestures": 0}
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
                await tap(shot, "soul_weapon_engraving", "lock", screen.lock_point(index), verified=True)
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
                await tap(shot, "soul_weapon_engraving", "piece", screen.drag_point(index), verified=True)
            shot, state = await wait_for(screen.popup_padlock)
            if state == "open":
                await tap(shot, "soul_weapon_engraving_piece", "padlock", screen.POPUP_LOCK_TAP,
                                  verified=True)
                shot, state = await wait_for(lambda s: screen.popup_padlock(s) == "closed" and "closed")
            if await ports.analyse(screen.popup, shot):
                await tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
                await wait_for(lambda s: not screen.popup(s))
            shot = await helpers.look()
            if await ports.analyse(screen.locked, shot, index) is True:
                done["locked"].append(index)
                return True
            return False

        async def remove(cells, reading):
            shot, before = await steady(size, shapes)
            if any(before["grid"] is None or before["grid"]["cells"].get(cell) != "piece" for cell in cells):
                problems.append(ports.t("la pièce à retirer a bougé"))
                return False
            start = screen.cell_centre(*cells[0])
            await helpers.front()
            await swipe(shot, "soul_weapon_engraving", "remove_piece", start, screen.INVENTORY_DROP,
                              REMOVE_MS, verified=True)
            shot, after = await steady(size, shapes)
            freed = [c["index"] for c, b in zip(after["cards"], before["cards"]) if b["placed"] and not c["placed"]]
            if after["grid"] is None or any(after["grid"]["cells"].get(cell) != "empty" for cell in cells) \
                    or len(freed) != 1:
                problems.append(ports.t("retirer la pièce en {cell} n’a pas libéré ses cases et une carte", cell=str(cells[0])))
                for index in [c["index"] for c in after["cards"] if c["locked"] is False]:
                    await lock(index)
                return False
            done["removed"].append(freed[0])
            if not await lock(freed[0]):
                problems.append(ports.t("n°{number} reste déverrouillée après son retrait", number=freed[0] + 1))
                await error(f"#{freed[0] + 1} stays unlocked after its removal")
                return False
            return True

        async def place(index, cells, card):
            shot, before = await steady(size, shapes)
            if before["cards"][index]["placed"] or any(before["grid"]["cells"].get(cell) != "empty" for cell in cells):
                problems.append(ports.t("n°{number} : carte ou cases changées avant le glisser", number=index + 1))
                return False
            under = set(await ports.analyse(screen.cubes, shot))
            base = rules.normalised([tuple(c) for c in shapes[card["shape"]]["cells"]])
            target = screen.hold_point(cells)
            await helpers.front()
            await swipe(shot, "soul_weapon_engraving", "drag_piece", screen.drag_point(index), target,
                              DRAG_MS, verified=True)
            turns = 0
            for _ in range(rules.MOST_PREVIEW):
                shot, found = await wait_for(screen.bar)
                if not found:
                    problems.append(ports.t("pas d’aperçu après avoir glissé n°{number}", number=index + 1))
                    return False
                now = await ports.analyse(screen.cubes, shot)
                step = rules.preview_step(under, set(now), found["valid"], base, turns, cells)
                if step[0] == "rotate":
                    await tap(shot, "soul_weapon_engraving_preview", "rotate", found["rotate"], verified=True)
                    turns += 1
                    await ports.clock.sleep(0.3)
                elif step[0] == "move":
                    await helpers.front()
                    await swipe(shot, "soul_weapon_engraving_preview", "move", screen.cell_centre(*step[1]),
                                      screen.cell_centre(*step[2]), MOVE_MS, verified=True)
                    await ports.clock.sleep(0.3)
                elif step[0] == "confirm":
                    await tap(shot, "soul_weapon_engraving_preview", "confirm", found["confirm"],
                                      verified=True)
                    shot, after = await steady(size, shapes)
                    if after["grid"] is None or sorted(cells) not in [sorted(map(tuple, p))
                                                                      for p in after["grid"]["pieces"]] \
                            or not after["cards"][index]["placed"]:
                        problems.append(ports.t("n°{number} pas lue posée après sa validation", number=index + 1))
                        return False
                    done["placed"].append(index)
                    if after["cards"][index]["locked"] is not True and not await lock(index):
                        problems.append(ports.t("n°{number} reste déverrouillée après sa pose", number=index + 1))
                        await error(f"#{index + 1} stays unlocked after its placing")
                        return False
                    return True
                else:
                    break
            await tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
            await wait_for(lambda s: not screen.bar(s))
            problems.append(ports.t("pose de n°{number} annulée ({why})", number=index + 1,
                                    why=step[1] if step[0] == "cancel" else ports.t("trop de gestes")))
            return False

        await tap(shot, "soul_weapon", "engraving", ENGRAVING_TAP)
        shot, opened = await wait_for(screen.title)
        if not opened:
            raise Stop("ouverture de la gravure")
        try:
            named = await ports.analyse(screen.weapon, shot, names, card_font)
            if named != entry["name"]:
                problems.append(ports.t("l’écran montre {seen}, pas {name}", seen=named or ports.t("un nom illisible"),
                                        name=entry["name"]))
            elif size != 5:
                problems.append(ports.t("grille {size}x{size} pas encore calibrée", size=size))
            elif not all(getattr(screen, gate, False) for gate in ("PADLOCK_LEARNED", "POPUP_LEARNED",
                                                                   "PREVIEW_LEARNED")):
                problems.append(ports.t("lectures de la gravure pas calibrées, rien n’a bougé"))
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
                            problems.append(ports.t("n°{number} reste déverrouillée", number=step[1] + 1))
                            await error(f"#{step[1] + 1} stays unlocked")
                            break
                    elif step[0] == "remove":
                        probed.append(step[1])
                        if not await remove(step[1], reading):
                            break
                    elif not await place(step[1], step[2], cards[step[1]]):
                        break
                else:
                    problems.append(ports.t("pas fini en {moves} gestes", moves=rules.MOST_STEPS))
            # Never left with a piece unlocked: all 8 read closed first.
            shot, reading = await steady(size, shapes)
            # A padlock unreadable is not closed: lock() reads it again and
            # never taps it.
            for card in reading["cards"]:
                if card["locked"] is not True and not await lock(card["index"]):
                    unread = card["locked"] is None
                    problems.append(ports.t("n°{number} laissée déverrouillée (cadenas illisible)" if unread
                                            else "n°{number} laissée déverrouillée", number=card["index"] + 1))
                    await error(f"#{card['index'] + 1} left unlocked" + (" (padlock unreadable)" if unread else ""))
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
                await tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
                shot, _ = await wait_for(lambda s: not screen.bar(s))
            if await ports.analyse(screen.popup, shot):
                await tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
                shot, _ = await wait_for(lambda s: not screen.popup(s))
            await tap(shot, "soul_weapon_engraving", "close", ENGRAVING_CLOSE_TAP)
        shot, back = await wait_for(back_on)
        if not back:
            raise Stop("retour de la gravure à l’écran Soul Weapon")
        seconds = round(ports.clock.monotonic() - since, 1)
        ports.log("normal", f"Engraving: {entry['name']} {variant_name} "
                  f"{'ready' if not problems else 'not ready'} in {seconds} s, {len(done['locked'])} locked, "
                  f"{len(done['removed'])} removed, {len(done['placed'])} placed")
        return shot, {"ok": not problems, "problems": problems, "locked": done["locked"],
                      "removed": done["removed"], "placed": done["placed"], "dragged": done["placed"],
                      "seconds": seconds, "gestures": gestures[0]}

    return setup
