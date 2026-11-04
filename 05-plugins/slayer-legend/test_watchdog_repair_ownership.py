"""Actual watchdog repairs and guarded navigation across ownership changes."""
import asyncio
import inspect
import unittest
from types import SimpleNamespace as NS

import test_menu_recovery as menu
import test_watchdog as watchdog_tests

watchdog = menu.soul.load('features/watchdog')


def closed(function, name):
    return inspect.getclosurevars(function).nonlocals[name]


class RepairOwnership(unittest.IsolatedAsyncioTestCase):
    def build(self, screen='promotion', full_stage=False):
        self.game = menu.soul.Game(screen=screen)
        if full_stage:
            original_ports = self.game.ports
            def ports():
                instance = original_ports()
                instance.store.saved['farming'] = {'switches': {'stage_change': 'real'}}
                return instance
            self.game.ports = ports
            reader = NS(regions=lambda table: ['known'] * 50,
                        battle_stage=lambda shot, names, *args: 920)
            self.ports, self.farming = menu.soul.build(self.game, stage_reader=reader)
        else:
            self.ports, self.farming = menu.build(self.game)
        self.ports.Busy = watchdog_tests.ports_module.Busy
        self.mode = {'mode': 'mpw18', 'state': 'farming', 'highest': 990}
        self.epoch = 0
        self.target = {'stage': 920, 'preset': None,
                       'soul_weapon': {'id': menu.soul.AMBITION, 'variant': 'Atk'}}
        self.confirmed = []
        self.ports.lease = NS(state=lambda: None)
        self.part = watchdog.watchdog(
            self.ports, menu.soul.fake_screens(), NS(), watchdog_tests.rules, lambda value: value,
            {'state': lambda: dict(self.mode), 'mode_epoch': lambda: self.epoch,
             'confirm': lambda *args, **kwargs: self.confirmed.append((args, kwargs))},
            {'state': lambda: {'enabled': False}}, {'running': lambda: False},
            lambda mode: dict(self.target), self.farming)
        # Exercise the real dispatcher without its independent polling clock.
        watch = closed(self.part['startup'][0], 'watch')
        tick = closed(closed(watch, 'watch_steps'), 'tick')
        self.repair = closed(tick, 'farm_repair')
        self.receipts = []
        self.part['api']['on_setup_verified'](self.receipts.append)

    async def test_menu_close_then_free_or_agent_stops_before_parking(self):
        for name in ('free', 'agent'):
            with self.subTest(mode=name):
                self.build()
                apply = self.game.apply

                def change_mode(screen, move, point):
                    apply(screen, move, point)
                    if (screen, move) == ('character_promotion', 'close_tab'):
                        self.mode['mode'] = name
                        self.epoch += 1

                self.game.apply = change_mode
                await self.repair('back_to_battle')
                self.assertEqual(self.game.moves, [('character_promotion', 'close_tab')])
                self.assertEqual(self.game.state['screen'], 'battle')
                self.assertEqual(self.confirmed, [])
                self.assertEqual(self.receipts, [])
                self.assertIsNone(self.farming['soul_weapon_state']()['cached'])

    async def test_mode_roundtrip_also_revokes_old_repair(self):
        self.build()
        apply = self.game.apply

        def roundtrip(screen, move, point):
            apply(screen, move, point)
            if move == 'close_tab':
                self.epoch += 2  # Free and back to the same farming mode.

        self.game.apply = roundtrip
        await self.repair('back_to_battle')
        self.assertEqual(self.game.moves, [('character_promotion', 'close_tab')])
        self.assertEqual(self.receipts, [])

    async def test_parking_branch_stops_after_mode_changes_during_focus(self):
        self.build('battle')
        focus = self.ports.focused

        async def changed_focus():
            self.mode['mode'] = 'agent'
            return await focus()

        self.ports.focused = changed_focus
        await self.repair('park')
        self.assertEqual(self.game.moves, [])
        self.assertEqual(self.receipts, [])

    async def test_full_farm_final_readback_cannot_cache_after_mode_change(self):
        self.build('battle', full_stage=True)
        analyse = self.ports.analyse
        final_read = []

        async def change_during_final_read(fn, *args):
            result = await analyse(fn, *args)
            if fn.__name__ == 'final_view':
                final_read.append(len(self.game.moves))
                self.mode['mode'] = 'free'
                self.epoch += 1
            return result

        self.ports.analyse = change_during_final_read
        await self.repair('loadout')
        self.assertTrue(final_read, 'exercise the actual equipment readback')
        self.assertIsNone(self.farming['soul_weapon_state']()['cached'])
        self.assertEqual(self.confirmed, [])
        self.assertEqual(self.receipts, [])
        self.assertEqual(len(self.game.moves), final_read[-1])

    async def test_unchanged_owner_completes_then_context_does_not_leak(self):
        self.build()
        await self.repair('back_to_battle')
        self.assertEqual(self.game.moves, [('character_promotion', 'close_tab'),
                                          ('battle', 'menu_equipment'),
                                          ('equipment_weapon', 'soul_weapon')])
        self.assertEqual(self.receipts, [], 'parking is never full setup proof')
        self.mode['mode'] = 'agent'
        # A later separately owned operation does not inherit the old guard.
        result = await self.farming['unpark']('agent')
        self.assertEqual(result['result'], 'done')
        self.assertEqual(self.game.state['screen'], 'battle')


if __name__ == '__main__':
    unittest.main()
