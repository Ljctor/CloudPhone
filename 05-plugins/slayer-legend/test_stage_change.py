"""Reaching a stage, its preset and AUTO on: the planning rules on views
described here, and the guarded sequence against a scripted game (fake
ports with the real navigation guard, readers answering from the game's
state, virtual time). Nothing touches Android.
Run: python3 -m unittest test_stage_change"""

import asyncio
import contextlib
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
LOG = load("features/ports").python_log("slayer-legend")
EXCEPTION = load("features/ports").exception_log(LOG)
PORTS = load("features/ports")
TEXTS = PORTS.text_ports()
french = TEXTS["french"]


def busy(text):
    """ports.Busy for its French text ("bail tenu par mine")."""
    holder = text.partition("bail tenu par ")[2]
    return PORTS.Busy(PORTS.HELD, holder=holder) if holder else PORTS.Busy(text)
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
        self.assertIn("région", french(rules.plan(view(None, [913]), 920)[1]))
        self.assertIn("aucune", french(rules.plan(view(GIANT, []), 920)[1]))
        self.assertIn("absent", french(rules.plan(view(GIANT, [913, 915]), 914)[1]))
        # Rows of another region than the banner's: not trusted.
        self.assertIn("région lue", french(rules.plan(view(GIANT, [921, 922]), 920)[1]))

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
                      "move_lands": None, "auto_unreadable": False, "focused": True, "busy": None,
                      "controls_unknown": False, "banner_stuck": False, "unfolded_forever": False,
                      "passing_until": None}
        self.state.update(state)
        self.moves = []
        self.calls = []
        self.alerts = []
        self.leases = []

    # -- what a screenshot holds
    def snapshot(self):
        # A screen passing by (an animation, a toast): battle after that.
        if self.state["passing_until"] is not None and self.now >= self.state["passing_until"]:
            self.state.update(screen="battle", passing_until=None)
        s = dict(self.state)
        s["unfolded"] = self.unfolded()
        s["now"] = self.now
        return (480, 1040, s)

    def unfolded(self):
        s = self.state
        return s["unfolded_forever"] or s["unfolded"] is not None and self.now - s["unfolded"] < 2.0

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
            if not s["banner_stuck"]:
                s.update(region=s["region"] + (1 if move == "next_region" else -1), offset=0)
        elif move == "scroll":
            s["offset"] = max(0, min(17, s["offset"] + (2 if point[1] > 0.6 else -2)))
        elif move == "move":
            row = round((point[1] - 0.45) / 0.126)
            stage = self.rows(s)[row]
            s.update(screen="battle", stage=s["move_lands"] or stage)
        elif move == "preset_arrow":
            # Tapped while unfolded, the arrow's spot is the AUTO tile.
            if self.unfolded():
                s["auto"] = not s["auto"]
            s["unfolded"] = self.now
        elif move == "preset_badge":
            if self.unfolded():
                s.update(screen="settings", selected=s["preset"], unfolded=None, unfolded_forever=False)
        elif move == "preset":
            s["selected"] = controls.NUMERALS[controls.PRESET_X.index(point[0])]
        elif move == "close" and screen == "battle_settings":
            s.update(screen="battle", preset=s["selected"])
        elif move == "auto":
            s["auto"] = not s["auto"]
        elif move == "leave" and screen == "saver":
            s["screen"] = "battle"

    def ports(self, switches="real"):
        game = self

        Busy = PORTS.Busy

        @contextlib.asynccontextmanager
        async def leased(holder, reason, seconds, user=False, pause=True):
            # pause=False: the user's minute is not waited for.
            if game.state["busy"] and (pause or game.state["busy"] != "l’utilisateur joue"):
                raise busy(game.state["busy"])
            game.leases.append((holder, reason))
            yield

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
            game.calls.append([move for move, _ in moves])
            for move, point in moves:
                game.moves.append((screen, move))
                game.apply(screen, move, point)
                game.now += gap

        async def hold(shot, screen, move, point, milliseconds):
            guarded(screen, move, point, "hold")
            game.moves.append((screen, move))
            game.apply(screen, move, point)
            game.now += milliseconds / 1000

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

        store = Store({"farming": {"switches": {name: switches for name in feature.SWITCHES}}})
        return SimpleNamespace(capture=capture, analyse=analyse, tap=tap, taps=taps, swipe=swipe, hold=hold,
                               focused=focused,
                               notify=notify, clock=SimpleNamespace(sleep=sleep, wall=lambda: 1e9 + game.now,
                                                                     monotonic=lambda: game.now),
                               leased=leased, Busy=Busy, pause_left=lambda: game.state.get("pause_left", 60),
                               store=store, enabled=lambda: True, respond=lambda value, status=200: (status, value),
                               log=LOG, exception=EXCEPTION, **TEXTS)


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

    fake_screens = SimpleNamespace(plain_battle=plain, open_tab=open_tab, TAB_TAP_Y=screens.TAB_TAP_Y,
                                   classify=lambda shot: shot[2]["screen"], SAVER_TAP=screens.SAVER_TAP,
                                   SAVER_HOLD_MS=screens.SAVER_HOLD_MS)
    fake_select = SimpleNamespace(regions=select.regions, view=view_of, battle_stage=battle_stage,
                                  STAGE_MAP_TAP=select.STAGE_MAP_TAP, ARROW_TAPS=select.ARROW_TAPS,
                                  MOVE_TAP_X=select.MOVE_TAP_X)
    fake_controls = SimpleNamespace(
        ARROW_TAP=controls.ARROW_TAP, BADGE_TAP=controls.BADGE_TAP, AUTO_TAP=controls.AUTO_TAP,
        controls=lambda shot: None if shot[2]["controls_unknown"] else (
            "unfolded" if shot[2]["unfolded"] else "folded"),
        unfolded_now=lambda shot: shot[2]["unfolded"], badge=badge, auto=auto,
        settings_open=lambda shot: shot[2]["screen"] == "settings",
        selected=lambda shot: shot[2]["selected"] if shot[2]["screen"] == "settings" else None,
        preset_tap=controls.preset_tap)
    return fake_screens, fake_select, fake_controls


