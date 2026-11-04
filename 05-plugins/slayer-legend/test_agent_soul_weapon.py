"""Explicit Agent weapon tests retain accepted targets and ordinary lease gates."""
import asyncio
import copy
import unittest
from types import SimpleNamespace

import test_stage_change as stage


class AgentSoulWeapon(unittest.IsolatedAsyncioTestCase):
    def build(self):
        self.game = stage.Game(stage=915, preset="II")
        self.target = {"stage": 920, "preset": "IV", "soul_weapon": {"id": 32, "variant": "Gold-maxed"}}
        self.revision = "accepted-1"
        self.agent = True
        self.interrupt = lambda: None
        self.calls = []
        self.input = None
        ports = self.game.ports()
        ports.last_input = lambda: self.input

        def soul_feature(ports, screens, reader, rules, table, helpers, engraving):
            async def ensure(weapon, variant, park):
                await helpers.front()
                self.calls.append((weapon, variant, park))
                self.interrupt()
                await helpers.front()
                return "equipped"

            async def park():
                await helpers.front()

            return {"ensure": ensure, "park": park, "switch": lambda: "real",
                    "state": lambda: {"engraving": "real"}}

        soul = {"feature": soul_feature, "reader": None, "rules": None, "table": None,
                "loadout": lambda mode: copy.deepcopy(self.target), "revision": lambda mode: self.revision,
                "applicability": lambda chosen: {"supported": True, "engraving_required": True},
                "engraving": {}}
        # Truthy capability; no fake engraving executor is called by the fake
        # soul feature. The actual ensure_soul_weapon lease/preflight is used.
        soul["engraving"] = {"available": True}
        part = stage.feature.stage_change(ports, *stage.readers(self.game), stage.rules, stage.TABLE, soul)
        part["api"]["bind_agent_context"](lambda: self.agent)
        self.handler = next(handler for method, path, handler in part["routes"]
                            if method == "POST" and path == "/farming/soul-weapon")

    async def request(self, body=None):
        payload = body if body is not None else {"mode": "mpw18", "if_revision": "accepted-1"}
        async def json():
            return payload
        return await self.handler(SimpleNamespace(json=json))

    async def test_weapon_only_even_when_stage_and_preset_differ(self):
        self.build()
        before = copy.deepcopy(self.target)
        status, answer = await self.request()
        self.assertEqual(status, 200)
        self.assertEqual(answer["result"], "done")
        self.assertTrue(answer["verified_weapon"])
        self.assertNotIn("verified_setup", answer)
        self.assertEqual(self.calls, [(32, "Gold-maxed", True)])
        self.assertEqual(self.game.moves, [])
        self.assertEqual((self.game.state["stage"], self.game.state["preset"]), (915, "II"))
        self.assertEqual(self.target, before)
        self.assertEqual(self.game.leases, [("stage_change", "farm mpw18")])

    async def test_agent_and_revision_required_before_any_execution(self):
        for change in (lambda: setattr(self, "agent", False), lambda: setattr(self, "revision", "changed")):
            self.build()
            change()
            status, _ = await self.request()
            self.assertEqual(status, 409)
            self.assertEqual(self.calls, [])
            self.assertEqual(self.game.leases, [])

    async def test_agent_exit_or_target_revision_change_interrupts(self):
        for interrupt, reason in (
                (lambda: setattr(self, "agent", False), "mode Agent indisponible"),
                (lambda: self.target["soul_weapon"].update(id=45), "configuration modifiée"),
                (lambda: setattr(self, "revision", "changed"), "configuration modifiée")):
            self.build()
            self.interrupt = interrupt
            status, answer = await self.request()
            self.assertEqual(status, 200)
            self.assertEqual(answer["result"], "failed")
            self.assertFalse(answer["verified_weapon"])
            self.assertNotIn("verified_setup", answer)
            self.assertIn(reason, answer["text_t"]["template"])

    async def test_user_input_defers_agent_execution_without_verified_result(self):
        self.build()
        before = copy.deepcopy(self.target)
        self.interrupt = lambda: setattr(self, "input", {"wall": 123, "monotonic": 10})
        status, answer = await self.request()
        self.assertEqual(status, 409)
        self.assertEqual(answer["error_t"]["template"], "l’utilisateur joue")
        self.assertNotIn("verified_weapon", answer)
        self.assertNotIn("verified_setup", answer)
        self.assertNotIn("result", answer)
        self.assertEqual(self.calls, [(32, "Gold-maxed", True)])
        self.assertEqual(self.game.moves, [])
        self.assertEqual(self.game.alerts, [])
        self.assertEqual(self.target, before)

    async def test_shared_lease_is_respected(self):
        self.build()
        self.game.state["busy"] = "bail tenu par mine"
        status, _ = await self.request()
        self.assertEqual(status, 409)
        self.assertEqual(self.calls, [])

    async def test_ad_hoc_target_is_refused(self):
        self.build()
        status, _ = await self.request({"mode": "mpw18", "if_revision": "accepted-1", "weapon_id": 45})
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])


