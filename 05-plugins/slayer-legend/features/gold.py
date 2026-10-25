"""Gold earned per second, read off the gold counter, and the souls
earned per second, per colour, read off the Equipment panel's souls row
(soul_counters.py: shown on the Soul Weapon screen, where the farming
modes park).

GET /gold        {text, value, rate, rate_text, span, window, read, box,
                  souls: {green, blue, red, white: {text, rate, span,
                  window}}}
GET /gold-font   the counter's pixel font, for the page to write the rate

The first GET /gold starts reading the counters every 10 s while the game
is in front; the readings stop 10 minutes after the last page asked (or
the watchdog: api current(), which asks as a page does).
Which readings count and the rate are in gold_rules.py: one window each,
the same rules, its length following the resolution read (full digits:
a short window); spending souls is left out, spending gold starts its
window again. The readings are the game's scan of the capture
(features/game.py, its gold and souls readers forced on it). Read-only:
it never touches the game.
"""



def gold(ports, screens, stage, counter, rules, souls=None):
    """souls: soul_counters.py (None: no souls rates)."""
    colours = souls.COLOURS if souls else ()
    game = getattr(ports, "game", None)
    status = {"window": rules.empty(), "read": None, "box": None, "asked": 0.0, "task": None,
              "souls": {colour: rules.empty() for colour in colours}}

    def gold_facts(shot):
        """The gold counter's reading, where the game is: ("saver", stage
        number) or ("battle", ink of the stage name line), and the souls
        row's readings (None: not shown). Under the Soul Weapon screen (a
        menu) the battle is shaded."""
        name = screens.classify(shot)
        reading = counter.read(shot, (1.0, screens.PARKED_SHADE) if name == "menu" else (1.0,))
        if name == "saver":
            return reading, ("saver", stage.read_saver(shot)[0]), None
        return (reading, ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME))),
                souls.read(shot) if souls else None)

    async def watch():
        while ports.clock.monotonic() - status["asked"] < rules.IDLE:
            try:
                shot = await ports.capture(max_age=rules.SECONDS) if await ports.focused() else None
                if not shot:
                    # Another app in front: the game stops.
                    status["window"] = rules.elsewhere(status["window"])
                    for colour in colours:
                        status["souls"][colour] = rules.elsewhere(status["souls"][colour])
                elif game is not None:
                    # The game's scan of this capture (features/game.py).
                    readings = await game["scan"](shot, ("gold", "souls"))
                    reading, row = readings.get("gold_reading"), readings.get("souls_reading")
                    kind, here = readings.get("gold_place") or (None, None)
                else:
                    reading, (kind, here), row = await ports.analyse(gold_facts, shot)
                if shot:
                    if reading:
                        status["read"] = ports.clock.wall()
                        status["box"] = reading["box"]
                    window, counts = rules.where(status["window"], kind, here)
                    if counts and reading:
                        window = rules.counted(window, reading, ports.clock.wall())
                    status["window"] = window
                    for colour in colours:
                        window, counts = rules.where(status["souls"][colour], kind, here)
                        count = (row or {}).get(colour)
                        if counts and count:
                            window = rules.counted(window, count, ports.clock.wall(), rules.SOULS_WINDOW, "skip")
                        status["souls"][colour] = window
            except Exception as e:
                ports.log("warning", f"Gold reading failed: {e!r}")
            await ports.clock.sleep(rules.SECONDS)
        status["task"] = None

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
            status["task"] = ports.spawn(watch())
        status["window"], rate, samples, seconds = measured(status["window"])
        return rate, samples, seconds

    def souls_now():
        """{colour: {text, rate, span, window}}."""
        answer = {}
        for colour in colours:
            status["souls"][colour], rate, samples, seconds = measured(status["souls"][colour], rules.SOULS_WINDOW)
            answer[colour] = {"text": status["souls"][colour]["text"], "rate": rate, "span": span(samples),
                              "window": seconds}
        return answer

    def current():
        """For the watchdog: {rate, span (seconds the samples cover),
        window (its length), last (Unix time of the last sample counted,
        on the battle screen), or None}."""
        rate, samples, seconds = asked()
        return {"rate": rate, "span": span(samples), "window": seconds,
                "last": samples[-1][0] if samples else None}

    async def handle_gold(request):
        rate, samples, seconds = asked()
        return ports.respond({
            "text": status["window"]["text"],
            "value": samples[-1][1] if samples else None,
            "rate": rate,
            "rate_text": counter.rate_text(rate),
            "span": span(samples),
            "window": seconds,
            "read": status["read"],
            "box": status["box"],
            "souls": souls_now(),
        })

    async def handle_font(request):
        return ports.respond({"height": len(counter.DIGITS["0"]),
                              "glyphs": {**counter.DIGITS, **counter.LETTERS, **counter.SIGNS}})

    return {"routes": [("GET", "/gold", handle_gold), ("GET", "/gold-font", handle_font)],
            "api": {"current": current}}
