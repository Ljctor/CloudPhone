import importlib.util
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

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

    async def test_integrated_scroll_history_is_retained_with_one_canonical_viewport(self):
        tree = json.loads((Path(__file__).parents[1] / 'screen_registry.json').read_text())['tree']
        key = 'manual:bbf78faa6af8402d89f169c29b83d024'
        marker = self.evidence.zones.mark_integrated(key, 'soul_weapon', tree, 'abcdef1', 'a' * 64)
        nodes = [{'id': key + ':before', 'screen': 'soul_weapon', 'captureId': key[7:],
                  'regions': [{'id': key, 'kind': 'vertical', 'source': 'recorded', 'rect': tree['soul_weapon']['scroll'][0]['rect']}]}]
        edges = [{'id': 'manual-edge:' + key[7:], 'from': key + ':before', 'to': key + ':after',
                  'kind': 'swipe', 'source': 'manual'}]
        self.evidence.apply_zones(nodes, edges)
        permanent = [r for r in nodes[0]['regions'] if r['source'] == 'registered_scroll_viewport']
        self.assertEqual(len(permanent), 1)
        self.assertEqual(permanent[0]['kind'], 'vertical')
        self.assertEqual(edges[0]['integration'], marker)
        self.assertEqual(nodes[0]['regions'][0]['integration'], marker)
        self.assertEqual(len(edges), 1, 'historical edge is annotated, never deleted')
        self.evidence.zones.append({'nodeId': key + ':before', 'zoneId': key, 'screen': 'soul_weapon',
            'operation': 'remove', 'kind': 'vertical', 'rect': permanent[0]['rect']}, {'soul_weapon'})
        self.evidence.apply_zones(nodes, edges)
        original = next(r for r in nodes[0]['regions'] if r['id'] == key)
        self.assertTrue(original['removedProposal'])
        self.assertNotIn('integration', original, 'pending removal cannot be hidden by integration')
        edges[0]['from'] = nodes[0]['id']
        self.evidence.zones.append({'nodeId': key + ':before', 'zoneId': 'edge:' + edges[0]['id'], 'screen': 'soul_weapon',
            'operation': 'remove', 'kind': 'vertical', 'rect': permanent[0]['rect']}, {'soul_weapon'})
        self.evidence.apply_zones(nodes, edges)
        self.assertTrue(edges[0]['removedProposal'])
        self.assertNotIn('integration', edges[0], 'pending edge removal stays visible')



    async def test_graph_generated_manual_edge_uses_exact_integrated_capture_origin(self):
        capture = '80a60ff702964e3fa33ca2f28eea23fc'
        key = 'manual:' + capture
        tree = json.loads((Path(__file__).parents[1] / 'screen_registry.json').read_text())['tree']
        entry = {**self.entry, 'id': capture, 'before': 'quest_repeat', 'after': 'quest_repeat',
                 'rect': [.08053691275167785, .25219639031461966, .587248322147651, .9328165453533793]}
        (self.manual / (capture + '.json')).write_text(json.dumps(entry))
        self.evidence.zones.mark_integrated(key, 'quest_repeat', tree, 'abcdef1', 'a' * 64)
        graph = self.evidence.graph()
        edge = next(edge for edge in graph['edges'] if edge['id'] == 'manual-edge:' + capture)
        self.assertEqual(edge['from'], key + ':before')
        self.assertEqual(edge['to'], key + ':after')
        self.assertEqual(edge['integration']['annotation'], key)
        self.assertEqual(edge['source'], 'manual')
        self.assertEqual(edge['kind'], 'swipe', 'history remains intact; rendering consumes the integration flag')
        for foreign in ({**edge, 'source': 'trace'}, {**edge, 'to': NODE},
                        {**edge, 'id': 'manual-edge:' + CAPTURE}):
            foreign.pop('integration', None)
            self.evidence.apply_zones(graph['nodes'], [foreign])
            self.assertNotIn('integration', foreign, 'no association across another source/capture')
        self.evidence.zones.append({'nodeId': key + ':before', 'zoneId': 'edge:' + edge['id'],
            'screen': 'quest_repeat', 'operation': 'remove', 'kind': 'vertical',
            'rect': entry['rect']}, {'quest_repeat'})
        refreshed = self.evidence.graph()
        pending = next(e for e in refreshed['edges'] if e['id'] == edge['id'])
        self.assertTrue(pending['removedProposal'])
        self.assertNotIn('integration', pending, 'pending removal remains visible through the real graph API')

    async def test_recording_url_comes_only_from_explicit_https_frontend_origins(self):
        response = await self.client.get("/api/recording-config")
        self.assertIsNone((await response.json())["secure_review_url"])
        self.evidence.frontend_origins = ("http://private.example:8100", "https://configured.example")
        response = await self.client.get("/api/recording-config", headers={"Origin": "http://private.example:8100"})
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://private.example:8100")
        self.assertEqual((await response.json())["secure_review_url"], "https://configured.example/navigation-review/")
        response = await self.client.get("/api/recording-config", headers={"Host": "untrusted.example"})
        self.assertEqual((await response.json())["secure_review_url"], "https://configured.example/navigation-review/")
        self.assertEqual((await self.client.get("/api/recording-config", headers={"Origin": "https://untrusted.example"})).status, 403)
        self.evidence.frontend_origins = ("http://private.example:8100",)
        self.assertIsNone((await (await self.client.get("/api/recording-config")).json())["secure_review_url"])

    async def test_measured_soul_button_bounds_are_shared_with_the_live_overlay(self):
        navigation = json.loads((Path(__file__).parents[1] / "navigation.json").read_text())
        for screen in ("soul_weapon", "soul_weapon_engraving"):
            spec = navigation["screens"][screen]
            regions = {region["id"]: region for region in self.evidence.configured_policy_regions(screen, spec)}
            for move in spec["moves"]:
                if "visual_rect" not in move:
                    continue
                region = regions["policy:" + move["id"]]
                self.assertEqual(region["rect"], move["visual_rect"])
                self.assertEqual(region["source"], "measured_control_bounds")
                self.assertFalse(region["gestureAuthority"])
                self.assertEqual(region["guard_rect"], move.get("area"))

    async def test_frontend_assets_and_api_are_available_under_https_proxy_prefix(self):
        source = Path(__file__).parent
        for filename in ("index.html", "app.js", "model.js", "style.css"):
            (self.static / filename).write_bytes((source / filename).read_bytes())
        parent = web.Application()
        parent.add_subapp("/navigation-review", server.make_app(self.evidence))
        async with TestClient(TestServer(parent)) as client:
            response = await client.get("/navigation-review/")
            html = await response.text()
            self.assertIn('href="./style.css"', html)
            self.assertIn('src="./app.js"', html)
            for asset in ("app.js", "style.css", "model.js", "page_oral_feedback.js", "page_zone_style.js"):
                self.assertEqual((await client.get("/navigation-review/" + asset)).status, 200, asset)
            graph = await (await client.get("/navigation-review/api/graph")).json()
            battle = next(node for node in graph["nodes"] if node["id"] == "example:battle")
            self.assertEqual((await client.get("/navigation-review" + battle["image"])).status, 200)
            self.assertEqual((await client.get("/navigation-review/api/recording-config")).status, 200)

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
        for kind in ("action", "forbidden", "scannable", "progression_value", "resource_value", "screen_identifier", "not-a-supported-type"):
            with self.subTest(kind=kind):
                (self.manual / f"{CAPTURE}.json").write_text(json.dumps({**self.entry, "kind": kind}))
                graph = await (await self.client.get("/api/graph")).json()
                self.assertFalse(any(edge["source"] == "manual" for edge in graph["edges"]))
                node = next(node for node in graph["nodes"] if node["id"] == NODE)
                self.assertEqual(node["annotation"], kind if kind != "not-a-supported-type" else "unknown")

    async def test_value_role_proposals_reload_without_navigation_authority(self):
        initial = await (await self.client.get("/api/graph")).json()
        node = next(node for node in initial["nodes"] if node["id"] == NODE)
        roles = ("progression_value", "resource_value", "screen_identifier")
        for kind in roles:
            body = {"nodeId": NODE, "screen": node["screen"], "operation": "add",
                    "kind": kind, "rect": [.1, .2, .3, .4]}
            response = await self.client.post("/api/zone-feedback", json=body)
            self.assertEqual(response.status, 201)
            self.assertIs((await response.json())["gestureAuthority"], False)
            for rect in (None, [.3, .2, .1, .4], [.1, .2, .1, .4], [True, .2, .3, .4]):
                self.assertEqual((await self.client.post("/api/zone-feedback", json={**body, "rect": rect})).status, 400)
        self.evidence.zones = server.zone_feedback.ZoneFeedback(self.feedback.parent)
        restored = await (await self.client.get("/api/graph")).json()
        node = next(node for node in restored["nodes"] if node["id"] == NODE)
        added = [region for region in node["regions"] if region.get("proposal") == "add"]
        self.assertEqual({region["kind"] for region in added}, set(roles))
        self.assertTrue(all(region["gestureAuthority"] is False for region in added))
        self.assertEqual(restored["edges"], initial["edges"])

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
                {"measured": True, "direction": "vertical", "rect": [.1,.3,.9,.9], "gesture": [.5, .8, .5, .4], "captures": ["battle_scroll.png"]}]}}}))
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

    async def test_forbidden_action_survives_api_reload_without_creating_edges(self):
        before = await (await self.client.get("/api/graph")).json()
        body = {"nodeId": NODE, "screen": "battle", "operation": "add", "kind": "action",
                "forbidden": True, "rect": [.4, .4, .5, .5]}
        response = await self.client.post("/api/zone-feedback", json=body)
        self.assertEqual(response.status, 201)
        saved = await response.json()
        self.assertEqual((saved["kind"], saved["forbidden"], saved["gestureAuthority"]), ("action", True, False))
        graph = await (await self.client.get("/api/graph")).json()
        node = next(node for node in graph["nodes"] if node["id"] == NODE)
        zone = next(region for region in node["regions"] if region["id"] == saved["zoneId"])
        self.assertEqual((zone["kind"], zone["forbidden"]), ("action", True))
        self.assertEqual(graph["edges"], before["edges"])
        self.assertEqual(self.evidence.zones.read()[0]["forbidden"], True)
        for value in (1, "true"):
            self.assertEqual((await self.client.post("/api/zone-feedback", json={**body, "forbidden": value})).status, 400)

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

    async def test_canonical_soul_policy_rejects_conflicting_image_and_uses_its_own_regions(self):
        plugin = self.root / "canonical-plugin"
        plugin.mkdir()
        (plugin / "navigation.json").write_text(json.dumps({"screens": {
            "soul_weapon": {"moves": [{"id": "breakdown", "forbidden": True, "area": [.66, .8, .97, .88]}]},
            "equipment_weapon": {"moves": [{"id": "accessories", "tap": [.3, .4]}]}}}))
        (plugin / "screen_registry.json").write_text(json.dumps({"screens": {
            "soul_weapon": {"example": "screenshots/soul_weapon.png", "status": "registered"},
            "equipment_weapon": {"status": "registered"}}}))
        (self.data / "screenshots" / "soul_weapon.png").write_bytes(b"mislabeled-archived-frame")
        ledger = self.root / "canonical-ledger.json"
        reviewed = {"items": {"example:soul_weapon": {"status": "ambiguous", "before": {
            "status": "processed", "screen": "equipment_weapon", "scan": {"screen": "battle", "overlays": ["equipment_weapon"]}}}}}
        ledger.write_text(json.dumps(reviewed))
        self.evidence.plugin_dir, self.evidence.ledger_path = plugin, ledger
        graph = await (await self.client.get("/api/graph")).json()
        soul = next(node for node in graph["nodes"] if node["id"] == "screen:soul_weapon")
        self.assertIsNone(soul["image"], "a calibrated conflicting identity cannot represent Soul Weapon")
        self.assertEqual({region["id"] for region in soul["regions"]}, {"policy:breakdown"})
        self.assertEqual(soul["regions"][0]["kind"], "action")
        self.assertTrue(soul["regions"][0]["forbidden"])
        reviewed["items"]["manual:" + CAPTURE] = {"status": "processed", "before": {
            "status": "processed", "screen": "soul_weapon", "scan": {"screen": "battle", "overlays": ["soul_weapon"]}}}
        ledger.write_text(json.dumps(reviewed))
        graph = await (await self.client.get("/api/graph")).json()
        soul = next(node for node in graph["nodes"] if node["id"] == "screen:soul_weapon")
        self.assertEqual(soul["representativeNodeId"], NODE)
        self.assertEqual(soul["status"], "configured")
        self.assertTrue(any(region["id"] == "policy:breakdown" for region in soul["regions"]))
        self.assertFalse(any(region["id"] == "policy:accessories" for region in soul["regions"]))

    async def test_variant_returns_require_the_matching_calibrated_visible_tab(self):
        registry = {"screens": {"character_promotion": {"kind": "overlay", "status": "registered"}}}
        move = {"id": "close_tab", "semantic_kind": "navigation", "to": "battle", "tap": [.073,.966],
                "needs": {"reduced_battle": True, "active_tab": "character_promotion", "required_overlay": "character_promotion"}}
        declared = {"character_promotion": {"moves": [move]}}
        battle = {"id": "screen:battle", "screen": "battle", "source": "configured", "image": "/api/image/example:battle", "scan": {"plain": True}}
        variant = {"id": "example:character_promotion_scroll_1", "screen": "character_promotion", "source": "example",
                   "image": "/api/image/example:character_promotion_scroll_1", "review": {"status": "processed"},
                   "scan": {"screen": "battle", "overlays": ["panel", "character_promotion"], "plain": False}}
        edges = []
        self.assertEqual(self.evidence.add_variant_returns([battle,variant], edges, registry, declared), 1)
        self.assertEqual(edges[0]["from"], variant["id"])
        self.assertEqual(edges[0]["to"], "screen:battle")
        self.assertEqual(edges[0]["status"], "to_verify")
        self.assertFalse(edges[0]["review"]["gestureAuthority"])
        for invalid in ({**variant, "review": {"status": "ambiguous"}},
                        {**variant, "screen": "character_growth"},
                        {**variant, "scan": {"screen":"battle", "overlays":["panel"], "plain":False}},
                        {**variant, "scan": {"screen":"battle", "overlays":["character_promotion","quest_panel"], "plain":False}}):
            self.assertEqual(self.evidence.add_variant_returns([battle, invalid], [], registry, declared), 0)
        self.assertEqual(self.evidence.add_variant_returns([dict(battle,scan={"plain":False}),variant], [], registry, declared), 0)
        self.assertEqual(self.evidence.add_variant_returns([battle,variant], [], registry,
                         {"character_promotion":{"moves":[dict(move, needs={"active_tab":"character_promotion"})]}}), 0)

    async def test_exact_removal_id_never_ghosts_another_policy_at_the_same_coordinates(self):
        plugin = self.root / "same-point-plugin"
        plugin.mkdir()
        (plugin / "navigation.json").write_text(json.dumps({"screens": {"quest_panel": {"moves": [
            {"id": "close", "semantic_kind": "navigation", "tap": [.5, .5]},
            {"id": "close_to_shop_event", "semantic_kind": "navigation", "tap": [.5, .5]}]}}}))
        self.evidence.plugin_dir = plugin
        proposal = {"nodeId": "screen:quest_panel", "zoneId": "policy:quest_panel:close", "screen": "quest_panel",
                    "operation": "remove", "kind": "navigation", "rect": [.485, .485, .515, .515]}
        self.assertEqual((await self.client.post("/api/zone-feedback", json=proposal)).status, 201)
        graph = await (await self.client.get("/api/graph")).json()
        node = next(node for node in graph["nodes"] if node["id"] == "screen:quest_panel")
        regions = {region["id"]: region for region in node["regions"]}
        self.assertTrue(regions["policy:close"]["removedProposal"])
        self.assertFalse(regions["policy:close_to_shop_event"].get("removedProposal", False))


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
