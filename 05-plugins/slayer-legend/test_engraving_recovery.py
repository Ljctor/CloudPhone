"""Interrupted engraving resumes its durable recipe before leaving the grid."""
import asyncio
import copy
import inspect
import os
import tempfile
from types import SimpleNamespace
import unittest

import test_soul_weapon as sw


class Recovery(unittest.IsolatedAsyncioTestCase):
    def setup_for(self, game, saved=None, rules=None, view=None, front=None):
        ports = game.ports()
        ports.store.saved['engraving_recovery'] = copy.deepcopy(saved or {})

        async def unchecked_front():
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
            SimpleNamespace(look=ports.capture, tap=ports.tap, front=front or unchecked_front,
                            Stop=sw.stage_change.Stop),
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

    async def test_revocation_during_identity_analysis_prevents_each_drag_kind(self):
        for move in ('remove_piece', 'drag_piece', 'move'):
            with self.subTest(move=move):
                game = sw.vision_game(screen='engraving', **({} if move == 'remove_piece' else {'pieces': {}}))
                owner = {'mode': 'agent'}
                revoked = []

                async def front():
                    if owner['mode'] != 'agent':
                        raise ports.Busy('mode Agent indisponible')

                setup, ports = self.setup_for(game, front=front)
                analyse = ports.analyse
                if move == 'move':
                    apply = game.apply

                    def shifted_preview(screen, action, point, end=None):
                        apply(screen, action, point, end)
                        if action == 'drag_piece':
                            preview = game.state['engraving']['preview']
                            preview['cells'] = [(r, c + 1) for r, c in preview['cells']]
                            row, col = preview['pivot']
                            preview['pivot'] = (row, col + 1)

                    game.apply = shifted_preview

                async def revoke_after_identity(fn, *args):
                    # Fault injection at the actual awaited identity boundary,
                    # after the caller's old guard and before Android input.
                    caller = inspect.currentframe().f_back
                    gesture = caller.f_locals.get('args', ())
                    is_target = (caller.f_code.co_name == 'swipe' and len(gesture) > 1
                                 and gesture[1] == move and fn.__name__ == 'identity')
                    del caller
                    result = await analyse(fn, *args)
                    if is_target:
                        owner['mode'] = 'free'
                        revoked.append(list(game.moves))
                    return result

                ports.analyse = revoke_after_identity
                with self.assertRaises(ports.Busy):
                    await self.apply(setup, game)
                self.assertEqual(len(revoked), 1, 'the real drag identity analysis must be reached')
                self.assertEqual(game.moves, revoked[0], 'no gesture may follow ownership revocation')
                self.assertNotIn(move, sw.engraving_moves(game))
                self.assertTrue(setup.state()['required'])
                self.assertFalse(setup.state()['verified'])
                self.assertFalse(setup.state()['completion_verified'])
                self.assertEqual(setup.state()['recipe']['name'], 'Gold-balanced')

    async def test_already_equipped_repair_refuses_unwritable_recovery_journal(self):
        game = sw.vision_game(screen='engraving')
        setup, ports = self.setup_for(game)
        before = copy.deepcopy(game.state['engraving'])
        with tempfile.TemporaryDirectory() as directory:
            state = sw.load('features/ports').State(os.path.join(directory, 'missing'))
            state.sections = dict(ports.store.sections)
            ports.store = state
            with self.assertRaises(sw.stage_change.Stop) as stopped:
                await self.apply(setup, game)
            self.assertIsInstance(stopped.exception.__cause__, OSError)
        self.assertEqual(game.moves, [], 'an existing loadout must survive a journal failure')
        self.assertEqual(game.state['engraving'], before)
        self.assertFalse(setup.state()['verified'])

    async def test_existing_weapon_repair_survives_restart_from_real_journal(self):
        game = sw.vision_game(screen='engraving')
        setup, ports = self.setup_for(game)
        state_module = sw.load('features/ports')
        original = ports.swipe
        with tempfile.TemporaryDirectory() as directory:
            state = state_module.State(directory)
            state.sections = dict(ports.store.sections)
            ports.store = state

            async def interrupt_after_removal(*args, **kwargs):
                # Read only the actual on-disk journal, not setup.state().
                pending = state_module.State(directory).saved['engraving_recovery']
                self.assertTrue(pending['required'])
                self.assertEqual(pending['recipe']['name'], 'Gold-balanced')
                await original(*args, **kwargs)
                raise asyncio.CancelledError()

            ports.swipe = interrupt_after_removal
            with self.assertRaises(asyncio.CancelledError):
                await self.apply(setup, game)
            persisted = state_module.State(directory).saved['engraving_recovery']
            restarted, _ = self.setup_for(game, persisted)
            _, result = await self.apply(restarted, game, recover=True)
            self.assertTrue(result['ok'])
            self.assert_complete(game)

    def test_real_relax_overlap_preserves_the_learned_relative_pickup(self):
        base = [(0, 0), (1, 0), (2, 0), (2, 1)]
        under = {(1, 1), (2, 0), (2, 1), (3, 1),
                 (1, 2), (2, 2), (3, 2), (4, 2), (1, 3), (2, 3), (3, 3), (4, 3)}
        # Current prepare frame031: only this upper-left cube is exposed;
        # its other three cells overlap the already placed T and two I.
        initial = ((1, 0), (1, 1), (1, 2), (2, 0))
        pickup, key = sw.setup_rules.preview_pickup(initial, under, under | {(1, 0)})
        self.assertEqual((pickup, key[1]), ((1, 0), (0, 0)))
        # Reviewed real crop: same one-column-left landing as current frame032.
        observed = sw.es.cubes(sw.fixtures.screen('eg_relax_preview_l-left-after-move'))
        landed = sw.setup_rules.unique_preview_cells(under, observed, base, 1)
        self.assertEqual(landed, ((0, -1), (0, 0), (0, 1), (1, -1)))
        learned = {key: sw.setup_rules.landing_response(landed, (1.7, 0))}
        picked, reused = sw.setup_rules.preview_pickup(landed, under, observed, learned)
        self.assertEqual(picked, (0, -1), 'keep relative(0,0), not newly exposed bottom cube(1,-1)')
        self.assertEqual(reused, key)
        target = [(0, 0), (0, 1), (0, 2), (1, 0)]
        endpoint = sw.setup_rules.landing_endpoint(target, learned[reused])
        self.assertEqual(endpoint, (1.7, 1))
        self.assertTrue(sw.nav.move_contains('soul_weapon_engraving_preview', 'move', sw.es.cell_centre(*endpoint)))
        self.assertIsNone(sw.setup_rules.preview_pickup(landed, under | {picked}, observed, learned))
        self.assertIsNone(sw.setup_rules.preview_pickup(landed, under, set(observed) - {picked}, learned),
                          'an inferred but unread cube cannot be picked')
        self.assertIsNone(sw.setup_rules.preview_pickup(landed, under, observed,
                          {(tuple(sw.setup_rules.normalised(base)), (0, 0)): learned[reused]}),
                          'another orientation cannot lend its response')

    async def test_removal_waits_for_postcondition_instead_of_stable_animation(self):
        for transition in ('old_frame', 'unknown_E', 'preview'):
            with self.subTest(transition=transition):
                game = sw.vision_game(screen='engraving')
                view = sw.fake_engraving_screen(game)
                original_apply = game.apply
                before, removed_at, removed_index, locks = [], [], [], []

                def apply(screen, move, point, end=None):
                    previous = game.snapshot()
                    original_apply(screen, move, point, end)
                    if move == 'remove_piece' and not removed_at:
                        before.append(previous)
                        removed_at.append(game.now)
                        removed_index.append(next(i for i, card in enumerate(game.state['engraving']['cards'])
                            if previous[2]['engraving']['cards'][i]['placed'] and not card['placed']))
                    elif move == 'lock' and removed_at:
                        locks.append(game.now)

                game.apply = apply
                grid, cards, bar = view.grid, view.cards, view.bar
                pending = lambda: removed_at and game.now < removed_at[0] + 1.5
                view.grid = lambda shot, size: grid(before[0], size) if pending() and transition == 'old_frame' else grid(shot, size)

                def animated_cards(shot, shapes):
                    result = cards(before[0] if pending() and transition == 'old_frame' else shot, shapes)
                    if pending() and transition == 'unknown_E':
                        result[removed_index[0]]['placed'] = None
                    return result

                view.cards = animated_cards
                view.bar = lambda shot: {'valid': False} if pending() and transition == 'preview' else bar(shot)
                setup, _ = self.setup_for(game, view=view)
                _, result = await self.apply(setup, game)
                self.assertTrue(result['ok'], result)
                self.assert_complete(game)
                self.assertGreaterEqual(locks[0], removed_at[0] + 1.75,
                                        'two matching postcondition reads must precede relocking')
                self.assertEqual(sw.engraving_moves(game).count('remove_piece'), 4,
                                 'each original piece is removed once; an animation never repeats a drag')

    async def test_removal_timeout_never_repeats_drag_and_still_relocks_visible_card(self):
        game = sw.vision_game(screen='engraving')
        removed_at, removed_index = [], []
        apply = game.apply
        def record_removal(screen, move, point, end=None):
            previous = game.snapshot()
            apply(screen, move, point, end)
            if move == 'remove_piece':
                removed_at.append(game.now)
                removed_index.append(next(i for i, card in enumerate(game.state['engraving']['cards'])
                    if previous[2]['engraving']['cards'][i]['placed'] and not card['placed']))
        game.apply = record_removal
        view = sw.fake_engraving_screen(game)
        cards = view.cards
        def unknown_E(shot, shapes):
            result = cards(shot, shapes)
            if removed_index:
                result[removed_index[0]]['placed'] = None
            return result
        view.cards = unknown_E
        setup, _ = self.setup_for(game, view=view)
        with self.assertLogs(level='WARNING') as logs:
            with self.assertRaises(sw.stage_change.Stop):
                await self.apply(setup, game)
        self.assertEqual(sw.engraving_moves(game).count('remove_piece'), 1)
        self.assertTrue(all(c['locked'] for c in game.state['engraving']['cards']))
        self.assertLessEqual(game.now - removed_at[0], 12)
        self.assertTrue(setup.state()['required'])
        self.assertTrue(any('removal diagnostic:' in line and '"phase":"timeout"' in line for line in logs.output))

    async def test_input_revocation_while_waiting_for_removal_sends_no_cleanup_gesture(self):
        game = sw.vision_game(screen='engraving')
        removed_at = []
        original_apply = game.apply
        def apply(screen, move, point, end=None):
            original_apply(screen, move, point, end)
            if move == 'remove_piece':
                removed_at.append(game.now)
        game.apply = apply
        setup, ports = self.setup_for(game)
        capture = ports.capture
        async def guarded_capture(*args, **kwargs):
            if removed_at:
                # Existing port/sequence guard refuses a new frame once the
                # human's input has revoked this operation's ownership.
                raise ports.Busy('l’utilisateur joue')
            return await capture(*args, **kwargs)
        ports.capture = guarded_capture
        with self.assertRaises(ports.Busy):
            await self.apply(setup, game)
        self.assertEqual(sw.engraving_moves(game), ['remove_piece'])
        self.assertTrue(setup.state()['required'])
        self.assertFalse(setup.state()['verified'])

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
        self.assertLessEqual(game.now - removed_at[0], 10.25)
        self.assertTrue(setup.state()['required'])
        self.assertFalse(setup.state()['verified'])
        self.assertTrue(any('(wait)' in line and 'unread=40' in line and 'matched=False' in line
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

    def coordinator(self, game, saved, variant='Gold-balanced', view=None):
        original = game.ports
        def restored_ports():
            ports = original()
            ports.store.saved['engraving_recovery'] = copy.deepcopy(saved)
            return ports
        game.ports = restored_ports
        part = {'setup': sw.engraving_setup.engraving_setup, 'screen': view or sw.fake_engraving_screen(game),
                'rules': sw.setup_rules, 'variant': lambda weapon_id, name: sw.VISION_VARIANTS.get(name)}
        loadouts = {'mpw18': {'stage': 920, 'preset': None,
                              'soul_weapon': {'id': sw.VISION_ID, 'variant': variant}}}
        stage_reader = SimpleNamespace(regions=lambda table: ['known'] * 50,
                                       battle_stage=lambda shot, names, *args: 920)
        return sw.build(game, loadouts, part, stage_reader)

    async def test_restart_legacy_empty_grid_completes_through_full_farm_coordinator(self):
        game = sw.vision_game(screen='engraving', pieces={}, farming={'switches': {'stage_change': 'real'}})
        for card in game.state['engraving']['cards']:
            card['locked'] = False
        saved = {'required': True, 'weapon_id': sw.VISION_ID, 'variant': 'Gold-balanced', 'phase': 'failed'}
        ports, api = self.coordinator(game, saved)
        answer = await api['farm'](920, None, 'mpw18')
        self.assertEqual(answer['result'], 'done', answer)
        self.assertTrue(answer['verified_setup'])
        self.assert_complete(game)
        state = ports.store.sections['engraving_recovery']()
        self.assertFalse(state['required'])
        self.assertTrue(state['verified'])
        self.assertEqual(state['recipe']['variant'], sw.VISION_VARIANTS['Gold-balanced'])

    async def test_no_history_uses_explicit_matching_target_for_empty_or_complete_grid(self):
        for empty in (True, False):
            with self.subTest(empty=empty):
                game = sw.vision_game(screen='engraving', pieces={} if empty else None,
                                      farming={'switches': {'stage_change': 'real'}})
                _, api = self.coordinator(game, {})
                answer = await api['farm'](920, None, 'mpw18')
                self.assertEqual(answer['result'], 'done', answer)
                self.assertTrue(answer['verified_setup'])
                self.assert_complete(game)

    async def test_no_history_other_visible_weapon_only_allows_safe_full_grid_closure(self):
        for empty in (True, False):
            with self.subTest(empty=empty):
                game = sw.vision_game(screen='engraving', pieces={} if empty else None)
                ports = game.ports()
                async def front():
                    pass
                helpers = SimpleNamespace(look=ports.capture, tap=ports.tap, front=front,
                                          Stop=sw.stage_change.Stop, to_battle=None)
                part = {'setup': sw.engraving_setup.engraving_setup, 'screen': sw.fake_engraving_screen(game),
                        'rules': sw.setup_rules, 'variant': lambda weapon_id, name: sw.VISION_VARIANTS.get(name)}
                api = sw.feature.soul_weapon(ports, sw.fake_screens(), sw.fake_reader(game), sw.rules,
                                            sw.TABLE, helpers, part)
                target = {'id': sw.AMBITION, 'variant': 'Gold-maxed'}
                if empty:
                    with self.assertRaises(sw.stage_change.Stop):
                        await api['recover_engraving'](game.snapshot(), target=target)
                    self.assertEqual(game.moves, [])
                else:
                    await api['recover_engraving'](game.snapshot(), target=target)
                    self.assertEqual(sw.engraving_moves(game), ['close'])
                self.assertNotIn(('soul_weapon', 'equip'), game.moves)

    async def test_permanently_unread_recovery_entry_is_bounded_and_has_no_input(self):
        game = sw.vision_game(screen='engraving', pieces={}, farming={'switches': {'stage_change': 'real'}})
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda *args: None
        saved = {'required': True, 'weapon_id': sw.VISION_ID, 'variant': 'Gold-balanced'}
        _, api = self.coordinator(game, saved, view=view)
        answer = await api['farm'](920, None, 'mpw18')
        self.assertEqual(answer['result'], 'failed')
        self.assertFalse(answer['verified_setup'])
        self.assertEqual(game.moves, [])
        self.assertGreaterEqual(game.now, sw.feature.SCREEN_WAIT_MOST)
        self.assertLessEqual(game.now, sw.feature.SCREEN_WAIT_MOST + .5)

    async def test_durable_recipe_precedes_explicit_current_variant_during_recovery(self):
        game = sw.vision_game(screen='engraving', pieces={}, farming={'switches': {'stage_change': 'real'}})
        saved = {'required': True, 'weapon_id': sw.VISION_ID, 'variant': 'Atk',
                 'recipe': {'weapon_id': sw.VISION_ID, 'name': 'Atk', 'variant': sw.VISION_VARIANTS['Atk']}}
        completed = []
        original = game.apply
        def apply(screen, move, point, end=None):
            if (screen, move) == ('soul_weapon_engraving', 'close'):
                completed.append(copy.deepcopy(game.state['engraving']['pieces']))
            original(screen, move, point, end)
        game.apply = apply
        _, api = self.coordinator(game, saved)
        answer = await api['farm'](920, None, 'mpw18')
        self.assertEqual(answer['result'], 'done', answer)
        self.assertTrue(answer['verified_setup'])
        expected = sorted(sorted(map(tuple, p['cells'])) for p in sw.VISION_VARIANTS['Atk']['pieces'])
        self.assertEqual(sorted(completed[0].values()), expected, 'finish durable intent before applying the new variant')
        self.assert_complete(game)

    async def test_legacy_fallback_refuses_different_weapon_or_variant_without_input(self):
        for changed in ('weapon', 'variant'):
            with self.subTest(changed=changed):
                game = sw.vision_game(screen='engraving', pieces={}, farming={'switches': {'stage_change': 'real'}})
                saved = {'required': True, 'weapon_id': sw.VISION_ID, 'variant': 'Gold-balanced'}
                if changed == 'weapon':
                    saved['weapon_id'] = sw.AMBITION
                else:
                    saved['variant'] = 'Atk'
                ports, api = self.coordinator(game, saved)
                before = copy.deepcopy(game.state)
                answer = await api['farm'](920, None, 'mpw18')
                self.assertEqual(answer['result'], 'failed')
                self.assertFalse(answer['verified_setup'])
                self.assertEqual(game.moves, [])
                self.assertEqual(game.state, before)
                state = ports.store.sections['engraving_recovery']()
                self.assertTrue(state['required'])
                self.assertNotIn('recipe', state)

    async def test_recovery_entry_retries_transient_unread_name_without_input(self):
        game = sw.vision_game(screen='engraving', pieces={}, farming={'switches': {'stage_change': 'real'}})
        view = sw.fake_engraving_screen(game)
        view.weapon = lambda shot, *args: None if shot[2]['now'] < .75 else 'Vision'
        saved = {'required': True, 'weapon_id': sw.VISION_ID, 'variant': 'Gold-balanced'}
        _, api = self.coordinator(game, saved, view=view)
        first_input = []
        original = game.apply
        def apply(*args, **kwargs):
            if not first_input:
                first_input.append(game.now)
            return original(*args, **kwargs)
        game.apply = apply
        answer = await api['farm'](920, None, 'mpw18')
        self.assertEqual(answer['result'], 'done', answer)
        self.assertGreaterEqual(first_input[0], .75)
        self.assert_complete(game)

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
