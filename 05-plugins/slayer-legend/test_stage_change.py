"""Reaching a stage, its preset and AUTO on: the planning rules on views
described here, and the guarded sequence against a scripted game (fake
ports with the real navigation guard, readers answering from the game's
state, virtual time). Nothing touches Android.
Run: python3 -m unittest test_stage_change"""

import asyncio
import importlib.util
import json
import os
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/stage_change_rules")
feature = load("features/stage_change")
mode_feature = load("features/mode")
mode_rules = load("features/mode_rules")
nav = load("nav")
select = load("stage_select")
controls = load("battle_controls")
screens = load("screens")
with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
NAMES = select.regions(TABLE)
GIANT = 45


def view(region, stages, cut=None, popup=True):
    return {"popup": popup, "region": region,
            "rows": [{"stage": s, "move": None if s == cut else 0.5} for s in stages]}


class Plan(unittest.TestCase):
    def test_moves(self):
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915]), 914), ("move", 0.5))
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915]), 920), ("scroll", "down"))
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915]), 902), ("scroll", "up"))
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915]), 925), ("arrow", "next_region"))
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915]), 899), ("arrow", "previous_region"))
        # The target's row is cut by the list: brought into view first.
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915], cut=915), 915), ("scroll", "down"))
        self.assertEqual(rules.plan(view(GIANT, [913, 914, 915], cut=913), 913), ("scroll", "up"))

    def test_failures(self):
        self.assertEqual(rules.plan(view(None, [], popup=False), 920)[0], "fail")
        self.assertIn("région", rules.plan(view(None, [913]), 920)[1])
        self.assertIn("aucune", rules.plan(view(GIANT, []), 920)[1])
        self.assertIn("absent", rules.plan(view(GIANT, [913, 915]), 914)[1])
        # Rows of another region than the banner's: not trusted.
        self.assertIn("région lue", rules.plan(view(GIANT, [921, 922]), 920)[1])

    def test_progress_and_support(self):
        self.assertFalse(rules.progressed(view(GIANT, [918, 919, 920]), view(GIANT, [918, 919, 920])))
        self.assertTrue(rules.progressed(view(GIANT, [915]), view(GIANT, [917])))
        self.assertTrue(rules.supported(920, NAMES))
        self.assertFalse(rules.supported(31, NAMES))
        self.assertFalse(rules.supported(None, NAMES))
        self.assertFalse(rules.supported(99999, NAMES))


