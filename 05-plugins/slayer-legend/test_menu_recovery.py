"""Real Latent Power/Promotion readings and bounded, guarded menu recovery."""
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


class GrowthReader(unittest.TestCase):
    def test_real_selected_growth_and_lit_character_tab(self):
        shot = model.screen('battle_emerald', 'character_growth_header', 'character_close_tab_lit_480')
        for size in ((360, 780), (480, 1040), (720, 1560)):
            seen = model.scaled(shot, *size)
            self.assertTrue(screens.character_growth(seen))
            overlays = screens.look(seen)['overlays']
            self.assertIn('character_growth', overlays)
            self.assertNotIn('character_enhance', overlays)
            self.assertNotIn('character_promotion', overlays)

    def test_other_headers_unknown_and_unlit_tab_refuse_growth_close(self):
        for header in ('character_enhance_header', 'character_promotion_header_live_480'):
            self.assertFalse(screens.character_growth(model.screen(
                'battle_emerald', header, 'character_close_tab_lit_480')))
        self.assertFalse(screens.character_growth(model.screen(
            'battle_emerald', 'character_growth_header', 'character_close_tab_unlit_480')))
        self.assertFalse(screens.character_growth(model.screen('battle_emerald', 'character_close_tab_lit_480')))
        for key in model.REGISTERED:
            if key != 'character_growth':
                self.assertFalse(screens.character_growth(model.made(key)), key)

    def test_guard_requires_specific_identity_lit_tab_and_visible_battle(self):
        seen = {'look': {'screen': 'battle', 'plain': False, 'overlays': ['panel', 'character_growth']},
                'combat_visible': True, 'active_tab': 'character_growth'}
        self.assertIsNone(soul.nav.guard('character_growth', 'close_tab', .073, .966, verified=True, seen=seen))
        for bad in (None, dict(seen, active_tab='character_enhance'), dict(seen, combat_visible=False),
                    dict(seen, look={'screen': 'battle', 'plain': False, 'overlays': ['panel']})):
            self.assertIsNotNone(soul.nav.guard('character_growth', 'close_tab', .073, .966, verified=True, seen=bad))
        self.assertIsNotNone(soul.nav.guard('character_growth', 'close_tab', .073, .966, seen=seen))
        move = next(move for move in soul.nav.connections('character_growth') if move['id'] == 'close_tab')
        self.assertFalse(move['assumed'], 'The close-tab return has supervised gameplay evidence')


class GrowthRecovery(unittest.TestCase):
    def test_fast_menu_capability_excludes_unrecognised_and_other_screens(self):
        for name in ('growth', 'promotion', 'latent_power', 'unknown', 'battle', 'equipment', 'soul'):
            game = soul.Game(screen=name)
            _, api = build(game)
            self.assertEqual(api['menu_recoverable'](game.snapshot()),
                             name in ('growth', 'promotion', 'latent_power'))


    def test_growth_closes_once_then_parks_without_changing_equipment(self):
        for mode in ('mpw4', 'mpw18', 'soul'):
            game = soul.Game(screen='growth')
            before = (game.state['equipped'], game.state['selected'])
            _, api = build(game)
            answer = asyncio.run(api['back_to_battle'](mode))
            self.assertEqual(answer['result'], 'done')
            self.assertEqual(game.moves, [('character_growth', 'close_tab'), ('battle', 'menu_equipment'),
                                          ('equipment_weapon', 'soul_weapon')])
            self.assertEqual((game.state['equipped'], game.state['selected']), before)
            self.assertNotIn('verified_setup', answer)

    def test_latent_return_growth_is_reread_before_its_own_close(self):
        game = LatentPowerRecovery().game('growth')
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('soul'))['result'], 'done')
        self.assertEqual(game.moves, [('latent_power', 'close'), ('character_growth', 'close_tab'),
                                      ('battle', 'menu_equipment'), ('equipment_weapon', 'soul_weapon')])

    def test_failed_tab_close_never_repeats_and_never_parks(self):
        game = soul.Game(screen='growth')
        game.apply = lambda *args: None
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'failed')
        self.assertEqual(game.moves, [('character_growth', 'close_tab')])
        self.assertLessEqual(game.now, 10.25)

    def test_user_interruption_after_close_stops_before_parking(self):
        game = soul.Game(screen='growth')
        original = game.apply
        def apply(*args):
            original(*args)
            game.state['focused'] = False
        game.apply = apply
        _, api = build(game)
        asyncio.run(api['back_to_battle']('soul'))
        self.assertEqual(game.moves, [('character_growth', 'close_tab')])

    def test_free_mine_agent_never_capture_or_move(self):
        for mode in ('free', 'mine', 'agent'):
            game = soul.Game(screen='growth')
            _, api = build(game)
            self.assertEqual(asyncio.run(api['back_to_battle'](mode))['result'], 'failed')
            self.assertEqual((game.moves, game.captures), ([], 0))


