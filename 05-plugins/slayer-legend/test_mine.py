"""The Closed Mine's farming loop on a scripted game, on virtual time:
"Repeat entry" that will not untick stops being tapped after three tries,
and turning the mine off and on again in one tick leaves a loop farming.
Run: python3 -m unittest test_mine

The plugin is set up as the gateway does it (gateway.py, the navigation
guard included) against a stand-in context: adb answers from the scene the
game is on, every input it is sent is recorded, and the mine's screen
readers (mine.py) answer from the scene too. Nothing touches Android.
"""

import asyncio
import heapq
import importlib.util
import os
import time
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
EPOCH = 1_800_000_000.0
W, H = 360, 780
FIGHT_GOLD = {"fight": True, "repeat": True, "gold_scroll": True}
FLOORS = [(0.3, 3), (0.4, 4), (0.5, 5), (0.6, 6)]


def load_feature(name):
    """features/<name>.py (or a module beside this file, "../nav")."""
    path = os.path.normpath(os.path.join(HERE, "features", f"{name}.py"))
    spec = importlib.util.spec_from_file_location(f"slayer_legend_test_{os.path.basename(name)}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Request:
    def __init__(self, body=None):
        self.query = {}
        self.remote = "127.0.0.1"
        self._body = body

    async def json(self):
        return self._body


class Game:
    """The scripted game, the virtual clock and the stand-in context.

    scenes: {name: {fight, repeat, gold_scroll, floor_list, floors,
    area_popup, feather_popup, after: (seconds, next), on: {tap: next}}}.
    """

    def __init__(self, scenes, first):
        self.scenes = scenes
        self.names = sorted(scenes)
        self.now = 0.0
        self.timers = []
        self.seq = 0
        self.scene = None
        self.entered = 0.0
        self.taps = []
        self.alerts = []
        # The user's last input (virtual monotonic seconds), or None.
        self.input = None
        self.go(first)

    # -- the clock
    def wall(self):
        return EPOCH + self.now

    def monotonic(self):
        return self.now

    async def sleep(self, seconds, result=None):
        future = asyncio.get_running_loop().create_future()
        self.seq += 1
        heapq.heappush(self.timers, (self.now + max(0.0, seconds), self.seq, future))
        await future
        return result

    # -- the scenes
    def go(self, name):
        self.scene, self.entered = name, self.now

    def current(self):
        for _ in range(10):
            after = self.scenes[self.scene].get("after")
            if not after or self.now - self.entered < after[0]:
                break
            self.go(after[1])
        return self.scenes[self.scene]

    def facts(self, shot):
        """The scene a screenshot was taken on (its first byte)."""
        return self.scenes[self.names[shot[2][0]]]

    def readers(self, real):
        """mine.py with its screen readers answering from the scene."""
        for name, key in [("in_fight", "fight"), ("repeat_ticked", "repeat"), ("gold_scroll", "gold_scroll"),
                          ("area_popup", "area_popup"), ("feather_popup", "feather_popup"),
                          ("floor_list", "floor_list")]:
            setattr(real, name, lambda shot, key=key: self.facts(shot).get(key, False))
        real.floors = lambda shot: list(self.facts(shot).get("floors", []))
        return real

    # -- the context
    def context(self):
        game = self
        routes = {}

        async def screenshot(max_age=0):
            game.current()
            pixels = bytearray(W * H * 3)
            pixels[0] = game.names.index(game.scene)
            return (W, H, bytes(pixels))

        async def adb(*args, timeout=10):
            game.current()
            if args[:2] == ("shell", "dumpsys"):
                return 0, "  mCurrentFocus=Window{1 u0 com.gear2.growslayer/x}\n"
            if args[:2] == ("shell", "pidof"):
                return 0, "4242\n"
            if args[:3] == ("shell", "input", "tap"):
                game.taps.append((game.now, tuple(int(a) for a in args[3:5])))
                nxt = game.scenes[game.scene].get("on", {}).get("tap")
                if nxt:
                    game.go(nxt)
            return 0, ""

        async def analyse(fn, *args):
            return fn(*args)

        async def notify(text):
            game.alerts.append((game.now, text))
            return True

        return SimpleNamespace(
            app=SimpleNamespace(on_startup=[]), id="slayer-legend", directory=HERE, data_dir=None, routes=routes,
            add_get=lambda path, handler: routes.__setitem__(("GET", path), handler),
            add_post=lambda path, handler: routes.__setitem__(("POST", path), handler),
            add_delete=lambda path, handler: routes.__setitem__(("DELETE", path), handler),
            last_input=lambda: None if game.input is None else {"monotonic": game.input, "wall": EPOCH + game.input},
            screenshot=screenshot, adb=adb, analyse=analyse, notify=notify,
            json=lambda value, status=200: SimpleNamespace(status=status, body=value))

    async def run(self, script, horizon):
        """script: [(time, [(method, path, body), ...])]: the requests of
        one item are made back to back, in one tick (method "INPUT": a user
        input then). Returns the answers [(time, path, body)]."""
        spec = importlib.util.spec_from_file_location("slayer_legend_test_gateway", os.path.join(HERE, "gateway.py"))
        gateway = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gateway)
        real_load = gateway.load_sibling
        gateway.load_sibling = lambda directory, name: (
            self.readers(real_load(directory, name)) if name == "mine" else real_load(directory, name))
        context = self.context()
        gateway.setup(context)
        for hook in context.app.on_startup:
            await hook(context.app)
        answers = []
        script = sorted(script, key=lambda item: item[0])
        while True:
            for _ in range(30):
                await asyncio.sleep(0)
            while script and script[0][0] <= self.now:
                for method, path, body in script.pop(0)[1]:
                    if method == "INPUT":
                        self.input = self.now
                        continue
                    response = await context.routes[(method, path)](Request(body))
                    answers.append((self.now, path, response.body))
                for _ in range(30):
                    await asyncio.sleep(0)
            due = [t for t in (self.timers[0][0] if self.timers else None, script[0][0] if script else None)
                   if t is not None]
            if not due or min(due) > horizon:
                break
            self.now = max(self.now, min(due))
            while self.timers and self.timers[0][0] <= self.now:
                future = heapq.heappop(self.timers)[2]
                if not future.done():
                    future.set_result(None)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return answers