def run(game, call, switches="real"):
    """The api call's answer, its text_t as text (French); its step
    timings kept in game.timings."""
    part = feature.stage_change(game.ports(switches), *readers(game), rules, TABLE)
    answer = asyncio.run(call(part["api"]))
    if isinstance(answer, dict):
        game.timings = answer.pop("timings", None)
        answer["text"] = french(answer.pop("text_t"))
    return answer


def done():
    return {"result": "done", "text": ""}


class Sequence(unittest.TestCase):
    def test_from_a_panel_to_920_preset_iv(self):
        game = Game(panel="shop_summon")
        self.assertEqual(run(game, lambda api: api["farm"](920, "IV", "mpw18")), done())
        self.assertEqual((game.state["stage"], game.state["preset"], game.state["auto"]), (920, "IV", True))
        until_move = game.moves[:game.moves.index(("stage_select", "move")) + 1]
        self.assertEqual(until_move[:2], [("shop_summon", "close"), ("battle", "stage_select")])
        self.assertEqual(set(until_move[2:-1]), {("stage_select", "scroll")})
        self.assertNotIn(("battle", "auto"), game.moves)
        self.assertIn(("battle_settings", "preset"), game.moves)
        self.assertEqual(game.leases, [("stage_change", "farm mpw18")])

    def test_next_region(self):
        game = Game(stage=915)
        self.assertEqual(run(game, lambda api: api["change_stage"](922)), done())
        self.assertEqual(game.state["stage"], 922)
        self.assertIn(("stage_select", "next_region"), game.moves)

    def test_a_banner_that_does_not_follow_stops(self):
        game = Game(stage=915, banner_stuck=True)
        answer = run(game, lambda api: api["change_stage"](922))
        self.assertEqual(answer["result"], "failed")
        self.assertIn("bannière", answer["text"])
        self.assertEqual(game.moves.count(("stage_select", "next_region")), 1)

    def test_already_there(self):
        game = Game(stage=920, preset="III")
        self.assertEqual(run(game, lambda api: api["farm"](920, "III", "mpw18")), done())
        # Only the unfolds that read the badge and AUTO.
        self.assertEqual(set(game.moves), {("battle", "preset_arrow")})

    def test_past_the_highest_stage_is_tried(self):
        # The gateway may never have seen a stage the game has unlocked.
        game = Game(stage=915)
        answer = run(game, lambda api: api["farm"](925, "III", "mpw18", 920))
        self.assertEqual(answer["result"], "done", answer["text"])
        self.assertEqual(game.state["stage"], 925)

    def test_a_stage_outside_the_known_regions_is_refused(self):
        game = Game(stage=915)
        answer = run(game, lambda api: api["farm"](5, "III", "mpw18", 930))
        self.assertEqual(answer["result"], "failed")
        self.assertIn("hors des régions connues", answer["text"])
        self.assertEqual(game.moves, [])

    def test_plan_by_default_taps_nothing(self):
        game = Game(stage=915, auto=False)
        with self.assertLogs(level="INFO") as logs:
            answer = run(game, lambda api: api["farm"](920, "IV", "mpw18"), switches="plan")
        self.assertEqual(answer["result"], "plan")
        self.assertIn("915 → 920", answer["text"])
        self.assertEqual(game.moves, [])
        self.assertTrue(any("plan only" in line for line in logs.output))

    def test_auto_off_stays_plan_until_recalibrated(self):
        game = Game(stage=920, auto=False)
        answer = run(game, lambda api: api["ensure_auto"]())
        self.assertEqual(answer["result"], "plan")
        self.assertIn("AUTO lu arrêté", answer["text"])
        self.assertNotIn(("battle", "auto"), game.moves)

    def test_auto_off_is_turned_on_once_learned(self):
        game = Game(stage=920, auto=False)
        feature.AUTO_TAP_LEARNED = True
        try:
            self.assertEqual(run(game, lambda api: api["ensure_auto"]()), done())
        finally:
            feature.AUTO_TAP_LEARNED = False
        self.assertTrue(game.state["auto"])
        self.assertEqual(game.moves.count(("battle", "auto")), 1)

    def test_auto_unreadable_is_not_touched(self):
        game = Game(stage=920, auto=False, auto_unreadable=True)
        self.assertIn("AUTO", run(game, lambda api: api["ensure_auto"]())["text"])
        self.assertNotIn(("battle", "auto"), game.moves)

    def test_unfold_and_badge_from_folded_in_one_call(self):
        game = Game(stage=920, preset="III")
        run(game, lambda api: api["set_preset"]("IV"))
        self.assertIn(["preset_arrow", "preset_badge"], game.calls)
        self.assertEqual(game.state["preset"], "IV")

    def test_unfolded_controls_get_the_badge_tap_alone(self):
        # Read unfolded, the arrow would fold them: the badge alone.
        game = Game(stage=920, preset="III", unfolded_forever=True)
        self.assertEqual(run(game, lambda api: api["set_preset"]("IV")), done())
        self.assertEqual(game.calls[0], ["preset_badge"])
        # Only the check on the badge afterwards unfolds them again.
        self.assertEqual(game.moves[:3], [("battle", "preset_badge"), ("battle_settings", "preset"),
                                          ("battle_settings", "close")])
        self.assertEqual(game.state["preset"], "IV")
        self.assertTrue(game.state["auto"])

    def test_unknown_controls_tap_nothing(self):
        game = Game(stage=920, preset="III", controls_unknown=True)
        answer = run(game, lambda api: api["set_preset"]("IV"))
        self.assertEqual(answer["result"], "failed")
        self.assertIn("illisibles", answer["text"])
        self.assertEqual(game.moves, [])

    def test_busy_lease_goes_up(self):
        game = Game(stage=915, busy="l’utilisateur joue")
        with self.assertRaises(RuntimeError):
            run(game, lambda api: api["farm"](920, "III", "mpw18"))
        self.assertEqual(game.moves, [])

    def test_wrong_landing_stops(self):
        game = Game(stage=915, move_lands=916)
        answer = run(game, lambda api: api["farm"](914, "III", "mpw18"))
        self.assertIn("stage 914 non ouvert par le jeu", answer["text"])
        self.assertIn("916", answer["text"])
        # Stopped there: nothing after the Move.
        self.assertEqual(game.moves[-1], ("stage_select", "move"))

    def test_unexpected_screen_stops_untouched(self):
        game = Game(screen="other")
        self.assertIn("écran inattendu", run(game, lambda api: api["farm"](920, "III", "mpw18"))["text"])
        self.assertEqual(game.moves, [])

    def test_a_screen_passing_by_is_waited_for(self):
        game = Game(screen="other", passing_until=1.5)
        self.assertEqual(run(game, lambda api: api["farm"](920, "III", "mpw18")), done())
        self.assertEqual(game.state["stage"], 920)

    def test_the_unexpected_screen_is_named(self):
        game = Game(screen="other")
        self.assertIn("lu : other", run(game, lambda api: api["farm"](920, "III", "mpw18"))["text"])

    def test_power_saving_mode_is_left_by_its_hold(self):
        game = Game(screen="saver")
        self.assertEqual(run(game, lambda api: api["farm"](920, "III", "mpw18")), done())
        self.assertEqual(game.moves[0], ("saver", "leave"))
        self.assertEqual(game.state["stage"], 920)

    def test_power_saving_mode_in_plan_taps_nothing(self):
        game = Game(screen="saver")
        self.assertEqual(run(game, lambda api: api["farm"](920, "III", "mpw18"), switches="plan")["result"], "plan")
        self.assertEqual(game.moves, [])

    def test_an_unread_panel_is_an_unexpected_screen(self):
        game = Game(panel="no_tab_lit")
        self.assertIn("écran inattendu", run(game, lambda api: api["farm"](920, "III", "mpw18"))["text"])
        self.assertEqual(game.moves, [])

    def test_unknown_region(self):
        game = Game()
        self.assertIn("hors des régions", run(game, lambda api: api["change_stage"](31))["text"])
        self.assertEqual(game.moves, [])

    def test_not_in_front(self):
        game = Game(panel="skill", focused=False)
        self.assertIn("premier plan", run(game, lambda api: api["farm"](920, None, "mpw18"))["text"])
        self.assertEqual(game.moves, [])


