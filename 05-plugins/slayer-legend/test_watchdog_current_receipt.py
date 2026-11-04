"""Real Mode/SetupEvidence and watchdog share one current full-repair receipt."""
import inspect
import unittest
from types import SimpleNamespace as NS

import test_mode_setup_status as status_tests
import test_watchdog as watchdog_tests

watchdog = status_tests.load('features/watchdog')


def closed(function, name):
    return inspect.getclosurevars(function).nonlocals[name]


class WatchdogCurrentReceipt(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.case = status_tests.SetupStatus()
        await self.case.asyncSetUp()
        self.case.engraving = 'real'
        self.mode_receipts = []
        self.case.part['api']['on_setup_verified'](self.mode_receipts.append)
        ports = self.case.ports
        ports.lease = NS(state=lambda: None)
        ports.exception = lambda *args: None
        for key in ('fill', 'is_t'):
            setattr(ports, key, watchdog_tests.TEXTS[key])
        self.receipts = []
        self.part = watchdog.watchdog(
            ports, None, None, watchdog_tests.rules, lambda value: value,
            self.case.part['api'], self.case.mines, {'running': lambda: False},
            self.case.loadouts['loadout'], self.case.farming)
        self.part['api']['on_setup_verified'](self.receipts.append)
        watch = closed(self.part['startup'][0], 'watch')
        tick = closed(closed(watch, 'watch_steps'), 'tick')
        closed(self.part['api']['look'], 'status')['mode'] = 'mpw18'
        self.repair = closed(tick, 'farm_repair')

    async def asyncTearDown(self):
        await self.case.asyncTearDown()

    async def test_startup_full_repair_commits_same_dated_receipt_before_event(self):
        observed = []

        def observe(receipt):
            state = self.case.part['api']['state']()
            observed.append((state['state'], state['setup_result'], receipt))

        self.part['api']['on_setup_verified'](observe)

        async def farm(*args, **kwargs):
            self.assertEqual(self.case.part['api']['state']()['state'], 'idle')
            self.assertIsNone(self.case.part['api']['state']()['setup_result'])
            self.case.now += 7
            return {'result': 'done', 'verified_setup': True}

        self.case.farming['farm'] = farm
        await self.repair('loadout')
        state = self.case.part['api']['state']()
        self.assertEqual(state['state'], 'farming')
        receipt = state['setup_result']
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt['at'], self.case.now)
        self.assertEqual(receipt['revision'], self.case.loadouts['revision']('mpw18'))
        self.assertEqual(receipt['target'], self.case.parts['mpw18'])
        self.assertEqual(self.receipts, [receipt])
        self.assertEqual(self.mode_receipts, [receipt])
        self.assertEqual(observed, [('farming', receipt, receipt)])

    async def test_mode_entry_publishes_once_to_the_same_mode_and_watchdog_observers(self):
        async def farm(*args, **kwargs):
            return {'result': 'done', 'verified_setup': True, 'text_t': None, 'timings': {}}

        self.case.farming['farm'] = farm
        await self.case.attempt()
        state = self.case.part['api']['state']()
        self.assertEqual(state['state'], 'farming')
        self.assertEqual(self.mode_receipts, [state['setup_result']])
        self.assertEqual(self.receipts, [state['setup_result']])

    async def test_external_commit_isolates_observer_failure_and_receipt_mutation(self):
        observed = []

        def broken(receipt):
            receipt['target']['preset'] = 'corrupted by observer'
            raise RuntimeError('observer failed')

        def healthy(receipt):
            state = self.case.part['api']['state']()
            observed.append((state['state'], state['setup_result'], receipt))

        self.case.part['api']['on_setup_verified'](broken)
        self.case.part['api']['on_setup_verified'](healthy)
        attempt = self.case.part['api']['begin_verification']('mpw18')
        receipt = self.case.part['api']['confirm']('mpw18', verified_setup=True, attempt=attempt)
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt['target'], self.case.parts['mpw18'])
        self.assertEqual(observed, [('farming', receipt, receipt)])
        self.assertEqual(self.mode_receipts, [receipt])
        self.assertEqual(self.receipts, [receipt])

    async def test_readback_relaunch_cannot_turn_startup_green_or_emit_receipt(self):
        async def farm(*args, **kwargs):
            for callback in self.case.relaunch:
                callback('new process during final readback')
            return {'result': 'done', 'verified_setup': True}

        self.case.farming['farm'] = farm
        await self.repair('loadout')
        state = self.case.part['api']['state']()
        self.assertEqual(state['state'], 'idle')
        self.assertIsNone(state['setup_result'])
        self.assertEqual(self.receipts, [])
        self.assertEqual(self.mode_receipts, [])

    async def test_partial_done_cannot_turn_startup_green_or_emit_receipt(self):
        async def farm(*args, **kwargs):
            return {'result': 'done', 'verified_setup': False}

        self.case.farming['farm'] = farm
        await self.repair('loadout')
        self.assertEqual(self.case.part['api']['state']()['state'], 'idle')
        self.assertIsNone(self.case.part['api']['state']()['setup_result'])
        self.assertEqual(self.receipts, [])

    async def test_external_attempt_rejects_changed_input_target_or_mode_epoch(self):
        for change in ('input', 'target', 'mode_epoch'):
            with self.subTest(change=change):
                self.case.input = None
                self.case.parts['mpw18']['preset'] = 'III'
                attempt = self.case.part['api']['begin_verification']('mpw18')
                if change == 'input':
                    self.case.input = {'wall': self.case.now, 'monotonic': self.case.now}
                elif change == 'target':
                    self.case.parts['mpw18']['preset'] = 'IV'
                else:
                    private = closed(self.case.part['api']['state'], 'status')
                    private['mode_epoch'] += 2
                receipt = self.case.part['api']['confirm'](
                    'mpw18', verified_setup=True, attempt=attempt)
                self.assertIsNone(receipt)
                self.assertEqual(self.case.part['api']['state']()['state'], 'idle')
                self.assertIsNone(self.case.part['api']['state']()['setup_result'])
                self.assertEqual(self.mode_receipts, [])
                self.assertEqual(self.receipts, [])

    async def test_external_completion_never_overwrites_an_active_entry(self):
        private = closed(self.case.part['api']['state'], 'status')
        for state in ('moving', 'waiting'):
            with self.subTest(state=state):
                private['state'] = 'idle'
                attempt = self.case.part['api']['begin_verification']('mpw18')
                private['state'] = state
                self.assertIsNone(self.case.part['api']['begin_verification']('mpw18'))
                self.assertIsNone(self.case.part['api']['confirm'](
                    'mpw18', verified_setup=True, attempt=attempt))
                self.assertEqual(self.case.part['api']['state']()['state'], state)
                self.assertIsNone(self.case.part['api']['state']()['setup_result'])

    async def test_bool_alone_is_never_current_external_evidence(self):
        receipt = self.case.part['api']['confirm']('mpw18', verified_setup=True)
        self.assertIsNone(receipt)
        self.assertEqual(self.case.part['api']['state']()['state'], 'idle')


if __name__ == '__main__':
    unittest.main()
