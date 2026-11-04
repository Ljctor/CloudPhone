"""Shared advisory storage never changes input policy or original captures."""
import importlib.util
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

SPEC = importlib.util.spec_from_file_location("shared_zones_test", Path(__file__).with_name("zone_feedback.py"))
shared = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shared)


def append_worker(directory, index):
    shared.ZoneFeedback(directory).append({"nodeId": "screen:battle", "zoneId": f"user:{index}", "screen": "battle",
        "operation": "add", "kind": "detection", "rect": [.1, .2, .3, .4]}, {"battle"})


class SharedZoneFeedback(unittest.TestCase):
    def test_forbidden_action_and_forbidden_navigation_persist_as_distinct_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = shared.ZoneFeedback(Path(temporary))
            body = {"nodeId": "screen:battle", "screen": "battle", "operation": "add", "rect": [.1, .2, .3, .4]}
            allowed = store.append({**body, "kind": "action"}, {"battle"})
            action = store.append({**body, "kind": "action", "forbidden": True}, {"battle"})
            navigation = store.append({**body, "kind": "forbidden"}, {"battle"})
            self.assertEqual(len({item["id"] for item in (allowed, action, navigation)}), 3)
            data = Path(temporary) / "data"
            manual = data / "manual-clicks"
            manual.mkdir(parents=True)
            capture = "a" * 32
            (manual / (capture + ".json")).write_text(json.dumps({
                "id": capture, "at": time.time(), "kind": "action", "forbidden": True,
                "capture_status": "complete", "before_scan": {"screen": "battle", "plain": True},
                "rect": [.4, .4, .5, .5]}))
            generated = store.read_annotations(data, {"battle"}, tree={"battle": {"parent": None}})
            recorded = next(zone for zone in generated if zone["id"] == "manual:" + capture)
            self.assertEqual((recorded["kind"], recorded["forbidden"], recorded["gestureAuthority"]), ("action", True, False))
            restored = shared.ZoneFeedback(Path(temporary)).read()
            self.assertEqual([(item["kind"], item["forbidden"]) for item in restored],
                             [("action", False), ("action", True), ("forbidden", True)])
            self.assertTrue(all(item["gestureAuthority"] is False for item in restored))
            for invalid in ({"kind": "action", "forbidden": 1},
                            {"kind": "navigation", "forbidden": True},
                            {"kind": "forbidden", "forbidden": False}):
                with self.assertRaises(ValueError):
                    store.append({**body, **invalid}, {"battle"})

    def test_value_roles_persist_independently_and_require_valid_rectangles(self):
        with tempfile.TemporaryDirectory() as directory:
            store = shared.ZoneFeedback(directory)
            roles = ("progression_value", "resource_value", "screen_identifier")
            for kind in roles:
                body = {"screen": "battle", "nodeId": "screen:battle", "operation": "add",
                        "kind": kind, "rect": [.1, .2, .3, .4]}
                item = store.append(body, {"battle"})
                self.assertEqual(item["kind"], kind)
                self.assertIs(item["gestureAuthority"], False)
                for rect in (None, [.3, .2, .1, .4], [.1, .2, .1, .4], [True, .2, .3, .4], [.1, .2, float("nan"), .4]):
                    with self.assertRaises(ValueError):
                        store.append({**body, "rect": rect}, {"battle"})
            restored = shared.ZoneFeedback(directory).read_annotations(directory, {"battle"})
            self.assertEqual({item["kind"] for item in restored}, set(roles))
            self.assertTrue(all(item["gestureAuthority"] is False for item in restored))

    def test_fresh_nested_annotation_uses_deepest_identity_not_overlay_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual = root / "data" / "manual-clicks"
            manual.mkdir(parents=True)
            capture = "c" * 32
            tree = {"battle": {"parent": None}, "equipment_weapon": {"parent": "battle"},
                    "soul_weapon": {"parent": "equipment_weapon"}}
            for overlays in (["panel", "soul_weapon", "equipment_weapon"], ["panel", "equipment_weapon", "soul_weapon"]):
                entry = {"id": capture, "at": time.time(), "kind": "scannable", "capture_status": "complete",
                         "before_scan": {"screen": "battle", "overlays": overlays}, "rect": [.1, .2, .3, .4]}
                (manual / f"{capture}.json").write_text(json.dumps(entry))
                zones = shared.ZoneFeedback(root / "review").read_annotations(root / "data", set(tree), tree=tree)
                self.assertEqual([zone["screen"] for zone in zones], ["soul_weapon"])

    def test_exact_user_zone_removal_does_not_mark_same_geometry_with_another_id(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = [{"id": "manual:" + character * 32, "nodeId": "manual:" + character * 32 + ":before",
                            "screen": "battle", "kind": "scannable", "rect": [.1, .2, .3, .4], "review_status": "processed"}
                           for character in ("a", "b")]
            (root / "trace-review.json").write_text(json.dumps({"annotations": annotations}))
            store = shared.ZoneFeedback(root)
            store.append({"nodeId": annotations[0]["nodeId"], "zoneId": annotations[0]["id"], "screen": "battle",
                          "operation": "remove", "kind": "detection", "rect": [.1, .2, .3, .4]}, {"battle"})
            zones = {zone["id"]: zone for zone in store.read_annotations(root, {"battle"})}
            self.assertTrue(zones[annotations[0]["id"]]["removedProposal"])
            self.assertFalse(zones[annotations[1]["id"]].get("removedProposal", False))

    def test_cross_process_writers_preserve_every_distinct_proposal(self):
        with tempfile.TemporaryDirectory() as directory:
            context = multiprocessing.get_context("fork")
            children = [context.Process(target=append_worker, args=(directory, i)) for i in range(8)]
            for child in children:
                child.start()
            for child in children:
                child.join(10)
                self.assertEqual(child.exitcode, 0)
            store = shared.ZoneFeedback(directory)
            self.assertEqual(len(store.read()), 8)
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)

    def test_fresh_vertical_annotation_keeps_exact_trajectory_and_nonzero_display_box(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manual = root / "data" / "manual-clicks"
            manual.mkdir(parents=True)
            capture = "a" * 32
            entry = {"id": capture, "at": time.time(), "kind": "vertical", "capture_status": "complete",
                     "before_scan": {"screen": "battle", "overlays": [], "plain": True},
                     "tap": {"x": .5, "y": .8, "end": {"x": .5, "y": .4}}}
            (manual / f"{capture}.json").write_text(json.dumps(entry))
            store = shared.ZoneFeedback(root / "review")
            zones = store.read_annotations(root / "data", {"battle"})
            self.assertEqual(len(zones), 1)
            self.assertLess(zones[0]["rect"][0], zones[0]["rect"][2])
            self.assertEqual(zones[0]["trajectory"], [{"x": .5, "y": .8}, {"x": .5, "y": .4}])
            self.assertTrue(zones[0]["user"])
            (root / "review").mkdir()
            (root / "review" / "trace-review.json").write_text(json.dumps({"items": {"manual:" + capture: {
                "before": {"status": "ambiguous", "screen": None}}}}))
            self.assertEqual(store.read_annotations(root / "data", {"battle"}), [], "historical bad classification cannot become a global overlay")

    def test_unknown_global_proposal_and_invalid_geometry_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            store = shared.ZoneFeedback(directory)
            body = {"nodeId": "screen:unknown", "screen": "unknown", "operation": "add", "kind": "detection", "rect": [.1, .2, .3, .4]}
            with self.assertRaises(ValueError):
                store.append(body)
            stored = store.append({**body, "nodeId": "manual:" + "a" * 32 + ":before"})
            self.assertEqual(stored["scope"], "node")
            named = store.append({**body, "screen": "archived_variant", "nodeId": "example:archived_variant"}, {"battle"})
            self.assertEqual(named["scope"], "node")
            self.assertFalse(named["known"])
            self.assertEqual(store.read_annotations(directory), [])
            with self.assertRaises(ValueError):
                store.append({**body, "screen": "battle", "nodeId": "screen:battle", "rect": [0, 0, 2, 2]})


if __name__ == "__main__":
    unittest.main()
