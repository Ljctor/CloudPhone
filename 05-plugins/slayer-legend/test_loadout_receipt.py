"""POST /loadout requires the actual full stage/preset transaction receipt.

Scripted captures and Soul verification stand-ins only; no Android or service.
"""
import asyncio
import copy
import unittest
from types import SimpleNamespace as NS

import test_stage_change as base
import test_engraving as engraving_tests


class LoadoutReceipt(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.game = base.Game(stage=915, preset='II')
        self.ports = self.game.ports()
        self.tasks = []
        self.calls = []
        self.weapon_verified = False
        self.override = None
        self.ports.store.saved['mode'] = {'mode': 'mpw18', 'default': 'mpw18', 'configured': True}
        self.ports.store.saved['loadouts'] = {'mpw18': {'stage': 920, 'preset': 'II', 'soul_weapon': None}}
        self.ports.enabled = lambda: True
        self.ports.pause_left = lambda: 0
        self.ports.last_input = lambda: None

        def spawn(coroutine):
            task = asyncio.create_task(coroutine)
            self.tasks.append(task)
            return task

        self.ports.spawn = spawn
        self.loadouts = engraving_tests.load('features/engraving').engraving(self.ports, engraving_tests.rules)
        accepted = self.loadouts['api']

        def soul_feature(ports, screens, reader, rules, table, helpers, engraving):
            async def ensure(*args, **kwargs):
                await helpers.front()
                self.calls.append('weapon_verified')
                self.weapon_verified = True

            async def park():
                pass

            return {'ensure': ensure, 'park': park, 'switch': lambda: 'real',
                    'verification_needed': lambda *args: not self.weapon_verified,
                    'state': lambda: {'engraving': 'real', 'recovery': {
                        'verified': self.weapon_verified, 'completion_verified': self.weapon_verified,
                        'locks_verified': self.weapon_verified, 'required': False,
                        'weapon_id': 32, 'variant': 'Gold-maxed'}}}

        soul = {'feature': soul_feature, 'reader': NS(title=lambda shot: False), 'rules': None,
                'table': None, 'loadout': accepted['loadout'], 'applicability': accepted['applicability'],
                'engraving': {'screen': NS(title=lambda shot: False)}}
        actual = base.feature.stage_change(self.ports, *base.readers(self.game), base.rules, base.TABLE, soul)['api']

        async def farm(*args, **kwargs):
            self.calls.append('full_farm')
            if self.override is not None:
                return copy.deepcopy(self.override)
            return await actual['farm'](*args, **kwargs)

        farming = dict(actual, farm=farm)
        mines = {'state': lambda: {'enabled': False, 'state': 'off'}, 'ended': False,
                 'start': lambda *args: None, 'stop': lambda: None, 'set_until': lambda *args: None}
        self.mode = base.mode_feature.mode(
            self.ports, base.mode_rules, None,
            NS(time_or_none=lambda value: value, number_or_none=lambda value, top: value),
            mines, None, NS(fresh=lambda: {'gold': None}), accepted, farming, base.setup_feature.mode_setup)
        self.write = next(handler for method, path, handler in self.loadouts['routes']
                          if (method, path) == ('POST', '/loadout'))

    async def asyncTearDown(self):
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def change_weapon(self):
        class Request:
            async def json(self):
                return {'mode': 'mpw18', 'soul_weapon': {'id': 32, 'variant': 'Gold-maxed'}}
        status, _ = await self.write(Request())
        self.assertEqual(status, 200)
        for _ in range(100):
            await asyncio.sleep(0)
        return self.mode['api']['state']()

    async def test_weapon_only_write_verifies_and_repairs_accepted_stage(self):
        state = await self.change_weapon()
        self.assertEqual(self.calls[0], 'full_farm')
        self.assertEqual(self.calls[1], 'weapon_verified', 'engraving verification still precedes stage work')
        self.assertEqual(self.game.state['stage'], 920)
        self.assertEqual(self.game.state['preset'], 'II')
        self.assertEqual(state['state'], 'farming')
        self.assertEqual(state['setup_result']['result'], 'done')
        self.assertEqual(state['setup_result']['target'], self.loadouts['api']['loadout']('mpw18'))

    async def test_wrong_paused_preset_remains_a_blocker_after_weapon_verification(self):
        self.game.state.update(preset='I', unfolded_forever=True)
        state = await self.change_weapon()
        self.assertEqual(self.calls[:2], ['full_farm', 'weapon_verified'])
        self.assertEqual(self.game.state['stage'], 915, 'readable preset refusal precedes stage navigation')
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['setup_result']['result'], 'failed')
        self.assertIn('Préréglage', state['message_t']['params']['why']['template'])
        self.assertFalse(any(' applied in ' in alert for alert in self.game.alerts))

    async def assert_partial_receipt_rejected(self, receipt):
        self.override = {'result': 'done', 'text_t': None, 'timings': {}, **receipt}
        state = await self.change_weapon()
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(state['setup_result']['result'], 'failed')
        self.assertEqual(state['message_t']['params']['why']['template'],
                         'Configuration demandée non vérifiée')
        self.assertEqual(self.calls, ['full_farm'], 'an incomplete contract is not retried as a fresh success')
        self.assertFalse(any(' applied in ' in alert for alert in self.game.alerts))

    async def test_done_without_a_complete_receipt_never_becomes_ready(self):
        await self.assert_partial_receipt_rejected({})

    async def test_done_with_false_verification_never_becomes_ready(self):
        await self.assert_partial_receipt_rejected({'verified_setup': False})

    async def test_cached_result_cannot_be_a_complete_setup_receipt(self):
        await self.assert_partial_receipt_rejected({'result': 'cached', 'verified_setup': True})

    async def test_equipped_result_cannot_be_a_complete_setup_receipt(self):
        await self.assert_partial_receipt_rejected({'result': 'equipped', 'verified_setup': True})

    async def test_unknown_result_cannot_be_a_complete_setup_receipt(self):
        await self.assert_partial_receipt_rejected({'result': None, 'verified_setup': True})
