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
from test_stage_change import french

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
            if not future.done():  # a sleep of a switch cancelled since
                future.set_result(None)


def harness(game, scroll=None, saved=None):
    """The mode feature over the real stage change, every capture and tap
    taking its time. scroll: gold_scroll's stand-in (default: nothing
    seen); saved: state.json's sections at the gateway's start."""
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

    async def farm(stage, preset, mode, highest=None, force=False):
        farmed.append((game.now, mode))
        return await stage_part["api"]["farm"](stage, preset, mode, highest, force)

    stages = {"mpw18": 905, "mpw4": 925}
    presets = {"mpw18": "IV", "mpw4": "II"}
    weapons = {"mpw18": None, "mpw4": None}
    listeners = []
    souls = []

    def loadout(mode):
        return {"stage": stages[mode], "preset": presets[mode], "soul_weapon": weapons[mode]}

    def change(mode, **fields):
        """A change of mode's loadout, as POST /loadout makes it."""
        before = loadout(mode)
        for key, value in fields.items():
            {"stage": stages, "preset": presets, "soul_weapon": weapons}[key][mode] = value
        for listener in listeners:
            listener(mode, before, loadout(mode))

    async def ensure_soul_weapon(mode, part=None):
        souls.append((game.now, mode, part["soul_weapon"]))
        await clock.sleep(5)
        return {"result": "done", "text": "", "timings": {"soul_weapon": 5.0}}

    loadouts = {"loadout": loadout,
                "stage": lambda mode: stages[mode], "set_stage": lambda mode, n: stages.__setitem__(mode, n or stages[mode]),
                "adopt_stage": lambda mode, n: None, "on_change": listeners.append}
    mines = {"start": lambda *a: None, "stop": lambda: None, "set_until": lambda until: None, "ended": False,
             "state": lambda: {"enabled": False, "state": "off", "floor": None, "area": None}}
    values = SimpleNamespace(time_or_none=lambda v: v, number_or_none=lambda v, top: v)
    # mpw4's gold scroll looks share the captures; nothing seen.
    scroll = scroll or SimpleNamespace(fresh=lambda: {"gold": None}, seen=lambda battle, shot: None,
                                       look=lambda kept, seen: (kept, None))
    screens = SimpleNamespace(classify=lambda shot: "battle")
    ports.store = base.Store(saved)
    part = mode_feature.mode(ports, mode_rules, None, values, mines, screens, scroll, loadouts,
                             {"farm": farm, "ensure_soul_weapon": ensure_soul_weapon})
    post = next(h for method, path, h in part["routes"] if method == "POST" and path == "/mode")
    get = next(h for method, path, h in part["routes"] if method == "GET")
    hold = next(h for method, path, h in part["routes"] if method == "POST" and path == "/mode/hold")

    class Request:
        def __init__(self, body):
            self.body = body

        async def json(self):
            return self.body

    return SimpleNamespace(clock=clock, ports=ports, farmed=farmed, presets=presets, stages=stages,
                           change=change, souls=souls, startup=part["startup"],
                           post=lambda body: post(Request(body)), state=lambda: get(None),
                           hold=lambda body: hold(Request(body)))


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
        self.assertEqual(state["state"], "farming", french(state["message_t"]))
        self.assertEqual(h.farmed[0][1], "mpw4")
        line = next(line for line in self.lines if line.startswith("switch "))
        self.assertRegex(line, r"^switch mpw18→mpw4 in \d+ s \(stage \d+ s, preset \d+ s, auto \d+ s, soul_weapon \d+ s\), done$")
        self.assertEqual(len(game.alerts), 1, game.alerts)
        self.assertRegex(game.alerts[0], r"^Farming mpw4 ready in \d+ s$", "within budget: the time alone")

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

    def test_the_timers_end_goes_back_to_the_default_mode(self):
        # Default mpw4: mpw18 chosen for 2 minutes, then back to mpw4.
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)

        async def go():
            answer = await h.post({"mode": "mpw4", "stage4": 925, "default": "mpw4"})
            self.assertIsNone(answer[1]["until"], "the default has no timer")
            await h.clock.until(lambda: there(game, 925, "II") and len(h.farmed) == 1, 300)
            answer = await h.post({"mode": "mpw18"})
            self.assertIsNotNone(answer[1]["until"], "mpw18 is timed now")
            await h.clock.until(lambda: there(game, 905, "IV") and len(h.farmed) == 2, 600)
            await h.post({"mode": "mpw18", "until": h.ports.clock.wall() + 120})
            await h.clock.until(lambda: there(game, 925, "II") and len(h.farmed) == 3, 900)
            return (await h.state())[1]
        state = asyncio.run(go())
        self.assertEqual((state["mode"], state["default"], state["until"]), ("mpw4", "mpw4", None))
        self.assertIn("Timer ended: back to farming mpw4 (stage 925)", game.alerts)

    def test_free_play_as_the_default_touches_nothing_at_the_end(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925, "default": "free",
                          "until": h.ports.clock.wall() + 120})
            await h.clock.until(lambda: there(game, 925, "II") and len(h.farmed) == 1, 300)
            await h.clock.until(lambda: "Timer ended: back to free play" in game.alerts, 900)
            return (await h.state())[1]
        state = asyncio.run(go())
        self.assertEqual((state["mode"], state["until"], state["state"]), ("free", None, "free"))
        self.assertEqual(french(state["message_t"]), "Jeu libre : rien n’est touché")
        self.assertEqual(len(h.farmed), 1)
        self.assertIn("Timer ended: back to free play", game.alerts)

    def test_mpw4_as_the_default_needs_its_stage(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)
        h.stages["mpw4"] = None
        answer = asyncio.run(h.post({"mode": "mpw18", "default": "mpw4"}))
        self.assertEqual(answer[0], 400)
        self.assertIn("stage", french(answer[1]["error_t"]))

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
        self.assertRegex(game.alerts[0], r"^Farming mpw4 ready in \d+ s; Switch mpw18 → mpw4 in \d+ s \(over 60 s\): "
                                         r"slowest step: stage change \(\d+ s\)$")

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
        # The hold said once; the time since the choice, the user's wait
        # included and said apart; no over-budget alert.
        self.assertEqual(len(game.alerts), 2, game.alerts)
        self.assertEqual(game.alerts[0], "Switch to farming mpw4 on hold: you are playing. Next try in 60 s.")
        self.assertRegex(game.alerts[1], r"^Farming mpw4 ready in \d+ s \(including 4\d s waiting: you were playing\)$")
        self.assertGreaterEqual(int(game.alerts[1].split(" in ")[1].split(" ")[0]), 40)
        self.assertTrue(there(game, 925, "II"))

    def on_hold(self, game, h, at, then, free=False):
        """mpw4 chosen while the user plays; at seconds later, then(h)."""
        seen = {}

        async def answer():
            await h.clock.sleep(at)
            seen["during"] = (await h.state())[1]
            seen["answers"] = await then(h)

        async def go():
            asyncio.get_running_loop().create_task(answer())
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: "answers" in seen and (
                any(line.startswith("switch ") for line in self.lines) or game.state["busy"] and free), 600)
            return (await h.state())[1]
        seen["after"] = asyncio.run(go())
        return seen

    def test_on_hold_one_alert_while_the_user_keeps_playing_then_it_goes_on(self):
        game = SlowGame(stage=905, preset="IV", busy="l’utilisateur joue")

        async def stop_playing(h):
            await h.clock.sleep(140)
            game.state["busy"] = None
            return []
        seen = self.on_hold(game, harness(game), 30, stop_playing)
        during = seen["during"]
        self.assertEqual((during["state"], during["setup"], during["hold"]["mode"]), ("waiting", True, "mpw4"))
        self.assertEqual(french(during["message_t"]), "Passage au farming mpw4 en attente : tu joues · nouvel essai dans 60 s")
        self.assertEqual(len(game.alerts), 2, game.alerts)
        self.assertEqual(game.alerts[0], "Switch to farming mpw4 on hold: you are playing. Next try in 60 s.")
        self.assertRegex(game.alerts[1], r"^Farming mpw4 ready in \d+ s \(including 1[67]\d s waiting: you were playing\)$")
        self.assertEqual((seen["after"]["state"], seen["after"]["hold"]), ("farming", None))

    def test_resume_now_runs_the_switch_while_the_user_plays(self):
        game = SlowGame(stage=905, preset="IV", busy="l’utilisateur joue")

        async def resume(h):
            return [await h.hold({"action": "resume"})]
        seen = self.on_hold(game, harness(game), 10, resume)
        self.assertEqual(seen["answers"][0][0], 200)
        self.assertTrue(there(game, 925, "II"))
        self.assertEqual(seen["after"]["state"], "farming")
        self.assertRegex(game.alerts[-1], r"^Farming mpw4 ready in \d+ s \(including 1\d s waiting: you were playing\)$")
        self.assertEqual(len(game.alerts), 2, game.alerts)

    def test_free_play_instead_touches_nothing(self):
        game = SlowGame(stage=905, preset="IV", busy="l’utilisateur joue")
        h = harness(game)

        async def free(h):
            answers = [await h.hold({"action": "free"})]
            answers.append(await h.hold({"action": "free"}))
            answers.append(await h.hold({"action": "resume"}))
            await h.clock.sleep(120)
            return answers
        seen = self.on_hold(game, h, 10, free, free=True)
        codes = [status for status, _ in seen["answers"]]
        self.assertEqual(codes, [200, 200, 409], "the same answer again changes nothing; another: nothing on hold")
        after = seen["after"]
        self.assertEqual((after["mode"], after["state"], after["hold"]), ("free", "free", None))
        self.assertIsNotNone(after["until"], "free play is timed, as its radio button")
        self.assertEqual(game.moves, [], "nothing tapped")
        self.assertEqual(game.alerts, ["Switch to farming mpw4 on hold: you are playing. Next try in 60 s."])

    def test_the_hold_alert_has_two_buttons_with_a_one_time_token_revoked_after(self):
        game = SlowGame(stage=905, preset="IV", busy="l’utilisateur joue")
        h = harness(game)
        sent, issued, revoked = [], [], []
        h.ports.action_token = lambda path, seconds: issued.append((path, seconds)) or "tok1"
        h.ports.revoke_action = revoked.append
        plain = h.ports.notify

        async def notify(text, actions=None):
            sent.append(actions)
            await plain(text)
        h.ports.notify = notify

        async def resume(h):
            hold = (await h.state())[1]["hold"]
            return [await h.hold({"action": "resume", "hold": hold["id"]}), hold]
        seen = self.on_hold(game, h, 10, resume)
        self.assertEqual(issued, [("/mode/hold", mode_rules.HOLD_TOKEN_SECONDS)])
        hold_id = seen["answers"][1]["id"]
        self.assertEqual(sent[0], [
            {"label": "Switch to free play", "path": "/mode/hold", "body": {"action": "free", "hold": hold_id},
             "token": "tok1"},
            {"label": "Resume now", "path": "/mode/hold", "body": {"action": "resume", "hold": hold_id},
             "token": "tok1"}])
        self.assertEqual(sent[1:], [None], "the ready notification has no buttons")
        self.assertEqual(revoked, ["tok1"], "the hold over: its buttons no longer work")

    def test_nothing_on_hold_is_refused(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)
        self.assertEqual(asyncio.run(h.hold({"action": "resume"}))[0], 409)
        self.assertEqual(asyncio.run(h.hold({"action": "later"}))[0], 400)

    def test_a_preset_change_of_the_running_mode_is_applied_at_once(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: there(game, 925, "II") and any(l.startswith("switch ") for l in self.lines), 600)
            start = game.now
            h.change("mpw4", preset="V")
            await h.clock.until(lambda: any(l.startswith("loadout ") for l in self.lines), start + 300)
            return game.now - start, (await h.state())[1]
        took, state = asyncio.run(go())
        self.assertLessEqual(took, mode_rules.SWITCH_BUDGET)
        self.assertTrue(there(game, 925, "V"))
        self.assertEqual(state["state"], "farming", french(state["message_t"]))
        line = next(l for l in self.lines if l.startswith("loadout "))
        self.assertRegex(line, r"^loadout mpw4 changed → applied in \d+ s \(.*\), done$")
        self.assertRegex(game.alerts[-1], r"^Loadout mpw4 applied in \d+ s$")
        self.assertEqual(len(h.farmed), 2, "the switch's own path, farm()")

    def test_a_soul_weapon_change_runs_its_step_alone(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)
        weapon = {"id": 36, "variant": "Gold-balanced"}

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: there(game, 925, "II") and any(l.startswith("switch ") for l in self.lines), 600)
            h.change("mpw4", soul_weapon=weapon)
            await h.clock.until(lambda: any(l.startswith("loadout ") for l in self.lines), 900)
        asyncio.run(go())
        self.assertEqual([(mode, part) for _, mode, part in h.souls], [("mpw4", weapon)])
        self.assertEqual(len(h.farmed), 1, "no farm() for the soul weapon alone")
        self.assertEqual(game.alerts[-1], "Loadout mpw4 applied in 5 s")

    def test_a_change_of_another_mode_or_the_same_values_does_nothing(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game)

        async def go():
            await h.post({"mode": "mpw4", "stage4": 925})
            await h.clock.until(lambda: there(game, 925, "II") and any(l.startswith("switch ") for l in self.lines), 600)
            h.change("mpw18", preset="I")
            h.change("mpw4", preset="II")
            for _ in range(50):
                await asyncio.sleep(0)
            return (await h.state())[1]
        state = asyncio.run(go())
        self.assertEqual(len(h.farmed), 1)
        self.assertFalse(state["setup"])
        self.assertFalse(any(l.startswith("loadout ") for l in self.lines))

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

    def test_loadout_changes_and_their_report(self):
        old = {"stage": 920, "preset": "III", "soul_weapon": None}
        self.assertEqual(mode_rules.loadout_changes(old, dict(old)), set())
        self.assertEqual(mode_rules.loadout_changes(old, dict(old, preset="IV", soul_weapon={"id": 1})),
                         {"preset", "soul_weapon"})
        line, alert = mode_rules.switch_report("mpw18", "mpw18", 21.2, {"preset": 4.0}, applied=True)
        self.assertEqual((line, alert), ("loadout mpw18 changed → applied in 21 s (preset 4 s)", None))
        _, alert = mode_rules.switch_report("mpw18", "mpw18", 75, {"stage": 70}, applied=True)
        self.assertTrue(alert.startswith("Loadout mpw18 applied in 75 s (over 60 s)"), alert)

    def test_the_ready_text(self):
        self.assertEqual(mode_rules.ready_text("mpw18", 34.4), "Farming mpw18 ready in 34 s")
        self.assertEqual(mode_rules.ready_text("mpw18", 21.0, applied=True), "Loadout mpw18 applied in 21 s")

    def test_the_budget_report(self):
        line, alert = mode_rules.switch_report("mpw4", "mpw18", 38.2, {"stage": 24.0, "preset": 4.4, "auto": 6.0})
        self.assertEqual(line, "switch mpw4→mpw18 in 38 s (stage 24 s, preset 4 s, auto 6 s)")
        self.assertIsNone(alert)
        _, alert = mode_rules.switch_report("mpw4", "mpw18", 75, {"stage": 50, "preset": 4, "auto": 6})
        self.assertEqual(alert, "Switch mpw4 → mpw18 in 75 s (over 60 s): slowest step: stage change (50 s)")
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


