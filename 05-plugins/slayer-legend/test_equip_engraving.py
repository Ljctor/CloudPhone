"""Equip invalidates engraving: persist recovery before touching the tag."""
import asyncio
import copy
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import test_soul_weapon as sw


class ResetOnEquipGame(sw.EngravingGame):
    def apply(self, screen, move, point, end=None):
        super().apply(screen, move, point, end)
        if screen == "soul_weapon" and move == "equip":
            self.state["engraving"]["pieces"].clear()
            for card in self.state["engraving"]["cards"]:
                card["placed"] = False


class EquipEngraving(unittest.IsolatedAsyncioTestCase):
    def game(self):
        return ResetOnEquipGame(screen="soul", equipped=sw.AMBITION, selected=sw.VISION_ID,
                                first_id=38, owned={sw.AMBITION, sw.VISION_ID})

    def build(self, game, saved=None, disabled=None):
        ports = game.ports()
        ports.store.saved.update(copy.deepcopy(saved or {}))
        ports.store.saved["farming"] = {"switches": {"stage_change": "real", "preset": "real"}}
        persisted = copy.deepcopy(ports.store.saved)

        def save(*, required=False):
            if (ports.store.sections.get("engraving_recovery", lambda: {})().get("phase") == "equip_pending"
                    and persisted.get("engraving_recovery", {}).get("phase") != "equip_pending"):
                self.assertTrue(required, "the pre-Equip save must demand durable persistence")
            persisted.update({key: copy.deepcopy(snapshot()) for key, snapshot in ports.store.sections.items()})

        ports.store.save = save
        allowed = ports.action_allowed
        ports.action_allowed = lambda screen, move: ((screen, move) not in
            {disabled, ("battle_settings", "preset")} and allowed(screen, move))
        loadout = {"stage": 920, "preset": "IV",
                   "soul_weapon": {"id": sw.VISION_ID, "variant": "Gold-balanced"}}
        engraving = {"setup": sw.engraving_setup.engraving_setup, "screen": sw.fake_engraving_screen(game),
                     "rules": sw.setup_rules, "variant": lambda *args: sw.VISION_VARIANTS["Gold-balanced"]}
        soul = {"feature": sw.feature.soul_weapon, "reader": sw.fake_reader(game), "rules": sw.rules,
                "table": sw.TABLE, "loadout": lambda mode: loadout, "engraving": engraving,
                "applicability": lambda chosen: {"supported": True, "engraving_required": True}}
        controls = SimpleNamespace(settings_open=lambda shot: False, badge=lambda shot: "II")
        part = sw.stage_change.stage_change(ports, sw.fake_screens(), SimpleNamespace(regions=lambda table: []),
                                            controls, sw.stage_rules, sw.STAGES, soul)
        return ports, part["api"], persisted

    def assert_ready(self, game, api):
        expected = sorted(sorted(map(tuple, piece["cells"]))
                          for piece in sw.VISION_VARIANTS["Gold-balanced"]["pieces"])
        self.assertEqual(sorted(game.state["engraving"]["pieces"].values()), expected)
        self.assertTrue(all(card["locked"] for card in game.state["engraving"]["cards"]))
        recovery = api["soul_weapon_state"]()["recovery"]
        self.assertFalse(recovery["required"])
        self.assertTrue(recovery["verified"])
        self.assertTrue(recovery["completion_verified"])

    async def interrupt_equip(self, game):
        ports, api, persisted = self.build(game)
        original = ports.tap

        async def interrupted(shot, screen, move, *args, **kwargs):
            if (screen, move) == ("soul_weapon", "equip"):
                recovery = persisted["engraving_recovery"]
                self.assertTrue(recovery["required"], "pending must reach durable storage before Equip")
                self.assertFalse(recovery["verified"])
                self.assertFalse(recovery["completion_verified"])
                self.assertEqual(recovery["weapon_id"], sw.VISION_ID)
                self.assertEqual(recovery["recipe"], {"weapon_id": sw.VISION_ID, "name": "Gold-balanced",
                                                    "variant": sw.VISION_VARIANTS["Gold-balanced"]})
                await original(shot, screen, move, *args, **kwargs)
                raise asyncio.CancelledError()
            await original(shot, screen, move, *args, **kwargs)

        ports.tap = interrupted
        with self.assertRaises(asyncio.CancelledError):
            await api["soul_weapon"]("mpw18")
        self.assertEqual(game.state["equipped"], sw.VISION_ID)
        self.assertEqual(game.state["engraving"]["pieces"], {})
        self.assertEqual(game.moves[-1], ("soul_weapon", "equip"), "cancellation must make no cleanup move")
        self.assertTrue(persisted["engraving_recovery"]["required"])
        self.assertIsNone(api["soul_weapon_state"]()["cached"])
        return copy.deepcopy(persisted)

    async def test_cancellation_inside_equip_keeps_durable_recipe_and_empty_grid_pending(self):
        await self.interrupt_equip(self.game())

    async def test_engraving_is_the_next_gesture_after_equip(self):
        game = self.game()
        _, api, _ = self.build(game)
        result = await api["soul_weapon"]("mpw18")
        self.assertEqual(result["result"], "done")
        equip_at = game.moves.index(("soul_weapon", "equip"))
        self.assertEqual(game.moves[equip_at + 1], ("soul_weapon", "engraving"))
        self.assert_ready(game, api)

    async def test_failed_pending_save_prevents_equip(self):
        game = self.game()
        ports, api, _ = self.build(game)
        before = copy.deepcopy(game.state["engraving"])

        def failed_save(*, required=False):
            self.assertTrue(required)
            raise RuntimeError("durable store unavailable")

        ports.store.save = failed_save
        result = await api["soul_weapon"]("mpw18")
        self.assertEqual(result["result"], "failed")
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        self.assertEqual(game.state["equipped"], sw.AMBITION)
        self.assertEqual(game.state["engraving"], before)

    async def test_actual_state_write_failure_prevents_equip(self):
        game = self.game()
        ports, api, _ = self.build(game)
        before = copy.deepcopy(game.state["engraving"])
        with tempfile.TemporaryDirectory() as directory:
            # A missing parent makes the real temporary-file write fail.
            state = sw.load("features/ports").State(os.path.join(directory, "missing"))
            state.sections = dict(ports.store.sections)
            state.saved = copy.deepcopy(ports.store.saved)
            ports.store = state
            result = await api["soul_weapon"]("mpw18")
            self.assertEqual(result["result"], "failed")
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        self.assertEqual(game.state["equipped"], sw.AMBITION)
        self.assertEqual(game.state["engraving"], before)

    async def test_actual_state_durable_recipe_is_reloadable_before_equip(self):
        game = self.game()
        ports, api, _ = self.build(game)
        state_module = sw.load("features/ports")
        original = ports.tap
        with tempfile.TemporaryDirectory() as directory:
            state = state_module.State(directory)
            state.sections = dict(ports.store.sections)
            state.saved = copy.deepcopy(ports.store.saved)
            ports.store = state

            async def interrupted(shot, screen, move, *args, **kwargs):
                if (screen, move) == ("soul_weapon", "equip"):
                    recovered = state_module.State(directory).saved["engraving_recovery"]
                    self.assertTrue(recovered["required"])
                    self.assertFalse(recovered["verified"])
                    self.assertEqual(recovered["phase"], "equip_pending")
                    self.assertEqual(recovered["recipe"], {"weapon_id": sw.VISION_ID, "name": "Gold-balanced",
                                                         "variant": sw.VISION_VARIANTS["Gold-balanced"]})
                    await original(shot, screen, move, *args, **kwargs)
                    raise asyncio.CancelledError()
                await original(shot, screen, move, *args, **kwargs)

            ports.tap = interrupted
            with self.assertRaises(asyncio.CancelledError):
                await api["soul_weapon"]("mpw18")
            self.assertTrue(state_module.State(directory).saved["engraving_recovery"]["required"])
        self.assertEqual(game.state["equipped"], sw.VISION_ID)
        self.assertEqual(game.state["engraving"]["pieces"], {})

    async def test_actual_state_file_or_directory_fsync_failure_prevents_equip(self):
        for failing_call in (1, 2):
            with self.subTest(fsync_call=failing_call), tempfile.TemporaryDirectory() as directory:
                game = self.game()
                ports, api, _ = self.build(game)
                before = copy.deepcopy(game.state["engraving"])
                state_module = sw.load("features/ports")
                state = state_module.State(directory)
                state.sections = dict(ports.store.sections)
                state.saved = copy.deepcopy(ports.store.saved)
                ports.store = state
                calls = []

                def failed_fsync(descriptor):
                    calls.append(descriptor)
                    if len(calls) == failing_call:
                        raise OSError("durable flush unavailable")

                with mock.patch.object(state_module.os, "fsync", side_effect=failed_fsync):
                    result = await api["soul_weapon"]("mpw18")
                self.assertEqual(result["result"], "failed")
                self.assertEqual(len(calls), failing_call)
                self.assertNotIn(("soul_weapon", "equip"), game.moves)
                self.assertEqual(game.state["equipped"], sw.AMBITION)
                self.assertEqual(game.state["engraving"], before)

    async def test_restart_on_battle_completes_grid_before_paused_preset_refusal(self):
        game = self.game()
        saved = await self.interrupt_equip(game)
        game.state.update(screen="battle", panel=None)
        game.moves.clear()
        _, api, _ = self.build(game, saved)
        result = await api["farm"](920, "IV", "mpw18")
        self.assertEqual(result["result"], "failed")
        self.assertEqual(result["failure_code"], "preset_action_paused")
        self.assertFalse(result["verified_setup"])
        self.assertIn("engraving_recovery", result["timings"])
        self.assertNotIn("stage", result["timings"])
        self.assertNotIn(("battle_settings", "preset"), game.moves)
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        self.assert_ready(game, api)

    async def test_disabled_mandatory_followup_preserves_old_equipment_and_grid(self):
        for disabled in (("soul_weapon", "engraving"), ("soul_weapon_engraving_preview", "confirm"),
                         ("soul_weapon_engraving", "lock")):
            with self.subTest(disabled=disabled):
                game = self.game()
                before = copy.deepcopy(game.state["engraving"])
                _, api, _ = self.build(game, disabled=disabled)
                result = await api["soul_weapon"]("mpw18")
                self.assertEqual(result["result"], "failed")
                self.assertNotIn(("soul_weapon", "equip"), game.moves)
                self.assertEqual(game.state["equipped"], sw.AMBITION)
                self.assertEqual(game.state["engraving"], before)


if __name__ == "__main__":
    unittest.main()
