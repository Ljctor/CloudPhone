"""Gold earned per second, read off the gold counter, and the souls
earned per second, per colour, read off the Equipment panel's souls row
(soul_counters.py: shown on the Soul Weapon screen, where the farming
modes park).

GET /gold        {text, value, rate, rate_text, span, window, read, box,
                  souls: {green, blue, red, white: {text, rate, span,
                  window}}}
GET /gold-font   the counter's pixel font, for the page to write the rate

The first GET /gold starts reading the counters every 2 s while the game
is in front; the readings stop 10 minutes after the last page asked (or
the watchdog: api current(), which asks as a page does).
Which readings count and the rate are in gold_rules.py: one window each,
the same rules, its length following the resolution read (full digits:
a short window); spending souls is left out, spending gold starts its
window again. The game observer publishes each completed reader with its
original capture timestamp and that frame's cheap stage context; slow Soul
OCR never holds Gold sampling behind a full scan. Older game APIs retain the
blocking exact-scan fallback. Read-only: it never touches the game. Exact cube/L3 observations survive gateway
restarts in state.json (hourly_resources), bounded by their original 30-minute
window and stage identity. Restored rates wait for a fresh matching stage
observation; restoring never refreshes a counter's acquisition timestamp.
"""

import math

RESOURCE_FIELDS = ("cubes", "weapon_l3", "accessory_l3")
RESOURCE_SAMPLE_LIMIT = 1024
RESOURCE_MAX_VALUE = 10 ** 100


def resource_ink(value):
    """Bound the stage-name mask; retain no screenshot colours or other pixels."""
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        return None
    rows = []
    width = None
    for row in value:
        if not isinstance(row, (list, str)) or not 1 <= len(row) <= 512:
            return None
        if width is None:
            width = len(row)
        if len(row) != width:
            return None
        if isinstance(row, str):
            if set(row) - {"0", "1"}:
                return None
            rows.append([char == "1" for char in row])
        elif all(type(item) is bool for item in row):
            rows.append(list(row))
        else:
            return None
    return rows if any(any(row) for row in rows) else None


def resource_samples(value, now, seconds):
    """Accept only original, ordered, recent exact integer observations."""
    if not isinstance(value, list) or not 1 <= len(value) <= RESOURCE_SAMPLE_LIMIT:
        return None
    samples = []
    previous = float("-inf")
    for sample in value:
        if not isinstance(sample, (list, tuple)) or len(sample) != 2:
            return None
        at, count = sample
        if (type(at) not in (int, float) or at < 0 or at > now or not math.isfinite(at) or at <= previous
                or type(count) is not int or not 0 <= count < RESOURCE_MAX_VALUE):
            return None
        if samples and count < samples[-1][1]:
            return None
        previous = at
        if now - at <= seconds:
            samples.append((at, count))
    return samples or None


def restored_resources(saved, now, rules):
    """Untrusted stored history never becomes a new observation at restart."""
    restored = {}
    if not isinstance(saved, dict) or type(saved.get("version")) is not int or saved.get("version") != 1:
        return restored
    models = saved.get("resources")
    if not isinstance(models, dict):
        return restored
    for field in RESOURCE_FIELDS:
        model = models.get(field)
        if not isinstance(model, dict) or model.get("resource") != field or model.get("source") != "scan":
            continue
        place = resource_ink(model.get("stage_ink"))
        samples = [] if model.get("samples") == [] else resource_samples(model.get("samples"), now, rules.RESOURCE_WINDOW)
        balance = model.get("balance")
        if balance is None and samples:
            balance = {"value": samples[-1][1]}
        value = balance.get("value") if isinstance(balance, dict) else None
        read = model.get("read")
        last = resource_samples([[read, value]], now, rules.RESOURCE_WINDOW)
        if (not place or samples is None or not last
                or samples and (read != samples[-1][0] or value != samples[-1][1])):
            continue
        at, count = last[0]
        restored[field] = {**rules.empty(), "place": place, "samples": samples,
                           "pending": samples[-1][1] if samples else None,
                           "pending_at": samples[-1][0] if samples else None,
                           "balance": {"value": count, "text": str(count), "read": at},
                           "text": str(count), "step": 1}

    return restored