class Switches(unittest.TestCase):
    def test_plan_by_default_and_post(self):
        game = Game()
        ports = game.ports()
        ports.store = Store({})
        part = feature.stage_change(ports, *readers(game), rules, TABLE)
        get = next(h for method, path, h in part["routes"] if method == "GET")
        post = next(h for method, path, h in part["routes"] if method == "POST")

        class Request:
            def __init__(self, body):
                self.body = body

            async def json(self):
                return self.body

        async def go():
            first = (await get(None))[1]["switches"]
            changed = (await post(Request({"stage_change": "real"})))[1]["switches"]
            refused = await post(Request({"auto": "yes"}))
            not_learned = await post(Request({"auto": "real", "preset": "real"}))
            return first, changed, refused, not_learned
        first, changed, refused, not_learned = asyncio.run(go())
        self.assertEqual(first, {"stage_change": "plan", "preset": "plan", "auto": "plan"})
        self.assertEqual(changed, {"stage_change": "real", "preset": "plan", "auto": "plan"})
        self.assertEqual(refused[0], 400)
        # The AUTO tap is not learned: auto stays plan, nothing else changes.
        self.assertEqual(not_learned[0], 400)
        self.assertIn("AUTO n’est pas encore appris", not_learned[1]["error"])
        self.assertEqual(ports.store.sections["farming"](), {"switches": changed})

    def test_a_real_auto_kept_reads_as_plan_until_learned(self):
        self.assertEqual(feature.kept_switches({"stage_change": "real", "auto": "real"}),
                         {"stage_change": "real", "preset": "plan", "auto": "plan"})
        feature.AUTO_TAP_LEARNED = True
        try:
            self.assertEqual(feature.kept_switches({"auto": "real"})["auto"], "real")
        finally:
            feature.AUTO_TAP_LEARNED = False