class GoldScrollInMpw4(unittest.TestCase):
    """mpw4 farming looks for the gold scroll whether it is the default
    mode (« Mode par défaut ») or a timed one."""
    GONE = "Farming mpw4: no more gold scroll"

    def missing(self):
        """The real record and debounce, the scroll never seen in battle."""
        real = base.load("gold_scroll")
        return SimpleNamespace(fresh=real.fresh, look=real.look,
                               seen=lambda battle, shot: False if battle else None)

    def alerted(self, h, game, start, limit=400):
        async def go():
            await start()
            await h.clock.until(lambda: self.GONE in game.alerts, game.now + limit)
            return (await h.state())[1]
        return asyncio.run(go())

    def test_as_the_default_mode(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game, scroll=self.missing())
        state = self.alerted(h, game, lambda: h.post({"mode": "mpw4", "stage4": 925, "default": "mpw4"}))
        self.assertEqual((state["mode"], state["default"], state["until"], state["gold"]),
                         ("mpw4", "mpw4", None, False))

    def test_as_a_timed_mode(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game, scroll=self.missing())
        state = self.alerted(h, game, lambda: h.post({"mode": "mpw4", "stage4": 925,
                                                     "until": h.ports.clock.wall() + 3600}))
        self.assertEqual((state["mode"], state["default"], state["gold"]), ("mpw4", "mpw18", False))

    def test_back_to_the_default_mpw4_after_a_timed_mode(self):
        game = SlowGame(stage=905, preset="IV")
        h = harness(game, scroll=self.missing())

        async def start():
            await h.post({"mode": "mpw18", "default": "mpw4", "stage4": 925,
                          "until": h.ports.clock.wall() + 60})
        state = self.alerted(h, game, start, limit=900)
        self.assertEqual((state["mode"], state["until"], state["gold"]), ("mpw4", None, False))
        self.assertIn("Timer ended: back to farming mpw4 (stage 925)", game.alerts)

    def test_after_a_gateway_restart_as_the_default_mode(self):
        game = SlowGame(stage=925, preset="II")
        h = harness(game, scroll=self.missing(),
                    saved={"mode": {"mode": "mpw4", "default": "mpw4", "until": None, "configured": True}})

        async def start():
            for hook in h.startup:
                await hook(None)
        state = self.alerted(h, game, start)
        self.assertEqual((state["mode"], state["default"], state["gold"]), ("mpw4", "mpw4", False))


if __name__ == "__main__":
    unittest.main()
