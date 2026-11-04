"""Readiness is a current gate; completed attempts require matching evidence."""
import asyncio
import copy
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
                      for name in ('mpw18', 'mpw4', 'soul')}
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

    async def test_complete_setup_receipt_confirms_restored_farming_idle(self):
        self.engraving = 'real'
        self.assertEqual(self.part['api']['state']()['state'], 'idle')
        self.part['api']['confirm']('mpw18', verified_setup=True)
        state = self.part['api']['state']()
        self.assertEqual(state['state'], 'farming')
        self.assertEqual(state['message_t']['params'],
                         {'name': 'mpw18', 'number': 970, 'preset': 'III'})
        self.assertEqual(self.farm_calls, [])

    async def test_health_and_other_target_receipts_do_not_confirm_startup_idle(self):
        self.engraving = 'real'
        for name, verified in (('mpw18', False), ('mpw4', True), ('soul', True)):
            with self.subTest(name=name, verified=verified):
                self.part['api']['confirm'](name, verified_setup=verified)
                self.assertEqual(self.part['api']['state']()['state'], 'idle')

    async def test_receipt_cannot_acknowledge_unconfigured_or_missing_farming_target(self):
        self.engraving = 'real'
        for mode, configured, stage in (('mpw18', False, 970), ('mpw18', True, None),
                                        ('free', True, 970), ('agent', True, 970)):
            with self.subTest(mode=mode, configured=configured, stage=stage):
                self.ports.store.saved['mode'] = {'mode': mode, 'default': mode, 'configured': configured}
                self.parts['mpw18']['stage'] = stage
                part = feature.mode(
                    self.ports, rules, timer_rules,
                    NS(time_or_none=lambda value: value, number_or_none=lambda value, top: value),
                    self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts,
                    self.farming, setup_feature.mode_setup)
                previous = part['api']['state']()['state']
                part['api']['confirm'](mode, verified_setup=True)
                self.assertEqual(part['api']['state']()['state'], previous)
                self.assertNotEqual(part['api']['state']()['state'], 'farming')

    async def test_complete_receipt_does_not_override_an_active_entry(self):
        self.engraving = 'real'
        self.block = asyncio.Event()
        await self.attempt()
        self.assertEqual(self.part['api']['state']()['state'], 'moving')
        self.part['api']['confirm']('mpw18', verified_setup=True)
        self.assertEqual(self.part['api']['state']()['state'], 'moving')

    async def test_full_setup_route_emits_only_its_valid_current_receipt(self):
        self.engraving = 'real'
        receipts = []
        self.part['api']['on_setup_verified'](receipts.append)

        async def farm(*args, **kwargs):
            return {'result': 'done', 'verified_setup': True, 'text_t': None, 'timings': {}}

        self.farming['farm'] = farm
        response, code = await self.call_setup(self.part['api']['state']()['setup_request'])
        self.assertEqual(code, 202)
        await self.settle()
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0], self.part['api']['state']()['setup_result'])
        self.assertEqual(receipts[0]['result'], 'done')
        self.assertEqual(receipts[0]['target'], self.parts['mpw18'])

    async def test_receipt_signal_does_not_acknowledge_input_relaunch_or_revision_invalidated_proof(self):
        self.engraving = 'real'
        receipts = []
        self.part['api']['on_setup_verified'](receipts.append)

        async def farm(*args, **kwargs):
            return {'result': 'done', 'verified_setup': True, 'text_t': None, 'timings': {}}

        self.farming['farm'] = farm
        for changed in ('input', 'relaunch', 'revision'):
            with self.subTest(changed=changed):
                self.input = None
                self.parts['mpw18']['preset'] = 'III'

                async def notify(*args, **kwargs):
                    if changed == 'input':
                        self.input = {'wall': self.now, 'monotonic': self.now}
                    elif changed == 'relaunch':
                        for callback in self.relaunch:
                            callback('new process')
                    else:
                        self.parts['mpw18']['preset'] = 'I'

                # Model invalidation at the asynchronous notification boundary
                # after execution, before durable attempt completion/publication.
                self.ports.notify = notify
                await self.attempt()
                self.assertIsNone(self.part['api']['state']()['setup_result'])
                self.assertEqual(receipts, [])

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

    async def test_failed_result_clears_only_after_verified_full_repair_of_same_mode(self):
        self.engraving = 'real'
        await self.attempt()
        failed = self.part['api']['state']()
        self.assertEqual(failed['state'], 'failed')
        self.assertEqual(failed['setup_result']['result'], 'failed')
        self.assertEqual(failed['tone'], 'error')
        target = failed['setup_result']['target']
        revision = failed['setup_result']['revision']
        # Seeing healthy combat proves neither the configured weapon nor its
        # engraving. Keep the same revision, so this exercises real clearing
        # instead of merely making the failed receipt stale.
        self.part['api']['watched_by'](lambda: {'mode': 'mpw18', 'level': None, 'blocked': False})
        self.part['api']['confirm']('mpw18')
        self.part['api']['confirm']('mpw4', verified_setup=True)
        unchanged = self.part['api']['state']()
        self.assertEqual(unchanged['state'], 'failed')
        self.assertEqual(unchanged['tone'], 'error')
        self.assertEqual(unchanged['setup_result'], failed['setup_result'])
        self.part['api']['confirm']('mpw18', verified_setup=True)
        repaired = self.part['api']['state']()
        self.assertEqual(repaired['state'], 'farming')
        self.assertEqual(repaired['tone'], 'ok')
        self.assertIsNone(repaired['setup_result'], 'the old failure must disappear after the full repair')
        self.assertEqual(self.parts['mpw18'], target)
        self.assertEqual(engravings.revision(self.parts['mpw18']), revision)

    async def call_setup(self, body):
        async def json_body(): return body
        handler = next(handler for method, route, handler in self.part['routes']
                       if method == 'POST' and route == '/mode/setup')
        return await handler(NS(json=json_body))

    async def test_current_watchdog_execution_blocker_is_visible_and_keeps_explicit_retry(self):
        self.engraving = 'real'
        receipt = self.part['api']['state']()['setup_request']
        reason = rules.t('Préréglage IV demandé, II lu : changement bloqué, actions en pause')
        target = copy.deepcopy(self.parts['mpw18'])
        look = {'mode': 'mpw18', 'execution_blocker_mode': 'mpw18',
                'execution_blocker_target': target, 'execution_blocker_t': reason, 'blocked': True}
        self.part['api']['watched_by'](lambda: look)
        state = self.part['api']['state']()
        self.assertEqual(state['setup_blocker_t'], reason)
        self.assertEqual(state['setup_request'], receipt, 'an explicit request can recheck a corrected preset')
        self.assertEqual(self.farm_calls, [])
        self.assertEqual(self.parts['mpw18'], target)

    async def test_execution_blocker_is_scoped_to_exact_current_mode_and_target(self):
        self.engraving = 'real'
        look = {'mode': 'mpw18', 'execution_blocker_mode': 'mpw4',
                'execution_blocker_target': copy.deepcopy(self.parts['mpw18']),
                'execution_blocker_t': rules.t('blocked')}
        self.part['api']['watched_by'](lambda: look)
        self.assertIsNone(self.part['api']['state']()['setup_blocker_t'])
        self.assertIsNotNone(self.part['api']['state']()['setup_request'])
        look['execution_blocker_mode'] = 'mpw18'
        self.parts['mpw18']['soul_weapon']['variant'] = 'different'
        self.assertIsNone(self.part['api']['state']()['setup_blocker_t'])
        self.assertIsNotNone(self.part['api']['state']()['setup_request'])

    async def test_pending_engraving_recovery_keeps_explicit_setup_available(self):
        self.engraving = 'real'
        reason = rules.t('blocked')
        self.part['api']['watched_by'](lambda: {
            'mode': 'mpw18', 'execution_blocker_mode': 'mpw18',
            'execution_blocker_target': copy.deepcopy(self.parts['mpw18']), 'execution_blocker_t': reason})
        self.farming['soul_weapon_state'] = lambda: {'recovery': {'required': True}}
        state = self.part['api']['state']()
        self.assertEqual(state['setup_blocker_t'], reason)
        self.assertIsNotNone(state['setup_request'], 'policy refusal must not strand an incomplete engraving')

    async def settle(self):
        for _ in range(100): await asyncio.sleep(0)

    async def test_typed_policy_refusal_runs_once_but_transient_failure_still_retries(self):
        self.engraving = 'real'
        reason = rules.t('Préréglage {wanted} demandé, {seen} lu : changement bloqué, actions en pause',
                         wanted='III', seen='II')
        done = {'result': 'done', 'text_t': None, 'timings': {}, 'verified_setup': True}
        answers = [{'result': 'failed', 'text_t': reason, 'timings': {},
                    'retryable': False, 'failure_code': 'preset_action_paused'}, done]
        calls = []
        async def farm(*args, **kwargs):
            calls.append((args, kwargs))
            return answers.pop(0)
        self.farming['farm'] = farm

        _, code = await self.call_setup(self.part['api']['state']()['setup_request'])
        self.assertEqual(code, 202)
        await self.settle()
        blocked = self.part['api']['state']()
        self.assertEqual(len(calls), 1, 'a permanent policy refusal must not consume the queued success')
        self.assertEqual(len(answers), 1)
        self.assertEqual(blocked['state'], 'failed')
        self.assertEqual(blocked['message_t']['params']['why'], reason)
        self.assertEqual(blocked['setup_result']['result'], 'failed')

        # An explicit later attempt encounters a transient failure with the
        # same wording. Its missing typed refusal must retain ordinary retry.
        answers[:] = [{'result': 'failed', 'text_t': reason, 'timings': {}}, done]
        calls.clear()
        _, code = await self.call_setup(blocked['setup_request'])
        self.assertEqual(code, 202)
        await self.settle()
        recovered = self.part['api']['state']()
        self.assertEqual(len(calls), 2)
        self.assertEqual(recovered['state'], 'farming')
        self.assertEqual(recovered['setup_result']['result'], 'done')

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
