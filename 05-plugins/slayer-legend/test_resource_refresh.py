"""Bounded resource visits with actual navigation guard and ownership ports.
Scene readers are explicit test doubles, never production calibration proof.
"""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location("refresh_" + name.replace("/", "_"), HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feature = load("features/resource_refresh")
rules = load("features/resource_refresh_rules")
nav = load("nav")
port_module = load("features/ports")
scroll_module = load("scrolling")
REGISTRY = json.loads((HERE / "screen_registry.json").read_text())


class ResourceRefresh(unittest.IsolatedAsyncioTestCase):
    def build(self, *, gate=True, start="soul_weapon", zero=False, unread_cube=False, unread_l3=False, verified=True):
        model = {"screen": start, "position": {"equipment_weapon": 0, "equipment_accessories": 0},
                 "now": 100.0, "input": None, "recovery": None, "enabled": True,
                 "mode": {"mode": "mpw18", "configured": True, "state": "farming", "setup": False, "hold": None}}
        inputs, captures, observed, intents = [], [], [], []
        hooks = {"input": lambda *args: None, "scan": lambda *args: None, "rate": None,
                 "observed_at": []}
        refresh_ref = {}

        async def adb(*args, **kwargs):
            if args[:2] == ("shell", "dumpsys"):
                return 0, "mCurrentFocus com.gear2.growslayer"
            if args[:2] != ("shell", "input"):
                raise AssertionError(args)
            source = model["screen"]
            if args[2] == "tap":
                point = (int(args[3]) / 480, int(args[4]) / 1040)
                found = next(m for m in nav.connections(source) if m.get("tap") and not m.get("forbidden")
                             and abs(m["tap"][0] - point[0]) < .005 and abs(m["tap"][1] - point[1]) < .005)
                model["screen"] = found["to"]
                action = found["id"]
            elif args[2] == "swipe":
                action = "back" if int(args[4]) < int(args[6]) else "forward"
                delta = -1 if action == "back" else 1
                model["position"][source] = max(0, min(2, model["position"][source] + delta))
            else:
                raise AssertionError(args)
            inputs.append((source, action))
            if refresh_ref:
                intents.append(refresh_ref["api"]["intention"]())
            hooks["input"](source, action)
            return 0, ""

        async def capture(max_age=0):
            shot = (480, 1040, copy.deepcopy({"screen": model["screen"], "position": model["position"]}))
            captures.append(shot)
            return shot

        async def analyse(fn, *args):
            return fn(*args)

        async def sleep(seconds):
            model["now"] += seconds

        ports = port_module.build(NS(id="refresh-test", adb=adb, screenshot=capture, analyse=analyse,
                                     screenshot_time=lambda shot: model["now"],
                                     json=lambda value: value, last_input=lambda: model["input"],
                                     log=lambda *args, **kwargs: None), nav)
        clock = NS(wall=lambda: model["now"], monotonic=lambda: model["now"], sleep=sleep)
        ports.clock = ports.lease.clock = clock
        ports.store.saved["resource_refresh"] = {"supervised_verified": verified}
        ports.enabled = lambda: model["enabled"]

        def look(shot):
            screen = shot[2]["screen"]
            if screen == "unknown":
                return {"screen": "unknown", "overlays": [], "plain": False}
            return {"screen": "battle", "overlays": [] if screen == "battle" else ["panel", screen],
                    "plain": screen == "battle"}

        def count(shot):
            screen = shot[2]["screen"]
            blocked = unread_l3 is True or unread_l3 == screen
            return (0 if zero else 3) if not blocked and shot[2]["position"].get(screen) == 1 else None

        equipment = NS(INSPECT_LEARNED=gate, SCROLL_LEARNED=gate,
                       inspect_weapon_safe=lambda shot: shot[2]["screen"] == "equipment_weapon",
                       scroll_safe=lambda shot, tab: shot[2]["screen"] == "equipment_" + tab,
                       read=count)
        equipment.scroll_safe = lambda shot, tab: shot[2]["screen"] == (
            "equipment_weapon" if tab == "weapon" else "equipment_accessories")
        screens = NS(REGISTRY={name: {"status": "registered", "fixtures": ["test-double"]}
                               for name in rules.REQUIRED_SCREENS}, TREE=REGISTRY["tree"], look=look)
        scrolling = NS(SWIPE_MS=900, SETTLE=.8, MOVED=.04, swipe_of=scroll_module.swipe_of,
                       moved=lambda a, b, rect: int(a[2]["position"] != b[2]["position"]))
        weapon = NS(tab=lambda shot: "weapon" if shot[2]["screen"] == "equipment_weapon" else None)

        async def scan(shot, force):
            screen = shot[2]["screen"]
            values = {"gold_place": ("battle", [[True]])}
            if screen == "weapon_detail" and not unread_cube:
                values["cubes"] = {"value": 1200, "text": "1,200"}
            if screen in ("equipment_weapon", "equipment_accessories"):
                values["weapon_l3" if screen == "equipment_weapon" else "accessory_l3"] = count(shot)
            hooks["scan"](screen)
            return values

        ports.game = {"scan": scan}
        def observe_resources(shot, readings, captured_at):
            observed.append((shot, readings))
            hooks["observed_at"].append(captured_at)

        gold = {"observe_resources": observe_resources, "current": lambda: None,
                "resources": lambda: {"cubes": {"rate": hooks["rate"]}}}
        farming = {"soul_weapon_switch": lambda: "real", "soul_weapon_state": lambda: {"recovery": model["recovery"]}}
        part = feature.resource_refresh(ports, screens, nav, equipment, weapon, scrolling,
                                       {"state": lambda: model["mode"]}, farming, gold, rules)
        refresh_ref.update(part)
        return model, inputs, captures, observed, intents, hooks, ports, part["api"]

    async def test_complete_guarded_circuit_and_valid_zero_returns_to_park(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(zero=True)
        requested = copy.deepcopy(model["mode"])
        result = await api["tick"]()
        self.assertEqual(result["result"], "complete")
        self.assertEqual(model["screen"], "soul_weapon")
        self.assertEqual(model["mode"], requested)
        self.assertEqual(set(result["read"]), {"cubes", "weapon_l3", "accessory_l3"})
        self.assertEqual(len(observed), 4)
        self.assertTrue(any(row.get("weapon_l3") == 0 for shot, row in observed))
        self.assertTrue(all(intent["kind"] == "resource_refresh" and not intent["route_known"] for intent in intents))
        self.assertFalse(result["active"])
        self.assertIsNone(result["intention"])
        self.assertIsNone(ports.lease.state())
        before = list(inputs)
        await api["tick"]()
        self.assertEqual(inputs, before, "completed visits wait their refresh interval")

    async def test_missing_calibration_blocks_before_any_capture_or_input(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(gate=False)
        result = await api["tick"]()
        self.assertEqual(result["result"], "blocked")
        self.assertIn("inspect_weapon_safe", result["missing"])
        self.assertEqual((inputs, captures), ([], []))

    async def test_user_input_stops_without_a_cleanup_gesture(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build()
        def interrupt(source, action):
            if action == "inspect_weapon":
                model["input"] = {"monotonic": model["now"] + .001, "wall": model["now"]}
        hooks["input"] = interrupt
        result = await api["tick"]()
        self.assertEqual(result["result"], "interrupted")
        self.assertEqual(inputs[-1], ("equipment_weapon", "inspect_weapon"))
        self.assertEqual(model["screen"], "weapon_detail")
        self.assertIsNone(ports.lease.state())

    async def test_new_mode_stops_route_without_changing_the_instruction(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build()
        hooks["input"] = lambda *args: model["mode"].update(mode="free")
        result = await api["tick"]()
        self.assertEqual(result["result"], "interrupted")
        self.assertEqual(len(inputs), 1)
        self.assertEqual(model["mode"]["mode"], "free")

    async def test_unread_cube_closes_only_known_popup_and_returns_to_park(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(unread_cube=True)
        result = await api["tick"]()
        self.assertEqual(result["result"], "partial")
        self.assertEqual(model["screen"], "soul_weapon")
        self.assertEqual(set(result["read"]), {"weapon_l3", "accessory_l3"})
        self.assertEqual(result["missing"], ["cubes"])
        self.assertIn(("weapon_detail", "close"), inputs)

    async def test_unread_l3_stops_at_boundary_and_never_invents_zero(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(unread_l3=True)
        result = await api["tick"]()
        self.assertEqual(result["result"], "partial")
        self.assertNotIn("weapon_l3", result["read"])
        self.assertEqual(model["screen"], "soul_weapon")
        self.assertLessEqual(len([i for i in inputs if i[1] == "forward"]), rules.MOST_SCROLLS * 2)

    async def test_unread_weapon_does_not_suppress_accessories(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(unread_l3="equipment_weapon")
        result = await api["tick"]()
        self.assertEqual(result["result"], "partial")
        self.assertEqual(result["missing"], ["weapon_l3"])
        self.assertIn("accessory_l3", result["read"])
        self.assertEqual(model["screen"], "soul_weapon")

    async def test_changed_screen_is_not_swallowed_as_an_unread_number(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(unread_cube=True)
        def change(screen):
            if screen == "weapon_detail":
                model["screen"] = "unknown"
        hooks["scan"] = change
        result = await api["tick"]()
        self.assertEqual(result["result"], "failed")
        self.assertNotIn(("equipment_weapon", "accessories"), inputs)
        self.assertEqual(model["screen"], "unknown")

    async def test_bootstrap_takes_two_cube_observations_but_existing_rate_needs_one(self):
        for rate, expected in ((None, 2), (1.0, 1)):
            model, inputs, captures, observed, intents, hooks, ports, api = self.build()
            hooks["rate"] = rate
            result = await api["tick"]()
            self.assertEqual(result["result"], "complete")
            self.assertEqual(len([r for shot, r in observed if "cubes" in r]), expected)
            self.assertLess(model["now"], 100 + rules.DEADLINE)
            if rate is None:
                self.assertGreaterEqual(hooks["observed_at"][1] - hooks["observed_at"][0], 10)

    async def test_scan_can_evict_capture_metadata_without_losing_acquisition_time(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build()
        original_scan = ports.game["scan"]
        acquisition_times = []

        async def scan_with_concurrent_captures(shot, force):
            acquisition_times.append(ports.capture_time(shot))
            # Model the debug stream acquiring four frames while OCR runs.
            model["now"] += .1
            for _ in range(4):
                await ports.capture(max_age=0)
            self.assertIsNone(ports.capture_time(shot))
            return await original_scan(shot, force)

        ports.game["scan"] = scan_with_concurrent_captures
        result = await api["tick"]()
        self.assertEqual(result["result"], "complete")
        self.assertEqual(hooks["observed_at"], acquisition_times)
        self.assertTrue(all(at is not None for at in acquisition_times))
        self.assertEqual(result["read"]["cubes"], acquisition_times[1])
        self.assertEqual(result["read"]["weapon_l3"], acquisition_times[2])
        self.assertEqual(result["read"]["accessory_l3"], acquisition_times[3])

    async def test_missing_acquisition_time_cannot_report_a_complete_visit(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(verified=False)
        ports.capture_time = lambda shot: None
        result = await api["tick"](supervised=True)
        self.assertEqual(result["result"], "failed")
        self.assertFalse(result["supervised_verified"])
        self.assertEqual(result["read"], {})
        self.assertEqual(observed, [])

    async def test_user_pause_recovery_and_unconfigured_modes_never_navigate(self):
        for block in ("pause", "recovery", "unconfigured"):
            model, inputs, captures, observed, intents, hooks, ports, api = self.build()
            if block == "pause":
                model["input"] = {"monotonic": model["now"], "wall": model["now"]}
            elif block == "recovery":
                model["recovery"] = {"required": True}
            else:
                model["mode"]["configured"] = False
            await api["tick"]()
            self.assertEqual((inputs, captures), ([], []), block)

    async def test_default_unsupervised_timer_never_captures_or_navigates(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(verified=False)
        state = await api["tick"]()
        self.assertEqual(state["result"], "pending_supervision")
        self.assertFalse(state["supervised_verified"])
        self.assertEqual((inputs, captures), ([], []))

    async def test_successful_or_partial_supervised_return_arms_only_future_visits(self):
        for partial in (False, True):
            model, inputs, captures, observed, intents, hooks, ports, api = self.build(verified=False, unread_l3=partial)
            state = await api["tick"](supervised=True)
            self.assertEqual(state["result"], "partial" if partial else "complete")
            self.assertTrue(state["supervised_verified"])
            self.assertEqual(model["screen"], "soul_weapon")
            self.assertTrue(ports.store.sections["resource_refresh"]()["supervised_verified"])
            before = list(inputs)
            await api["tick"]()
            self.assertEqual(inputs, before, "first success does not bypass the interval")

    async def test_failed_or_interrupted_supervision_does_not_arm_automation(self):
        for failure in ("changed", "input"):
            model, inputs, captures, observed, intents, hooks, ports, api = self.build(verified=False)
            def stop(source, action):
                if failure == "input":
                    model["input"] = {"monotonic": model["now"] + .001, "wall": model["now"]}
                else:
                    model["screen"] = "unknown"
            hooks["input"] = stop
            state = await api["tick"](supervised=True)
            self.assertIn(state["result"], ("failed", "interrupted"))
            self.assertFalse(state["supervised_verified"])
            before = list(inputs)
            await api["tick"]()
            self.assertEqual(inputs, before)

    async def test_cancelled_supervision_does_not_arm_automation(self):
        model, inputs, captures, observed, intents, hooks, ports, api = self.build(verified=False)
        hooks["input"] = lambda *args: api["cancel"]()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.create_task(api["tick"](supervised=True))
        self.assertFalse(api["state"]()["supervised_verified"])
        self.assertIsNone(ports.lease.state())


if __name__ == "__main__":
    unittest.main()
