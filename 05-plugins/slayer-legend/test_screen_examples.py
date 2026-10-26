"""The plugin page gets only archived examples tied to catalogue screens."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("slayer_screen_examples", HERE / "features/screen_examples.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScreenExamples(unittest.TestCase):
    def test_archived_capture_and_its_real_details_are_in_the_game_answer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            code, data = root / "code", root / "data"
            code.mkdir()
            shots = data / "screenshots"
            shots.mkdir(parents=True)
            (code / "screen_registry.json").write_text(json.dumps({"tree": {
                "forest": {"example": "screenshots/forest.png", "variants": ["screenshots/forest_alt.png"],
                           "scroll": [{"measured": True, "captures": ["forest_bottom.png"],
                                       "start": "156", "end": "165"}]},
                "other": {"example": "screenshots/missing.png"}}}))
            (code / "screen_snapshots.json").write_text(json.dumps({"forest": [
                {"label": "Floor", "value": "162"}]}))
            (code / "screen_snapshots_world.json").write_text("{}")
            (code / "screen_inventory.json").write_text(json.dumps({"forest": {
                "kind": "weapons", "rows": [{"appearance": "blue", "grades": [4],
                "enhancements": [200], "counts": [3], "source": "forest.png"}]},
                "other": {"kind": "classes", "status": "never_read"}}))
            for name in ("forest", "forest_bottom", "orphan"):
                (shots / (name + ".png")).write_bytes(b"\x89PNG\r\n\x1a\n")
            (shots / "manifest.json").write_text(json.dumps({name: {
                "file": name + ".png", "captured": 42} for name in ("forest", "forest_bottom", "orphan")}))
            api = module.examples(code, data, "/api/v1/plugins/slayer-legend")
            answer = api["enrich"]({"screens": [{"screen": "forest"}, {"screen": "other"}]})
            forest, other = answer["screens"]
            self.assertEqual(forest["example"]["url"], "/api/v1/plugins/slayer-legend/examples/forest")
            self.assertEqual([item["label"] for item in forest["examples"]],
                             ["Capture principale", "Défilement 1"])
            self.assertEqual(forest["details"], [
                {"label": "Floor", "value": "162"},
                {"label": "Blue", "value": "Grade 4: +200, 3/5"},
                {"label": "Défilement observé", "value": "156 → 165"}])
            self.assertEqual(forest["inventory"]["kind"], "weapons")
            self.assertTrue(forest["observed"])
            self.assertEqual(other["examples"], [])
            self.assertEqual(other["details"], [{"label": "Classes", "value": "never read"}])
            self.assertFalse(other["observed"])


if __name__ == "__main__":
    unittest.main()
