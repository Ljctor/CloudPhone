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
- before closing: a fresh capture must read the entire weapon grid filled
  and all 8 padlocks closed; a card
  still open is locked; one that stays open, or whose padlock stays
  unreadable (never tapped), is an error alert and a problem, never left
  silently;
- closed with the red X, back on Soul Weapon. Ready only when
  rules.check finds nothing left.

The target recipe is saved before any mutation. Pending recipes for other
weapons remain in independent pending_by_weapon records when a new weapon
is requested; recovery resumes only the recognised weapon's matching record.
Recovery verifies that recipe before leaving; a legacy recovery with no recipe only closes
a completely filled, locked grid and does not certify a target variant.

Nothing at all while the engraving switch (switch()) is not "real": no
gesture, one error log, and the setup not ready (rules.NOT_SET_UP).

Never touched: Change, the gear, %. A bright (unlocked) card's drawing is
not read: each slot keeps the shape and level read while it was locked.
"""


import asyncio
import copy
import json


ENGRAVING_TAP = (0.33, 0.636)
ENGRAVING_CLOSE_TAP = (0.11, 0.955)
# Slow drags, so the game takes them as drags (eg5 to eg6: 800 ms; eg7:
# 1200 ms).
DRAG_MS = 1200
REMOVE_MS = 800
MOVE_MS = 800
# The budget the user gave a mode switch.
BUDGET = 60
# Screen transitions can outlast the fine-grained card polling deadline on
# the real capture/analysis pipeline. Keep a separate, bounded allowance.
TRANSITION_WAIT = 10.0


def engraving_setup(ports, screen, rules, helpers, wait_for, back_on, switch=lambda: "off", source_weapon=None):
    """screen: engraving_screen.py; rules: engraving_setup_rules.py;
    helpers: the soul weapon's (look, tap, front, Stop); wait_for(test,
    most): the soul weapon's polled wait; back_on(shot): the Soul Weapon
    screen is shown (its title); source_weapon(shot, names): its selected
    weapon name; switch(): the engraving switch, "real" or "off"."""
    Stop = helpers.Stop
    # The gestures of the setup running (taps and drags).
    gestures = [0]
    active = [None]

    def require_enabled():
        if switch() != "real":
            raise Stop("gravure désactivée : opération arrêtée")
    def require_followups(*moves):
        # A pink drag can create an unlocked card or a placement preview.
        # Do not begin that mutation if its mandatory finishing action is
        # paused. Missing policy capability also fails closed.
        allowed = getattr(ports, "action_allowed", None)
        if not callable(allowed) or any(not allowed(screen_id, move) for screen_id, move in moves):
            raise Stop("Action désactivée à la demande de l’utilisateur")

    recovery = copy.deepcopy(ports.store.saved.get("engraving_recovery") or {})
    ports.store.register("engraving_recovery", lambda: dict(recovery))

    def remember_state(**changes):
        recovery.update(changes, at=ports.clock.wall())
        ports.store.save()

    def read(shot, size, shapes):
        return {"grid": screen.grid(shot, size), "cards": screen.cards(shot, shapes)}

    def signature(reading):
        if reading["grid"] is None:
            return None
        return (sorted(reading["grid"]["cells"].items()),
                sorted(tuple(sorted(map(tuple, piece))) for piece in reading["grid"]["pieces"]),
                [(c["shape"], c["level"], c.get("kind"), c["locked"], c["placed"]) for c in reading["cards"]])

    async def error(text):
        """An error alert for the developer (something did not work as
        calibrated), the setup going on."""
        ports.log("error", f"Engraving: {text}")
        await ports.notify(f"Engraving: {text}"[:200])

    poll = wait_for

    async def run(shot, entry, variant_name, variant, names, card_font, shapes, recovery_only=False):
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

        def identity(shot, source=False, allow_unread=False):
            """Bind every raw observation to this target, including under
            a piece popup/preview. Polling can wait for an unread name;
            gestures always require a fresh exact name. A different readable
            name stops immediately, including during polling."""
            require_enabled()
            if source:
                named = source_weapon(shot, names) if source_weapon and back_on(shot) else None
            else:
                named = screen.weapon(shot, names, card_font) if screen.title(shot) else None
            if named is None and allow_unread:
                return None
            if named != entry["name"]:
                raise Stop("l’écran montre {seen}, pas {name}", seen=named or ports.t("un nom illisible"),
                           name=entry["name"])
            return named

        def observed(shot, reader, *args):
            identity(shot)
            return reader(shot, *args)

        async def observe(reader, shot, *args):
            return await ports.analyse(observed, shot, reader, *args)

        async def wait_for(reader, most=None, transition=None):
            captures, unread = 0, 0
            since = ports.clock.monotonic()

            def named(shot, source=False):
                nonlocal unread
                result = identity(shot, source=source, allow_unread=True)
                if result is None:
                    unread += 1
                return result is not None

            def checked(shot):
                nonlocal captures
                require_enabled()
                captures += 1
                if transition == "opening" and not screen.title(shot):
                    if back_on(shot):
                        named(shot, source=True)
                    return False
                if transition == "closing":
                    if back_on(shot):
                        return reader(shot) if named(shot, source=True) else False
                    if screen.title(shot):
                        named(shot)
                    return False
                # Rendering may temporarily hide the name during any bounded
                # observation phase, not only the title transitions. Do not
                # read grid/cards/controls or issue input on that capture.
                return reader(shot) if named(shot) else False

            if transition and most is None:
                most = TRANSITION_WAIT
            result = await poll(checked) if most is None else await poll(checked, most)
            if unread:
                ports.log("warning", f"Engraving identity polling ({transition or 'wait'}): "
                          f"captures={captures} unread={unread} "
                          f"elapsed={round(ports.clock.monotonic() - since, 2)}s "
                          f"matched={bool(result[1])}")
            return result

        async def tap(shot, screen_id, *args, **kwargs):
            await ports.analyse(identity, shot, screen_id == "soul_weapon")
            require_enabled()
            gestures[0] += 1
            await helpers.tap(shot, screen_id, *args, **kwargs)

        async def swipe(shot, *args, **kwargs):
            await ports.analyse(identity, shot)
            require_enabled()
            gestures[0] += 1
            await ports.swipe(shot, *args, **kwargs)

        async def steady(size, shapes, most=3.0):
            """Two matching target-bound observations within a fixed deadline."""
            since = ports.clock.monotonic()
            last, end = None, since + most
            captures, unread = 0, 0

            def read_named(shot):
                if identity(shot, allow_unread=True) is None:
                    return None
                return read(shot, size, shapes)

            def diagnostic(matched):
                if unread or not matched:
                    ports.log("warning", "Engraving identity polling (steady): "
                              f"captures={captures} unread={unread} "
                              f"elapsed={round(ports.clock.monotonic() - since, 2)}s matched={matched}")

            while True:
                await ports.clock.sleep(.25)
                shot = await helpers.look()
                captures += 1
                reading = await ports.analyse(read_named, shot)
                if reading is None:
                    unread += 1
                    last = None
                else:
                    if last is not None and signature(reading) is not None and signature(reading) == signature(last):
                        diagnostic(True)
                        return shot, reading
                    last = reading
                if ports.clock.monotonic() >= end:
                    diagnostic(False)
                    raise Stop("gravure : lectures instables ou grille illisible")

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
            require_followups(("soul_weapon_engraving", "lock"),
                              ("soul_weapon_engraving_piece", "padlock"))
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
            if not await observe(screen.popup, shot):
                state = await observe(screen.locked, shot, index)
                if state is not False:
                    return state is True
                await tap(shot, "soul_weapon_engraving", "piece", screen.drag_point(index), verified=True)
            shot, state = await wait_for(screen.popup_padlock)
            if state == "open":
                await tap(shot, "soul_weapon_engraving_piece", "padlock", screen.POPUP_LOCK_TAP,
                                  verified=True)
                shot, state = await wait_for(lambda s: screen.popup_padlock(s) == "closed" and "closed")
            if await observe(screen.popup, shot):
                await tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
                await wait_for(lambda s: not screen.popup(s))
            shot = await helpers.look()
            if await observe(screen.locked, shot, index) is True:
                done["locked"].append(index)
                return True
            return False

        async def remove(cells, reading):
            require_followups(("soul_weapon_engraving", "lock"),
                              ("soul_weapon_engraving_piece", "padlock"))
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
            require_followups(("soul_weapon_engraving_preview", "rotate"),
                              ("soul_weapon_engraving_preview", "confirm"),
                              ("soul_weapon_engraving_preview", "cancel"),
                              ("soul_weapon_engraving", "lock"),
                              ("soul_weapon_engraving_piece", "padlock"))
            shot, before = await steady(size, shapes)
            if before["cards"][index]["placed"] or any(before["grid"]["cells"].get(cell) != "empty" for cell in cells):
                problems.append(ports.t("n°{number} : carte ou cases changées avant le glisser", number=index + 1))
                return False
            under = set(await observe(screen.cubes, shot))
            base = rules.normalised([tuple(c) for c in shapes[card["shape"]]["cells"]])
            initial = rules.initial_placement_cells(base, cells, rules.ROTATION_PIVOTS.get(card["shape"]))
            if initial is None:
                raise Stop("gravure : pivot non calibré pour {shape}", shape=card["shape"])
            target = screen.hold_point(initial)
            await helpers.front()
            await swipe(shot, "soul_weapon_engraving", "drag_piece", screen.drag_point(index), target,
                              DRAG_MS, verified=True)
            turns = 0
            for preview_moves in range(1, rules.MOST_PREVIEW + 1):
                last, latest = [None], [None]
                preview_counts = {"observations": 0, "complete_observations": 0, "complete_signatures": []}

                def settled_preview(s):
                    preview_counts["observations"] += 1
                    found = screen.bar(s)
                    now = screen.cubes(s) if found else {}
                    latest[0] = (found, now)
                    if not found:
                        last[0] = None
                        return False
                    if not rules.preview_locations(under, now, base, turns):
                        # A transient partial drawing grants no action, but
                        # does not invalidate the last complete observation.
                        # A second matching complete capture is still needed
                        # before input, within this same bounded preview phase.
                        return False
                    preview_counts["complete_observations"] += 1
                    # Control centroids can jitter with antialiasing while
                    # cubes and validity are unchanged. Use the latest fresh
                    # bar coordinates for input, not for geometry stability.
                    candidate = rules.preview_step(under, set(now), found["valid"], base, turns, cells)
                    preview_counts["complete_signatures"].append({
                        "cells": [list(cell) for cell in sorted(now)], "valid": found["valid"],
                        "step": candidate[0],
                    })
                    del preview_counts["complete_signatures"][:-8]
                    # A complete piece can translate or pulse while its
                    # orientation is unchanged. Rotate/move use this capture's
                    # geometry; confirmation alone needs two fresh exact,
                    # valid target observations.
                    signature = ((candidate[0], tuple(map(tuple, rules.turned(base, turns))))
                                 if candidate[0] in ("rotate", "move") else
                                 (candidate[0], tuple(sorted(now)), found["valid"]))
                    stable = last[0] == signature
                    last[0] = signature
                    return stable

                # Rotation/movement animations can briefly omit one cube or
                # show the previous orientation while their bar remains lit.
                # Observe a complete expected shape twice before any next
                # control, without repeating the preceding gesture.
                shot, stable = await wait_for(settled_preview, TRANSITION_WAIT)
                found, now = latest[0]
                if not found:
                    problems.append(ports.t("pas d’aperçu après avoir glissé n°{number}", number=index + 1))
                    return False
                step = (rules.preview_step(under, set(now), found["valid"], base, turns, cells) if stable
                        else ("cancel", ports.t("aperçu pas situé")))
                if step[0] == "rotate":
                    await tap(shot, "soul_weapon_engraving_preview", "rotate", found["rotate"], verified=True)
                    turns += 1
                    await ports.clock.sleep(0.3)
                elif step[0] == "move":
                    current = rules.unique_preview_cells(under, now, base, turns)
                    if current is None:
                        step = ("cancel", ports.t("aperçu pas situé"))
                        break
                    # Dragging any cube reanchors the piece at release. A
                    # finger delta is not a piece delta. Aim its lower-left
                    # bounding anchor directly at the requested final cells.
                    visible = set(current) - under
                    pickup = min(visible, key=lambda cell: (-cell[0], cell[1]))
                    await helpers.front()
                    await swipe(shot, "soul_weapon_engraving_preview", "move", screen.cell_centre(*pickup),
                                      screen.hold_point(cells), MOVE_MS, verified=True)
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
            # One bounded diagnostic at cancellation, before the preview is
            # dismissed. No screenshots or game input are added here; these
            # geometry-only observations can be paired with a private capture.
            ports.log("warning", "Engraving preview diagnostic: " + json.dumps({
                "phase": "preview_cancel", "weapon_id": entry["id"], "card": index + 1,
                "before": [list(cell) for cell in sorted(under)],
                "now": [{"cell": list(cell), "kind": kind} for cell, kind in sorted(now.items())],
                "base": [list(cell) for cell in base], "target": [list(cell) for cell in cells],
                "rotation": turns, "valid": found["valid"], "preview_moves": preview_moves,
                "last_step": step[0],
                **preview_counts,
            }, sort_keys=True, separators=(",", ":")))
            await tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
            await wait_for(lambda s: not screen.bar(s))
            problems.append(ports.t("pose de n°{number} annulée ({why})", number=index + 1,
                                    why=step[1] if step[0] == "cancel" else ports.t("trop de gestes")))
            return False

        if size != 5:
            raise Stop("grille {size}x{size} pas encore calibrée", size=size)
        if variant:
            uncalibrated = sorted({piece["shape"] for piece in variant["pieces"]}
                                 - set(rules.ROTATION_PIVOTS))
            if uncalibrated:
                raise Stop("gravure : pivot non calibré pour {shape}", shape=", ".join(uncalibrated))
        if not all(getattr(screen, gate, False) for gate in
                   ("PADLOCK_LEARNED", "POPUP_LEARNED", "PREVIEW_LEARNED")):
            raise Stop("lectures de la gravure pas calibrées, rien n’a bougé")
        remember_state(required=True)
        if not await ports.analyse(screen.title, shot):
            await tap(shot, "soul_weapon", "engraving", ENGRAVING_TAP)
            shot, opened = await wait_for(screen.title, transition="opening")
            if not opened:
                raise Stop("ouverture de la gravure")
        named = await ports.analyse(identity, shot)
        if named != entry["name"]:
            raise Stop("l’écran montre {seen}, pas {name}", seen=named or ports.t("un nom illisible"),
                       name=entry["name"])
        # Recover interrupted previews/popups only while this operation still
        # owns input. Cancellation itself never performs additional gestures.
        found = await observe(screen.bar, shot)
        if found:
            await tap(shot, "soul_weapon_engraving_preview", "cancel", found["cancel"], verified=True)
            shot, cleared = await wait_for(lambda s: not screen.bar(s))
            if not cleared:
                raise Stop("gravure : aperçu non fermé")
        if await observe(screen.popup, shot):
            await tap(shot, "soul_weapon_engraving_piece", "close", screen.POPUP_CLOSE_TAP)
            shot, cleared = await wait_for(lambda s: not screen.popup(s))
            if not cleared:
                raise Stop("gravure : détail de pièce non fermé")
        named = await ports.analyse(identity, shot)
        if named != entry["name"]:
            raise Stop("l’écran montre {seen}, pas {name}", seen=named or ports.t("un nom illisible"),
                       name=entry["name"])
        elif variant is not None:
            probed = []
            for _ in range(rules.MOST_STEPS):
                shot, reading = await steady(size, shapes)
                cards = remember(reading["cards"])
                if reading["grid"] is not None and {cell for cell, value in reading["grid"]["cells"].items()
                                                     if value != "none"} != {tuple(cell) for cell in entry["cells"]}:
                    problems.append(ports.t("la grille lue n’a pas la forme de {name}", name=entry["name"]))
                    break
                step = rules.next_step(reading["grid"], cards, variant, shapes, gold, probed)
                if step[0] in ("done", "fail"):
                    if step[0] == "fail":
                        problems.append(step[1])
                    break
                if step[0] == "lock":
                    require_followups(("soul_weapon_engraving", "lock"),
                                      ("soul_weapon_engraving_piece", "padlock"))
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
        if not all(card["locked"] is True for card in reading["cards"]) or len(reading["cards"]) != 8:
            raise Stop("gravure : récupération requise, les huit cadenas ne sont pas confirmés fermés")
        named = await ports.analyse(identity, shot)
        remember_state(locks_verified=True)
        if variant is not None and size == 5 and named == entry["name"]:
            problems = problems + [p for p in rules.check(reading["grid"], reading["cards"], variant,
                                                          entry["cells"], entry["name"], variant_name, gold)
                                   if p not in problems]
        # Locks alone do not recover a layout: an empty cell loses the
        # weapon's completion bonus. Keep the durable target pending and the
        # screen open until the entire expected pattern is filled.
        expected = {tuple(cell) for cell in entry["cells"]}
        occupied = {cell for cell, state in reading["grid"]["cells"].items() if state == "piece"}
        partition = [tuple(cell) for piece in reading["grid"]["pieces"] for cell in piece]
        complete = (occupied == expected and set(partition) == expected and len(partition) == len(expected)
                    and {cell for cell, state in reading["grid"]["cells"].items() if state != "none"} == expected)
        remember_state(completion_verified=complete)
        if not complete:
            if problems:
                raise Stop(rules.alert(entry["name"], variant_name, problems))
            raise Stop("gravure : récupération requise, grille incomplète ou illisible")
        if recovery_only and problems:
            raise Stop(rules.alert(entry["name"], variant_name, problems))
        # Leave only after a fresh stable observation proved every card locked
        # and all cells occupied. Legacy recovery can prove safe closure, but
        # cannot certify a recipe it never received.
        await tap(shot, "soul_weapon_engraving", "close", ENGRAVING_CLOSE_TAP)
        shot, back = await wait_for(back_on, transition="closing")
        if not back:
            raise Stop("retour de la gravure à l’écran Soul Weapon")
        seconds = round(ports.clock.monotonic() - since, 1)
        result_name = ("complete locked grid, recipe not verified" if variant is None else
                       "ready" if not problems else "not ready")
        ports.log("normal", f"Engraving: {entry['name']} {variant_name} "
                  f"{result_name} in {seconds} s, {len(done['locked'])} locked, "
                  f"{len(done['removed'])} removed, {len(done['placed'])} placed")
        return shot, {"ok": not problems, "problems": problems, "locked": done["locked"],
                      "removed": done["removed"], "placed": done["placed"], "dragged": done["placed"],
                      "seconds": seconds, "gestures": gestures[0]}

    async def setup(shot, entry, variant_name, variant, names, card_font, shapes, recovery_only=False):
        if switch() != "real":
            return await run(shot, entry, variant_name, variant, names, card_font, shapes, recovery_only)
        # A newly requested weapon supersedes the current intent, but it
        # must not erase an unfinished recipe belonging to another weapon.
        # Archives contain independent records, never nested archive maps.
        pending = copy.deepcopy(recovery.get("pending_by_weapon") or {})
        previous_id = recovery.get("weapon_id")
        different = previous_id not in (None, entry["id"])
        archived = pending.get(str(entry["id"])) if different else None
        if recovery_only and different and recovery.get("required") and archived is None:
            raise Stop("gravure interrompue : la cible de récupération est une autre arme")
        if different and recovery.get("required"):
            pending[str(previous_id)] = {key: copy.deepcopy(value) for key, value in recovery.items()
                                         if key != "pending_by_weapon"}
        if recovery_only and archived is not None:
            recovery.clear()
            recovery.update(copy.deepcopy(archived))
        if recovery_only:
            recipe = recovery.get("recipe") or {}
            if recipe.get("weapon_id") == entry["id"]:
                variant_name, variant = recipe["name"], copy.deepcopy(recipe["variant"])
        changes = {"pending_by_weapon": pending}
        if variant is not None:
            changes["recipe"] = {"weapon_id": entry["id"], "name": variant_name,
                                 "variant": copy.deepcopy(variant)}
        remember_state(required=bool(recovery.get("required")), phase="recovering" if recovery_only else "applying",
                       weapon_id=entry["id"], variant=variant_name, locks_verified=False, verified=False,
                       completion_verified=False, error=None, **changes)
        task = asyncio.current_task()
        active[0] = task
        try:
            result = await run(shot, entry, variant_name, variant, names, card_font, shapes, recovery_only)
        except BaseException as exc:
            remember_state(phase="interrupted" if isinstance(exc, asyncio.CancelledError) else "failed",
                           error=type(exc).__name__ if isinstance(exc, asyncio.CancelledError) else str(exc))
            raise
        finally:
            if active[0] is task:
                active[0] = None
        if result[1]["ok"] and variant is not None:
            pending = copy.deepcopy(recovery.get("pending_by_weapon") or {})
            pending.pop(str(entry["id"]), None)
            remember_state(pending_by_weapon=pending)
        remember_state(required=(not result[1]["ok"] or
                                 (recovery_only and variant is None and bool(recovery.get("required")))),
                       phase=("recovered" if recovery_only else "verified") if result[1]["ok"] else "failed",
                       verified=bool(result[1]["ok"] and variant is not None), locks_verified=True)
        return result

    def cancel():
        task = active[0]
        if task is not None and not task.done():
            task.cancel()

    setup.cancel = cancel
    setup.state = lambda: copy.deepcopy(recovery)
    return setup
