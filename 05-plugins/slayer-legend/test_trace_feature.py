"""Persistent typed annotations, with no game actions available to the feature."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feature = load("annotation_feature", "features/trace.py")
graphs = load("annotation_graph", "trace.py")


class Annotations(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tasks = []
        self.release = asyncio.Event()
        self.visible = True
        self.frames = []
        self.slept = []
        self.captures = 0

        async def capture(**kwargs):
            self.captures += 1
            return self.frames.pop(0) if self.frames else (12, 26, bytes(12 * 26 * 3))

        async def focused():
            return self.visible

        async def analyse(fn, *args):
            return fn(*args)

        async def sleep(seconds):
            await self.release.wait()
            self.slept.append(seconds)

        def spawn(coro):
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task

        self.ports = NS(data_path=lambda name: str(Path(self.temp.name) / name),
                        clock=NS(wall=lambda: 100, sleep=sleep), capture=capture, focused=focused,
                        analyse=analyse, spawn=spawn, respond=lambda value, status=200: (value, status),
                        log=lambda *args: None, t=lambda value, **kwargs: value)
        self.restart()

    def restart(self):
        api = feature.trace(self.ports, NS(classify=lambda shot: "battle", look=lambda shot: {"screen": "battle", "overlays": [], "plain": True, "unneeded": "omitted"}), graphs,
                            NS(png=lambda shot: b"PNG"))
        self.routes = {(method, path): handler for method, path, handler in api["routes"]}

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def call(self, method, path, body=None):
        async def request_json():
            return body
        return await self.routes[method, path](NS(json=request_json))

    async def advance(self):
        for _ in range(200):
            await asyncio.sleep(0)

    async def test_all_five_types_survive_restart_with_both_private_captures(self):
        for kind in feature.ANNOTATION_KINDS:
            self.release.clear()
            armed, status = await self.call("POST", "/trace/arm", {"kind": kind})
            self.assertEqual(status, 200)
            root = Path(self.temp.name) / "manual-clicks"
            before = root / (armed["id"] + "-before.png")
            self.assertEqual(before.stat().st_mode & 0o777, 0o600)
            self.assertEqual((await self.call("GET", "/trace"))[0]["armed"]["kind"], kind)
            tap = {"x": .2, "y": .3, "kind": "tap"}
            if kind in ("vertical", "horizontal", "scannable"):
                tap.update(kind="swipe", end={"x": .2 if kind == "vertical" else .7,
                                              "y": .8 if kind in ("vertical", "scannable") else .3})
            self.assertEqual((await self.call("POST", "/trace", tap))[1], 202)
            await self.advance()
            metadata = root / (armed["id"] + ".json")
            self.assertEqual(json.loads(metadata.read_text())["capture_status"], "pending")
            self.release.set()
            await self.advance()
            record = json.loads(metadata.read_text())
            self.assertEqual(record["kind"], kind)
            self.assertEqual(record["tap"], tap)
            self.assertEqual(record["before_scan"], {"screen": "battle", "overlays": [], "plain": True})
            self.assertEqual(record["after_scan"], record["before_scan"])
            if kind == "scannable":
                self.assertEqual(record["rect"], [.2, .3, .7, .8])
            self.assertEqual(record["capture_status"], "complete")
        self.assertEqual(sum(edge["count"] for edge in (await self.call("GET", "/trace/graph"))[0]["edges"]), 1)
        self.restart()
        clicks = (await self.call("GET", "/trace/manual"))[0]["clicks"]
        self.assertEqual({item["kind"] for item in clicks}, set(feature.ANNOTATION_KINDS))
        self.assertTrue(all(item["capture_status"] == "complete" and item["before_url"] and item["after_url"]
                            for item in clicks))

    async def test_restart_preserves_before_and_reports_interruption(self):
        await self.call("POST", "/trace/arm", {"kind": "forbidden"})
        self.restart()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["capture_status"], "error")
        self.assertIn("before_url", item)
        self.assertNotIn("after_url", item)

    async def test_game_leaving_keeps_annotation_and_before_image(self):
        await self.call("POST", "/trace/arm", {"kind": "navigation"})
        await self.call("POST", "/trace", {"x": .4, "y": .5})
        await self.advance()
        self.visible = False
        self.release.set()
        await self.advance()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["capture_status"], "error")
        self.assertEqual(item["tap"]["x"], .4)
        self.assertNotIn("after_url", item)

    async def test_invalid_kind_cannot_arm_or_store(self):
        for body in ({"kind": "purchase"}, [], None):
            self.assertEqual((await self.call("POST", "/trace/arm", body))[1], 400)
        self.assertEqual((await self.call("GET", "/trace/manual"))[0]["clicks"], [])

    async def test_navigation_stops_after_two_matching_changed_frames(self):
        await self.call("POST", "/trace/arm", {"kind": "navigation"})
        white = (12, 26, bytes([255]) * (12 * 26 * 3))
        self.frames = [white, white]
        await self.call("POST", "/trace", {"x": .4, "y": .5})
        await self.advance()
        self.release.set()
        await self.advance()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["capture_status"], "complete")
        self.assertTrue(item["after_stable"])
        self.assertEqual(self.captures, 3)
        self.assertLess(sum(self.slept), .5)

    async def test_slow_navigation_waits_past_early_unchanged_frames(self):
        await self.call("POST", "/trace/arm", {"kind": "navigation"})
        black = (12, 26, bytes(12 * 26 * 3))
        white = (12, 26, bytes([255]) * (12 * 26 * 3))
        self.frames = [black] * 7 + [white, white]
        await self.call("POST", "/trace", {"x": .4, "y": .5})
        await self.advance()
        self.release.set()
        await self.advance()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["capture_status"], "complete")
        self.assertTrue(item["after_stable"])
        self.assertEqual(self.captures, 10)
        self.assertGreater(sum(self.slept), 1)
        self.assertLess(sum(self.slept), 2)

    async def test_cancel_disarms_only_the_requested_annotation(self):
        armed, _ = await self.call("POST", "/trace/arm", {"kind": "navigation"})
        await self.call("POST", "/trace/cancel", {"id": "0" * 32})
        self.assertEqual((await self.call("GET", "/trace"))[0]["armed"]["id"], armed["id"])
        await self.call("POST", "/trace/cancel", {"id": armed["id"]})
        self.assertIsNone((await self.call("GET", "/trace"))[0]["armed"])
        await self.call("POST", "/trace", {"x": .4, "y": .5})
        await self.advance()
        self.release.set()
        await self.advance()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["error"], "annotation cancelled")
        self.assertEqual(item["capture_status"], "cancelled")
        self.assertNotIn("tap", item)
        self.assertNotIn("after_url", item)

    async def test_cancel_pending_capture_stops_its_after_task(self):
        armed, _ = await self.call("POST", "/trace/arm", {"kind": "forbidden"})
        await self.call("POST", "/trace", {"x": .4, "y": .5})
        await self.advance()
        await self.call("POST", "/trace/cancel", {"id": armed["id"]})
        self.release.set()
        await self.advance()
        self.assertIsNone((await self.call("GET", "/trace"))[0]["pending"])
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["error"], "annotation cancelled")
        self.assertEqual(item["capture_status"], "cancelled")
        self.assertNotIn("after_url", item)
        for body in ({}, [], {"id": "bad"}):
            self.assertEqual((await self.call("POST", "/trace/cancel", body))[1], 400)

    async def test_scannable_requires_area_and_normalises_reverse_corners(self):
        armed, _ = await self.call("POST", "/trace/arm", {"kind": "scannable"})
        for tap in ({"x": .8, "y": .8},
                    {"x": .8, "y": .8, "kind": "swipe", "end": {"x": .2, "y": .8}}):
            self.assertEqual((await self.call("POST", "/trace", tap))[1], 400)
        self.assertEqual((await self.call("GET", "/trace"))[0]["armed"]["id"], armed["id"])
        tap = {"x": .8, "y": .8, "kind": "swipe", "end": {"x": .2, "y": .2}}
        self.assertEqual((await self.call("POST", "/trace", tap))[1], 202)
        await self.advance()
        self.release.set()
        await self.advance()
        item = (await self.call("GET", "/trace/manual"))[0]["clicks"][0]
        self.assertEqual(item["rect"], [.2, .2, .8, .8])
        self.assertEqual(item["capture_status"], "complete")
        self.assertEqual((await self.call("GET", "/trace/graph"))[0]["edges"], [])
