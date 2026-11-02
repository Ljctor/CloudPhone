"""Interrupted engraving resumes its durable recipe before leaving the grid."""
import asyncio
import copy
from types import SimpleNamespace
import unittest

import test_soul_weapon as sw


class Recovery(unittest.IsolatedAsyncioTestCase):
    def setup_for(self, game, saved=None, rules=None, view=None):
        ports = game.ports()
        ports.store.saved['engraving_recovery'] = copy.deepcopy(saved or {})

        async def front():
            pass

        async def poll(test, most=3):
            end = game.now + most
            while True:
                await ports.clock.sleep(.25)
                shot = await ports.capture()
                value = test(shot)
                if value or game.now >= end:
                    return shot, value

        setup = sw.engraving_setup.engraving_setup(
            ports, view or sw.fake_engraving_screen(game), rules or sw.setup_rules,
            SimpleNamespace(look=ports.capture, tap=ports.tap, front=front, Stop=sw.stage_change.Stop),
            poll, lambda shot: shot[2]['screen'] == 'soul', lambda: 'real',
            source_weapon=sw.fake_reader(game).name)
        return setup, ports

    async def apply(self, setup, game, recover=False):
        return await setup(game.snapshot(), sw.VISION, None if recover else 'Gold-balanced',
                           None if recover else sw.VISION_VARIANTS['Gold-balanced'],
                           sw.NAMES, sw.reader.CARD_FONT, sw.TABLE['shapes'], recovery_only=recover)

    def assert_complete(self, game):
        want = sorted(sorted(map(tuple, piece['cells']))
                      for piece in sw.VISION_VARIANTS['Gold-balanced']['pieces'])
        self.assertEqual(sorted(game.state['engraving']['pieces'].values()), want)
        self.assertTrue(all(card['locked'] for card in game.state['engraving']['cards']))
        self.assertEqual(game.state['screen'], 'soul')

    async def test_restart_replays_recipe_after_cancelled_removal(self):
        game = sw.vision_game(screen='engraving')
        setup, ports = self.setup_for(game)
        original = ports.swipe

        async def interrupted(*args, **kwargs):
            await original(*args, **kwargs)
            raise asyncio.CancelledError()

        ports.swipe = interrupted
        with self.assertRaises(asyncio.CancelledError):
            await self.apply(setup, game)
        saved = copy.deepcopy(setup.state())
        self.assertTrue(saved['required'])
        self.assertEqual(saved['recipe']['name'], 'Gold-balanced')
        self.assertEqual(sw.engraving_moves(game), ['remove_piece'])
        restarted, _ = self.setup_for(game, saved)
        _, result = await self.apply(restarted, game, recover=True)
        self.assertTrue(result['ok'])
        self.assert_complete(game)
        self.assertTrue(restarted.state()['verified'])
        self.assertFalse(restarted.state()['required'])

    async def test_failed_preview_keeps_recipe_pending_and_grid_open(self):
        game = sw.vision_game(screen='engraving')
        rules = SimpleNamespace(**vars(sw.setup_rules))
        rules.preview_step = lambda *args: ('cancel', rules.t('aperçu pas situé'))
        setup, _ = self.setup_for(game, rules=rules)
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game)
        saved = setup.state()
        self.assertTrue(saved['required'])
        self.assertFalse(saved['completion_verified'])
        self.assertEqual(game.state['screen'], 'engraving')
        self.assertNotIn(('soul_weapon_engraving', 'close'), game.moves)
        restarted, _ = self.setup_for(game, saved)
        _, result = await self.apply(restarted, game, recover=True)
        self.assertTrue(result['ok'])
        self.assert_complete(game)

    async def test_legacy_empty_layout_never_counts_locks_as_recovery(self):
        game = sw.vision_game(screen='engraving', pieces={})
        setup, _ = self.setup_for(game, {'required': True, 'weapon_id': sw.VISION_ID})
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game, recover=True)
        self.assertEqual(game.moves, [])
        self.assertTrue(setup.state()['required'])
        self.assertFalse(setup.state()['verified'])

    async def test_legacy_full_layout_can_close_without_certifying_recipe(self):
        game = sw.vision_game(screen='engraving')
        setup, _ = self.setup_for(game, {'required': True, 'weapon_id': sw.VISION_ID})
        _, result = await self.apply(setup, game, recover=True)
        self.assertTrue(result['ok'])
        self.assertTrue(setup.state()['completion_verified'])
        self.assertFalse(setup.state()['verified'])
        self.assertTrue(setup.state()['required'])
        self.assertEqual(sw.engraving_moves(game), ['close'])

    async def test_pending_other_weapon_cannot_erase_durable_target(self):
        game = sw.vision_game(screen='engraving')
        saved = {'required': True, 'weapon_id': sw.AMBITION, 'variant': 'Gold-maxed'}
        setup, _ = self.setup_for(game, saved)
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game, recover=True)
        self.assertEqual(game.moves, [])
        self.assertEqual(setup.state()['weapon_id'], sw.AMBITION)
        self.assertEqual(setup.state()['variant'], 'Gold-maxed')

    async def test_changed_weapon_keeps_both_intents_and_restart_recovers_matching_archive(self):
        game = sw.vision_game(screen='engraving')
        setup, ports = self.setup_for(game)
        original = ports.swipe

        async def interrupted(*args, **kwargs):
            await original(*args, **kwargs)
            raise asyncio.CancelledError()

        ports.swipe = interrupted
        with self.assertRaises(asyncio.CancelledError):
            await self.apply(setup, game)
        old = copy.deepcopy(setup.state())
        # A different requested target gets its own durable intent even when
        # its preparation fails before input (the capture still shows Vision).
        requested = next(entry for entry in sw.TABLE['weapons'] if entry['id'] == sw.AMBITION)
        variants = sw.engraving_rules.variants(requested, sw.engraving_rules.any_orientation(sw.TABLE))
        new_name = next(iter(variants))
        ports.swipe = original
        before_moves = list(game.moves)
        with self.assertRaises(sw.stage_change.Stop):
            await setup(game.snapshot(), requested, new_name, variants[new_name], sw.NAMES,
                        sw.reader.CARD_FONT, sw.TABLE['shapes'])
        changed = copy.deepcopy(setup.state())
        self.assertEqual(game.moves, before_moves, 'a mismatched capture cannot mutate either weapon')
        self.assertEqual(changed['weapon_id'], sw.AMBITION)
        self.assertEqual(changed['recipe']['name'], new_name)
        archived = changed['pending_by_weapon'][str(sw.VISION_ID)]
        self.assertEqual(archived['recipe'], old['recipe'])
        self.assertTrue(archived['required'])
        self.assertNotIn('pending_by_weapon', archived)
        # After a process restart, only the recognised weapon's archived
        # recipe may run. The other requested target remains pending.
        restarted, _ = self.setup_for(game, changed)
        _, result = await self.apply(restarted, game, recover=True)
        self.assertTrue(result['ok'])
        self.assert_complete(game)
        recovered = restarted.state()
        self.assertFalse(recovered['required'], 'current target has now been verified')
        self.assertNotIn(str(sw.VISION_ID), recovered['pending_by_weapon'])
        self.assertEqual(recovered['pending_by_weapon'][str(sw.AMBITION)]['recipe'], changed['recipe'])
        self.assertTrue(recovered['pending_by_weapon'][str(sw.AMBITION)]['required'])
        self.assertNotIn('pending_by_weapon', recovered['pending_by_weapon'][str(sw.AMBITION)])

    async def test_successful_new_target_does_not_clear_other_weapon_archive(self):
        game = sw.vision_game(screen='engraving')
        prior = {'required': True, 'weapon_id': sw.AMBITION, 'variant': 'Gold-maxed',
                 'recipe': {'weapon_id': sw.AMBITION, 'name': 'Gold-maxed', 'variant': {'pieces': []}}}
        setup, _ = self.setup_for(game, prior)
        _, result = await self.apply(setup, game)
        self.assertTrue(result['ok'])
        self.assertFalse(setup.state()['required'])
        self.assertEqual(setup.state()['pending_by_weapon'][str(sw.AMBITION)], prior)
        self.assert_complete(game)

    async def test_unequipped_screen_without_inventory_never_grants_mutation(self):
        # Real unequipped engravings show the grid and the text "This Soul
        # Weapon is not equipped." in place of all eight inventory cards.
        # The card reader returns eight unread slots, not usable cards.
        game = sw.vision_game(screen='engraving')
        game.state['equipped'] = sw.AMBITION
        view = sw.fake_engraving_screen(game)
        view.cards = lambda *args: [dict(index=index, shape=None, level=None, kind=None,
                                        locked=None, placed=None, bright=None) for index in range(8)]
        setup, _ = self.setup_for(game, view=view)
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game)
        self.assertEqual(game.moves, [])
        self.assertEqual(game.state['equipped'], sw.AMBITION)
        self.assertFalse(setup.state()['verified'])
        self.assertTrue(setup.state()['required'])

    async def test_transient_unread_identity_is_observed_until_two_named_grid_frames(self):
        game = sw.vision_game(screen='engraving')
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda shot, *args: None if 0 < shot[2]['now'] < .75 else 'Vision'
        setup, ports = self.setup_for(game, view=view)
        inputs = []
        swipe = ports.swipe

        async def timed_swipe(*args, **kwargs):
            inputs.append(game.now)
            await swipe(*args, **kwargs)

        # helpers.tap captured ports.tap during construction; record game
        # application itself as well, including padlock corner inputs.
        original_apply = game.apply
        def applied(*args, **kwargs):
            inputs.append(game.now)
            return original_apply(*args, **kwargs)
        game.apply = applied
        ports.swipe = timed_swipe
        with self.assertLogs(level='WARNING') as logs:
            _, result = await self.apply(setup, game)
        self.assertTrue(result['ok'])
        self.assert_complete(game)
        self.assertGreaterEqual(min(inputs), 1.0)
        self.assertTrue(any('steady' in line and 'captures=4 unread=2' in line and 'matched=True' in line
                            for line in logs.output))

    async def test_lock_polling_waits_read_only_for_transient_unread_name(self):
        game = sw.vision_game(screen='engraving')
        unavailable_until = [0]
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda shot, *args: None if shot[2]['now'] < unavailable_until[0] else 'Vision'
        original = game.apply
        def apply(screen, move, point, end=None):
            original(screen, move, point, end)
            if move == 'lock':
                unavailable_until[0] = game.now + .75
        game.apply = apply
        setup, _ = self.setup_for(game, view=view)
        with self.assertLogs(level='WARNING') as logs:
            _, result = await self.apply(setup, game)
        self.assertTrue(result['ok'])
        self.assert_complete(game)
        self.assertTrue(any('(wait)' in line and 'unread=2' in line and 'matched=True' in line
                            for line in logs.output))

    async def test_persistently_unread_identity_after_remove_times_out_without_cleanup_input(self):
        game = sw.vision_game(screen='engraving')
        removed_at = []
        original = game.apply
        def apply(screen, move, point, end=None):
            original(screen, move, point, end)
            if move == 'remove_piece':
                removed_at.append(game.now)
        game.apply = apply
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda shot, *args: None if removed_at else 'Vision'
        setup, _ = self.setup_for(game, view=view)
        with self.assertLogs(level='WARNING') as logs:
            with self.assertRaises(sw.stage_change.Stop):
                await self.apply(setup, game)
        self.assertEqual(sw.engraving_moves(game), ['remove_piece'])
        self.assertLessEqual(game.now - removed_at[0], 3.25)
        self.assertTrue(setup.state()['required'])
        self.assertFalse(setup.state()['verified'])
        self.assertTrue(any('steady' in line and 'unread=12' in line and 'matched=False' in line
                            for line in logs.output))

    async def test_readable_wrong_name_after_remove_stops_on_first_capture(self):
        game = sw.vision_game(screen='engraving')
        removed_at = []
        original = game.apply
        def apply(screen, move, point, end=None):
            original(screen, move, point, end)
            if move == 'remove_piece':
                removed_at.append(game.now)
        game.apply = apply
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda shot, *args: 'Ambition' if removed_at else 'Vision'
        setup, _ = self.setup_for(game, view=view)
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game)
        self.assertEqual(sw.engraving_moves(game), ['remove_piece'])
        self.assertLessEqual(game.now - removed_at[0], .25)
        self.assertTrue(setup.state()['required'])

    async def test_gesture_identity_remains_strict_after_stable_observation(self):
        game = sw.vision_game(screen='engraving')
        game.state['engraving']['cards'][0]['locked'] = False
        view = sw.fake_engraving_screen(game)
        def lock_point(index):
            # Invalidate identity after the stable read but before the tap's
            # own guard. Last-known identity must never authorize this input.
            view.weapon = lambda *args: None
            return sw.es.lock_point(index)
        view.lock_point = lock_point
        setup, _ = self.setup_for(game, view=view)
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game)
        self.assertEqual(game.moves, [])
        self.assertTrue(setup.state()['required'])

    async def test_forbidden_relock_stops_before_removal(self):
        game = sw.vision_game(screen='engraving')
        setup, ports = self.setup_for(game)
        ports.action_allowed = lambda screen, move: move != 'lock'
        with self.assertRaises(sw.stage_change.Stop):
            await self.apply(setup, game)
        self.assertEqual(game.moves, [])
        self.assertTrue(all(card['locked'] for card in game.state['engraving']['cards']))


if __name__ == '__main__':
    unittest.main()
