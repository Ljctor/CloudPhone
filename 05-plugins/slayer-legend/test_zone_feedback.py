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
