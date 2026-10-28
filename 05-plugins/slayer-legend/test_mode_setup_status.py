"""Readiness is a current gate; completed attempts require matching evidence."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location('setup_status_' + name.replace('/', '_'), ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

feature, rules, engravings = load('features/mode'), load('features/mode_rules'), load('features/engraving')
timer_rules = load('features/timer_rules')
setup_feature = load('features/mode_setup')


class SetupEvidence(unittest.TestCase):
    """Evidence identity is independent of orchestration and device operations."""

    def setUp(self):
        self.now = 1000
        self.input = None
        self.revision = 'accepted-1'
        self.target = {'stage': 970, 'preset': 'III', 'soul_weapon': {'id': 32, 'variant': 'Gold-maxed'}}
        self.relaunch = []
        ports = NS(t=rules.t, clock=NS(wall=lambda: self.now), last_input=lambda: self.input,
                   enabled=lambda: True, on_relaunch=self.relaunch.append)
        loadouts = {'revision': lambda mode: self.revision, 'loadout': lambda mode: self.target,
                    'stage': lambda mode: self.target['stage']}
        self.evidence = setup_feature.mode_setup(ports, loadouts, {})

    def complete(self, attempt, **changes):
        arguments = dict(mode='mpw18', completed=True, state='farming',
                         message=rules.t('Farming {name} au stage {number}', name='mpw18', number=970))
        self.evidence.complete_attempt(attempt, **dict(arguments, **changes))

    def test_new_attempt_supersedes_an_old_outcome_and_public_results_are_detached(self):
        previous = self.evidence.begin_attempt('mpw18', 970)
        current = self.evidence.begin_attempt('mpw18', 970)
        self.complete(previous)
        self.assertFalse(self.evidence.has_result)
        self.complete(current)
        result = self.evidence.current_result('mpw18')
        self.assertEqual(result['result'], 'done')
        self.assertNotIn('input_mark', result)
        self.assertNotIn('launch_epoch', result)
        result['target']['soul_weapon']['variant'] = 'Atk'
        result['message_t']['params']['number'] = 1
        again = self.evidence.current_result('mpw18')
        self.assertEqual(again['target']['soul_weapon']['variant'], 'Gold-maxed')
        self.assertEqual(again['message_t']['params']['number'], 970)

    def test_attempt_snapshots_the_nested_target_and_cannot_publish_after_identity_changes(self):
        attempt = self.evidence.begin_attempt('mpw18', 970)
        self.target['soul_weapon']['variant'] = 'Atk'
        self.assertEqual(attempt.target['soul_weapon']['variant'], 'Gold-maxed')
        self.revision = 'accepted-2'
        self.complete(attempt)
        self.assertIsNone(self.evidence.current_result('mpw18'))
        for changed in ('input', 'launch', 'mode', 'stage'):
            with self.subTest(changed=changed):
                self.input = None
                attempt = self.evidence.begin_attempt('mpw18', 971 if changed == 'stage' else 970)
                if changed == 'input':
                    self.input = {'wall': 1000, 'monotonic': 40}
                if changed == 'launch':
                    self.relaunch[0]('relaunch')
                self.complete(attempt, mode='mpw4' if changed == 'mode' else 'mpw18')
                self.assertFalse(self.evidence.has_result)

    def test_result_is_bounded_in_time_mode_and_mine_context(self):
        self.complete(self.evidence.begin_attempt('mpw18', 970))
        self.assertIsNone(self.evidence.current_result('mpw4'))
        self.assertIsNone(self.evidence.current_result('mpw18', mine_enabled=True))
        for now, valid in ((999, False), (1000, True), (1120, True), (1120.001, False)):
            self.now = now
            self.assertEqual(self.evidence.current_result('mpw18') is not None, valid)

    def test_receipt_is_not_evidence_and_clear_revokes_a_pending_attempt(self):
        self.assertEqual(self.evidence.request('mpw18', configured=True),
                         {'mode': 'mpw18', 'if_revision': 'accepted-1'})
        self.assertFalse(self.evidence.has_result)
        self.assertIsNone(self.evidence.request('mpw18', configured=True, busy=True))
        self.assertIsNone(self.evidence.request('mpw18', configured=True, mine_enabled=True))
        attempt = self.evidence.begin_attempt('mpw18', 970)
        self.evidence.clear_result()
        self.complete(attempt)
        self.assertFalse(self.evidence.has_result)


class SetupStatus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000.0; self.input = None; self.playing = False; self.engraving = 'off'; self.soul = 'real'; self.enabled = True; self.farm_calls = []
        self.tasks = []; self.callbacks = []; self.relaunch = []; self.block = None; self.started = asyncio.Event(); self.mine_active = False
        self.parts = {name: {'stage': 970, 'preset': 'III', 'soul_weapon': {'id': 32, 'variant': 'Gold-maxed'}}
                      for name in ('mpw18', 'mpw4')}
        async def sleep(seconds): self.now += seconds; await asyncio.sleep(0)
        async def notify(*args, **kwargs): pass
        def spawn(coro):
            task = asyncio.create_task(coro); self.tasks.append(task); return task
        async def farm(*args, **kwargs):
            self.farm_calls.append((args, kwargs))
            self.started.set()
            if self.block: await self.block.wait()
            return {'result': 'failed', 'text_t': rules.t('écran inattendu'), 'timings': {}}
        self.ports = NS(t=rules.t, log=lambda *a, **k: None, english=lambda text: str(text), notify=notify,
            store=NS(saved={'mode': {'mode': 'mpw18', 'default': 'mpw18', 'configured': True}},
                     register=lambda *a: None, save=lambda: None),
            clock=NS(wall=lambda: self.now, monotonic=lambda: self.now, sleep=sleep), spawn=spawn,
            respond=lambda body, status=200: (body, status),
            enabled=lambda: self.enabled, pause_left=lambda: 5 if self.playing else 0, last_input=lambda: self.input,
            on_relaunch=self.relaunch.append, Busy=type('Busy', (Exception,), {}))
        self.loadouts = {'loadout': lambda name: dict(self.parts[name]), 'stage': lambda name: self.parts[name]['stage'],
            'set_stage': lambda name, n: self.parts[name].update(stage=n), 'adopt_stage': lambda *a: None,
            'on_change': self.callbacks.append, 'revision': lambda name: engravings.revision(self.parts[name]),
            'variant': lambda *a: {}, 'applicability': lambda chosen: {'supported': True, 'engraving_required': True}}
        # A real variant is nonempty; the off gate requires a configured recipe.
        self.loadouts['variant'] = lambda *a: {'pieces': []}
        self.farming = {'farm': farm, 'engraving_switch': lambda: self.engraving,
                        'soul_weapon_switch': lambda: self.soul}
        self.mines = {'state': lambda: {'enabled': self.mine_active, 'state': 'farming' if self.mine_active else 'off'}, 'ended': False,
                      'start': lambda *a: None, 'stop': lambda: None, 'set_until': lambda *a: None}
        self.part = feature.mode(self.ports, rules, timer_rules, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming, setup_feature.mode_setup)

    async def asyncTearDown(self):
        for task in self.tasks: task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def attempt(self):
        before = dict(self.parts['mpw18']); self.parts['mpw18']['preset'] = 'IV'
        self.callbacks[0]('mpw18', before, dict(self.parts['mpw18']))
        for _ in range(100): await asyncio.sleep(0)

    async def test_off_gate_is_visible_without_an_attempt_and_idle_is_red(self):
        state = self.part['api']['state']()
        self.assertEqual(state['state'], 'idle')
        self.assertIn('Gravure automatique désactivée', state['setup_blocker_t']['template'])
        self.assertIn('supervision', state['setup_blocker_t']['template'])
        self.assertNotIn('en attente', state['setup_blocker_t']['template'], 'off alone cannot prove first-run history')
        self.assertIsNone(state['setup_result'])
        self.assertEqual(state['tone'], 'error')
        self.playing = True
        self.assertEqual(self.part['api']['state']()['tone'], 'hold')
        self.playing = False
        self.part['api']['watched_by'](lambda: {'mode': 'mpw18', 'repairing': 'park'})
        self.assertEqual(self.part['api']['state']()['tone'], 'setup', 'an active return keeps its movement tone')

    async def test_mine_override_does_not_inherit_a_farm_engraving_blocker(self):
        self.mine_active = True
        state = self.part['api']['state']()
        self.assertIsNone(state['setup_blocker_t'])
        self.assertNotEqual(state['tone'], 'error')

    async def test_free_play_does_not_inherit_a_farm_engraving_blocker(self):
        self.ports.store.saved['mode'] = {'mode': 'free', 'default': 'free', 'configured': True}
        free = feature.mode(self.ports, rules, timer_rules, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming, setup_feature.mode_setup)
        self.assertIsNone(free['api']['state']()['setup_blocker_t'])
        self.assertNotEqual(free['api']['state']()['tone'], 'error')

    async def test_actual_result_is_revision_bound_fresh_and_invalidated_by_input_or_relaunch(self):
        self.engraving = 'real'
        await self.attempt()
        result = self.part['api']['state']()['setup_result']
        self.assertEqual(result['result'], 'failed')
        self.assertEqual(result['revision'], engravings.revision(self.parts['mpw18']))
        self.assertEqual(result['target'], self.parts['mpw18'])
        self.parts['mpw18']['preset'] = 'V'
        self.assertIsNone(self.part['api']['state']()['setup_result'])
        self.parts['mpw18']['preset'] = 'IV'
        self.now += 121
        self.assertIsNone(self.part['api']['state']()['setup_result'])
        self.now -= 121
        self.input = {'wall': self.now, 'monotonic': self.now}
        self.assertIsNone(self.part['api']['state']()['setup_result'])
        self.input = None
        self.relaunch[0]('test relaunch')
        self.assertIsNone(self.part['api']['state']()['setup_result'])

    async def test_pending_path_is_not_red_even_with_a_known_off_gate(self):
        self.block = asyncio.Event()
        await self.attempt()
        self.assertEqual(self.part['api']['state']()['state'], 'moving')
        self.assertEqual(self.part['api']['state']()['tone'], 'setup')
        self.assertIsNone(self.part['api']['state']()['setup_result'])

    async def test_health_or_external_confirmation_cannot_synthesize_setup_evidence(self):
        self.engraving = 'real'
        await self.attempt()
        self.assertEqual(self.part['api']['state']()['state'], 'failed')
        self.part['api']['confirm']('mpw18')
        self.assertEqual(self.part['api']['state']()['state'], 'failed')
        # A separate caller may resolve execution status after its own
        # full verification, but cannot manufacture this attempt's receipt.
        self.parts['mpw18']['preset'] = 'V'
        self.part['api']['confirm']('mpw18', verified_setup=True)
        self.assertEqual(self.part['api']['state']()['state'], 'farming')
        self.assertIsNone(self.part['api']['state']()['setup_result'])

    async def call_setup(self, body):
        async def json_body(): return body
        handler = next(handler for method, route, handler in self.part['routes']
                       if method == 'POST' and route == '/mode/setup')
        return await handler(NS(json=json_body))

    async def settle(self):
        for _ in range(100): await asyncio.sleep(0)

    async def test_explicit_setup_retries_unchanged_target_and_only_reports_actual_result(self):
        self.engraving = 'real'
        target = dict(self.parts['mpw18'])
        receipt = self.part['api']['state']()['setup_request']
        self.assertEqual(receipt, {'mode': 'mpw18', 'if_revision': engravings.revision(target)})
        answer, code = await self.call_setup(receipt)
        self.assertEqual(code, 202)
        self.assertEqual(answer['state'], 'moving')
        self.assertTrue(answer['setup'])
        self.assertIsNone(answer['setup_request'])
        self.assertIsNone(answer['setup_result'], 'accepting a request cannot certify that the setup ran')
        await self.settle()
        self.assertTrue(self.farm_calls)
        self.assertTrue(all(args[:3] == (970, 'III', 'mpw18') and not kwargs.get('force')
                            for args, kwargs in self.farm_calls))
        self.assertEqual(self.parts['mpw18'], target, 'retrying does not mutate the accepted loadout')
        result = self.part['api']['state']()['setup_result']
        self.assertEqual(result['result'], 'failed', 'the actual failed setup remains failed after an accepted request')
        self.assertEqual(result['revision'], receipt['if_revision'])
        self.assertEqual(result['target'], target)
        calls = len(self.farm_calls)
        _, code = await self.call_setup(self.part['api']['state']()['setup_request'])
        self.assertEqual(code, 202, 'a completed failed attempt can retry the same target again')
        await self.settle()
        self.assertGreater(len(self.farm_calls), calls)

    async def test_setup_rejects_stale_revision_wrong_mode_and_malformed_requests(self):
        self.engraving = 'real'
        receipt = self.part['api']['state']()['setup_request']
        for body in (dict(receipt, if_revision='old'), dict(receipt, mode='mpw4'),
                     dict(receipt, mode='free'), dict(receipt, if_revision=None), None):
            answer, code = await self.call_setup(body)
            self.assertGreaterEqual(code, 400)
            self.assertIn('error_t', answer)
        await self.settle()
        self.assertEqual(self.farm_calls, [])

    async def test_setup_gates_do_not_queue_when_off_blocked_in_mine_or_without_stage(self):
        self.engraving = 'real'
        receipt = self.part['api']['state']()['setup_request']
        for attribute, disabled in (('enabled', False), ('engraving', 'off'), ('soul', 'off'), ('mine_active', True)):
            previous = getattr(self, attribute); setattr(self, attribute, disabled)
            self.assertIsNone(self.part['api']['state']()['setup_request'])
            _, code = await self.call_setup(receipt)
            self.assertEqual(code, 409)
            setattr(self, attribute, previous)
        self.parts['mpw18']['stage'] = None
        self.assertIsNone(self.part['api']['state']()['setup_request'])
        _, code = await self.call_setup(receipt)
        self.assertEqual(code, 409)
        await self.settle()
        self.assertEqual(self.farm_calls, [])

    async def test_duplicate_setup_cannot_replace_an_active_transaction(self):
        self.engraving = 'real'
        self.block = asyncio.Event()
        receipt = self.part['api']['state']()['setup_request']
        replies = await asyncio.gather(self.call_setup(receipt), self.call_setup(receipt))
        self.assertEqual(sorted(code for _, code in replies), [202, 409])
        await self.started.wait()
        self.assertEqual(len(self.farm_calls), 1)
        self.assertIsNone(self.part['api']['state']()['setup_request'])
        _, code = await self.call_setup(receipt)
        self.assertEqual(code, 409)
        self.assertEqual(len(self.farm_calls), 1)
        self.assertFalse(self.tasks[-1].cancelled(), 'a duplicate request cannot cancel the running setup')

    async def test_timer_subtraction_expires_instead_of_making_nondefault_unlimited(self):
        self.ports.store.saved['mode'] = {'mode': 'agent', 'default': 'mpw18', 'configured': True,
                                          'until': self.now + 60}
        part = feature.mode(self.ports, rules, timer_rules, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming, setup_feature.mode_setup)
        handler = next(handler for method, route, handler in part['routes'] if route == '/mode/timer')
        async def subtract(): return {'add': -30}
        answer, code = await handler(NS(json=subtract))
        self.assertEqual(code, 200)
        self.assertEqual(answer['until'], self.now)
        self.assertEqual(rules.due(answer['mode'], answer['until'], {}, self.now), 'timer')

    async def test_default_timer_adjustment_cannot_create_a_deadline(self):
        handler = next(handler for method, route, handler in self.part['routes'] if route == '/mode/timer')
        async def extend(): return {'add': 30}
        answer, code = await handler(NS(json=extend))
        self.assertEqual(code, 200)
        self.assertEqual(answer['mode'], answer['default'])
        self.assertIsNone(answer['until'])

    async def test_nondefault_mode_returns_to_default_after_its_deadline(self):
        self.ports.store.saved['mode'] = {'mode': 'agent', 'default': 'mpw18', 'configured': True,
                                          'until': self.now + 1}
        part = feature.mode(self.ports, rules, timer_rules, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming, setup_feature.mode_setup)
        await part['startup'][0](None)
        await self.settle()
        answer = part['api']['state']()
        self.assertEqual(answer['mode'], 'mpw18')
        self.assertIsNone(answer['until'])

    async def test_restored_mine_receives_its_normalised_finite_deadline(self):
        self.mine_active = True
        deadlines = []
        self.mines['set_until'] = deadlines.append
        self.ports.store.saved['mode'] = {'mode': 'mine', 'default': 'mpw18', 'configured': True, 'until': None}
        part = feature.mode(self.ports, rules, timer_rules, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming, setup_feature.mode_setup)
        self.assertEqual(part['api']['state']()['until'], self.now + 1800)
        self.assertEqual(deadlines, [self.now + 1800])