class LatentPowerReader(unittest.TestCase):
    PARTS = ('latent_power_title_480', 'latent_power_description_480', 'latent_power_close_480')

    def test_complete_real_landmarks_scale_and_name_the_opaque_panel(self):
        for size in ((360, 780), (480, 1040), (720, 1560)):
            shot = model.scaled(model.screen(*self.PARTS, background=(12, 6, 3)), *size)
            self.assertTrue(screens.latent_power(shot))
            found = screens.look(shot)
            self.assertEqual(found['screen'], 'latent_power')
            self.assertEqual(found['battle_viewport']['size'], 'none')
            self.assertEqual(screens.classify(shot), 'menu')
            self.assertFalse(found['plain'])

    def test_each_missing_landmark_refuses_and_neighbours_stay_distinct(self):
        for missing in self.PARTS:
            shot = model.screen(*(name for name in self.PARTS if name != missing))
            self.assertFalse(screens.latent_power(shot), missing)
            self.assertNotEqual(screens.look(shot)['screen'], 'latent_power')
        for key in model.REGISTERED:
            if key != 'latent_power':
                self.assertFalse(screens.latent_power(model.made(key)), key)
        # Real Growth/Promotion headers plus a shared red X are insufficient.
        for header in ('character_growth_header', 'character_promotion_header_live_480', 'eg_title', 'sw_title'):
            self.assertFalse(screens.latent_power(model.screen(header, self.PARTS[-1])))

    def test_guard_requires_fresh_identity_and_refuses_every_control(self):
        seen = {'look': {'screen': 'latent_power', 'overlays': [], 'plain': False}}
        point = screens.LATENT_POWER_CLOSE
        self.assertIsNone(soul.nav.guard('latent_power', 'close', *point, verified=True, seen=seen))
        self.assertIsNotNone(soul.nav.guard('latent_power', 'close', *point, seen=seen))
        for bad in (None, {'look': {'screen': 'unknown'}}, {'look': {'screen': 'battle'}}):
            self.assertIsNotNone(soul.nav.guard('latent_power', 'close', *point, verified=True, seen=bad))
        self.assertIsNotNone(soul.nav.guard('latent_power', 'panel_controls', .5, .85, verified=True, seen=seen))
        self.assertIsNotNone(soul.nav.guard('latent_power', 'close', .5, .85, verified=True, seen=seen))
        self.assertEqual(soul.nav.connections('latent_power')[0]['to'], 'unknown')


class LatentPowerRecovery(unittest.TestCase):
    def game(self, destination='battle', after_close=None):
        game = soul.Game(screen='latent_power')
        original = game.apply
        def apply(screen, move, point):
            original(screen, move, point)
            if screen == 'latent_power' and move == 'close':
                game.state['screen'] = destination
                if after_close:
                    after_close(game)
        game.apply = apply
        return game

    def test_one_close_then_verified_battle_parks_under_existing_lease(self):
        for mode in ('mpw4', 'mpw18', 'soul'):
            game = self.game()
            before = (game.state['equipped'], game.state['selected'])
            _, api = build(game)
            answer = asyncio.run(api['back_to_battle'](mode))
            self.assertEqual(answer['result'], 'done')
            self.assertEqual(game.moves, [('latent_power', 'close'), ('battle', 'menu_equipment'),
                                          ('equipment_weapon', 'soul_weapon')])
            self.assertEqual((game.state['equipped'], game.state['selected']), before)
            self.assertEqual(game.leases, [('stage_change', 'farm '+mode)])
            self.assertNotIn('verified_setup', answer)

    def test_known_promotion_return_closes_only_its_calibrated_tab(self):
        game = self.game('promotion')
        _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('soul'))['result'], 'done')
        self.assertEqual(game.moves, [('latent_power', 'close'), ('character_promotion', 'close_tab'),
                                      ('battle', 'menu_equipment'), ('equipment_weapon', 'soul_weapon')])

    def test_falsely_lit_tab_on_unknown_return_cannot_authorize_a_second_tap(self):
        game = self.game('unrecognised_growth')
        original = soul.fake_screens()
        original.open_tab = lambda shot: (.073, 'character_enhance') if shot[2]['screen'] == 'unrecognised_growth' else None
        with patch.object(soul, 'fake_screens', return_value=original):
            _, api = build(game)
        self.assertEqual(asyncio.run(api['back_to_battle']('mpw4'))['result'], 'failed')
        self.assertEqual(game.moves, [('latent_power', 'close')])

    def test_unknown_destination_or_unchanged_panel_never_repeats_close(self):
        for destination in ('unknown', 'latent_power', 'unrecognised_growth'):
            game = self.game(destination)
            _, api = build(game)
            answer = asyncio.run(api['back_to_battle']('mpw4'))
            self.assertEqual(answer['result'], 'failed')
            self.assertEqual(game.moves, [('latent_power', 'close')])
            self.assertLessEqual(game.now, 10.25)

    def test_interruption_after_close_prevents_second_gesture(self):
        game = self.game(after_close=lambda game: game.state.update(focused=False))
        _, api = build(game)
        asyncio.run(api['back_to_battle']('mpw4'))
        self.assertEqual(game.moves, [('latent_power', 'close')])

    def test_free_agent_mine_never_even_capture(self):
        for mode in ('free', 'agent', 'mine'):
            game = self.game()
            _, api = build(game)
            self.assertEqual(asyncio.run(api['back_to_battle'](mode))['result'], 'failed')
            self.assertEqual((game.moves, game.captures), ([], 0))


def build(game):
    original = soul.fake_screens()
    original.LATENT_POWER_CLOSE = screens.LATENT_POWER_CLOSE
    original.latent_power = lambda shot: shot[2]["screen"] == "latent_power"
    original.character_growth = lambda shot: shot[2]["screen"] == "growth"
    original.character_promotion = lambda shot: shot[2]['screen'] == 'promotion'
    old_look = original.look
    original.look = lambda shot: ({'screen': 'battle', 'plain': False, 'overlays': ['panel', 'character_promotion']}
                                 if shot[2]['screen'] == 'promotion' else
                                 {'screen': 'battle', 'plain': False, 'overlays': ['panel', 'character_growth']}
                                 if shot[2]['screen'] == 'growth' else
                                 {"screen": "latent_power", "overlays": [], "plain": False}
                                 if shot[2]['screen'] == 'latent_power' else old_look(shot))
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
