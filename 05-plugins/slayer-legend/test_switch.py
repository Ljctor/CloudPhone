"""A mode switch within 60 s, plugin alone: the mode feature and the real
stage change sequence against test_stage_change's scripted game, on a
virtual clock, with step latencies (a capture, an adb tap, the game's
screens taking time to show). The clock starts at the trigger (POST
/mode, or the timer's end) and stops once the battle screen shows the
target stage, its preset and AUTO on. No watchdog runs here: the timer's
end alone starts the switch back.
Run: python3 -m unittest test_switch"""

import asyncio
import heapq
import logging
import unittest
from types import SimpleNamespace

import test_stage_change as base

mode_feature = base.mode_feature
mode_rules = base.mode_rules

# Seconds, as expected on the phone (see the README's "Mode switch").
CAPTURE = 0.6
TAP = 0.4
# How long the game takes to show the screen a move leads to.
SHOWS = {"close": 0.8, "stage_select": 1.2, "scroll": 0.8, "next_region": 0.8, "previous_region": 0.8,
         "move": 4.0, "preset_badge": 0.8, "preset": 0.3}


class SlowGame(base.Game):
    """The scripted game, whose screens show SHOWS[move] after the move."""

    def __init__(self, **state):
        super().__init__(**state)
        self.hidden = None

    def apply(self, screen, move, point):
        before = dict(self.state)
        super().apply(screen, move, point)
        delay = SHOWS.get(move, 0.8 if move == "close" else 0)
        if delay:
            self.hidden = (self.now + delay, before)

    def snapshot(self):
        if self.hidden and self.now < self.hidden[0]:
            shown, self.state = self.state, self.hidden[1]
            try:
                return super().snapshot()
            finally:
                self.state = shown
        return super().snapshot()


class Clock:
    """Virtual time: sleepers wake in order; time jumps to the next one
    once every task waits."""

    def __init__(self, game):
        self.game = game
        self.sleepers = []
        self.count = 0

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.count += 1
        heapq.heappush(self.sleepers, (self.game.now + max(0.0, seconds), self.count, future))
        await future

    async def until(self, done, limit):
        while True:
            for _ in range(50):
                await asyncio.sleep(0)
            if done():
                return
            assert self.sleepers, "nothing left to wake"
            at, _, future = heapq.heappop(self.sleepers)
            assert at <= limit, f"not done by {limit} s"
            self.game.now = max(self.game.now, at)
            future.set_result(None)


def harness(game):
    """The mode feature over the real stage change, every capture and tap
    taking its time."""
    clock = Clock(game)
    ports = game.ports("real")
    plain = {"capture": ports.capture, "tap": ports.tap, "taps": ports.taps, "swipe": ports.swipe}

    async def capture(max_age=0):
        shot = await plain["capture"](max_age)
        await clock.sleep(CAPTURE)
        return shot

    async def tap(*args, **kwargs):
        await clock.sleep(TAP)
        await plain["tap"](*args, **kwargs)

    async def taps(*args, **kwargs):
        await clock.sleep(TAP)
        await plain["taps"](*args, **kwargs)

    async def swipe(shot, screen, move, start, end, milliseconds):
        await clock.sleep(TAP + milliseconds / 1000)
        await plain["swipe"](shot, screen, move, start, end, milliseconds)

    ports.capture, ports.tap, ports.taps, ports.swipe = capture, tap, taps, swipe
    ports.clock.sleep = clock.sleep
    ports.spawn = lambda coroutine: asyncio.get_running_loop().create_task(coroutine)
    readers = base.readers(game)
    stage_part = base.feature.stage_change(ports, *readers, base.rules, base.TABLE)
    farmed = []

    async def farm(stage, preset, mode, highest=None):
        farmed.append((game.now, mode))
        return await stage_part["api"]["farm"](stage, preset, mode, highest)

    stages = {"mpw18": 905, "mpw4": 925}
    presets = {"mpw18": "IV", "mpw4": "II"}
    loadouts = {"loadout": lambda mode: {"stage": stages[mode], "preset": presets[mode], "soul_weapon": None},
                "stage": lambda mode: stages[mode], "set_stage": lambda mode, n: stages.__setitem__(mode, n or stages[mode]),
                "adopt_stage": lambda mode, n: None}
    mines = {"start": lambda *a: None, "stop": lambda: None, "set_until": lambda until: None, "ended": False,
             "state": lambda: {"enabled": False, "state": "off", "floor": None, "area": None}}
    values = SimpleNamespace(time_or_none=lambda v: v, number_or_none=lambda v, top: v)
    # mpw4's gold scroll looks share the captures; nothing seen.
    scroll = SimpleNamespace(fresh=lambda: {"gold": None}, seen=lambda battle, shot: None,
                             look=lambda kept, seen: (kept, None))
    screens = SimpleNamespace(classify=lambda shot: "battle")
    ports.store = base.Store()
    part = mode_feature.mode(ports, mode_rules, None, values, mines, screens, scroll, loadouts, {"farm": farm})
    post = next(h for method, path, h in part["routes"] if method == "POST" and path == "/mode")
    get = next(h for method, path, h in part["routes"] if method == "GET")

    class Request:
        def __init__(self, body):
            self.body = body

        async def json(self):
            return self.body

    return SimpleNamespace(clock=clock, ports=ports, farmed=farmed, presets=presets, stages=stages,
                           post=lambda body: post(Request(body)), state=lambda: get(None))


