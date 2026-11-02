"""Incomplete recipes cannot replace a weapon with its completion bonus."""
import copy
import unittest

import test_soul_weapon as sw


class CoverageApplicability(unittest.TestCase):
    def test_all_59_incomplete_gold_maxed_recipes_are_refused(self):
        rotate = sw.engraving_rules.any_orientation(sw.TABLE)
        rejected = []
        for entry in sw.TABLE["weapons"]:
            if entry.get("grid") != 5 or sum(item["name"] == entry["name"] for item in sw.TABLE["weapons"]) > 1:
                continue
            variant = sw.engraving_rules.variants(entry, rotate).get("Gold-maxed")
            if not variant:
                continue
            coverage = sw.engraving_rules.check(entry["cells"], [piece["cells"] for piece in variant["pieces"]])
            if coverage["complete"]:
                continue
            with self.subTest(weapon=entry["name"]):
                support = sw.engraving_rules.automation(entry["id"], sw.TABLE, rotate, "Gold-maxed")
                self.assertFalse(support["supported"])
                self.assertEqual(support["code"], "incomplete_variant")
                self.assertEqual(support["reason_t"]["params"]["count"], len(coverage["missing"]))
                self.assertIn("bonus de complétion", sw.french(support["reason_t"]))
            rejected.append(entry["id"])
        self.assertEqual(len(rejected), 59)
        self.assertTrue(sw.engraving_rules.automation(sw.AMBITION, sw.TABLE, rotate, "Gold-maxed")["supported"])


class CoverageBeforeEquip(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_target_preserves_equipped_weapon_and_grid_without_any_input(self):
        for invalid in ("missing", "overlap", "outside"):
            with self.subTest(invalid=invalid):
                game = sw.vision_game(screen="soul")
                game.state.update(equipped=sw.AMBITION, selected=sw.AMBITION)
                before = copy.deepcopy(game.state)
                requested = copy.deepcopy(sw.VISION_VARIANTS["Gold-maxed" if invalid == "missing" else "Gold-balanced"])
                if invalid == "overlap":
                    requested["pieces"].append(copy.deepcopy(requested["pieces"][0]))
                elif invalid == "outside":
                    requested["pieces"][0]["cells"].append([-1, -1])
                part = {"setup": sw.engraving_setup.engraving_setup, "screen": sw.fake_engraving_screen(game),
                        "rules": sw.setup_rules, "variant": lambda *args: requested}
                loadout = {"mpw18": {"stage": 920, "preset": None,
                                      "soul_weapon": {"id": sw.VISION_ID, "variant": "Gold-maxed"}}}
                # This standalone harness advertises support to ensure the
                # executor's own guard protects callers independently.
                _, api = sw.build(game, loadout, part)
                answer = await api["soul_weapon"]("mpw18")
                self.assertEqual(answer["result"], "failed")
                self.assertIn("bonus de complétion", sw.french(answer["text_t"]))
                if invalid == "missing":
                    self.assertIn("4 case(s) manquante(s)", sw.french(answer["text_t"]))
                self.assertEqual(game.moves, [])
                self.assertEqual(game.captures, 0, "refuse before opening or equipping the requested weapon")
                self.assertEqual(game.state, before)
                self.assertIsNone(api["soul_weapon_state"]()["cached"])


if __name__ == "__main__":
    unittest.main()