def mine(enabled=True, until=None):
    return ("POST", "/mine", {"enabled": enabled, "floor": 5, "area": 2, "until": until})


GET_MINE = ("GET", "/mine", None)
REPEAT = (346, 89)


class MineTest(unittest.TestCase):
    def setUp(self):
        self.saved = time.time, time.monotonic, asyncio.sleep
        self.real_sleep = asyncio.sleep

    def tearDown(self):
        time.time, time.monotonic, asyncio.sleep = self.saved

    def play(self, scenes, first, script, horizon):
        game = Game(scenes, first)
        real_sleep = self.real_sleep

        async def sleep(seconds, result=None):
            # The driver's own yields stay real; every wait of the plugin is virtual.
            if seconds == 0:
                return await real_sleep(0, result)
            return await game.sleep(seconds, result)

        time.time, time.monotonic, asyncio.sleep = game.wall, game.monotonic, sleep
        answers = asyncio.run(game.run(script, horizon))
        return game, answers

    def last(self, answers, path):
        return [body for _, p, body in answers if p == path][-1]


class Untick(MineTest):
    """Repeat entry stays ticked: three tries, then blocked with one alert
    and no more taps."""

    def check_blocked(self, game, answers, reason):
        repeat_taps = [t for t, point in game.taps if point == REPEAT]
        self.assertEqual(len(repeat_taps), 3, game.taps)
        self.assertEqual(len(game.taps), 3, "nothing else is tapped")
        blocked = [text for _, text in game.alerts if "ne se décoche pas" in text]
        self.assertEqual(len(blocked), 1, game.alerts)
        self.assertIn("après 3 essais", blocked[0])
        self.assertIn(reason, blocked[0])
        state = self.last(answers, "/mine")
        self.assertEqual((state["enabled"], state["state"]), (False, "blocked"))

    def test_gold_scroll_gone(self):
        scenes = {"fight": {"fight": True, "repeat": True, "gold_scroll": False}}
        game, answers = self.play(scenes, "fight", [(0, [mine()]), (300, [GET_MINE]), (600, [GET_MINE])], 600)
        self.check_blocked(game, answers, "Plus de parchemin doré")
        self.assertEqual([text for _, text in game.alerts if text.startswith("Plus de parchemin doré (")],
                         ["Plus de parchemin doré (étage 5, zone 2)"])

    def test_timer_ends(self):
        scenes = {"fight": dict(FIGHT_GOLD)}
        game, answers = self.play(scenes, "fight", [(0, [mine(until=EPOCH + 30)]), (300, [GET_MINE])], 400)
        self.check_blocked(game, answers, "Durée écoulée")

    def test_third_try_takes(self):
        scenes = {"fight": {"fight": True, "repeat": True, "gold_scroll": False, "after": (35, "fight2")},
                  "fight2": {"fight": True, "repeat": True, "gold_scroll": False, "on": {"tap": "unticked"}},
                  "unticked": {"fight": True, "repeat": False}}
        game, answers = self.play(scenes, "fight", [(0, [mine()]), (200, [GET_MINE])], 300)
        self.assertEqual(len(game.taps), 3)
        self.assertEqual([text for _, text in game.alerts if "ne se décoche pas" in text], [])
        state = self.last(answers, "/mine")
        self.assertEqual((state["enabled"], state["state"]), (False, "stopped"))