def gold(ports, screens, stage, counter, rules, souls=None, table=None):
    """souls: soul_counters.py (None: no souls rates)."""
    colours = souls.COLOURS if souls else ()
    interval = getattr(rules, "GOLD_SECONDS", rules.SECONDS)
    game = getattr(ports, "game", None)
    status = {
        "window": rules.empty(),
        "read": None,
        "box": None,
        "shade": 1.0,
        "asked": 0.0,
        "task": None,
        "watching": False,
        "foreground": None,
        "accept_after": None,
        "observed": {},
        "souls": {colour: rules.empty() for colour in colours},
        "resources": {field: rules.empty() for field in RESOURCE_FIELDS},
        "resource_read": {},
        "frame": None,
        "frame_at": None,
        "balance": None,
        "reset_at": None,
        "reset_reason": None,
    }

    store = getattr(ports, "store", None)
    restored = restored_resources((getattr(store, "saved", {}) or {}).get("hourly_resources"),
                                  ports.clock.wall(), rules)
    for field, window in restored.items():
        status["resources"][field] = window
        status["resource_read"][field] = window["balance"]["read"]
    saved_at = ports.clock.monotonic()
    restored_at = ports.clock.wall()
    pending_restore = set(restored)
    pending_stage = {}
    context_at = None

    def resource_snapshot():
        models = {}
        now = ports.clock.wall()
        for field, window in status["resources"].items():
            place = resource_ink(window["place"])
            samples = resource_samples(window["samples"][-RESOURCE_SAMPLE_LIMIT:], now, rules.RESOURCE_WINDOW) or []
            balance = window.get("balance")
            if balance is None and samples:
                balance = {"value": samples[-1][1], "read": samples[-1][0]}
            last = resource_samples([[balance.get("read"), balance.get("value")]], now, rules.RESOURCE_WINDOW) if balance else None
            if not place or not last:
                continue
            models[field] = {"resource": field, "source": "scan", "read": last[0][0],
                             "balance": {"value": last[0][1]},
                             "stage_ink": ["".join("1" if bit else "0" for bit in row) for row in place],
                             "samples": samples}

        return {"version": 1, "resources": models}

    if store is not None:
        store.register("hourly_resources", resource_snapshot)

    def observe_resources(shot, readings, captured_at=None):
        """Count a visit's forced scan now; a short popup need not wait for
        the background poll. Duplicate timestamps never count twice."""
        if captured_at is None:
            captured_at = (
                ports.capture_time(shot) if hasattr(ports, "capture_time") else ports.clock.wall()
            )
        now = ports.clock.wall()
        if (type(captured_at) not in (int, float) or captured_at < 0 or captured_at > now
                or not math.isfinite(captured_at) or now - captured_at > rules.RESOURCE_WINDOW):
            return
        nonlocal saved_at, context_at
        changed = False
        important = False
        kind, here = readings.get("gold_place") or (None, None)
        valid_place = kind == "battle" and resource_ink(here) is not None
        if context_at is None or captured_at > context_at:
            context_at = captured_at
            # Follow stage context even when the resource panel is hidden.
            # One different mask suppresses a slope; only a second distinct
            # capture agreeing on that mask discards its old-stage samples.
            if valid_place:
                for field, window in status["resources"].items():
                    if field in pending_restore and captured_at < restored_at:
                        continue
                    place = window["place"]
                    if place is None or rules.same_place(place, here):
                        status["resources"][field] = {**window, "place": here if place is None else place, "odd": 0}
                        pending_stage.pop(field, None)
                        pending_restore.discard(field)
                    elif field in pending_stage and rules.same_place(pending_stage[field], here):
                        status["resources"][field] = rules.restarted(window, here)
                        pending_stage.pop(field, None)
                        pending_restore.discard(field)
                        changed = important = True
                    else:
                        pending_stage[field] = here
        for field, window in status["resources"].items():
            value = readings.get(field)
            raw = value.get("value") if isinstance(value, dict) else value
            if type(raw) is not int or not 0 <= raw < RESOURCE_MAX_VALUE:
                continue
            # Each field carries its own acquisition watermark across restarts.
            previous_read = status["resource_read"].get(field)
            if previous_read is not None and captured_at <= previous_read:
                continue
            before = window
            counts = (valid_place and field not in pending_stage and field not in pending_restore
                      and window["place"] is not None and rules.same_place(window["place"], here))
            if counts:
                exact = {
                    "value": raw,
                    "text": value.get("text", str(raw)) if isinstance(value, dict) else str(raw),
                    "step": 1,
                    "full": True,
                }
                window = rules.counted(
                    window, exact, captured_at, rules.RESOURCE_WINDOW, short=rules.RESOURCE_WINDOW
                )
                status["resource_read"][field] = captured_at
                window = {**window, "balance": {"value": raw, "text": exact["text"], "read": captured_at}}
            status["resources"][field] = window
            if window != before:
                changed = True
                important |= (not before["samples"] or len(window["samples"]) <= 2
                              or window["samples"][-1][1] != before["samples"][-1][1])
        if store is not None and changed and (important or ports.clock.monotonic() - saved_at >= 10):
            saved_at = ports.clock.monotonic()
            store.save()

    def gold_facts(shot):
        """The gold counter's reading, where the game is: ("saver", stage
        number) or ("battle", ink of the stage name line), and the souls
        row's readings (None: not shown). Under the Soul Weapon screen (a
        menu) the battle is shaded."""
        name = screens.classify(shot)
        reading = counter.read(shot, (1.0, screens.PARKED_SHADE) if name == "menu" else (1.0,))
        if name == "saver":
            return reading, ("saver", stage.read_saver(shot)[0]), None
        return (
            reading,
            ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME))),
            souls.read(shot) if souls else None,
        )

    def consume(reader, shot, captured_at, readings):
        """Each completed reader advances its own acquisition watermark,
        including unread results. Another reader on the same frame is new
        evidence, not a duplicate of the first completion."""
        if (type(captured_at) not in (int, float) or not math.isfinite(captured_at)
                or captured_at > ports.clock.wall()
                or status["accept_after"] is not None and captured_at < status["accept_after"]
                or captured_at <= status["observed"].get(reader, float("-inf"))):
            return
        status["observed"][reader] = captured_at
        kind, here = readings.get("gold_place") or (None, None)
        if reader == "gold":
            status["frame"], status["frame_at"] = shot[2], captured_at
            reading = readings.get("gold_reading")
            after_reset = status["reset_at"] is None or captured_at > status["reset_at"]
            if reading and after_reset:
                status["read"] = captured_at
                status["balance"] = {"text": reading["text"], "value": reading["value"]}
                status["box"] = reading["box"]
                status["shade"] = reading.get("shade", 1.0)
            window, counts = rules.where(status["window"], kind, here)
            if counts and reading and after_reset:
                previous = window["samples"]
                window = rules.counted(window, reading, captured_at)
                if (previous and window["samples"] and window["samples"][-1][0] == captured_at
                        and window["samples"][-1][1] < previous[-1][1]):
                    status["reset_at"] = captured_at
                    status["reset_reason"] = "balance_decreased"
            status["window"] = window
        elif reader == "souls":
            row = readings.get("souls_reading")
            for colour in colours:
                window, counts = rules.where(status["souls"][colour], kind, here)
                count = (row or {}).get(colour)
                if counts and count:
                    window = rules.counted(window, count, captured_at, rules.SOULS_WINDOW, "skip")
                status["souls"][colour] = window
        if reader in ("gold", "cubes", "equipment_l3"):
            observe_resources(shot, readings, captured_at)

    def completed(event):
        if (not status["watching"] or status["foreground"] is False
                or ports.clock.monotonic() - status["asked"] >= rules.IDLE):
            return
        if event["reader"] in ("gold", "souls", "cubes", "equipment_l3"):
            # Context was obtained from this exact frame before OCR started.
            consume(event["reader"], event["shot"], event["at"], {**event["values"], **event["context"]})

    streaming = game is not None and callable(game.get("on_read"))
    unsubscribe = game["on_read"](completed) if streaming else lambda: None

    async def watch():
        try:
            while ports.clock.monotonic() - status["asked"] < rules.IDLE:
                try:
                    shot = await ports.capture(max_age=interval) if await ports.focused() else None
                    if not shot:
                        status["foreground"] = False
                        status["accept_after"] = ports.clock.wall()
                        status["window"] = rules.elsewhere(status["window"])
                        for colour in colours:
                            status["souls"][colour] = rules.elsewhere(status["souls"][colour])
                    else:
                        status["foreground"] = True
                        # Real ports publish the capture to the bounded game
                        # observer. Completion listeners consume its existing
                        # jobs independently; this loop never waits for OCR.
                        if not streaming:
                            captured_at = ports.capture_time(shot) if hasattr(ports, "capture_time") else ports.clock.wall()
                            if game is not None:
                                readings = await game["scan"](shot, ("gold", "souls", "cubes", "equipment_l3"))
                            else:
                                reading, place, row = await ports.analyse(gold_facts, shot)
                                readings = {"gold_reading": reading, "gold_place": place, "souls_reading": row}
                            for reader in ("gold", "souls", "cubes", "equipment_l3"):
                                consume(reader, shot, captured_at, readings)
                except Exception as exc:
                    ports.log("warning", f"Gold reading failed: {exc!r}")
                await ports.clock.sleep(interval)
        finally:
            status["watching"] = False
            status["task"] = None

    async def stop(app):
        status["watching"] = False
        unsubscribe()

    def observe_spend(reason="enhance", at=None):
        """Reset Gold/hour after a verified paid gesture; keep the raw balance.

        The caller must identify a paid control on the actual before frame.
        A newer post-input capture establishes a new baseline, even when
        simultaneous earnings hide the expenditure in the net balance.
        """
        at = ports.clock.wall() if at is None else at
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at):
            return False
        if status["reset_at"] is not None and at < status["reset_at"]:
            return False
        status["window"] = rules.restarted(status["window"], status["window"]["place"])
        status["reset_at"] = at
        status["reset_reason"] = reason
        return True

    def measured(window, long=rules.WINDOW):
        """(window with its samples trimmed, rate, samples, seconds of
        its window)."""
        seconds = rules.window_for(window["step"], long)
        rate, samples = rules.rate(window["samples"], ports.clock.wall(), seconds)
        return {**window, "samples": samples}, rate, samples, seconds

    def span(samples):
        return samples[-1][0] - samples[0][0] if samples else 0

    def asked():
        """The gold rate now, (rate, samples, seconds of its window); the
        readings go on IDLE more."""
        status["asked"] = ports.clock.monotonic()
        if status["task"] is None:
            status["watching"] = True
            status["task"] = ports.spawn(watch())
        status["window"], rate, samples, seconds = measured(status["window"])
        return rate, samples, seconds

    def souls_now():
        """{colour: {text, rate, span, window}}."""
        answer = {}
        for colour in colours:
            status["souls"][colour], rate, samples, seconds = measured(
                status["souls"][colour], rules.SOULS_WINDOW
            )
            answer[colour] = {
                "text": status["souls"][colour]["text"],
                "rate": rate,
                "span": span(samples),
                "window": seconds,
                "read": samples[-1][0] if samples else None,
            }
        return answer

    def current():
        """For the watchdog: {rate, span (seconds the samples cover),
        window (its length), last (Unix time of the last sample counted,
        on the battle screen), or None}."""
        rate, samples, seconds = asked()
        return {
            "rate": rate,
            "span": span(samples),
            "window": seconds,
            "last": samples[-1][0] if samples else None,
        }

    def resources_now():
        answer = {}
        for field, window in status["resources"].items():
            read = status["resource_read"].get(field)
            # A hidden counter retains its dated last measurement. It does
            # not gain fresh timestamps, zero samples, or new confidence.
            rate, samples = rules.rate(
                window["samples"],
                read if read is not None else ports.clock.wall(),
                rules.RESOURCE_WINDOW,
            )
            if field in pending_restore or field in pending_stage:
                rate = None
            state = (
                "unread"
                if read is None
                else (
                    "stale"
                    if ports.clock.wall() - read > rules.RESOURCE_WINDOW
                    else "measuring" if rate is None else "measured"
                )
            )
            answer[field] = {
                "rate": rate,
                "read": read,
                "span": span(samples),
                "window": rules.RESOURCE_WINDOW,
                "text": (window.get("balance") or {}).get("text", window["text"]),
                "value": (window.get("balance") or {}).get("value", samples[-1][1] if samples else None),
                "status": state,
            }
        return answer

    def farming():
        """The observed stage's catalogued drop, never a selected mode's target.
        Unknown, stale or pre-input readings do not choose a counter."""
        empty = {"farming_stage": None, "farming_drop": None, "farming_read": None}
        if game is None or table is None or "view" not in game or "facts" not in game:
            return empty
        fact = game["facts"]().get("stage")
        view = game["view"]()
        if not fact or not view or not fact.get("verified") or fact.get("source") != "scan":
            return empty
        look = view["look"]
        base = look.get("classified") if look["screen"] == "unknown" else look["screen"]
        age = ports.clock.wall() - fact["seen"]
        last_input = ports.last_input() if hasattr(ports, "last_input") else None
        if (
            base not in ("battle", "saver")
            or not 0 <= age <= 30
            or last_input
            and last_input["wall"] > fact["seen"]
        ):
            return empty
        number = fact["value"]
        if (
            not isinstance(number, int)
            or isinstance(number, bool)
            or not 1 <= number <= len(table["stages"])
        ):
            return empty
        entry = dict(zip(table["fields"], table["stages"][number - 1]))
        drop = {"W": "weapon", "A": "accessory"}.get(entry.get("drop"))
        return {"farming_stage": number, "farming_drop": drop, "farming_read": fact["seen"]}

    async def handle_gold(request):
        rate, samples, seconds = asked()
        return ports.respond(
            {
                "observed_at": ports.clock.wall(),
                "text": (status["balance"] or {}).get("text", status["window"]["text"]),
                "value": (status["balance"] or {}).get("value"),
                "reset_at": status["reset_at"],
                "reset_reason": status["reset_reason"],
                "rate": rate,
                "rate_text": counter.rate_text(rate),
                "span": span(samples),
                "window": seconds,
                "read": status["read"],
                "box": status["box"],
                "shade": status["shade"],
                "souls": souls_now(),
                "resources": resources_now(),
                **farming(),
            }
        )

    async def handle_font(request):
        return ports.respond(
            {
                "height": len(counter.DIGITS["0"]),
                "glyphs": {**counter.DIGITS, **counter.LETTERS, **counter.SIGNS},
            }
        )

    return {
        "routes": [("GET", "/gold", handle_gold), ("GET", "/gold-font", handle_font)],
        "shutdown": [stop],
        "api": {
            "current": current,
            "observe_resources": observe_resources,
            "resources": resources_now,
            "observe_spend": observe_spend,
        },
    }