class FarmRecoveryBeforePreset(unittest.IsolatedAsyncioTestCase):
    async def test_pending_empty_grid_is_completed_before_forbidden_preset(self):
        import test_soul_weapon as sw
        game = sw.vision_game(screen="battle", pieces={})
        ports = game.ports()
        async def taps(shot, screen, moves, gap, verified=()):
            for move, point in moves:
                await ports.tap(shot, screen, move, point, verified=move in verified)
                await ports.clock.sleep(gap)
        ports.taps = taps
        ports.store.saved["farming"] = {"switches": {"stage_change": "real", "preset": "real"}}
        ports.store.saved["engraving_recovery"] = {
            "required": True, "weapon_id": sw.VISION_ID, "variant": "Gold-balanced",
            "recipe": {"weapon_id": sw.VISION_ID, "name": "Gold-balanced",
                       "variant": copy.deepcopy(sw.VISION_VARIANTS["Gold-balanced"])}}
        accepted = {"stage": 920, "preset": "IV",
                    "soul_weapon": {"id": sw.VISION_ID, "variant": "Gold-balanced"}}
        soul = {"feature": sw.feature.soul_weapon, "reader": sw.fake_reader(game), "rules": sw.rules,
                "table": sw.TABLE, "loadout": lambda mode: accepted,
                "applicability": lambda chosen: {"supported": True, "engraving_required": True},
                "engraving": {"setup": sw.engraving_setup.engraving_setup,
                              "screen": sw.fake_engraving_screen(game), "rules": sw.setup_rules,
                              "variant": lambda weapon, variant: sw.VISION_VARIANTS.get(variant)}}
        original = game.apply
        def apply(screen, move, point, end=None):
            if screen == "battle" and move == "preset_badge":
                game.state["screen"] = "settings"
            else:
                original(screen, move, point, end)
        game.apply = apply
        controls = SimpleNamespace(controls=lambda shot: "folded", unfolded_now=lambda shot: False,
                                   ARROW_TAP=stage.controls.ARROW_TAP, BADGE_TAP=stage.controls.BADGE_TAP,
                                   badge=lambda shot: "II", settings_open=lambda shot: shot[2]["screen"] == "settings",
                                   selected=lambda shot: "II", preset_tap=stage.controls.preset_tap)
        select = SimpleNamespace(regions=lambda table: ["known"] * 50, battle_stage=lambda *args: 920,
                                 view=lambda *args: {"popup": False})
        screens = sw.fake_screens()
        screens.PARKED_SHADE = sw.screens.PARKED_SHADE
        part = stage.feature.stage_change(ports, screens, select, controls, sw.stage_rules, sw.STAGES, soul)
        answer = await part["api"]["farm"](920, "IV", "mpw18")
        self.assertEqual(answer["result"], "failed")
        self.assertFalse(answer["verified_setup"])
        self.assertEqual(sw.french(answer["text_t"]),
                         "Préréglage IV demandé, II lu : changement bloqué, actions en pause")
        expected = sorted(sorted(map(tuple, piece["cells"]))
                          for piece in sw.VISION_VARIANTS["Gold-balanced"]["pieces"])
        self.assertEqual(sorted(game.state["engraving"]["pieces"].values()), expected)
        self.assertTrue(all(card["locked"] for card in game.state["engraving"]["cards"]))
        recovery = part["api"]["soul_weapon_state"]()["recovery"]
        self.assertTrue(recovery["verified"])
        self.assertFalse(recovery["required"])
        self.assertNotIn(("battle_settings", "preset"), game.moves)
        self.assertIn(("soul_weapon_engraving", "close"), game.moves)
        self.assertNotIn(("battle", "preset_badge"), game.moves)
        self.assertNotIn("stage", answer["timings"], "fresh mismatch blocks before stage navigation")
        self.assertEqual(game.leases, [("stage_change", "farm mpw18")])


if __name__ == "__main__":
    unittest.main()
