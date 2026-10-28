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

class SetupStatus(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 1000.0; self.input = None; self.playing = False; self.engraving = 'off'; self.soul = 'real'
        self.tasks = []; self.callbacks = []; self.relaunch = []; self.block = None; self.started = asyncio.Event(); self.mine_active = False
        self.parts = {name: {'stage': 970, 'preset': 'III', 'soul_weapon': {'id': 32, 'variant': 'Gold-maxed'}}
                      for name in ('mpw18', 'mpw4')}
        async def sleep(seconds): self.now += seconds; await asyncio.sleep(0)
        async def notify(*args, **kwargs): pass
        def spawn(coro):
            task = asyncio.create_task(coro); self.tasks.append(task); return task
        async def farm(*args, **kwargs):
            self.started.set()
            if self.block: await self.block.wait()
            return {'result': 'failed', 'text_t': rules.t('écran inattendu'), 'timings': {}}
        self.ports = NS(t=rules.t, log=lambda *a, **k: None, english=lambda text: str(text), notify=notify,
            store=NS(saved={'mode': {'mode': 'mpw18', 'default': 'mpw18', 'configured': True}},
                     register=lambda *a: None, save=lambda: None),
            clock=NS(wall=lambda: self.now, monotonic=lambda: self.now, sleep=sleep), spawn=spawn,
            enabled=lambda: True, pause_left=lambda: 5 if self.playing else 0, last_input=lambda: self.input,
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
        self.part = feature.mode(self.ports, rules, None, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming)

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
        free = feature.mode(self.ports, rules, None, NS(time_or_none=lambda v: v, number_or_none=lambda v, n: v),
            self.mines, None, NS(fresh=lambda: {'gold': None}), self.loadouts, self.farming)
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
