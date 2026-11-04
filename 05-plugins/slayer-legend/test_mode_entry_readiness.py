"""Farming entry uses the existing launcher and real lease, without a device."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('entry_' + name.replace('/', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ports_module = load('features/ports')
launch_module = load('features/launch')
launch_rules = load('features/launch_rules')
mode_module = load('features/mode')
mode_rules = load('features/mode_rules')
setup_module = load('features/mode_setup')
nav = load('nav')


class EntryReadiness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100.0
        self.process = False
        self.front = False
        self.last_input = None
        self.commands = []
        self.order = []
        self.tasks = []
        self.launch_started = asyncio.Event()
        self.allow_launch = asyncio.Event()
        self.allow_launch.set()
        self.farmed = asyncio.Event()

        async def adb(*args, **kwargs):
            self.commands.append(args)
            if args[:2] == ('shell', 'pidof'):
                if self.process is None:
                    return 2, 'unavailable'
                return (0, '1234') if self.process else (1, '')
            if args[:3] == ('shell', 'dumpsys', 'window'):
                if self.front is None:
                    return 0, ''
                package = ports_module.PACKAGE if self.front else 'com.android.launcher'
                return 0, 'mCurrentFocus=Window{123 u0 ' + package + '/.MainActivity}'
            if args[:3] == ('shell', 'am', 'start'):
                self.order.append('launch')
                self.launch_started.set()
                await self.allow_launch.wait()
                self.process = self.front = True
                return 0, ''
            return 0, ''

        async def analyse(fn, *args):
            return fn(*args)

        async def notify(*args, **kwargs):
            pass

        context = NS(id='slayer-legend', adb=adb, analyse=analyse, notify=notify,
                     json=lambda value, **kwargs: value, last_input=lambda: self.last_input,
                     log=lambda *args, **kwargs: None)
        self.ports = ports_module.build(context, nav)
        self.ports.clock.wall = lambda: 1000000 + self.now
        self.ports.clock.monotonic = lambda: self.now

        async def sleep(seconds):
            if asyncio.current_task().get_coro().__qualname__.endswith('.watch'):
                await asyncio.Event().wait()
            if self.last_input is not None and not self.launch['running']():
                await asyncio.Event().wait()  # Keep the user's hold pending.
            self.now += seconds
            await asyncio.sleep(0)

        self.ports.clock.sleep = sleep

        async def capture(**kwargs):
            return (480, 1040, 'battle')

        self.ports.capture = capture
        self.ports.crashed = lambda: self.async_value(False)

        def spawn(coroutine):
            task = asyncio.create_task(coroutine)
            self.tasks.append(task)
            return task

        self.ports.spawn = spawn
        screens = NS(classify=lambda shot: shot[2], plain_battle=lambda shot: True)
        self.launch = launch_module.launch(self.ports, screens, launch_rules)['api']
        self.parts = {name: {'stage': stage, 'preset': None}
                      for name, stage in [('mpw18', 920), ('mpw4', 931), ('soul', 970)]}
        loadouts = {'loadout': lambda name: dict(self.parts[name]),
                    'stage': lambda name: self.parts[name]['stage'],
                    'set_stage': lambda name, value: self.parts[name].update(stage=value),
                    'adopt_stage': lambda *args: None}
        mines = {'state': lambda: {'enabled': False, 'state': 'off', 'floor': None, 'area': None},
                 'start': lambda *args: None, 'stop': lambda: None,
                 'set_until': lambda *args: None, 'ended': False}

        async def farm(*args, **kwargs):
            async with self.ports.leased('stage_change', 'farming test', 60):
                self.assertTrue(self.process and self.front)
                self.order.append('farm')
                self.farmed.set()
            return {'result': 'done', 'text_t': None, 'verified_setup': True}

        self.mode = mode_module.mode(
            self.ports, mode_rules, None, NS(time_or_none=lambda value: value,
                                             number_or_none=lambda value, top: value),
            mines, screens, NS(fresh=lambda: {'gold': None}), loadouts,
            {'farm': farm}, setup_module.mode_setup, self.launch)
        self.post = next(fn for method, path, fn in self.mode['routes']
                         if (method, path) == ('POST', '/mode'))

    async def asyncTearDown(self):
        self.allow_launch.set()
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def async_value(self, value):
        return value

    async def choose(self, name):
        class Request:
            async def json(self):
                return {'mode': name, 'stage4': 931, 'stageSoul': 970}
        await self.post(Request())

    async def turns(self, count=30):
        for _ in range(count):
            await asyncio.sleep(0)

    async def test_home_launches_under_lease_before_farming_without_killing(self):
        await self.choose('soul')
        await asyncio.wait_for(self.farmed.wait(), 1)
        self.assertEqual(self.order, ['launch', 'farm'])
        self.assertTrue(all('-S' not in command and 'force-stop' not in command for command in self.commands))
        self.assertIsNone(self.ports.lease.state())

    async def test_mode_epoch_distinguishes_return_to_same_config_without_game_input(self):
        self.process = self.front = True
        await self.choose('soul')
        await asyncio.wait_for(self.farmed.wait(), 1)
        first = self.mode['api']['mode_epoch']()
        await self.choose('free')
        await self.turns()
        await self.choose('soul')
        await self.turns()
        self.assertGreater(self.mode['api']['mode_epoch'](), first)

    async def test_already_focused_game_needs_no_launch(self):
        self.process = self.front = True
        await self.choose('soul')
        await asyncio.wait_for(self.farmed.wait(), 1)
        self.assertEqual(self.order, ['farm'])

    async def test_free_and_agent_never_start_entry_launch(self):
        for name in ('free', 'agent'):
            await self.choose(name)
            await self.turns()
        self.assertEqual(self.order, [])

    async def test_mode_change_cancels_owned_launch_before_farm(self):
        self.allow_launch.clear()
        await self.choose('soul')
        await asyncio.wait_for(self.launch_started.wait(), 1)
        await self.choose('free')
        await self.turns()
        self.assertFalse(self.launch['running']())
        self.assertEqual(self.order, ['launch'])
        self.assertIsNone(self.ports.lease.state())

    async def test_input_before_launch_task_takes_lease_prevents_any_start(self):
        original = self.ports.spawn

        def spawn(coroutine):
            if coroutine.cr_code.co_qualname.endswith('.run'):
                self.last_input = {'wall': self.ports.clock.wall(), 'monotonic': self.now + .01}
            return original(coroutine)

        self.ports.spawn = spawn
        await self.choose('soul')
        await self.turns()
        self.assertEqual(self.order, [])
        self.assertIsNone(self.ports.lease.state())

    async def test_user_input_during_launch_does_not_start_farm(self):
        self.allow_launch.clear()
        await self.choose('soul')
        await asyncio.wait_for(self.launch_started.wait(), 1)
        self.last_input = {'wall': self.ports.clock.wall(), 'monotonic': self.now + .01}
        self.allow_launch.set()
        await self.turns()
        self.assertEqual(self.order, ['launch'])
        self.assertFalse(self.farmed.is_set())

    async def test_existing_launch_is_joined_without_duplicate(self):
        self.allow_launch.clear()
        external = self.launch['start']('launch', True)
        await asyncio.wait_for(self.launch_started.wait(), 1)
        await self.choose('soul')
        self.allow_launch.set()
        await asyncio.wait_for(self.farmed.wait(), 1)
        await external
        self.assertEqual(self.order, ['launch', 'farm'])

    async def test_mode_change_does_not_cancel_an_existing_user_launch(self):
        self.allow_launch.clear()
        external = self.launch['start']('launch', True)
        await asyncio.wait_for(self.launch_started.wait(), 1)
        await self.choose('soul')
        await self.turns(5)
        await self.choose('free')
        await self.turns()
        self.assertTrue(self.launch['running']())
        self.allow_launch.set()
        await external
        self.assertEqual(self.order, ['launch'])
        self.assertFalse(self.farmed.is_set())

    async def test_changed_loadout_during_launch_cannot_start_stale_farm(self):
        self.allow_launch.clear()
        await self.choose('soul')
        await asyncio.wait_for(self.launch_started.wait(), 1)
        self.parts['soul']['stage'] = 971
        self.allow_launch.set()
        await self.turns()
        self.assertEqual(self.order, ['launch'])
        self.assertFalse(self.farmed.is_set())

    async def test_unknown_process_or_focus_never_authorises_launch(self):
        for process, front in ((None, False), (True, None)):
            self.process, self.front = process, front
            await self.choose('soul')
            await self.turns()
            self.assertEqual(self.order, [])
            await self.choose('free')
            await self.turns()
