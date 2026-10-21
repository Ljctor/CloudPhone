"""Gold earned per second, read off the gold counter.

GET /gold        {text, value, rate, rate_text, span, read, box}
GET /gold-font   the counter's pixel font, for the page to write the rate

The first GET /gold starts reading the counter every 10 s while the game
is in front; the readings stop 10 minutes after the last page asked (or
the watchdog: api current(), which asks as a page does).
Which readings count and the rate are in gold_rules.py. Read-only: it
never touches the game.
"""

import logging


def gold(ports, screens, stage, counter, rules):
    status = {"window": rules.empty(), "read": None, "box": None, "asked": 0.0, "task": None}

    def gold_facts(shot):
        """The gold counter's reading and where the game is: ("saver",
        stage number) or ("battle", ink of the stage name line)."""
        reading = counter.read(shot)
        if screens.classify(shot) == "saver":
            return reading, ("saver", stage.read_saver(shot)[0])
        return reading, ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME)))

    async def watch():
        while ports.clock.monotonic() - status["asked"] < rules.IDLE:
            try:
                shot = await ports.capture(max_age=rules.SECONDS) if await ports.focused() else None
                if not shot:
                    # Another app in front: the game stops.
                    status["window"] = rules.elsewhere(status["window"])
                else:
                    reading, (kind, here) = await ports.analyse(gold_facts, shot)
                    if reading:
                        status["read"] = ports.clock.wall()
                        status["box"] = reading["box"]
                    window, counts = rules.where(status["window"], kind, here)
                    if counts and reading:
                        window = rules.counted(window, reading, ports.clock.wall())
                    status["window"] = window
            except Exception as e:
                logging.warning(f"Gold reading failed: {e!r}")
            await ports.clock.sleep(rules.SECONDS)
        status["task"] = None

    def asked():
        """The rate now, (rate, samples); the readings go on IDLE more."""
        status["asked"] = ports.clock.monotonic()
        if status["task"] is None:
            status["task"] = ports.spawn(watch())
        rate, samples = rules.rate(status["window"]["samples"], ports.clock.wall())
        status["window"] = {**status["window"], "samples": samples}
        return rate, samples

    def current():
        """For the watchdog: {rate, span (seconds the samples cover), last
        (Unix time of the last sample counted, on the battle screen), or
        None}."""
        rate, samples = asked()
        return {"rate": rate, "span": samples[-1][0] - samples[0][0] if samples else 0,
                "last": samples[-1][0] if samples else None}

    async def handle_gold(request):
        rate, samples = asked()
        return ports.respond({
            "text": status["window"]["text"],
            "value": samples[-1][1] if samples else None,
            "rate": rate,
            "rate_text": counter.rate_text(rate),
            "span": samples[-1][0] - samples[0][0] if samples else 0,
            "read": status["read"],
            "box": status["box"],
        })

    async def handle_font(request):
        return ports.respond({"height": len(counter.DIGITS["0"]),
                              "glyphs": {**counter.DIGITS, **counter.LETTERS, **counter.SIGNS}})

    return {"routes": [("GET", "/gold", handle_gold), ("GET", "/gold-font", handle_font)],
            "api": {"current": current}}
