"""Actual lease/action ports under interrupted and replaced mode transactions.
All input goes to an in-memory adb stand-in; no device is contacted.
"""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location(f"ownership_{name.replace('/', '_')}", HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ports_module = load("features/ports")
mode_feature = load("features/mode")
setup_feature = load("features/mode_setup")
mode_rules = load("features/mode_rules")
nav = load("nav")
SHOT = (480, 1040, b"")
POINT = (0.41, 0.966)


class Ownership(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.inputs = []
        self.last_input = None

        async def adb(*args, **kwargs):
            self.inputs.append(args)
            return 0, ""

        async def analyse(fn, *args):
            return fn(*args)

        async def notify(*args, **kwargs):
            pass

        context = NS(id="slayer-legend", adb=adb, analyse=analyse, notify=notify,
                     json=lambda value, **kwargs: value, last_input=lambda: self.last_input,
                     log=lambda *args, **kwargs: None)
        self.ports = ports_module.build(context, nav)

    async def tap(self):
        await self.ports.tap(SHOT, "battle", "menu_equipment", POINT)

    async def test_same_named_transactions_exclude_each_other_and_external_release(self):
        async with self.ports.leased("stage_change", "first", 60):
            async def contender():
                with self.assertRaises(self.ports.Busy):
                    async with self.ports.leased("stage_change", "second", 60):
                        self.fail("same holder name must not confer ownership")
            await asyncio.create_task(contender())
            self.assertFalse(self.ports.lease.release("stage_change"))
            self.assertIsNotNone(self.ports.lease.take("stage_change", "outside renewal", 60, user=True))
            await self.tap()
        self.assertEqual(len(self.inputs), 1)
        self.assertIsNone(self.ports.lease.state())

    async def test_expired_owner_cannot_use_or_release_successor_lease(self):
        entered = asyncio.Event()
        finish_old = asyncio.Event()
        old_finished = asyncio.Event()

        async def old():
            async with self.ports.leased("stage_change", "old", 60):
                entered.set()
                await finish_old.wait()
                with self.assertRaises(self.ports.Busy):
                    await self.tap()
            old_finished.set()

        task = asyncio.create_task(old())
        await entered.wait()
        self.ports.lease.held["until"] = 0
        async with self.ports.leased("stage_change", "successor", 60):
            finish_old.set()
            await old_finished.wait()
            self.assertEqual(self.ports.lease.state()["reason"], "successor")
            await self.tap()
        await task
        self.assertEqual(len(self.inputs), 1)

    async def test_child_task_cannot_inherit_parent_action_authority(self):
        async with self.ports.leased("stage_change", "parent", 60):
            async def inherited():
                with self.assertRaises(self.ports.Busy):
                    await self.tap()
            await asyncio.create_task(inherited())
            await self.tap()
        self.assertEqual(len(self.inputs), 1)

    async def test_user_input_stops_owner_and_cannot_be_hidden_by_token_renewal(self):
        async with self.ports.leased("stage_change", "running", 60):
            held = self.ports.lease.held
            self.last_input = {"monotonic": held["mark"] + .001, "wall": self.ports.clock.wall()}
            self.assertIsNone(self.ports.lease.take("stage_change", "renewed", 60, pause=False,
                                                 owner=held["owner"]))
            with self.assertRaises(self.ports.Busy):
                await self.tap()
        self.assertEqual(self.inputs, [])

    async def test_external_holder_api_still_renews_and_releases_by_name(self):
        self.assertIsNone(self.ports.lease.take("agent", "outside", 60, user=True))
        self.assertIsNone(self.ports.lease.take("agent", "renewed", 120, user=True))
        self.assertTrue(self.ports.lease.release("agent"))

    async def test_mode_coalesces_requests_until_cancelled_transaction_cleanup_finishes(self):
        started = asyncio.Event()
        cleanup = asyncio.Event()
        allow_cleanup = asyncio.Event()
        latest_started = asyncio.Event()
        calls = []
        order = []
        tasks = []
        callbacks = []
        parts = {"mpw18": {"stage": 920, "preset": "III"},
                 "mpw4": {"stage": 931, "preset": "III"}}

        async def farm(stage, preset, name, highest=None):
            async with self.ports.leased("stage_change", name, 60):
                calls.append((name, stage))
                if len(calls) == 1:
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        order.append("cleanup began")
                        cleanup.set()
                        await allow_cleanup.wait()
                        await self.tap()
                        order.append("cleanup finished")
                else:
                    order.append("successor began")
                    await self.tap()
                    latest_started.set()
            return {"result": "done", "text_t": None}

        def spawn(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task

        self.ports.spawn = spawn
        loadouts = {"loadout": lambda name: dict(parts[name]), "stage": lambda name: parts[name]["stage"],
                    "set_stage": lambda name, value: parts[name].update(stage=value),
                    "adopt_stage": lambda *args: None, "on_change": callbacks.append}
        mines = {"state": lambda: {"enabled": False, "state": "off", "floor": None, "area": None},
                 "start": lambda *args: None, "stop": lambda: None, "set_until": lambda *args: None,
                 "ended": False}
        values = NS(time_or_none=lambda v: v, number_or_none=lambda v, top: v)
        part = mode_feature.mode(self.ports, mode_rules, None, values, mines, None,
                                 NS(fresh=lambda: {"gold": None}), loadouts, {"farm": farm}, setup_feature.mode_setup)
        refresh = {"active": False, "intention": {"kind": "resource_refresh", "destination": "soul_weapon"}}
        part["api"]["resource_refresh_by"](lambda: refresh)
        self.assertIsNone(part["api"]["state"]()["intention"])
        refresh["active"] = True
        self.assertEqual(part["api"]["state"]()["intention"]["kind"], "resource_refresh")
        refresh["active"] = False
        post = next(fn for method, path, fn in part["routes"] if (method, path) == ("POST", "/mode"))

        class Request:
            async def json(self):
                return {"mode": "mpw4", "stage4": 931}

        try:
            await post(Request())
            await asyncio.wait_for(started.wait(), 1)
            intent = part["api"]["state"]()["intention"]
            self.assertEqual(intent["kind"], "apply_loadout")
            self.assertEqual(intent["destination"], "battle")
            self.assertIsNone(intent["route"])
            self.assertFalse(intent["route_known"], "no full path was computed")
            self.assertNotIn("owner", intent, "internal transaction token is not public JSON")
            changed = callbacks[0]
            before = dict(parts["mpw4"])
            parts["mpw4"]["stage"] = 932
            changed("mpw4", before, dict(parts["mpw4"]))
            await asyncio.wait_for(cleanup.wait(), 1)
            # Two further changes while cleanup is awaiting must neither
            # cancel it again nor start their obsolete successors.
            for stage in (933, 934):
                before = dict(parts["mpw4"])
                parts["mpw4"]["stage"] = stage
                changed("mpw4", before, dict(parts["mpw4"]))
            for _ in range(5):
                await asyncio.sleep(0)
            self.assertEqual(calls, [("mpw4", 931)])
            self.assertEqual(self.inputs, [])
            allow_cleanup.set()
            await asyncio.wait_for(latest_started.wait(), 1)
            self.assertEqual(calls, [("mpw4", 931), ("mpw4", 934)])
            self.assertEqual(order, ["cleanup began", "cleanup finished", "successor began"])
            self.assertEqual(len(self.inputs), 2)
            self.assertIsNone(self.ports.lease.state())
            # A queued transaction can be superseded before its coroutine
            # gets its first turn. Its cancelled wrapper must not launch it.
            latest_started.clear()
            for stage in (935, 936):
                before = dict(parts["mpw4"])
                parts["mpw4"]["stage"] = stage
                changed("mpw4", before, dict(parts["mpw4"]))
            await asyncio.wait_for(latest_started.wait(), 1)
            self.assertEqual(calls, [("mpw4", 931), ("mpw4", 934), ("mpw4", 936)])
        finally:
            allow_cleanup.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