class Game:
    """The scripted game: a state the fake readers read, changed by the
    taps the fake ports let through the real navigation guard."""

    def __init__(self, **state):
        self.now = 0.0
        self.state = {"screen": "battle", "panel": None, "stage": 915, "region": None, "offset": 0,
                      "preset": "III", "selected": None, "auto": True, "unfolded": None,
                      "move_lands": None, "auto_unreadable": False, "focused": True}
        self.state.update(state)
        self.moves = []
        self.alerts = []

    # -- what a screenshot holds
    def snapshot(self):
        s = dict(self.state)
        s["unfolded"] = s["unfolded"] is not None and self.now - s["unfolded"] < 2.0
        s["now"] = self.now
        return (480, 1040, s)

    def rows(self, s):
        first = s["region"] * 20 + 1 + s["offset"]
        return [first + i for i in range(3)]

    # -- the moves
    def apply(self, screen, move, point):
        s = self.state
        if move == "close" and screen != "stage_select" and screen != "battle_settings":
            s["panel"] = None
        elif move == "stage_select":
            s.update(screen="popup", region=(s["stage"] - 1) // 20, offset=max(0, min(17, (s["stage"] - 1) % 20 - 2)))
        elif move in ("next_region", "previous_region"):
            s.update(region=s["region"] + (1 if move == "next_region" else -1), offset=0)
        elif move == "scroll":
            s["offset"] = max(0, min(17, s["offset"] + (2 if point[1] > 0.6 else -2)))
        elif move == "move":
            row = round((point[1] - 0.45) / 0.126)
            stage = self.rows(s)[row]
            s.update(screen="battle", stage=s["move_lands"] or stage)
        elif move == "preset_arrow":
            s["unfolded"] = self.now
        elif move == "preset_badge":
            s.update(screen="settings", selected=s["preset"], unfolded=None)
        elif move == "preset":
            s["selected"] = controls.NUMERALS[controls.PRESET_X.index(point[0])]
        elif move == "close" and screen == "battle_settings":
            s.update(screen="battle", preset=s["selected"])
        elif move == "auto":
            s["auto"] = not s["auto"]

    def ports(self):
        game = self

        def guarded(screen, move, point, kind="tap", verified=False):
            refusal = nav.guard(screen, move, point[0], point[1], kind, verified)
            if refusal:
                raise RuntimeError(refusal)

        async def capture(max_age=0):
            return game.snapshot()

        async def analyse(fn, *args):
            return fn(*args)

        async def tap(shot, screen, move, point, verified=False):
            guarded(screen, move, point, verified=verified)
            game.moves.append((screen, move))
            game.apply(screen, move, point)

        async def taps(shot, screen, moves, gap, verified=()):
            for move, point in moves:
                guarded(screen, move, point, verified=move in verified)
            for move, point in moves:
                game.moves.append((screen, move))
                game.apply(screen, move, point)
                game.now += gap

        async def swipe(shot, screen, move, start, end, milliseconds):
            guarded(screen, move, start, "swipe")
            game.moves.append((screen, move))
            game.apply(screen, move, start)

        async def focused():
            return game.state["focused"]

        async def sleep(seconds):
            game.now += seconds

        async def notify(text):
            game.alerts.append(text)

        return SimpleNamespace(capture=capture, analyse=analyse, tap=tap, taps=taps, swipe=swipe, focused=focused,
                               notify=notify, clock=SimpleNamespace(sleep=sleep, wall=lambda: 1e9 + game.now,
                                                                     monotonic=lambda: game.now))


def readers(game):
    """Stand-ins for screens, stage_select and battle_controls that read
    the game's state off the screenshot."""
    def plain(shot):
        s = shot[2]
        return s["screen"] == "battle" and s["panel"] is None

    def open_tab(shot):
        tab = shot[2]["panel"]
        if shot[2]["screen"] != "battle":
            return None
        return next(((x, name) for x, name in screens.TABS if name == tab), None)

    def view_of(shot, names):
        s = shot[2]
        if s["screen"] != "popup":
            return {"popup": False, "region": None, "rows": []}
        return {"popup": True, "region": s["region"],
                "rows": [{"stage": stage, "move": 0.45 + 0.126 * i} for i, stage in enumerate(game.rows(s))]}

    def battle_stage(shot, names):
        return shot[2]["stage"] if plain(shot) else None

    def badge(shot):
        s = shot[2]
        return s["preset"] if plain(shot) and s["unfolded"] else None

    def auto(first, second):
        if not (first[2]["unfolded"] and second[2]["unfolded"]) or first[2]["auto_unreadable"]:
            return None
        return "on" if second[2]["auto"] else "off"

    fake_screens = SimpleNamespace(plain_battle=plain, open_tab=open_tab, TAB_TAP_Y=screens.TAB_TAP_Y)
    fake_select = SimpleNamespace(regions=select.regions, view=view_of, battle_stage=battle_stage,
                                  STAGE_MAP_TAP=select.STAGE_MAP_TAP, ARROW_TAPS=select.ARROW_TAPS,
                                  MOVE_TAP_X=select.MOVE_TAP_X)
    fake_controls = SimpleNamespace(
        ARROW_TAP=controls.ARROW_TAP, BADGE_TAP=controls.BADGE_TAP, AUTO_TAP=controls.AUTO_TAP,
        folded=lambda shot: not shot[2]["unfolded"], badge=badge, auto=auto,
        settings_open=lambda shot: shot[2]["screen"] == "settings",
        selected=lambda shot: shot[2]["selected"] if shot[2]["screen"] == "settings" else None,
        preset_tap=controls.preset_tap)
    return fake_screens, fake_select, fake_controls


def run(game, call):
    part = feature.stage_change(game.ports(), *readers(game), rules, TABLE)
    return asyncio.run(call(part["api"]))


class Sequence(unittest.TestCase):
    def test_from_a_panel_to_920_preset_iv(self):
        game = Game(panel="shop_summon")
        self.assertIsNone(run(game, lambda api: api["farm"](920, "IV")))
        self.assertEqual((game.state["stage"], game.state["preset"], game.state["auto"]), (920, "IV", True))
        until_move = game.moves[:game.moves.index(("stage_select", "move")) + 1]
        self.assertEqual(until_move[:2], [("shop_summon", "close"), ("battle", "stage_select")])
        self.assertEqual(set(until_move[2:-1]), {("stage_select", "scroll")})
        self.assertNotIn(("battle", "auto"), game.moves)
        self.assertIn(("battle_settings", "preset"), game.moves)

    def test_next_region(self):
        game = Game(stage=915)
        self.assertIsNone(run(game, lambda api: api["change_stage"](922)))
        self.assertEqual(game.state["stage"], 922)
        self.assertIn(("stage_select", "next_region"), game.moves)

    def test_already_there(self):
        game = Game(stage=920, preset="III")
        self.assertIsNone(run(game, lambda api: api["farm"](920, "III")))
        # Only the unfolds that read the badge and AUTO.
        self.assertEqual(set(game.moves), {("battle", "preset_arrow")})

    def test_auto_off_is_turned_on(self):
        game = Game(stage=920, auto=False)
        self.assertIsNone(run(game, lambda api: api["ensure_auto"]()))
        self.assertTrue(game.state["auto"])
        self.assertEqual(game.moves.count(("battle", "auto")), 1)

    def test_auto_unreadable_is_not_touched(self):
        game = Game(stage=920, auto=False, auto_unreadable=True)
        self.assertIn("AUTO", run(game, lambda api: api["ensure_auto"]()))
        self.assertNotIn(("battle", "auto"), game.moves)
        self.assertIsNone(run(game, lambda api: api["auto_state"]()))

    def test_wrong_landing_stops(self):
        game = Game(stage=915, move_lands=916)
        failure = run(game, lambda api: api["farm"](914, "III"))
        self.assertIn("vérification après Move", failure)
        self.assertIn("916", failure)
        # Stopped there: nothing after the Move.
        self.assertEqual(game.moves[-1], ("stage_select", "move"))

    def test_unexpected_screen_stops_untouched(self):
        game = Game(screen="other")
        self.assertIn("écran inattendu", run(game, lambda api: api["farm"](920, "III")))
        self.assertEqual(game.moves, [])

    def test_unknown_region(self):
        game = Game()
        self.assertIn("hors des régions", run(game, lambda api: api["change_stage"](31)))
        self.assertEqual(game.moves, [])

    def test_not_in_front(self):
        game = Game(panel="skill", focused=False)
        self.assertIn("premier plan", run(game, lambda api: api["farm"](920, None)))
        self.assertEqual(game.moves, [])


class Store:
    saved = {}

    def register(self, section, snapshot):
        pass

    def save(self):
        pass


class Mode(unittest.TestCase):
    def enter(self, failure):
        game = Game()
        calls = []

        async def farm(stage, preset):
            calls.append((stage, preset))
            return failure

        ports = game.ports()

        async def wait_forever(seconds):
            await asyncio.Event().wait()  # the timed mode's watch waits: only entering is tested
        ports.clock.sleep = wait_forever
        ports.store = Store()
        ports.respond = lambda value, status=200: (status, value)
        mines = {"start": lambda *a: None, "stop": lambda: None, "set_until": lambda until: None, "ended": False,
                 "state": lambda: {"enabled": False, "state": "off", "floor": None, "area": None}}
        loadouts = {"loadout": lambda mode: {"stage": 920, "preset": "III", "soul_weapon": None},
                    "stage": lambda mode: {"mpw18": 920, "mpw4": 931}[mode], "set_stage": lambda mode, n: None,
                    "adopt_stage": lambda mode, n: None}
        values = SimpleNamespace(time_or_none=lambda v: v, number_or_none=lambda v, top: v)
        scroll = SimpleNamespace(fresh=lambda: {"gold": None})

        async def body():
            ports.spawn = lambda coroutine: asyncio.get_running_loop().create_task(coroutine)
            part = mode_feature.mode(ports, mode_rules, None, values, mines, None, scroll, loadouts,
                                     {"farm": farm})
            handler = next(h for method, path, h in part["routes"] if method == "POST" and path == "/mode")

            class Request:
                async def json(self):
                    return {"mode": "mpw4", "stage4": 931}
            await handler(Request())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            get = next(h for method, path, h in part["routes"] if method == "GET")
            return (await get(None))[1]

        state = asyncio.run(body())
        return calls, state, game.alerts

    def test_enter_farms_with_the_loadout(self):
        calls, state, alerts = self.enter(None)
        self.assertEqual(calls, [(931, "III")])
        self.assertEqual(state["state"], "farming", state["message"])
        self.assertEqual(alerts, [])

    def test_failure_is_one_alert(self):
        calls, state, alerts = self.enter("ouverture de Select Region")
        self.assertEqual(state["state"], "failed")
        self.assertEqual(len(alerts), 1)
        self.assertIn("ouverture de Select Region", alerts[0])


if __name__ == "__main__":
    unittest.main()
