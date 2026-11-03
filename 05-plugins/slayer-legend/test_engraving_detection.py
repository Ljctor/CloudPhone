"""Farming checks today's grid even when an older run left no pending marker."""
import copy
import unittest

import test_soul_weapon as sw
import test_equip_engraving as eq


class EngravingDetection(unittest.IsolatedAsyncioTestCase):
    def build(self, *, empty=True, saved=None):
        game = sw.vision_game(screen="soul", pieces={} if empty else None)
        ports, api, persisted = eq.EquipEngraving().build(game, saved)
        return game, ports, api, persisted

    async def test_boot_repairs_empty_grid_despite_historical_success_before_paused_preset(self):
        historical = {"engraving_recovery": {
            "weapon_id": sw.VISION_ID, "variant": "Gold-balanced", "verified": True,
            "required": False, "locks_verified": True, "completion_verified": True,
            "recipe": {"weapon_id": sw.VISION_ID, "name": "Gold-balanced",
                       "variant": copy.deepcopy(sw.VISION_VARIANTS["Gold-balanced"])}}}
        game, _, api, _ = self.build(saved=historical)
        self.assertTrue(api["soul_verification_needed"]("soul"))
        result = await api["farm"](920, "IV", "soul")
        self.assertEqual(result["failure_code"], "preset_action_paused")
        self.assertFalse(result["verified_setup"], "a good engraving does not certify the blocked preset")
        self.assertIn("engraving_recovery", result["timings"])
        self.assertNotIn("stage", result["timings"])
        eq.EquipEngraving().assert_ready(game, api)
        self.assertEqual(game.state["screen"], "soul")
        self.assertFalse(api["soul_verification_needed"]("soul"))

    async def test_periodic_check_detects_and_repairs_empty_grid_without_user_input(self):
        game, _, api, _ = self.build()
        self.assertEqual((await api["soul_weapon"]("mpw18"))["result"], "done")
        self.assertFalse(api["soul_verification_needed"]("mpw18"))
        game.moves.clear()
        game.state["engraving"]["pieces"].clear()
        for card in game.state["engraving"]["cards"]:
            card["placed"] = False
        game.now += 299
        self.assertFalse(api["soul_verification_needed"]("mpw18"))
        game.now += 1
        self.assertTrue(api["soul_verification_needed"]("mpw18"))
        self.assertEqual((await api["soul_weapon"]("mpw18"))["result"], "done")
        self.assertEqual(game.moves[0], ("soul_weapon", "engraving"))
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        eq.EquipEngraving().assert_ready(game, api)

    async def test_user_input_invalidates_complete_proof_immediately(self):
        game, ports, api, _ = self.build()
        self.assertEqual((await api["soul_weapon"]("mpw18"))["result"], "done")
        self.assertFalse(api["soul_verification_needed"]("mpw18"))
        game.now += 1
        ports.last_input = lambda: {"wall": ports.clock.wall()}
        self.assertTrue(api["soul_verification_needed"]("mpw18"))

    async def test_periodic_healthy_grid_check_returns_to_parking_without_mutation(self):
        game, _, api, _ = self.build()
        self.assertEqual((await api["soul_weapon"]("soul"))["result"], "done")
        game.moves.clear()
        game.now += 300
        self.assertEqual((await api["soul_weapon"]("soul"))["result"], "done")
        self.assertEqual(game.moves, [("soul_weapon", "engraving"), ("soul_weapon_engraving", "close")])
        self.assertEqual(game.state["screen"], "soul")
        self.assertFalse(api["soul_verification_needed"]("soul"))

    async def test_paused_preset_from_battle_returns_to_soul_parking_without_full_success(self):
        game, _, api, _ = self.build()
        self.assertEqual((await api["soul_weapon"]("soul"))["result"], "done")
        game.state.update(screen="battle", panel=None)
        game.moves.clear()
        result = await api["farm"](920, "IV", "soul")
        self.assertEqual(result["failure_code"], "preset_action_paused")
        self.assertFalse(result["verified_setup"])
        self.assertNotIn("engraving_recovery", result["timings"], "fresh proof needs no extra grid visit")
        self.assertEqual(game.moves, [("battle", "menu_equipment"), ("equipment_weapon", "soul_weapon")])
        self.assertEqual(game.state["screen"], "soul")

    async def test_relaunch_invalidates_complete_proof_immediately(self):
        game, _, api, _ = self.build()
        self.assertEqual((await api["soul_weapon"]("mpw18"))["result"], "done")
        self.assertFalse(api["soul_verification_needed"]("mpw18"))
        game.now += 1
        api["relaunched"]("soul").close()
        self.assertTrue(api["soul_verification_needed"]("soul"))


if __name__ == "__main__":
    unittest.main()
