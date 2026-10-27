"""Top-bar resource OCR on reviewed, account-free crops from real captures."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location("slayer_currency_test_" + name.replace("/", "_"),
                                                  os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


currencies = load("top_currencies")
fixtures = load("test_fixtures")
rules = load("features/game_rules")


class TopCurrencies(unittest.TestCase):
    def test_exact_real_counters(self):
        for name, emerald, diamond in (
            ("top_currencies_battle", 276362, 984),
            ("top_currencies_equipment", 276362, 1494),
            ("top_currencies_shaded", 276362, 984),
        ):
            shot = fixtures.screen(name)
            self.assertEqual(currencies.read(shot, "emerald")["value"], emerald, name)
            self.assertEqual(currencies.read(shot, "diamond")["value"], diamond, name)

    def test_icon_is_required(self):
        width, height, pixels = fixtures.screen("top_currencies_battle")
        pixels = bytearray(pixels)
        for field in ("emerald", "diamond"):
            altered = pixels.copy()
            x0, y0, x1, y1 = currencies.COUNTERS[field]["icon"]
            for y in range(y0, y1):
                for x in range(x0, x1):
                    altered[(y * width + x) * 3:(y * width + x + 1) * 3] = bytes((20, 16, 14))
            self.assertIsNone(currencies.read((width, height, altered), field))

    def test_both_resources_are_live_fields(self):
        self.assertFalse(rules.FIELDS["emerald"]["pending"])
        self.assertFalse(rules.FIELDS["diamond"]["pending"])
        self.assertIn("currencies", rules.readers_for({"screen": "battle", "overlays": []}))
        self.assertNotIn("currencies", rules.readers_for({"screen": "saver", "overlays": []}))
        shot = fixtures.screen("top_currencies_battle")
        values = {field: currencies.read(shot, field) for field in ("emerald", "diamond")}
        facts, _ = rules.noted({}, values, 1234.0)
        rows = {row["field"]: row for row in rules.answer(facts)["resources"]}
        self.assertEqual(rows["emerald"]["value"]["value"], 276362)
        self.assertEqual(rows["diamond"]["value"]["value"], 984)


if __name__ == "__main__":
    unittest.main()
