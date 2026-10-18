"""The navigation graph is consistent and its guard lets the plugin's own
actions through and nothing forbidden. Run: python3 -m unittest test_nav"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nav = load("nav")
mine = load("mine")


class Graph(unittest.TestCase):
    def test_consistent(self):
        self.assertEqual(nav.check(), [])

    def test_forbidden_buttons(self):
        for screen, move, point in [
            ("soul_weapon", "breakdown", (0.81, 0.841)),
            ("soul_weapon_engraving", "change", (0.50, 0.955)),
            ("raid_camp", "raid", (0.54, 0.96)),
            ("raid_camp", "cooking", (0.66, 0.96)),
            ("shop_summon", "summon", (0.70, 0.60)),
            ("equipment_weapon", "batch_combine", (0.50, 0.905)),
        ]:
            self.assertIn("forbidden", nav.guard(screen, move, *point))

    def test_allowed_move_on_a_forbidden_spot(self):
        # The Equip tag is orange like Breakdown: a tap meant for it but
        # landing on Breakdown is refused.
        self.assertIsNotNone(nav.guard("soul_weapon", "equip", 0.80, 0.84))
        self.assertIsNone(nav.guard("soul_weapon", "equip", 0.09, 0.847))

    def test_refused_by_default(self):
        self.assertIsNotNone(nav.guard("battle", "no_such_move", 0.5, 0.5))
        self.assertIsNotNone(nav.guard("no_such_screen", "start", 0.5, 0.836))
        self.assertIsNotNone(nav.guard("saver", "leave", 0.5, 0.88))  # a hold, not a tap

    def test_plugin_actions(self):
        self.assertIsNone(nav.guard("title", "start", 0.50, 0.836))
        self.assertIsNone(nav.guard("save_notice", "confirm", 0.314, 0.745))
        self.assertIsNone(nav.guard("saver", "leave", 0.50, 0.88, "hold"))
        for point in mine.AREA_TAPS:
            self.assertIsNone(nav.guard("mine_area", "area", *point))
        for point in mine.FEATHER_TAPS:
            self.assertIsNone(nav.guard("mine_feathers", "feathers", *point))
        self.assertIsNone(nav.guard("mine_fight", "repeat", *mine.REPEAT_TAP))
        self.assertIsNone(nav.guard("mine_list", "scroll", 0.5, 0.40, "swipe"))
        self.assertIsNone(nav.guard("mine_list", "scroll", 0.5, 0.65, "swipe"))


if __name__ == "__main__":
    unittest.main()