class Reenable(MineTest):
    """Off and on again in one tick: a loop farms again at its next look."""

    def test_through_the_mine(self):
        scenes = {"fight": dict(FIGHT_GOLD)}
        game, answers = self.play(scenes, "fight", [
            (0, [mine()]), (25, [mine(False), mine()]), (60, [GET_MINE]),
            (70, [mine(False), mine(), mine(False), mine()]), (100, [GET_MINE])], 120)
        farming = [body["state"] for t, p, body in answers if p == "/mine" and body["enabled"] and t in (60, 100)]
        self.assertEqual(farming, ["farming", "farming"])

    def test_one_loop_relaunches_once(self):
        scenes = {
            "fight": {**FIGHT_GOLD, "after": (45, "list")},
            "list": {"floor_list": True, "floors": FLOORS, "on": {"tap": "area"}},
            "area": {"floor_list": True, "area_popup": True, "on": {"tap": "feathers"}},
            "feathers": {"floor_list": True, "feather_popup": True, "on": {"tap": "fight2"}},
            "fight2": dict(FIGHT_GOLD),
        }
        game, answers = self.play(scenes, "fight", [
            (0, [mine()]), (15, [mine(False), mine()]), (16, [mine(False), mine(), mine(False), mine()]),
            (150, [GET_MINE])], 200)
        # The floor, the Area and the feathers, once each.
        self.assertEqual(len(game.taps), 3, game.taps)
        self.assertEqual(self.last(answers, "/mine")["state"], "farming")

    def test_through_the_mode(self):
        scenes = {"fight": dict(FIGHT_GOLD)}
        to_mine = ("POST", "/mode", {"mode": "mine", "floor": 5, "area": 2})
        game, answers = self.play(scenes, "fight", [
            (0, [to_mine]), (25, [("POST", "/mode", {"mode": "mpw18"}), to_mine]), (60, [GET_MINE])], 80)
        state = self.last(answers, "/mine")
        self.assertEqual((state["enabled"], state["state"]), (True, "farming"))


RELAUNCH_SCENES = {
    "fight": {**FIGHT_GOLD, "after": (45, "list")},
    "list": {"floor_list": True, "floors": FLOORS, "on": {"tap": "area"}},
    "area": {"floor_list": True, "area_popup": True, "on": {"tap": "feathers"}},
    "feathers": {"floor_list": True, "feather_popup": True, "on": {"tap": "fight2"}},
    "fight2": dict(FIGHT_GOLD),
}
INPUT = ("INPUT", None, None)