def there(game, stage, preset):
    """The battle screen shows stage, preset (on the badge's state) and AUTO on."""
    s = game.snapshot()[2]
    return s["screen"] == "battle" and s["panel"] is None and s["stage"] == stage and s["preset"] == preset \
        and s["auto"]


class Switch(unittest.TestCase):
    def setUp(self):
        logger = logging.getLogger("cloudphone.slayer-legend")
        self.lines = []
        handler = logging.Handler()
        handler.emit = lambda record: self.lines.append(record.getMessage())
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, logger.level)
        logger.setLevel(logging.INFO)

    def test_a_radio_change_switches_within_60_s(self):
        # mpw18 on 905 preset IV, a bottom panel open; to mpw4: 925 (the
        # next region, then scrolls), preset II.
        game = SlowGame(stage=905, preset="IV", panel="shop_summon")
        h = harness(game)

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925})
            start = game.now
            await h.clock.until(lambda: (there(game, 925, "II")
                                         and any("switch" in line for line in self.lines)), start + 300)
            return game.now - start, (await h.state())[1]
        took, state = asyncio.run(go())
        self.assertLessEqual(took, mode_rules.SWITCH_BUDGET, self.lines)
        self.assertEqual(state["state"], "farming", state["message"])
        self.assertEqual(h.farmed[0][1], "mpw4")
        line = next(line for line in self.lines if line.startswith("switch "))
        self.assertRegex(line, r"^switch mpw18→mpw4 in \d+ s \(stage \d+ s, preset \d+ s, auto \d+ s, soul_weapon \d+ s\), done$")
        self.assertEqual(len(game.alerts), 1, game.alerts)
        self.assertRegex(game.alerts[0], r"^Farming mpw4 prêt en \d+ s$", "within budget: the time alone")

    def test_the_timers_end_switches_back_on_time_without_a_watchdog(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925, "until": h.ports.clock.wall() + 120})
            until = h.ports.clock.wall() + 120
            await h.clock.until(lambda: there(game, 925, "II") and len(h.farmed) == 1, 300)
            await h.clock.until(lambda: len(h.farmed) == 2, 600)
            started = h.ports.clock.wall()
            await h.clock.until(lambda: there(game, 905, "IV") and sum("switch" in l for l in self.lines) == 2, 900)
            return started - until, h.ports.clock.wall() - started, (await h.state())[1]
        late, took, state = asyncio.run(go())
        self.assertLessEqual(abs(late), 5, "the switch back starts at the timer's end")
        self.assertLessEqual(took, mode_rules.SWITCH_BUDGET)
        self.assertEqual((state["mode"], state["state"]), ("mpw18", "farming"))
        self.assertTrue(any(line.startswith("switch mpw4→mpw18 in ") for line in self.lines), self.lines)

    def test_over_budget_it_completes_logs_and_alerts_the_slowest_step(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)
        SHOWS["move"], kept = 70.0, SHOWS["move"]
        base.feature.MOVE_SETTLE, kept_settle = 80.0, base.feature.MOVE_SETTLE
        try:
            async def go():
                await h.post({"mode": "mpw4", "stage4": 925})
                await h.clock.until(lambda: any(line.startswith("switch ") for line in self.lines), 600)
                return (await h.state())[1]
            state = asyncio.run(go())
        finally:
            SHOWS["move"], base.feature.MOVE_SETTLE = kept, kept_settle
        self.assertEqual(state["state"], "farming", "it still completes")
        self.assertTrue(there(game, 925, "II"))
        self.assertEqual(len(game.alerts), 1, game.alerts)
        self.assertRegex(game.alerts[0], r"^Farming mpw4 prêt en \d+ s ; Passage mpw18 → mpw4 en \d+ s \(plus de 60 s\) : "
                                         r"étape la plus lente : changement de stage \(\d+ s\)$")

    def test_the_users_minute_is_waited_apart_and_never_counted(self):
        # The user played just before: the lease is refused for 40 s.
        game = SlowGame(stage=905, preset="IV", busy="l’utilisateur joue")
        h = harness(game)

        async def free_after(seconds):
            await h.clock.sleep(seconds)
            game.state["busy"] = None

        async def go():
            asyncio.get_running_loop().create_task(free_after(40))
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: any(line.startswith("switch ") for line in self.lines), 600)
        asyncio.run(go())
        line = next(line for line in self.lines if line.startswith("switch "))
        self.assertRegex(line, r"^switch mpw18→mpw4 in (\d+) s \(.*\) \(\+4\d s waiting for the lease\), done$")
        self.assertLessEqual(int(line.split(" in ")[1].split(" ")[0]), mode_rules.SWITCH_BUDGET)
        # The time since the choice, the user's wait included; no over-budget alert.
        self.assertEqual(len(game.alerts), 1, game.alerts)
        self.assertRegex(game.alerts[0], r"^Farming mpw4 prêt en \d+ s$")
        self.assertGreaterEqual(int(game.alerts[0].split(" en ")[1].split(" ")[0]), 40)
        self.assertTrue(there(game, 925, "II"))

    def test_while_it_sets_up_the_state_says_so(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)
        seen = []

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: game.now >= 3, 600)
            seen.append((await h.state())[1]["setup"])
            await h.clock.until(lambda: any(line.startswith("switch ") for line in self.lines), 600)
            seen.append((await h.state())[1]["setup"])
        asyncio.run(go())
        self.assertEqual(seen, [True, False])

    def test_the_ready_text(self):
        self.assertEqual(mode_rules.ready_text("mpw18", 34.4), "Farming mpw18 prêt en 34 s")
        self.assertEqual(mode_rules.ready_text("mpw18", 21.0, applied=True), "Configuration mpw18 appliquée en 21 s")

    def test_the_budget_report(self):
        line, alert = mode_rules.switch_report("mpw4", "mpw18", 38.2, {"stage": 24.0, "preset": 4.4, "auto": 6.0})
        self.assertEqual(line, "switch mpw4→mpw18 in 38 s (stage 24 s, preset 4 s, auto 6 s)")
        self.assertIsNone(alert)
        _, alert = mode_rules.switch_report("mpw4", "mpw18", 75, {"stage": 50, "preset": 4, "auto": 6})
        self.assertEqual(alert, "Passage mpw4 → mpw18 en 75 s (plus de 60 s) : étape la plus lente : "
                                "changement de stage (50 s)")
        # The lease's wait (the user's minute, another holder) is said, never counted.
        line, alert = mode_rules.switch_report("mpw4", "mpw18", 20, {"stage": 10, "preset": 4, "auto": 6}, 55)
        self.assertEqual(line, "switch mpw4→mpw18 in 20 s (stage 10 s, preset 4 s, auto 6 s) "
                               "(+55 s waiting for the lease)")
        self.assertIsNone(alert)

    def test_the_timed_modes_watch_wakes_at_the_timers_end(self):
        self.assertEqual(mode_rules.next_look(None, 100), mode_rules.WATCH_EVERY)
        self.assertEqual(mode_rules.next_look(200, 100), mode_rules.WATCH_EVERY)
        self.assertAlmostEqual(mode_rules.next_look(103, 100), 3.1)
        self.assertEqual(mode_rules.next_look(90, 100), 0.2)


if __name__ == "__main__":
    unittest.main()
