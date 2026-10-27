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
# What a fresh capture of the Soul Weapon screen showed: no tag, or the
# tag where it was seen (0.09, 0.847).
CLEAR = {"selected": None, "target": "Ambition", "tag": None, "tag_box": None, "tags": []}
TAG = [0.03, 0.835, 0.15, 0.86]


class Graph(unittest.TestCase):
    def test_consistent(self):
        self.assertEqual(nav.check(), [])

    def test_forbidden_buttons(self):
        for screen, move, point in [
            ("soul_weapon", "breakdown", (0.81, 0.841)),
            ("soul_weapon_engraving", "change", (0.50, 0.955)),
            ("soul_weapon_engraving", "settings", (0.87, 0.955)),
            ("soul_weapon_engraving", "percent", (0.83, 0.807)),
            ("raid_camp", "raid", (0.54, 0.96)),
            ("raid_camp", "cooking", (0.66, 0.96)),
            ("shop_summon", "summon", (0.70, 0.60)),
            ("equipment_weapon", "batch_combine", (0.50, 0.905)),
            ("battle", "scroll", (0.94, 0.15)),
            ("battle", "top_menu", (0.935, 0.025)),
            ("top_menu", "ranking", (0.785, 0.027)),
            ("top_menu", "settings", (0.86, 0.027)),
            ("top_menu", "mail", (0.86, 0.068)),
            ("battle", "better_weapon_toast", (0.85, 0.345)),
            ("weapon_detail", "enhance", (0.3, 0.835)),
            ("weapon_detail", "equip", (0.7, 0.835)),
            ("black_orb", "orb", (0.50, 0.60)),
            ("black_orb", "obtain", (0.89, 0.963)),
            ("black_orb", "summon", (0.50, 0.963)),
            ("black_orb_accessory", "awaken", (0.50, 0.80)),
        ]:
            self.assertIn("forbidden", nav.guard(screen, move, *point))

    def test_engraving_locks_and_drags(self):
        # A padlock and a drag need their check first; a drag is a swipe
        # from a card, never a tap; Change, the gear and % stay out of reach.
        self.assertIn("check first", nav.guard("soul_weapon_engraving", "lock", 0.28, 0.616))
        self.assertIsNone(nav.guard("soul_weapon_engraving", "lock", 0.28, 0.616, verified=True))
        self.assertIn("check first", nav.guard("soul_weapon_engraving", "drag_piece", 0.22, 0.639, "swipe"))
        self.assertIsNone(nav.guard("soul_weapon_engraving", "drag_piece", 0.22, 0.639, "swipe", True))
        self.assertIn("is a swipe", nav.guard("soul_weapon_engraving", "drag_piece", 0.22, 0.639, verified=True))
        self.assertIsNotNone(nav.guard("soul_weapon_engraving", "drag_piece", 0.5, 0.955, "swipe", True))
        self.assertIsNotNone(nav.guard("soul_weapon_engraving", "lock", 0.83, 0.807, verified=True))

    def test_allowed_move_on_a_forbidden_spot(self):
        # A tap meant for the weapon list but landing on Breakdown is
        # refused.
        self.assertIsNotNone(nav.guard("soul_weapon", "select", 0.80, 0.84, verified=True, seen=CLEAR))
        self.assertIsNone(nav.guard("soul_weapon", "select", 0.09, 0.70, verified=True, seen=CLEAR))

    def test_soul_weapon_list_avoids_its_tags(self):
        # Select and scroll need the fresh capture's tags, and stay off them.
        self.assertIn("check first", nav.guard("soul_weapon", "select", 0.09, 0.70))
        self.assertIn("needs what the fresh capture shows", nav.guard("soul_weapon", "select", 0.09, 0.70,
                                                                      verified=True))
        tagged = dict(CLEAR, tags=[TAG])
        self.assertIn("on a tag", nav.guard("soul_weapon", "select", 0.09, 0.847, verified=True, seen=tagged))
        self.assertIsNone(nav.guard("soul_weapon", "select", 0.09, 0.80, verified=True, seen=tagged))
        self.assertIn("on a tag", nav.guard("soul_weapon", "scroll", 0.09, 0.847, "swipe", True, tagged))
        self.assertIsNone(nav.guard("soul_weapon", "scroll", 0.087, 0.80, "swipe", True, tagged))

    def test_equip_only_on_a_tag_read_equip_on_the_target(self):
        equip = {"selected": "Ambition", "target": "Ambition", "tag": "Equip", "tag_box": TAG, "tags": [TAG]}
        self.assertIn("check first", nav.guard("soul_weapon", "equip", 0.09, 0.847))
        self.assertIn("needs what the fresh capture shows", nav.guard("soul_weapon", "equip", 0.09, 0.847,
                                                                      verified=True))
        self.assertIsNone(nav.guard("soul_weapon", "equip", 0.09, 0.847, verified=True, seen=equip))
        # Off the tag, another weapon selected, an unread name or tag: refused.
        self.assertIn("not on the tag", nav.guard("soul_weapon", "equip", 0.09, 0.70, verified=True, seen=equip))
        self.assertIn("target", nav.guard("soul_weapon", "equip", 0.09, 0.847, verified=True,
                                          seen=dict(equip, selected="Grand")))
        self.assertIn("target", nav.guard("soul_weapon", "equip", 0.09, 0.847, verified=True,
                                          seen=dict(equip, selected=None)))
        self.assertIn("tag read", nav.guard("soul_weapon", "equip", 0.09, 0.847, verified=True,
                                            seen=dict(equip, tag=None)))

    def test_unequip_refused_forever(self):
        # The tag read Unequip: refused, whatever the move and the checks.
        unequip = {"selected": "Ambition", "target": "Ambition", "tag": "Unequip", "tag_box": TAG, "tags": [TAG]}
        self.assertIn("forbidden", nav.guard("soul_weapon", "unequip", 0.09, 0.847, verified=True, seen=unequip))
        for move, kind in (("equip", "tap"), ("select", "tap"), ("scroll", "swipe")):
            self.assertIn("forbidden", nav.guard("soul_weapon", move, 0.09, 0.847, kind, True, unequip), move)
        equip = next(m["precondition"] for m in nav.connections("soul_weapon") if m["id"] == "equip")
        self.assertIn(("soul_weapon", "equip", equip), nav.preconditions())

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

    def test_panels_close_through_visible_combat(self):
        for screen, x in [("character_enhance", 0.073), ("character_growth", 0.073), ("skill", 0.24),
                          ("equipment_weapon", 0.41), ("equipment_relic", 0.41), ("companion", 0.585),
                          ("adventure_map", 0.755), ("dungeon_map", 0.755), ("shop_summon", 0.925)]:
            self.assertIsNone(nav.guard(screen, "close", 0.5, 0.18, verified=True,
                                        seen={"look": {"screen": "battle", "plain": False, "overlays": ["panel"]},
                                              "combat_visible": True}), screen)
            self.assertIn("check first", nav.guard(screen, "close", 0.5, 0.18))
            for look in ({"screen": "unknown", "plain": False, "overlays": ["panel"]},
                         {"screen": "battle", "plain": True, "overlays": []},
                         {"screen": "battle", "plain": False, "overlays": ["panel", "soul_weapon"]}):
                self.assertIsNotNone(nav.guard(screen, "close", .5, .18, verified=True,
                                               seen={"look": look, "combat_visible": True}))
            self.assertIsNotNone(nav.guard(screen, "close", .5, .18, verified=True))
            self.assertEqual(next(m for m in nav.connections(screen) if m["id"] == "close")["to"], "battle")
        # A bottom tab is not the panel's close action.
        self.assertIsNotNone(nav.guard("shop_summon", "close", 0.073, 0.966))

    def test_weapon_card_can_be_inspected_without_enhancing(self):
        move = next(m for m in nav.connections("equipment_weapon") if m["id"] == "inspect_weapon")
        self.assertEqual(move["to"], "weapon_detail")
        self.assertIn("check first", nav.guard("equipment_weapon", "inspect_weapon", 0.15, 0.52))
        self.assertIsNone(nav.guard("equipment_weapon", "inspect_weapon", 0.15, 0.52, verified=True))
        self.assertIsNotNone(nav.guard("equipment_weapon", "inspect_weapon", 0.5, 0.905, verified=True))
        self.assertIn("forbidden", nav.guard("equipment_weapon", "batch_combine", 0.5, 0.905))
        self.assertIsNone(nav.guard("weapon_detail", "close", 0.5, 0.955))
        self.assertIn("forbidden", nav.guard("weapon_detail", "enhance", 0.3, 0.835))

    def test_battle_controls(self):
        # The arrow's spot is on the AUTO tile once unfolded: tapped only
        # once the controls read folded; AUTO never (the user, 2026-10-22).
        self.assertIn("check first", nav.guard("battle", "preset_arrow", 0.975, 0.444))
        self.assertIsNone(nav.guard("battle", "preset_arrow", 0.975, 0.444, verified=True))
        self.assertIsNone(nav.guard("battle", "preset_badge", 0.965, 0.405))
        self.assertIn("forbidden", nav.guard("battle", "auto", 0.93, 0.447))
        self.assertIn("forbidden", nav.guard("battle", "auto", 0.93, 0.447, verified=True))
        self.assertIsNone(nav.guard("battle_settings", "preset", 0.66, 0.305))
        self.assertIsNone(nav.guard("battle_settings", "close", 0.09, 0.965))

    def test_select_region(self):
        self.assertIsNone(nav.guard("battle", "stage_select", 0.30, 0.07))
        self.assertIsNone(nav.guard("stage_select", "next_region", 0.875, 0.345))
        self.assertIsNone(nav.guard("stage_select", "previous_region", 0.125, 0.345))
        self.assertIsNone(nav.guard("stage_select", "scroll", 0.5, 0.75, "swipe"))
        self.assertIsNone(nav.guard("stage_select", "scroll", 0.5, 0.45, "swipe"))
        # Move only on a row read as the target; never the info button.
        self.assertIn("check first", nav.guard("stage_select", "move", 0.78, 0.757))
        self.assertIsNone(nav.guard("stage_select", "move", 0.78, 0.757, verified=True))
        self.assertIn("forbidden", nav.guard("stage_select", "info", 0.16, 0.6))
        self.assertIsNone(nav.guard("stage_select", "close", 0.5, 0.94))

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