class Lease(MineTest):
    """The mine's taps wait for the shared lease: a minute after a user
    input, and while another holder has it."""

    def test_a_user_input_pauses_the_relaunch_a_minute(self):
        game, answers = self.play(RELAUNCH_SCENES, "fight", [(0, [mine()]), (44, [INPUT]), (80, [GET_MINE]),
                                                             (200, [GET_MINE])], 200)
        self.assertEqual(len(game.taps), 3, game.taps)
        self.assertGreaterEqual(game.taps[0][0], 44 + 60, game.taps)
        waiting = [body for t, p, body in answers if t == 80][0]
        self.assertEqual((waiting["state"], waiting["message"]), ("waiting", "En attente : l’utilisateur joue"))
        self.assertEqual(self.last(answers, "/mine")["state"], "farming")

    def test_an_outside_holder_defers_it_until_released(self):
        take = ("POST", "/lease", {"holder": "agent", "reason": "réglages", "seconds": 600})
        game, answers = self.play(RELAUNCH_SCENES, "fight", [
            (0, [mine(), take]), (80, [GET_MINE, ("DELETE", "/lease", {"holder": "someone"})]),
            (100, [("DELETE", "/lease", {"holder": "agent"}), ("GET", "/lease", None)]), (200, [GET_MINE])], 200)
        self.assertTrue(game.taps and game.taps[0][0] >= 100, game.taps)
        self.assertEqual(len(game.taps), 3)
        at_80 = {p: body for t, p, body in answers if t == 80}
        self.assertEqual(at_80["/mine"]["message"], "En attente : bail tenu par agent")
        self.assertEqual(at_80["/lease"]["error"], "not your lease")
        self.assertEqual([body for t, p, body in answers if t == 100 and p == "/lease"][-1], {"lease": None})

    def test_the_plugin_off_taps_nothing_until_it_is_back_on(self):
        off, on = ("POST", "/enabled", {"enabled": False}), ("POST", "/enabled", {"enabled": True})
        game, answers = self.play(RELAUNCH_SCENES, "fight", [
            (0, [mine(), off]), (80, [GET_MINE, ("GET", "/enabled", None)]), (100, [on]), (250, [GET_MINE])], 250)
        self.assertTrue(game.taps and game.taps[0][0] >= 100, game.taps)
        at_80 = {p: body for t, p, body in answers if t == 80}
        self.assertEqual(at_80["/mine"]["message"], "Plugin désactivé")
        self.assertEqual(at_80["/enabled"], {"enabled": False})
        self.assertEqual(self.last(answers, "/mine")["state"], "farming")

    def test_the_lease_is_refused_to_the_plugin_while_it_is_off(self):
        game = Game({"fight": dict(FIGHT_GOLD)}, "fight")
        ports = load_feature("ports").build(game.context(), load_feature("../nav"))
        ports.set_enabled(False)
        self.assertEqual(ports.lease.take("watchdog", "x", 60), "plugin désactivé")
        self.assertIsNone(ports.lease.take("agent", "x", 60, user=True), "an outside holder still may")
        ports.lease.release("agent")
        ports.set_enabled(True)
        self.assertIsNone(ports.lease.take("watchdog", "x", 60))

    def test_no_tap_hold_or_swipe_without_the_lease(self):
        game = Game({"fight": dict(FIGHT_GOLD)}, "fight")
        ports = load_feature("ports").build(game.context(), load_feature("../nav"))
        shot = (W, H, bytes(W * H * 3))

        async def outside():
            for action in (ports.tap(shot, "title", "start", (0.50, 0.836)),
                           ports.hold(shot, "saver", "leave", (0.50, 0.88), 4000),
                           ports.swipe(shot, "mine_list", "scroll", (0.5, 0.4), (0.5, 0.65), 600)):
                with self.assertRaises(ports.Busy):
                    await action

        asyncio.run(outside())
        self.assertEqual(game.taps, [])

    def test_the_plugins_own_names_and_bad_bodies_are_refused(self):
        for body in ({"holder": "mine", "reason": "x", "seconds": 60}, {"holder": "agent", "seconds": 60},
                     {"holder": "agent", "reason": "x", "seconds": 0}, {"holder": "", "reason": "x", "seconds": 9},
                     None):
            _, answers = self.play({"fight": dict(FIGHT_GOLD)}, "fight", [(0, [("POST", "/lease", body)])], 1)
            self.assertIn("error", answers[0][2], body)

    def test_a_lease_expires_with_a_warning_and_is_renewed_by_its_holder(self):
        take = ("POST", "/lease", {"holder": "agent", "reason": "réglages", "seconds": 60})
        with self.assertLogs(level="WARNING") as logs:
            _, answers = self.play({"fight": dict(FIGHT_GOLD)}, "fight", [
                (0, [take]), (50, [take]), (100, [("GET", "/lease", None)]), (120, [("GET", "/lease", None)])], 120)
        state = {t: body for t, p, body in answers}
        self.assertEqual(state[100]["lease"]["since"], EPOCH, "renewed: since kept")
        self.assertEqual(state[100]["lease"]["until"], EPOCH + 110)
        self.assertIsNone(state[120]["lease"])
        self.assertIn("lease of agent expired (réglages)", "\n".join(logs.output))


class FreePlayWarning(MineTest):
    """Free play warns once 2 minutes before its end, again once the timer
    was moved later; the mode feature's watch, through the gateway."""

    WARNING = "Le Cloud Phone reprend la main dans 2 min, prolonge le jeu libre si tu joues encore"

    def test_once_then_again_after_a_longer_timer(self):
        scenes = {"fight": dict(FIGHT_GOLD)}
        game, _ = self.play(scenes, "fight", [
            (0, [("POST", "/mode", {"mode": "free", "until": EPOCH + 600})]),
            (530, [("POST", "/mode/timer", {"add": 5})])], 1000)
        warnings = [t for t, text in game.alerts if text == self.WARNING]
        self.assertEqual(len(warnings), 2, game.alerts)
        self.assertTrue(480 <= warnings[0] <= 490, warnings)
        self.assertTrue(780 <= warnings[1] <= 790, warnings)
        self.assertEqual([text for _, text in game.alerts if text.startswith("Minuteur écoulé")],
                         ["Minuteur écoulé : retour au farming mpw18"])
        self.assertEqual(game.taps, [], "free play touches nothing")


if __name__ == "__main__":
    unittest.main()
