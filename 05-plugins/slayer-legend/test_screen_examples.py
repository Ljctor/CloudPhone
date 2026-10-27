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
                "kind": "weapons", "items": [{"id": "weapon-blue-grade-4", "name": None,
                "appearance": "blue", "grade": 4, "enhancement": 200,
                "displayed_fraction": {"numerator": 3, "denominator": 5},
                "owned": None, "equipped": False,
                "source": {"capture": "forest.png", "box": [0, 0, 10, 10]}}]},
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
                {"label": "Défilement observé", "value": "156 → 165"}])
            self.assertEqual(forest["inventory"]["kind"], "weapons")
            self.assertEqual(forest["inventory"]["items"][0]["source"]["box"], [0, 0, 10, 10])
            self.assertTrue(forest["observed"])
            self.assertEqual(other["examples"], [])
            self.assertEqual(other["details"], [{"label": "Classes", "value": "never read"}])
            self.assertFalse(other["observed"])

    def test_captured_equipment_is_individual_and_does_not_guess_ownership(self):
        inventory = json.loads((HERE / "screen_inventory.json").read_text(encoding="utf-8"))
        registry = json.loads((HERE / "screen_registry.json").read_text(encoding="utf-8"))["tree"]
        for screen in ("equipment_weapon", "equipment_accessories"):
            items = inventory[screen]["items"]
            node = registry[screen]
            captures = {Path(node["example"]).name}
            captures.update(Path(path).name for section in node.get("scroll", [])
                            for path in section.get("captures", []))
            self.assertEqual(len(items), 25)
            self.assertEqual(len({item["id"] for item in items}), 25)
            self.assertEqual(sum(item["equipped"] for item in items), 1)
            self.assertTrue(all(item["owned"] is None for item in items if not item["equipped"]))
            self.assertTrue(all(item["name"] is None and item["rarity"] is None for item in items))
            for item in items:
                source = item["source"]
                self.assertIn(source["capture"], captures)
                x0, y0, x1, y1 = source["box"]
                self.assertTrue(0 <= x0 < x1 <= 480 and 0 <= y0 < y1 <= 1040)


if __name__ == "__main__":
    unittest.main()
