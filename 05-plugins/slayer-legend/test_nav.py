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
            ("battle", "scroll", (0.94, 0.15)),
            ("black_orb", "orb", (0.50, 0.60)),
            ("black_orb", "obtain", (0.89, 0.963)),
            ("black_orb", "summon", (0.50, 0.963)),
            ("black_orb_accessory", "awaken", (0.50, 0.80)),
        ]:
            self.assertIn("forbidden", nav.guard(screen, move, *point))

    def test_allowed_move_on_a_forbidden_spot(self):
        # A tap meant for the weapon list but landing on Breakdown is
        # refused.
        self.assertIsNotNone(nav.guard("soul_weapon", "select", 0.80, 0.84))
        self.assertIsNone(nav.guard("soul_weapon", "select", 0.09, 0.70))

    def test_equip_tag_refused(self):
        # On the equipped weapon the tag reads Unequip: refused for now.
        self.assertIn("forbidden", nav.guard("soul_weapon", "equip", 0.09, 0.847))

    def test_ad_summons(self):
        # Summons by ad are allowed, the paid ones beside them are not.
        for name, y in [("weapon", 0.54), ("accessories", 0.68), ("skill", 0.82)]:
            self.assertIsNone(nav.guard("shop_summon", f"ad_summon_{name}", 0.88, y))
        self.assertIsNotNone(nav.guard("shop_summon", "ad_summon_weapon", 0.80, 0.54))

    def test_precondition(self):
        # A reward is claimed only once its bar was read as full.
        self.assertIn("check first", nav.guard("quest_panel", "claim", 0.79, 0.29))
        self.assertIn(("quest_panel", "claim", "the row's reward bar is full, read from pixels"), nav.preconditions())

    def test_androids_crash_dialog(self):
        # "Close app" only where uiautomator says it is (verified); never
        # "App info" (Force stop, Clear storage).
        self.assertIn("check first", nav.guard("crash_dialog", "close", 0.5, 0.6))
        self.assertIsNone(nav.guard("crash_dialog", "close", 0.5, 0.6, verified=True))
        self.assertIsNotNone(nav.guard("crash_dialog", "close", 0.5, 0.95, verified=True), "outside the dialog")
        self.assertIn("forbidden", nav.guard("crash_dialog", "app_info", 0.5, 0.6))

    def test_androids_not_responding_dialog(self):
        # "Wait" only; its "Close app" kills the game.
        self.assertIsNone(nav.guard("anr_dialog", "wait", 0.5, 0.6, verified=True))
        self.assertIn("check first", nav.guard("anr_dialog", "wait", 0.5, 0.6))
        self.assertIn("forbidden", nav.guard("anr_dialog", "close", 0.5, 0.6))
        self.assertIn("forbidden", nav.guard("anr_dialog", "app_info", 0.5, 0.6))

    def test_refused_by_default(self):
        self.assertIsNotNone(nav.guard("battle", "no_such_move", 0.5, 0.5))
        self.assertIsNotNone(nav.guard("no_such_screen", "start", 0.5, 0.836))
        self.assertIsNotNone(nav.guard("saver", "leave", 0.5, 0.88))  # a hold, not a tap

    def test_plugin_actions(self):
        self.assertIsNone(nav.guard("title", "start", 0.50, 0.836))
        self.assertIsNone(nav.guard("save_notice", "confirm", 0.314, 0.745))
        self.assertIsNone(nav.guard("battle", "quest", 0.94, 0.09))
        self.assertIsNone(nav.guard("quest_panel", "claim", 0.79, 0.29, verified=True))
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
