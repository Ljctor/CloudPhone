"""Configuration-scoped rates consume actual observation events, never polled rates."""
import asyncio
import copy
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('rate_history_' + name.replace('/', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feature = load('features/rate_history')
rules = load('features/gold_rules')
engraving = load('features/engraving')


class History(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.input = None
        self.epoch = 1
        self.mode_epoch = 0
        self.enabled = True
        self.state = {'mode': 'soul', 'state': 'farming', 'tone': 'ok', 'hold': None}
        self.watch = {'symptom': None, 'repairing': None}
        self.parts = {mode: {'stage': 920, 'preset': 'IV', 'soul_weapon': {'id': 32, 'variant': 'Gold-maxed'}}
                      for mode in feature.FARMED}
        self.fact = {'value': 920, 'verified': True, 'source': 'scan', 'seen': self.now}
        self.table = {'fields': ['drop'], 'stages': [['W'] for _ in range(1000)]}
        self.table['stages'][920] = ['A']
        self.saved = {}
        self.build()

    def build(self):
        self.readers, self.proofs, self.repairs, self.actions, self.launches = [], [], [], [], []
        self.sections = {}
        self.saves = 0

        def save():
            self.saves += 1
            self.saved = {key: copy.deepcopy(snapshot()) for key, snapshot in self.sections.items()}

        ports = NS(store=NS(saved=copy.deepcopy(self.saved), register=self.sections.__setitem__, save=save),
                   clock=NS(wall=lambda: self.now, monotonic=lambda: self.now),
                   last_input=lambda: self.input, enabled=lambda: self.enabled,
                   on_relaunch=self.launches.append, on_action=self.actions.append,
                   respond=lambda value: value)
        self.built = feature.rate_history(
            ports, rules, {'state': lambda: self.state, 'on_setup_verified': self.proofs.append,
                           'mode_epoch': lambda: self.mode_epoch},
            {'loadout': lambda mode: copy.deepcopy(self.parts[mode]),
             'revision': lambda mode: engraving.revision(self.parts[mode])},
            {'facts': lambda: {'stage': self.fact}, 'on_read': self.subscribe},
            {'on_setup_verified': self.repairs.append, 'look': lambda: self.watch}, self.table)

    def subscribe(self, callback):
        self.readers.append(callback)
        return lambda: self.readers.remove(callback)

    def proof(self, source='mode', **changes):
        mode = self.state['mode']
        receipt = {'result': 'done', 'mode': mode, 'at': self.now,
                   'target': copy.deepcopy(self.parts[mode]), 'revision': engraving.revision(self.parts[mode])}
        (self.proofs if source == 'mode' else self.repairs)[0]({**receipt, **changes})

    def event(self, reader, values, at=None, epoch=None):
        at = self.now if at is None else at
        self.fact = {'value': self.parts.get(self.state['mode'], self.parts['soul'])['stage'],
                     'verified': True, 'source': 'scan', 'seen': at}
        event = {'reader': reader, 'at': at, 'epoch': self.epoch if epoch is None else epoch,
                 'context': {'gold_place': ('battle', [[1, 1, 1]])}, 'values': values}
        self.readers[0](event)

    def sample(self, field, value, at):
        self.now = at
        reading = {'value': value, 'text': str(value), 'step': 1, 'full': True}
        if field == 'gold':
            self.event('gold', {'gold_reading': reading})
        elif field.startswith('soul_'):
            self.event('souls', {'souls_reading': {field[5:]: reading}})
        else:
            self.event('cubes' if field == 'cubes' else 'equipment_l3', {field: value})

    def row(self, field='gold', mode='soul'):
        return next(row for row in self.built['api']['get']()['configs'][mode]['fields'] if row['field'] == field)

    def test_measurements_are_dated_from_samples_and_exactly_six_fields(self):
        self.sample('gold', 100, 1001)
        self.assertIsNone(self.row()['rate_per_hour'], 'farming state alone is not a verified episode')
        self.proof()
        fields = ('gold', 'cubes', 'weapon_l3', 'soul_green', 'soul_blue', 'soul_red')
        for field in fields:
            self.sample(field, 100, 1002)
            self.sample(field, 120, 1012)
        self.now = 1040
        rows = self.built['api']['get']()['configs']['soul']['fields']
        self.assertEqual([row['field'] for row in rows], list(fields))
        self.assertTrue(all(row['rate_per_hour'] == 7200 for row in rows))
        self.assertTrue(all(row['measured_at'] == 1012 and row['window_start'] == 1002 for row in rows))
        before = copy.deepcopy(self.saved)
        self.built['api']['get']()
        self.assertEqual(self.saved, before, 'polling cannot refresh or invent a measurement')

    def test_same_stage_other_variant_and_return_keep_separate_history(self):
        self.proof()
        self.sample('gold', 100, 1001)
        self.sample('gold', 110, 1011)
        original = copy.deepcopy(self.parts['soul'])
        self.parts['soul']['soul_weapon']['variant'] = 'Gold-balanced'
        self.assertIsNone(self.row()['rate_per_hour'])
        self.now = 1020
        self.proof()
        self.sample('gold', 1000, 1021)
        self.assertIsNone(self.row()['rate_per_hour'], 'old samples from the same stage cannot enter this variant')
        self.sample('gold', 1040, 1031)
        self.assertEqual(self.row()['rate_per_hour'], 14400)
        self.parts['soul'] = original
        self.assertEqual(self.row()['rate_per_hour'], 3600)
        self.assertEqual(self.row()['measured_at'], 1011)

    def test_mode_input_launch_and_late_epoch_boundaries_never_join_samples(self):
        for boundary in ('mode', 'input', 'launch', 'epoch'):
            with self.subTest(boundary=boundary):
                self.setUp()
                self.proof()
                self.sample('cubes', 100, 1001)
                if boundary == 'mode':
                    self.mode_epoch += 2  # Free play and back, even with no observations between.
                elif boundary == 'input':
                    self.input = {'wall': 1002, 'monotonic': 1002}
                elif boundary == 'launch':
                    self.launches[0]('new process')
                else:
                    self.epoch += 1
                    self.sample('cubes', 110, 1002)
                self.now = 1010
                self.proof(source='watchdog')
                self.sample('cubes', 200, 1011)
                self.assertIsNone(self.row('cubes')['rate_per_hour'])
                self.event('cubes', {'cubes': 10000}, at=999)
                self.sample('cubes', 210, 1021)
                self.assertEqual(self.row('cubes')['rate_per_hour'], 3600)

    def test_periodic_readonly_renewal_keeps_sparse_cube_and_l3_samples(self):
        self.proof()
        for field in ('cubes', 'weapon_l3'):
            self.sample(field, 100, 1001)
        self.state['tone'] = 'setup'
        self.watch.update(symptom='verification_due', repairing='loadout')
        self.sample('cubes', 5000, 1290)  # A checking-phase sample must not enter the model.
        for event in ({'screen': 'soul_weapon', 'move': 'close'},
                      {'screen': 'soul_weapon_engraving', 'move': 'lock'},
                      {'screen': 'soul_weapon_engraving_preview', 'move': 'rotate'}):
            self.actions[0](event)
        self.state['tone'] = 'ok'
        self.watch.update(symptom=None, repairing=None)
        self.now = 1300
        self.proof(source='watchdog')
        self.event('cubes', {'cubes': 9000}, at=1291)  # Delayed checking-phase OCR stays excluded.
        for field in ('cubes', 'weapon_l3'):
            self.sample(field, 110, 1301)
            self.assertEqual(self.row(field)['rate_per_hour'], 120)
            self.assertEqual(self.row(field)['span'], 300)

    def test_actual_mutation_starts_empty_but_keeps_last_historical_snapshot(self):
        for screen, move in feature.MUTATIONS:
            with self.subTest(screen=screen, move=move):
                self.setUp()
                self.proof()
                self.sample('cubes', 100, 1001)
                self.sample('cubes', 110, 1011)
                old = copy.deepcopy(self.row('cubes'))
                self.actions[0]({'screen': screen, 'move': move})
                self.now = 1020
                self.proof()
                self.sample('cubes', 1000, 1021)
                self.assertEqual(self.row('cubes'), old)
                self.sample('cubes', 1020, 1031)
                self.assertEqual(self.row('cubes')['rate_per_hour'], 7200)
                self.assertEqual(self.row('cubes')['window_start'], 1021)

    def test_restart_restores_snapshots_not_active_samples(self):
        self.proof()
        self.sample('cubes', 100, 1001)
        self.sample('cubes', 110, 1011)
        self.saved = json.loads(json.dumps(self.saved))
        self.build()
        self.assertEqual(self.row('cubes')['measured_at'], 1011)
        self.sample('cubes', 10000, 1012)
        self.assertEqual(self.row('cubes')['measured_at'], 1011)
        self.now = 1020
        self.proof(source='watchdog')
        self.sample('cubes', 20000, 1021)
        self.assertEqual(self.row('cubes')['measured_at'], 1011)
        self.sample('cubes', 20010, 1031)
        self.assertEqual(self.row('cubes')['window_start'], 1021)

    def test_mode_and_drop_selection_and_unsupported_profiles_are_explicit(self):
        self.proof()
        self.sample('gold', 100, 1001)
        self.sample('gold', 110, 1011)
        self.assertIsNone(self.row(mode='mpw4')['rate_per_hour'])
        self.parts['mpw4']['stage'] = 921
        result = self.built['api']['get']()['configs']
        self.assertEqual(result['mpw4']['fields'][2]['field'], 'accessory_l3')
        self.assertEqual(result['soul']['fields'][2]['field'], 'weapon_l3')
        for mode in ('free', 'mine'):
            self.assertFalse(result[mode]['supported'])
            self.assertEqual(len(result[mode]['fields']), 6)
            self.assertTrue(all(row['rate_per_hour'] is None for row in result[mode]['fields']))
        self.parts['soul']['preset'] = None
        self.assertFalse(self.built['api']['get']()['configs']['soul']['supported'])

    def test_wrong_or_unverified_stage_and_old_or_future_observations_cannot_measure(self):
        self.proof()
        self.sample('gold', 100, 1001)
        self.now = 1011
        for at, epoch in ((999, 1), (1012, 1), (1011, None)):
            event = {'reader': 'gold', 'at': at, 'epoch': epoch,
                     'context': {'gold_place': ('battle', [[1, 1, 1]])},
                     'values': {'gold_reading': {'value': 1000, 'step': 1, 'full': True}}}
            self.readers[0](event)
        self.assertIsNone(self.row()['rate_per_hour'])
        self.fact['verified'] = False
        self.readers[0]({'reader': 'gold', 'at': 1011, 'epoch': 1,
                         'context': {'gold_place': ('battle', [[1, 1, 1]])},
                         'values': {'gold_reading': {'value': 1000, 'step': 1, 'full': True}}})
        self.assertIsNone(self.row()['rate_per_hour'])
        self.event('battle_stage', {'stage': 921})
        self.sample('gold', 110, 1021)
        self.assertIsNone(self.row()['rate_per_hour'])

    def test_zero_is_an_actual_two_point_measurement_and_bad_persistence_stays_unknown(self):
        self.proof()
        self.sample('cubes', 100, 1001)
        self.sample('cubes', 100, 1011)
        self.assertEqual(self.row('cubes')['rate_per_hour'], 0)
        stored = self.saved['config_rate_history']['configs']
        for record in stored.values():
            record['rates']['cubes']['rate_per_hour'] = float('nan')
        self.build()
        self.assertIsNone(self.row('cubes')['rate_per_hour'])

    def test_readonly_route_contract_includes_unknown_profiles_and_rejects_bad_receipts(self):
        handler = self.built['routes'][0][2]
        response = asyncio.run(handler(None))
        self.assertEqual(response['version'], 1)
        self.assertEqual(set(response['configs']), {'mpw18', 'mpw4', 'soul', 'free', 'mine'})
        for change in ({'result': 'failed'}, {'revision': 'another-revision'},
                       {'target': {**self.parts['soul'], 'preset': 'I'}}, {'at': self.now + 1}):
            self.setUp()
            self.proof(**change)
            self.sample('gold', 100, self.now + 1)
            self.sample('gold', 110, self.now + 1)
            self.assertIsNone(self.row()['rate_per_hour'])
