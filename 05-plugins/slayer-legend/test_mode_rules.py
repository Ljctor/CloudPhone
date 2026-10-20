"""The mode's rules (features/mode_rules.py): a mode is chosen only once
configured. Run: python3 -m unittest test_mode_rules"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/mode_rules")


class Request(unittest.TestCase):
    def test_mpw4_needs_its_stage(self):
        asked, error = rules.request({"mode": "mpw4"})
        self.assertIsNone(asked)
        self.assertEqual(error, "Farming mpw4 : choisis d’abord son stage")
        asked, error = rules.request({"mode": "mpw4", "stage4": 31})
        self.assertIsNone(error)
        self.assertEqual((asked[0], asked[2]["stage4"]), ("mpw4", 31))

    def test_the_mine_needs_its_floor_and_area(self):
        for body in ({"mode": "mine"}, {"mode": "mine", "floor": 12}, {"mode": "mine", "area": 3},
                     {"mode": "mine", "floor": 12, "area": 6}, {"mode": "mine", "floor": 10000, "area": 3}):
            asked, error = rules.request(body)
            self.assertIsNone(asked, body)
            self.assertTrue(error.startswith("Mine fermée : choisis d’abord"), (body, error))
        asked, error = rules.request({"mode": "mine", "floor": 12, "area": 3})
        self.assertIsNone(error)
        self.assertEqual(asked[0], "mine")

    def test_the_others_need_nothing(self):
        for mode in ("mpw18", "free"):
            asked, error = rules.request({"mode": mode})
            self.assertIsNone(error, mode)
            self.assertEqual(asked[0], mode)

    def test_the_default_has_no_timer(self):
        asked, _ = rules.request({"mode": "mpw18", "until": 1_800_000_000})
        self.assertIsNone(asked[1])


if __name__ == "__main__":
    unittest.main()
