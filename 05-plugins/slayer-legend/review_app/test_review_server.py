import importlib.util
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from aiohttp.test_utils import AioHTTPTestCase

SPEC = importlib.util.spec_from_file_location("review_server", Path(__file__).with_name("review_server.py"))
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)
CAPTURE = "a" * 32
NODE = f"manual:{CAPTURE}:before"


class ReviewAPI(AioHTTPTestCase):
    async def get_application(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.manual = self.data / "manual-clicks"
        self.manual.mkdir(parents=True)
        self.trace = {"version": 1, "nodes": [{"id": 7, "screen": "battle", "thumb": "a" * 312, "private": "do-not-publish"}],
                      "edges": [{"from": 7, "to": 7, "x": .2, "y": .3, "kind": "swipe", "x2": .2, "y2": .8}]}
        (self.data / "trace.json").write_text(json.dumps(self.trace))
        self.entry = {"id": CAPTURE, "kind": "vertical", "before": "battle", "after": "menu", "capture_status": "complete",
                      "rect": [.1, .2, .3, .8], "tap": {"kind": "swipe", "x": .2, "y": .3, "end": {"x": .2, "y": .8}},
                      "private": "do-not-publish"}
        (self.manual / f"{CAPTURE}.json").write_text(json.dumps(self.entry))
        (self.manual / f"{CAPTURE}-before.png").write_bytes(b"\x89PNG\r\n\x1a\nunit-test-image")
        (self.data / "screenshots").mkdir()
        (self.data / "screenshots" / "battle.png").write_bytes(b"\x89PNG\r\n\x1a\narchived-image")
        self.feedback = self.root / "review" / "feedback.json"
        self.static = self.root / "static"
        self.static.mkdir()
        (self.static / "index.html").write_text("<!doctype html><title>Review</title>")
        self.evidence = server.Evidence(self.data, self.feedback, self.static)
        return server.make_app(self.evidence)

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self.temporary.cleanup()

    async def test_graph_preserves_actual_edges_and_distinguishes_missing_full_images(self):
        response = await self.client.get("/api/graph")
        self.assertEqual(response.status, 200)
        graph = await response.json()
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertIsNone(nodes["trace:7"]["image"])
        self.assertEqual(nodes["trace:7"]["thumbnail"]["pixels"], "a" * 312)
        self.assertEqual(nodes[NODE]["regions"][0]["kind"], "vertical")
        self.assertIsNone(nodes[f"manual:{CAPTURE}:after"]["image"])
        self.assertIn("example:battle", nodes)
        manual_edge = next(edge for edge in graph["edges"] if edge["source"] == "manual")
        self.assertEqual(manual_edge["end"], {"x": .2, "y": .8})
        self.assertNotIn("do-not-publish", json.dumps(graph))

    async def test_missing_images_and_traversal_are_never_served(self):
        self.assertEqual((await self.client.get(f"/api/image/{NODE}")).status, 200)
        self.assertEqual((await self.client.get("/api/image/example:battle")).status, 200)
        for path in (f"/api/image/manual:{CAPTURE}:after", "/api/image/../../trace.json",
                     "/api/image/example:%2e%2e%2ftrace", "/review_server.py", "/api/image/trace:7"):
            self.assertEqual((await self.client.get(path)).status, 404, path)
        outside = self.root / "private.png"
        outside.write_bytes(b"private")
        (self.manual / f"{CAPTURE}-before.png").unlink()
        (self.manual / f"{CAPTURE}-before.png").symlink_to(outside)
        self.assertEqual((await self.client.get(f"/api/image/{NODE}")).status, 404)

    async def test_feedback_is_atomic_separate_and_survives_reload(self):
        old_graph = (self.data / "trace.json").read_bytes()
        old_manual = (self.manual / f"{CAPTURE}.json").read_bytes()
        payload = {"nodeId": NODE, "text": "This is the battle screen", "correctScreen": "battle"}
        response = await self.client.post("/api/feedback", json=payload)
        self.assertEqual(response.status, 201)
        saved = await response.json()
        reloaded = server.Evidence(self.data, self.feedback)
        self.assertEqual(reloaded.feedback(), [saved])
        self.assertEqual(self.feedback.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.data / "trace.json").read_bytes(), old_graph)
        self.assertEqual((self.manual / f"{CAPTURE}.json").read_bytes(), old_manual)
        self.assertEqual(list(self.feedback.parent.glob(".review-feedback-*")), [])

    async def test_feedback_rejects_cross_origin_non_json_unknown_ids_and_large_bodies(self):
        payload = {"nodeId": NODE, "text": "correction"}
        self.assertEqual((await self.client.post("/api/feedback", json=payload, headers={"Origin": "https://other.invalid"})).status, 403)
        self.assertEqual((await self.client.post("/api/feedback", data=json.dumps(payload))).status, 415)
        self.assertEqual((await self.client.post("/api/feedback", json={**payload, "nodeId": "../../private"})).status, 400)
        self.assertEqual((await self.client.post("/api/feedback", json={**payload, "text": "x" * 20000})).status, 413)
        self.assertEqual((await self.client.put("/api/feedback", json=payload)).status, 405)

    async def test_corrupted_feedback_is_not_overwritten(self):
        self.feedback.parent.mkdir()
        self.feedback.write_text("broken original")
        response = await self.client.post("/api/feedback", json={"nodeId": NODE, "text": "new"})
        self.assertEqual(response.status, 503)
        self.assertEqual(self.feedback.read_text(), "broken original")

    async def test_reviewed_example_does_not_invent_a_graph_transition(self):
        ledger = self.root / "ledger.json"
        ledger.write_text(json.dumps({"items": {"example:battle": {"status": "processed", "before": {
            "nodeId": "example:battle", "screen": "battle", "status": "processed", "reason": "current_calibrated_reader"}}}}))
        self.evidence.ledger_path = ledger
        graph = await (await self.client.get("/api/graph")).json()
        node = next(node for node in graph["nodes"] if node["id"] == "example:battle")
        self.assertEqual(node["review"]["status"], "processed")
        self.assertFalse(any(edge["from"] == node["id"] or edge["to"] == node["id"] for edge in graph["edges"]))

    async def test_annotation_types_never_promote_actions_or_unknown_evidence_to_navigation(self):
        for kind in ("action", "forbidden", "scannable", "not-a-supported-type"):
            with self.subTest(kind=kind):
                (self.manual / f"{CAPTURE}.json").write_text(json.dumps({**self.entry, "kind": kind}))
                graph = await (await self.client.get("/api/graph")).json()
                self.assertFalse(any(edge["source"] == "manual" for edge in graph["edges"]))
                node = next(node for node in graph["nodes"] if node["id"] == NODE)
                self.assertEqual(node["annotation"], kind if kind != "not-a-supported-type" else "unknown")

    async def test_declared_graph_is_separate_and_only_explicit_safe_routes_are_added(self):
        plugin = self.root / "plugin"
        plugin.mkdir()
        (plugin / "navigation.json").write_text(json.dumps({"screens": {
            "battle": {"name": "Battle", "moves": [
                {"id": "menu", "semantic_kind": "navigation", "to": "menu", "tap": [.2, .3]},
                {"id": "action", "semantic_kind": "action", "to": "menu", "tap": [.3, .3]},
                {"id": "forbidden", "semantic_kind": "navigation", "to": "menu", "tap": [.4, .3], "forbidden": True},
                {"id": "self", "semantic_kind": "navigation", "to": "battle", "tap": [.5, .3]}]},
            "menu": {"name": "Menu", "moves": []}}}))
        (plugin / "screen_registry.json").write_text(json.dumps({"screens": {
            "battle": {"example": "screenshots/battle.png"}}, "tree": {"battle": {"scroll": [
                {"measured": True, "direction": "vertical", "gesture": [.5, .8, .5, .4], "captures": ["battle_scroll.png"]}]}}}))
        (self.data / "screenshots" / "battle_scroll.png").write_bytes(b"actual-archived-frame")
        self.evidence.plugin_dir = plugin
        graph = await (await self.client.get("/api/graph")).json()
        nodes = {node["id"]: node for node in graph["nodes"]}
        battle = nodes["screen:battle"]
        self.assertEqual(battle["source"], "configured")
        self.assertEqual(battle["status"], "configured_unverified")
        self.assertEqual(battle["representativeNodeId"], "example:battle")
        declared = [edge for edge in graph["edges"] if edge["source"] == "configured"]
        self.assertEqual({edge["id"] for edge in declared}, {"configured:battle:menu", "configured-scroll:battle:0:0"})
        self.assertTrue(all(edge["status"] == "to_verify" for edge in declared))
        self.assertEqual(nodes["screen:menu"]["image"], None)
        payload = {"nodeId": "screen:battle", "edgeId": "configured:battle:menu", "text": "Review declared route"}
        self.assertEqual((await self.client.post("/api/feedback", json=payload)).status, 201)

    async def test_zone_removal_is_idempotent_advisory_and_preserves_recorded_routes(self):
        before = await (await self.client.get("/api/graph")).json()
        payload = {"nodeId": NODE, "zoneId": "region:" + CAPTURE, "screen": "battle", "operation": "remove",
                   "kind": "vertical", "rect": [.1, .2, .3, .8]}
        response = await self.client.post("/api/zone-feedback", json=payload)
        self.assertEqual(response.status, 201)
        item = await response.json()
        self.assertTrue(item["pending"])
        duplicate = await (await self.client.post("/api/zone-feedback", json=payload)).json()
        self.assertEqual(item["id"], duplicate["id"])
        graph = await (await self.client.get("/api/graph")).json()
        node = next(node for node in graph["nodes"] if node["id"] == NODE)
        zone = next(region for region in node["regions"] if region["id"] == payload["zoneId"])
        self.assertEqual(zone["source"], "recorded")
        self.assertTrue(zone["user"])
        self.assertTrue(zone["removedProposal"])
        self.assertEqual(len(graph["edges"]), len(before["edges"]))
        self.assertEqual(len((await (await self.client.get("/api/zone-feedback")).json())["items"]), 1)

    async def test_zone_add_and_revision_are_shared_and_never_change_route_geometry(self):
        old = await (await self.client.get("/api/revision")).json()
        payload = {"nodeId": NODE, "screen": "battle", "operation": "add", "kind": "forbidden", "rect": [.4, .4, .5, .5]}
        response = await self.client.post("/api/zone-feedback", json=payload)
        self.assertEqual(response.status, 201)
        item = await response.json()
        revision = await (await self.client.get("/api/revision")).json()
        self.assertNotEqual(revision["revision"], old["revision"])
        self.assertEqual(revision, await (await self.client.get("/api/revision")).json())
        graph = await (await self.client.get("/api/graph")).json()
        node = next(node for node in graph["nodes"] if node["id"] == NODE)
        zone = next(region for region in node["regions"] if region["id"] == item["zoneId"])
        self.assertEqual((zone["source"], zone["proposal"], zone["user"]), ("user_feedback", "add", True))
        self.assertFalse(item["gestureAuthority"])
        self.assertEqual(self.evidence.zones.read()[0]["id"], item["id"])

    async def test_unknown_zone_proposals_are_scoped_to_one_evidence_node(self):
        (self.manual / f"{CAPTURE}.json").write_text(json.dumps({**self.entry, "before": "unknown", "after": "unknown"}))
        payload = {"nodeId": NODE, "screen": "unknown", "operation": "add", "kind": "detection", "rect": [.4, .4, .5, .5]}
        self.assertEqual((await self.client.post("/api/zone-feedback", json=payload)).status, 201)
        graph = await (await self.client.get("/api/graph")).json()
        before = next(node for node in graph["nodes"] if node["id"] == NODE)
        after = next(node for node in graph["nodes"] if node["id"] == f"manual:{CAPTURE}:after")
        self.assertTrue(any(region.get("proposal") == "add" for region in before["regions"]))
        self.assertFalse(any(region.get("proposal") == "add" for region in after["regions"]))
        self.assertEqual(self.evidence.zones.read_annotations(self.data), [])
        (self.data / "screenshots" / "unclassified_variant.png").write_bytes(b"archived-png")
        payload.update(nodeId="example:unclassified_variant", screen="unclassified_variant")
        response = await self.client.post("/api/zone-feedback", json=payload)
        self.assertEqual(response.status, 201)
        self.assertEqual((await response.json())["scope"], "node")

    async def test_zone_geometry_and_shared_style_static_paths_are_strict(self):
        payload = {"nodeId": NODE, "zoneId": "region:" + CAPTURE, "screen": "battle", "operation": "remove",
                   "kind": "vertical", "rect": [.1, .2, .9, .9]}
        self.assertEqual((await self.client.post("/api/zone-feedback", json=payload)).status, 400)
        self.assertEqual((await self.client.post("/api/zone-feedback", json={**payload, "operation": "add", "rect": [0, 0, 2, 2]})).status, 400)
        self.assertEqual((await self.client.get("/page_zone_style.js")).status, 200)
        self.assertEqual((await self.client.get("/zone_feedback.py")).status, 404)


class ReviewerLifetime(unittest.IsolatedAsyncioTestCase):
    async def test_service_shutdown_kills_and_drains_its_passive_reviewer_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            processor = root / "processor.py"
            marker = root / "ledger.json.started"
            processor.write_text("import os,sys,time\nfrom pathlib import Path\n"
                                 "Path(sys.argv[sys.argv.index('--ledger')+1]+'.started').write_text(str(os.getpid()))\n"
                                 "time.sleep(60)\n")
            evidence = server.Evidence(root, root / "feedback.json", ledger_path=root / "ledger.json", processor=processor)
            task = asyncio.create_task(evidence.review_loop())
            try:
                for _ in range(100):
                    if marker.exists():
                        break
                    await asyncio.sleep(.01)
                self.assertTrue(marker.exists(), "bounded reviewer child should have started")
                pid = int(marker.read_text())
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
