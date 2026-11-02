"""Only a fresh recovery in this ensure call can replace its engraving pass."""
import asyncio
import copy
import unittest

import test_soul_weapon as sw


class RecoveryReuse(unittest.IsolatedAsyncioTestCase):
    def build(self, weapon=None, variant="Gold-balanced", after_recovery=lambda: None):
        game = sw.vision_game(screen="engraving", pieces={})
        game.state["owned"].add(sw.AMBITION)
        ports = game.ports()
        ports.store.saved["engraving_recovery"] = {
            "required": True, "weapon_id": sw.VISION_ID, "variant": "Gold-balanced",
            "recipe": {"weapon_id": sw.VISION_ID, "name": "Gold-balanced",
                       "variant": copy.deepcopy(sw.VISION_VARIANTS["Gold-balanced"])}}
        game.ports = lambda: ports
        calls = []
        def factory(*args, **kwargs):
            actual = sw.engraving_setup.engraving_setup(*args, **kwargs)
            async def setup(shot, entry, name, pieces, *rest, recovery_only=False):
                calls.append((entry["id"], recovery_only))
                if entry["id"] != sw.VISION_ID:
                    raise sw.stage_change.Stop("test : configuration normale de la nouvelle arme atteinte")
                result = await actual(shot, entry, name, pieces, *rest, recovery_only=recovery_only)
                if recovery_only:
                    after_recovery()
                return result
            setup.state, setup.cancel = actual.state, actual.cancel
            return setup
        part = {"setup": factory, "screen": sw.fake_engraving_screen(game), "rules": sw.setup_rules,
                "variant": lambda weapon, name: sw.engraving_rules.variants(
                    sw.engraving_rules.weapon_by_id(weapon, sw.TABLE), True).get(name)}
        target = {"mpw18": {"stage": 920, "preset": None,
                            "soul_weapon": {"id": weapon or sw.VISION_ID, "variant": variant}}}
        _, api = sw.build(game, target, part)
        return game, ports, api, calls

    async def test_matching_recovery_applies_engraving_once_and_checks_equipment(self):
        game, ports, api, calls = self.build()
        final_reads = []
        analyse = ports.analyse
        async def counted(reader, *args):
            if reader.__name__ == "final_view":
                final_reads.append(True)
            return await analyse(reader, *args)
        ports.analyse = counted
        answer = await api["soul_weapon"]("mpw18")
        self.assertEqual(answer["result"], "done")
        self.assertEqual(calls, [(sw.VISION_ID, True)])
        self.assertTrue(final_reads)
        self.assertTrue(api["soul_weapon_state"]()["recovery"]["verified"])
        self.assertEqual(sw.engraving_moves(game).count("close"), 1)

    async def test_different_variant_still_runs_normal_setup(self):
        game, _, api, calls = self.build(variant="Atk")
        answer = await api["soul_weapon"]("mpw18")
        self.assertEqual(answer["result"], "done")
        self.assertEqual(calls, [(sw.VISION_ID, True), (sw.VISION_ID, False)])
        self.assertEqual(sw.engraving_moves(game).count("close"), 2)

    async def test_different_weapon_still_reaches_its_normal_setup(self):
        game, _, api, calls = self.build(weapon=sw.AMBITION)
        answer = await api["soul_weapon"]("mpw18")
        self.assertEqual(answer["result"], "failed")
        self.assertEqual(calls, [(sw.VISION_ID, True), (sw.AMBITION, False)])
        self.assertEqual(game.state["equipped"], sw.AMBITION)
        self.assertIn("configuration normale", sw.french(answer["text_t"]))

    async def test_user_input_after_recovery_prevents_reuse(self):
        input_mark = [None]
        game, ports, api, calls = self.build(after_recovery=lambda: input_mark.__setitem__(0, {"wall": 123}))
        ports.last_input = lambda: input_mark[0]
        await api["soul_weapon"]("mpw18")
        self.assertEqual(calls, [(sw.VISION_ID, True), (sw.VISION_ID, False)])

    async def test_user_input_during_final_check_cannot_publish_reused_recovery(self):
        _, ports, api, calls = self.build()
        input_mark = [None]
        ports.last_input = lambda: input_mark[0]
        analyse = ports.analyse
        async def interrupted(reader, *args):
            result = await analyse(reader, *args)
            if reader.__name__ == "final_view":
                input_mark[0] = {"wall": 123}
            return result
        ports.analyse = interrupted
        answer = await api["soul_weapon"]("mpw18")
        self.assertEqual(answer["result"], "failed")
        self.assertEqual(calls, [(sw.VISION_ID, True)])
        self.assertIsNone(api["soul_weapon_state"]()["cached"])


if __name__ == "__main__":
    unittest.main()
