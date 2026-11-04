"""Real Promotion/Character-tab readings and bounded, guarded menu recovery."""
import asyncio
import unittest
from unittest.mock import patch

import test_screen_model as model
import test_soul_weapon as soul

screens = model.screens


class PromotionReader(unittest.TestCase):
    def test_real_selected_promotion_and_lit_character_tab(self):
        shot = model.screen('battle_emerald', 'character_promotion_header_live_480', 'character_close_tab_lit_480')
        for size in ((480, 1040), (720, 1560)):
            seen = model.scaled(shot, *size)
            self.assertTrue(screens.character_promotion(seen))
            self.assertIn('character_promotion', screens.look(seen)['overlays'])

    def test_other_character_tabs_and_unlit_tab_never_authorize_close(self):
        for header in ('character_enhance_header', 'character_growth_header'):
            self.assertFalse(screens.character_promotion(model.screen(
                'battle_emerald', header, 'character_close_tab_lit_480')))
        self.assertFalse(screens.character_promotion(model.screen(
            'battle_emerald', 'character_promotion_header_live_480', 'character_close_tab_unlit_480')))
        self.assertFalse(screens.character_promotion(model.screen('battle_emerald', 'character_close_tab_lit_480')))

    def test_close_guard_requires_the_specific_panel_and_active_tab(self):
        seen = {'look': {'screen': 'battle', 'plain': False, 'overlays': ['panel', 'character_promotion']},
                'combat_visible': True, 'active_tab': 'character_promotion'}
        self.assertIsNone(soul.nav.guard('character_promotion', 'close_tab', .073, .966, verified=True, seen=seen))
        self.assertIn('active bottom tab', soul.nav.guard('character_promotion', 'close_tab', .073, .966,
                      verified=True, seen={**seen, 'active_tab': 'character_enhance'}))
        self.assertIn('recognised overlay', soul.nav.guard('character_promotion', 'close_tab', .073, .966,
                      verified=True, seen={**seen, 'look': {**seen['look'], 'overlays': ['panel']}}))


def build(game):
    original = soul.fake_screens()
    original.character_promotion = lambda shot: shot[2]['screen'] == 'promotion'
    old_look = original.look
    original.look = lambda shot: ({'screen': 'battle', 'plain': False, 'overlays': ['panel', 'character_promotion']}
                                 if shot[2]['screen'] == 'promotion' else old_look(shot))
    with patch.object(soul, 'fake_screens', return_value=original):
        return soul.build(game)


class MenuRecovery(unittest.TestCase):
    def test_promotion_closes_once_then_parks_without_changing_loadout(self):
        game = soul.Game(screen='promotion')
        _, api = build(game)
        before = game.state['equipped']
        answer = asyncio.run(api['back_to_battle']('mpw4'))
        self.assertEqual(answer['result'], 'done')
        self.assertEqual(game.moves, [('character_promotion', 'close_tab'), ('battle', 'menu_equipment'),
                                      ('equipment_weapon', 'soul_weapon')])
        self.assertEqual((game.state['screen'], game.state['equipped']), ('soul', before))
        self.assertEqual(game.leases, [('stage_change', 'farm mpw4')])
        self.assertNotIn('verified_setup', answer, 'parking is not proof of a complete loadout setup')

    def test_unknown_panel_stops_without_any_tap(self):
        game = soul.Game(screen='unknown')
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'failed')
        self.assertEqual(game.moves, [])

    def test_already_parked_is_not_a_new_navigation(self):
        game = soul.Game(screen='soul')
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'done')
        self.assertEqual(game.moves, [])

    def test_failed_close_is_not_repeated_and_does_not_start_parking(self):
        game = soul.Game(screen='promotion')
        game.apply = lambda *args: None
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'failed')
        self.assertEqual(game.moves, [('character_promotion', 'close_tab')])
        self.assertLessEqual(game.now, 10.25)

    def test_free_play_and_mine_never_start_recovery(self):
        for mode in ('free', 'mine', 'agent'):
            game = soul.Game(screen='promotion')
            _, api = build(game)
            self.assertEqual(asyncio.run(api['back_to_battle'](mode))['result'], 'failed')
            self.assertEqual((game.moves, game.captures), ([], 0))

    def test_soul_farming_uses_the_same_existing_parking_capability(self):
        game = soul.Game(screen='promotion')
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('soul'))['result'], 'done')
        self.assertEqual(game.state['screen'], 'soul')
        self.assertEqual(game.leases, [('stage_change', 'farm soul')])

    def test_user_interruption_after_close_stops_before_parking(self):
        game = soul.Game(screen='promotion')
        original = game.apply
        def interrupted(*args):
            original(*args)
            game.state['focused'] = False
        game.apply = interrupted
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'failed')
        self.assertEqual(game.moves, [('character_promotion', 'close_tab')])

    def test_stalled_capture_hits_the_total_deadline_and_cancels(self):
        game = soul.Game(screen='promotion')
        ports = game.ports()
        async def stalled(*args, **kwargs):
            await asyncio.Event().wait()
        ports.capture = stalled
        game.ports = lambda: ports
        _, api = build(game)
        with patch.object(soul.stage_change, 'MENU_RECOVERY_SECONDS', .01):
            answer = asyncio.run(api['back_to_battle']('mpw4'))
        self.assertEqual(answer['result'], 'failed')
        self.assertIn('interrompu', soul.french(answer['text_t']))
        self.assertEqual(game.moves, [])


if __name__ == '__main__':
    unittest.main()