class Store:
    def __init__(self, saved=None):
        self.saved = saved or {}
        self.sections = {}

    def register(self, section, snapshot):
        self.sections[section] = snapshot

    def save(self):
        pass


class Mode(unittest.TestCase):
    def enter(self, answers, confirm=None):
        """answers: what farm does each time: an answer ({result, text}:
        its text a template), or Busy's text."""
        game = Game()
        calls = []
        answers = list(answers)

        async def farm(stage, preset, mode, highest=None):
            calls.append((stage, preset, mode))
            answer = answers.pop(0)
            if isinstance(answer, str):
                raise busy(answer)
            return {"result": answer["result"], "text_t": answer["text"] and {"template": answer["text"], "params": {}}}

        ports = game.ports()

        async def wait(seconds):
            game.now += seconds
            if not answers:
                await asyncio.Event().wait()  # the timed mode's watch waits: only entering is tested
        ports.clock.sleep = wait
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
            for _ in range(20):
                await asyncio.sleep(0)
            if confirm:
                part["api"]["confirm"](confirm)
            get = next(h for method, path, h in part["routes"] if method == "GET")
            return (await get(None))[1]

        state = asyncio.run(body())
        return calls, state, game.alerts

    def test_enter_farms_with_the_loadout(self):
        calls, state, alerts = self.enter([done()])
        self.assertEqual(calls, [(931, "III", "mpw4")])
        self.assertEqual(state["state"], "farming", state["message"])
        self.assertEqual(alerts, ["Farming mpw4 ready in 0 s"])

    def test_failure_is_tried_again_within_the_budget_then_one_alert(self):
        failed = {"result": "failed", "text": "ouverture de Select Region"}
        calls, state, alerts = self.enter([failed] * 8)
        # Tried at 0, 2, 6, 14, 30 and 46 s: the next would be past 60 s.
        self.assertEqual(len(calls), 6)
        self.assertEqual(state["state"], "failed")
        self.assertEqual(len(alerts), 1)
        self.assertIn("opening Select Region", alerts[0])

    def test_a_failure_then_a_success_farms_without_alert(self):
        failed = {"result": "failed", "text": "écran inattendu"}
        calls, state, alerts = self.enter([failed, done()])
        self.assertEqual(len(calls), 2)
        self.assertEqual(state["state"], "farming", state["message"])
        self.assertEqual(alerts, ["Farming mpw4 ready in 2 s"], "no failure alert, the retry's time in")

    def test_retry_backoff(self):
        self.assertEqual([mode_rules.retry_after(n, 0) for n in (1, 2, 3, 4, 5)], [2, 4, 8, 16, 16])
        self.assertIsNone(mode_rules.retry_after(5, 46))
        self.assertEqual(mode_rules.retry_after(4, 30), 16)

    def test_the_watchdog_confirms_a_failed_mode(self):
        failed = {"result": "failed", "text": "écran inattendu"}
        calls, state, alerts = self.enter([failed] * 8, confirm="mpw4")
        self.assertEqual(state["state"], "farming", state["message"])
        self.assertIn("931", state["message"])

    def test_a_confirmation_for_another_mode_changes_nothing(self):
        failed = {"result": "failed", "text": "écran inattendu"}
        calls, state, alerts = self.enter([failed] * 8, confirm="mpw18")
        self.assertEqual(state["state"], "failed")

    def test_a_user_who_plays_makes_it_wait_for_the_next_look(self):
        calls, state, alerts = self.enter(["l’utilisateur joue", done()])
        self.assertEqual(len(calls), 2)
        self.assertEqual(state["state"], "farming")
        self.assertIsNone(state["hold"], "the hold is over")
        self.assertEqual(alerts[0], "Switch to farming mpw4 on hold: you are playing. Next try in 60 s.")
        # The fake's sleeps all move one clock: the hold's time is all of it.
        self.assertRegex(alerts[1], r"^Farming mpw4 ready in (\d+) s \(including \1 s waiting: you were playing\)$")
        self.assertEqual(len(alerts), 2)

    def test_another_holder_is_waited_for_without_a_hold(self):
        calls, state, alerts = self.enter(["bail tenu par mine", done()])
        self.assertEqual(alerts, ["Farming mpw4 ready in 2 s"])

    def test_the_lease_waited_for_30_min_at_most_then_one_alert(self):
        held = 1 + mode_rules.LEASE_WAIT // mode_rules.BUSY_RETRY
        calls, state, alerts = self.enter(["bail tenu par mine"] * held + [done()])
        # mpw4 gave up after LEASE_WAIT (one alert); its timer then ended:
        # back to mpw18, which farms.
        self.assertEqual([mode for _, _, mode in calls], ["mpw4"] * held + ["mpw18"])
        self.assertIn("lease still taken after 30 min (lease held by mine), to do by hand", alerts[0])
        self.assertEqual(len([a for a in alerts if "lease" in a]), 1)

    def test_plan_is_said_not_alerted(self):
        calls, state, alerts = self.enter([{"result": "plan", "text": "stage 915 → 931"}])
        self.assertEqual(state["state"], "plan")
        self.assertIn("plan seul", state["message"])
        self.assertEqual(alerts, [])


if __name__ == "__main__":
    unittest.main()
