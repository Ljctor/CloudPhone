"""Bounded resource-reading visits under their own exclusive lease.
The selected farming instruction is unchanged. No equip, enhancement,
purchase or engraving action is part of this circuit.
"""
import asyncio


class Stopped(RuntimeError):
    pass


class Interrupted(Stopped):
    pass


class UnreadCounter(Stopped):
    pass


def resource_refresh(ports, screens, navigation, equipment, weapon, scrolling, modes, farming, gold, rules):
    saved = ports.store.saved.get("resource_refresh") or {}
    status = {"active": False, "result": "idle", "intention": None, "reason_t": None,
              "supervised_verified": saved.get("supervised_verified") is True,
              "last_attempt": saved.get("last_attempt"), "last_complete": saved.get("last_complete"),
              "next_at": 0, "read": dict(saved.get("read") or {}), "missing": []}
    running = {"task": None, "mode": None, "deadline": None, "reported": None, "supervised_task": None,
               "cancelled": False}
    ports.store.register("resource_refresh", lambda: {key: status[key] for key in (
        "last_attempt", "last_complete", "read", "supervised_verified")})

    def state():
        return {**status, "read": dict(status["read"]), "missing": list(status["missing"])}

    def report(result, reason=None):
        status.update(result=result, reason_t=reason)
        key = (result, str(reason))
        if key != running["reported"] and result in ("blocked", "failed"):
            ports.log("error", "Resource refresh: " + ports.english(reason))
        running["reported"] = key

    def recovery():
        current = farming.get("soul_weapon_state", lambda: None)() or {}
        return current.get("recovery")

    def check():
        current = modes["state"]()
        if (running["cancelled"] or current.get("mode") != running["mode"]
                or not rules.eligible(current, ports.enabled(), recovery())
                or farming["soul_weapon_switch"]() != "real" or ports.pause_left() > 0):
            raise Interrupted("refresh no longer authorized")
        if ports.clock.monotonic() >= running["deadline"]:
            raise Stopped("resource visit exceeded its time budget")

    def identity(seen):
        if seen.get("screen") != "battle":
            return None
        overlays = set(seen.get("overlays") or ())
        if overlays - {"panel", "better_weapon_toast", "equipment_weapon", "equipment_accessories", "weapon_detail", "soul_weapon"}:
            return None
        for name in ("weapon_detail", "soul_weapon", "equipment_accessories", "equipment_weapon"):
            if name in overlays:
                return name
        return "battle" if seen.get("plain") and not overlays - {"better_weapon_toast"} else None

    async def look(expected=None):
        check()
        if not await ports.focused():
            raise Interrupted("game no longer in front")
        shot = await ports.capture(max_age=0)
        if not shot:
            raise Stopped("no fresh capture")
        seen = await ports.analyse(screens.look, shot)
        check()
        found = identity(seen)
        if expected is not None and found != expected:
            raise Stopped(f"expected {expected}, observed {found or 'unidentified screen'}")
        return shot, found

    def intention(destination, phase):
        status["intention"] = {"kind": "resource_refresh", "destination": destination, "phase": phase,
                               "purpose_t": ports.t("Actualiser les compteurs de ressources"),
                               "route": None, "route_known": False}

    def move(screen, name):
        return next(item for item in navigation.connections(screen) if item["id"] == name)

    async def arrived(destination, alternatives=()):
        end = ports.clock.monotonic() + rules.WAIT
        while True:
            shot, found = await look()
            if found in (destination,) + alternatives:
                return shot
            if ports.clock.monotonic() >= end:
                raise Stopped(f"destination {destination} not observed")
            await ports.clock.sleep(rules.FRAME_POLL)

    async def tap(screen, name, destination, predicate=None, alternatives=()):
        intention(destination, "navigation")
        shot, _ = await look(screen)
        if predicate is not None and not await ports.analyse(predicate, shot):
            raise Stopped(f"uncalibrated or unsafe {screen}/{name}")
        check()
        await ports.tap(shot, screen, name, tuple(move(screen, name)["tap"]), verified=predicate is not None)
        return await arrived(destination, alternatives)

    async def scroll(screen, back=False):
        intention(screen, "scrolling")
        before, _ = await look(screen)
        tab = "weapon" if screen == "equipment_weapon" else "accessories"
        if not await ports.analyse(equipment.scroll_safe, before, tab):
            raise Stopped("equipment scroll gap not safely observed")
        start, end = scrolling.swipe_of(move(screen, "scroll"), back)
        check()
        await ports.swipe(before, screen, "scroll", start, end, scrolling.SWIPE_MS, verified=True)
        await ports.clock.sleep(scrolling.SETTLE)
        after, _ = await look(screen)
        end_at = ports.clock.monotonic() + rules.WAIT
        while True:
            await ports.clock.sleep(rules.FRAME_POLL)
            settled, _ = await look(screen)
            if await ports.analyse(scrolling.moved, after, settled,
                                   next(area["rect"] for area in screens.TREE[screen]["scroll"]
                                        if area.get("move") == f"{screen}/scroll")) < scrolling.MOVED:
                return before, settled
            if ports.clock.monotonic() >= end_at:
                raise Stopped("equipment list did not settle")
            after = settled

    def viewport(screen):
        return next(area["rect"] for area in screens.TREE[screen]["scroll"] if area.get("move") == f"{screen}/scroll")

    async def to_start(screen):
        for _ in range(rules.MOST_SCROLLS):
            before, after = await scroll(screen, back=True)
            if await ports.analyse(scrolling.moved, before, after, viewport(screen)) < scrolling.MOVED:
                return after
        raise Stopped("equipment list start not reached within gesture limit")

    async def sample(shot, field):
        check()
        # The bounded capture metadata cache can rotate while OCR awaits.
        # Keep acquisition time with this observation before starting OCR.
        captured_at = ports.capture_time(shot)
        if captured_at is None:
            raise Stopped("resource capture acquisition time unavailable")
        readings = await ports.game["scan"](shot, ("gold", "cubes", "equipment_l3", "souls"))
        value = readings.get(field)
        if value is None:
            raise UnreadCounter(f"{field} unread on its fresh capture")
        gold["observe_resources"](shot, readings, captured_at)
        status["read"][field] = captured_at
        return value

    async def read_l3(screen, field):
        for attempt in range(rules.MOST_SCROLLS + 1):
            shot, _ = await look(screen)
            if await ports.analyse(equipment.read, shot) is not None:
                return await sample(shot, field)  # a real zero is valid
            if attempt < rules.MOST_SCROLLS:
                before, after = await scroll(screen)
                if await ports.analyse(scrolling.moved, before, after, viewport(screen)) < scrolling.MOVED:
                    break
        raise UnreadCounter(f"{field} not found or unread within gesture limit")

    async def phase(field, expected, operation):
        try:
            await operation()
        except UnreadCounter:
            # A missing number is independent from the next resource. Only
            # continue once the unchanged, authorized screen is read again;
            # a different screen/user interruption must still stop everything.
            await look(expected)
            status["missing"].append(field)

    async def cubes(shot):
        await sample(shot, "cubes")
        counter = gold.get("resources", lambda: {})().get("cubes", {})
        if (counter.get("rate") is None and ports.clock.monotonic() + rules.BOOTSTRAP_GAP
                + rules.RETURN_RESERVE < running["deadline"]):
            await ports.clock.sleep(rules.BOOTSTRAP_GAP)
            second, _ = await look("weapon_detail")
            await sample(second, "cubes")

    async def circuit():
        shot, source = await look()
        if source == "soul_weapon":
            await tap("soul_weapon", "close", "equipment_weapon")
        elif source == "battle":
            await tap("battle", "menu_equipment", "equipment_weapon", alternatives=("equipment_accessories",))
            _, opened = await look()
            if opened == "equipment_accessories":
                await tap("equipment_accessories", "weapon", "equipment_weapon")
        elif source == "equipment_accessories":
            await tap("equipment_accessories", "weapon", "equipment_weapon")
        elif source == "weapon_detail":
            await tap("weapon_detail", "close", "equipment_weapon")
        elif source != "equipment_weapon":
            raise Stopped("no calibrated resource route from the current screen")
        await to_start("equipment_weapon")
        shot = await tap("equipment_weapon", "inspect_weapon", "weapon_detail", equipment.inspect_weapon_safe)
        intention("weapon_detail", "reading")
        await phase("cubes", "weapon_detail", lambda: cubes(shot))
        await tap("weapon_detail", "close", "equipment_weapon")
        await phase("weapon_l3", "equipment_weapon", lambda: read_l3("equipment_weapon", "weapon_l3"))
        await tap("equipment_weapon", "accessories", "equipment_accessories")
        await to_start("equipment_accessories")
        await phase("accessory_l3", "equipment_accessories", lambda: read_l3("equipment_accessories", "accessory_l3"))
        await tap("equipment_accessories", "weapon", "equipment_weapon")
        await tap("equipment_weapon", "soul_weapon", "soul_weapon",
                  lambda shot: weapon.tab(shot) == "weapon")
        # Keep regular read-only Gold/souls sampling alive while parked.
        gold["current"]()

    async def return_to_park():
        """Only calibrated read-only returns, while still authorized and
        holding this visit's lease. Never cleanup through a user's input."""
        _, source = await look()
        if source == "soul_weapon":
            return
        if source == "weapon_detail":
            await tap("weapon_detail", "close", "equipment_weapon")
        elif source == "equipment_accessories":
            await tap("equipment_accessories", "weapon", "equipment_weapon")
        elif source != "equipment_weapon":
            raise Stopped("no calibrated return from the observed screen")
        await tap("equipment_weapon", "soul_weapon", "soul_weapon",
                  lambda shot: weapon.tab(shot) == "weapon")

    async def tick(supervised=False):
        if status["active"]:
            return state()
        if not status["supervised_verified"] and not supervised:
            report("pending_supervision", ports.t("Actualisation des ressources : premier passage supervisé en attente"))
            return state()
        if supervised and status["supervised_verified"]:
            return state()
        if not supervised and ports.clock.wall() < status["next_at"]:
            return state()
        current = modes["state"]()
        if not rules.eligible(current, ports.enabled(), recovery()) or ports.pause_left() > 0:
            return state()
        if farming["soul_weapon_switch"]() != "real":
            report("deferred", ports.t("Soul Weapon désactivée : configuration demandée non appliquée"))
            return state()
        status["missing"] = rules.missing(screens, navigation, equipment)
        if status["missing"]:
            status["next_at"] = ports.clock.wall() + rules.EVERY
            report("blocked", ports.t("Actualisation des ressources bloquée : {gates}", gates=", ".join(status["missing"])))
            return state()
        status["last_attempt"] = ports.clock.wall()
        running.update(task=asyncio.current_task(), mode=current["mode"], deadline=ports.clock.monotonic() + rules.DEADLINE,
                       cancelled=False)
        try:
            async with ports.leased(rules.HOLDER, "refresh resource balances", rules.DEADLINE + 10):
                status["active"] = True
                report("running")
                try:
                    await circuit()
                except (ports.Busy, Interrupted, asyncio.CancelledError):
                    raise
                except Exception:
                    try:
                        await return_to_park()
                    except Exception:
                        pass  # unknown/changed screen: no blind return tap
                    raise
                if status["missing"]:
                    report("partial", ports.t("Actualisation des ressources incomplète : {fields}",
                                               fields=", ".join(status["missing"])))
                else:
                    status["last_complete"] = ports.clock.wall()
                    report("complete")
                if supervised:
                    # Every phase ended at a freshly recognized Soul Weapon
                    # screen. Unread counters can be partial; failed or
                    # interrupted navigation never establishes supervision.
                    status["supervised_verified"] = True
        except ports.Busy:
            report("deferred")
        except Interrupted:
            report("interrupted")
        except asyncio.CancelledError:
            report("interrupted")
            raise
        except Exception as exc:
            report("failed", ports.t("Actualisation des ressources arrêtée : {why}", why=str(exc)))
        finally:
            delay = rules.POLL if status["result"] in ("deferred", "interrupted") else rules.EVERY
            status.update(active=False, intention=None, next_at=ports.clock.wall() + delay)
            running["task"] = None
            ports.store.save()
        return state()

    def cancel():
        running["cancelled"] = True
        task = running["task"]
        if task is not None and not task.done():
            task.cancel()

    async def watch():
        task = None
        try:
            while True:
                if task is None or task.done():
                    if task is not None and not task.cancelled():
                        task.exception()
                    task = ports.spawn(tick())
                await ports.clock.sleep(rules.POLL)
        finally:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def start(app):
        ports.spawn(watch())

    async def handle_get(request):
        return ports.respond(state())

    async def handle_supervised(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if not isinstance(body, dict) or body.get("supervised") is not True:
            return ports.respond({"error_t": ports.t("Attendu : {expected}", expected="{supervised: true}")}, status=400)
        task = running["supervised_task"]
        if status["supervised_verified"] or status["active"] or task is not None and not task.done():
            return ports.respond({"accepted": False, **state()}, status=409)
        running["supervised_task"] = ports.spawn(tick(supervised=True))
        return ports.respond({"accepted": True, **state()})

    return {"api": {"state": state, "intention": lambda: status["intention"], "tick": tick, "cancel": cancel},
            "routes": [("GET", "/resource-refresh", handle_get), ("POST", "/resource-refresh", handle_supervised)],
            "startup": [start]}
