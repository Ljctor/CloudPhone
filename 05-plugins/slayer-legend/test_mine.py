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
            screenshot=screenshot, adb=adb, analyse=analyse, notify=notify,
            json=lambda value, status=200: SimpleNamespace(status=status, body=value))

    async def run(self, script, horizon):
        """script: [(time, [(method, path, body), ...])]: the requests of
        one item are made back to back, in one tick. Returns the answers
        [(time, path, body)]."""
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


if __name__ == "__main__":
    unittest.main()
