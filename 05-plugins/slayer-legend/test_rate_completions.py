"""Rate scheduling on the real observation pipeline, with blocked fake OCR.
These gates prove ordering and bounds; they are not reader calibration evidence.
"""
import asyncio
from collections import Counter
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('completion_' + name.replace('/', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


observation = load('features/game_observation')
reader_module = load('features/game_readers')
game_module = load('features/game')
game_rules = load('features/game_rules')
facts_module = load('features/game_facts')
gold_module = load('features/gold')
gold_rules = load('features/gold_rules')
ports_module = load('features/ports')


class RateCompletions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.tasks = set()
        self.now = 100.0
        self.capture_gate = asyncio.Event()
        self.sleep_gate = asyncio.Event()
        self.soul_gate = asyncio.Event()
        self.soul_gate.set()
        self.gold_gates = {}
        self.metadata = {}
        self.calls = Counter()
        self.events = []
        self.soul_running = self.max_soul_running = 0

    async def asyncTearDown(self):
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        self.directory.cleanup()

    async def turns(self, count=40):
        for _ in range(count):
            await asyncio.sleep(0)

    def track(self, task):
        self.tasks.add(task)
        return task

    def build(self, with_souls=True):
        async def capture(max_age=0):
            await self.capture_gate.wait()
            return None
        async def focused():
            return True
        async def sleep(seconds):
            await self.sleep_gate.wait()
        async def detect(fn, *args):
            return fn(*args)
        async def analyse(fn, *args):
            reader, shot = args[:2]
            self.calls[(reader, shot[2])] += 1
            if reader == 'souls':
                self.soul_running += 1
                self.max_soul_running = max(self.max_soul_running, self.soul_running)
                try:
                    await self.soul_gate.wait()
                finally:
                    self.soul_running -= 1
            elif reader == 'gold' and shot[2] in self.gold_gates:
                await self.gold_gates[shot[2]].wait()
            return fn(*args)
        ports = NS(clock=NS(wall=lambda: self.now, monotonic=lambda: self.now, sleep=sleep),
                   capture=capture, capture_time=lambda shot: self.metadata.get(id(shot)),
                   focused=focused, analyse=analyse, detect=detect,
                   spawn=lambda coroutine: self.track(asyncio.create_task(coroutine)), track_task=self.track,
                   log=lambda *args: None, respond=lambda value: value,
                   store=ports_module.State(self.directory.name),
                   lease=NS(state=lambda: None), last_input=lambda: None)
        screens = NS(look=lambda shot: {'screen': 'battle', 'overlays': ['soul_weapon'], 'plain': False},
                     classify=lambda shot: 'battle')
        def gold(shot, *args):
            value = int(shot[2])
            reading = None if value == 102 else {'text': str(value), 'value': value, 'full': True,
                                               'step': 1, 'box': (0, 0, 1, 1)}
            return {'gold': None if reading is None else {'text': reading['text'], 'value': value},
                    'gold_reading': reading}
        def souls(shot, *args):
            value = int(shot[2]) * 2
            count = {'text': str(value), 'value': value, 'full': True, 'step': 1}
            return {'souls': {'green': count}, 'souls_reading': {'green': count}}
        readers = {'gold': gold, **({'souls': souls} if with_souls else {})}
        # Context belongs to the image, not whichever OCR reader happens to finish first.
        context = lambda shot, *args: {'gold_place': ('battle', [[True, False], [True, False]])}
        registry = reader_module.ReaderRegistry(screens, game_rules, readers, context=context)
        facts = facts_module.FactStore(ports, game_rules)
        pipeline = observation.ObservationPipeline(ports, registry, facts)
        producer = observation.CaptureProducer(ports, pipeline)
        built = game_module.game(ports, game_rules, facts, pipeline, producer)
        ports.game = built['api']
        built['api']['on_read'](self.events.append)
        part = gold_module.gold(ports, None, None, NS(rate_text=lambda value: value), gold_rules,
                                NS(COLOURS=('green',)))
        handler = next(fn for method, path, fn in part['routes'] if path == '/gold')
        self.ports, self.pipeline, self.api, self.handler = ports, pipeline, built['api'], handler
        return part

    def frame(self, at):
        self.now = max(self.now, float(at))
        shot = (1, 1, str(at).encode())
        self.metadata[id(shot)] = float(at)
        return shot

    async def feed(self, at):
        shot = self.frame(at)
        self.pipeline.saw(shot)
        await self.turns()
        return shot

    async def test_slow_soul_jobs_do_not_delay_two_new_gold_captures_or_exact_scan_barrier(self):
        self.build()
        self.soul_gate.clear()
        await self.handler(None)
        await self.feed(100)
        second = await self.feed(104)
        exact = self.track(asyncio.create_task(self.api['scan'](second, ('souls',))))
        await self.turns()
        await self.feed(108)
        state = await self.handler(None)
        self.assertEqual((state['read'], state['value'], state['span']), (108, 108, 8))
        self.assertEqual(state['rate'], 1)
        self.assertFalse(exact.done(), 'mandatory exact-frame scan must still wait for its Soul reader')
        self.assertGreaterEqual(self.pipeline.telemetry()['soul_waiting'], 1)
        self.assertEqual(self.max_soul_running, 1)
        self.soul_gate.set()
        result = await exact
        await self.turns()
        self.assertEqual(result['gold_reading']['value'], 104, 'an exact scan cannot return the newer frame')
        self.assertEqual(self.max_soul_running, 1)
        self.assertTrue(all(count == 1 for count in self.calls.values()), 'each frame/reader shares one OCR job')
        self.assertEqual((await self.handler(None))['read'], 108, 'late Soul completion cannot rewind Gold')

    async def test_soul_completion_uses_same_frame_context_before_gold_ocr_finishes(self):
        self.build()
        self.gold_gates[b'100'] = asyncio.Event()
        await self.handler(None)
        await self.feed(100)
        state = await self.handler(None)
        self.assertIsNone(state['read'])
        self.assertEqual(state['souls']['green']['read'], 100)
        self.assertEqual(state['souls']['green']['text'], '200')
        event = next(event for event in self.events if event['reader'] == 'souls')
        self.assertEqual(event['context']['gold_place'], ('battle', [[True, False], [True, False]]))
        self.gold_gates[b'100'].set()
        await self.turns()
        self.assertEqual((await self.handler(None))['read'], 100)

    async def test_newer_unread_gold_completion_blocks_a_late_older_valid_read(self):
        self.build(with_souls=False)
        await self.handler(None)
        await self.feed(98)
        self.gold_gates[b'100'] = asyncio.Event()
        await self.feed(100)
        await self.feed(102)  # A completed unread observation, not a failed task.
        self.gold_gates[b'100'].set()
        await self.turns()
        state = await self.handler(None)
        self.assertEqual((state['read'], state['value']), (98, 98))
        self.assertFalse(self.api['facts']()['gold']['verified'])

    async def test_stale_epoch_does_not_emit_or_update_a_rate(self):
        self.build(with_souls=False)
        self.gold_gates[b'100'] = asyncio.Event()
        await self.handler(None)
        await self.feed(100)
        self.api['relaunched']('test epoch transition')
        self.gold_gates[b'100'].set()
        await self.turns()
        self.assertFalse(self.events)
        self.assertIsNone((await self.handler(None))['read'])

    async def test_pending_background_lane_and_explicit_claim_run_once_including_unread_cache(self):
        self.build(with_souls=False)
        await self.handler(None)
        shot = self.frame(102)
        frame = await self.pipeline.detect(shot, self.pipeline.observed(shot))
        self.pipeline.enqueue(frame)  # Queue background work without yielding to its lane.
        result = await self.api['scan'](shot, ('gold',))  # Claim that same work first.
        self.assertIsNone(result['gold_reading'])
        await self.turns()
        await self.api['scan'](shot, ('gold',))
        self.assertEqual(self.calls[('gold', b'102')], 1)
        self.assertEqual(len([event for event in self.events if event['reader'] == 'gold']), 1)

    async def test_completion_retains_capture_time_and_context_after_metadata_and_frame_cache_eviction(self):
        self.build()
        self.soul_gate.clear()
        await self.handler(None)
        first = await self.feed(100)
        stamp = self.pipeline.observed(first)
        for at in range(104, 144, 2):
            await self.feed(at)
        self.metadata.clear()
        self.assertFalse(any(frame['pixels'] is first[2] for frame in self.pipeline.frames))
        exact = self.track(asyncio.create_task(self.pipeline.scan_observed(first, ('souls',), stamp)))
        await self.turns()
        self.soul_gate.set()
        await exact
        await self.turns(100)
        self.assertEqual(self.calls[('souls', b'100')], 1, 'cache eviction cannot duplicate in-flight OCR')
        event = next(event for event in self.events if event['reader'] == 'souls' and event['shot'] is first)
        self.assertEqual(event['at'], 100)
        self.assertEqual(event['context']['gold_place'][0], 'battle')
        self.assertEqual((await self.handler(None))['read'], 142)

    def test_detector_stage_context_is_reused_without_duplicate_stage_extraction(self):
        for base in ('battle', 'saver'):
            with self.subTest(base=base):
                extractions = []
                def crop(*args):
                    extractions.append('battle')
                    return [[True]]
                def saver(*args):
                    extractions.append('saver')
                    return 970, None
                stage = NS(BATTLE_NAME=(0, 0, 1, 1), _crop=crop, _ink=lambda rows: rows, read_saver=saver)
                screens = NS(SOUL_WEAPON='soul_weapon', PARKED_SHADE=.6,
                             look=lambda shot: {'screen': base, 'overlays': [], 'plain': True},
                             classify=lambda shot: base)
                readers = reader_module.reader_table(screens, stage, NS(regions=lambda table: []),
                    NS(read=lambda *args: None), None, None, None, None, None, {}, None)
                registry = reader_module.ReaderRegistry(screens, game_rules, readers,
                                                        context=reader_module.stage_context(stage))
                shot = (1, 1, b'image')
                look, context = registry.identify_context(shot)
                values = registry.read('gold', shot, look, context)
                self.assertEqual(extractions, [base])
                self.assertEqual(values['gold_place'], context['gold_place'])

    async def test_focus_loss_discards_old_in_flight_completions(self):
        self.build(with_souls=False)
        self.gold_gates[b'100'] = asyncio.Event()
        await self.handler(None)
        await self.feed(100)
        self.now = 104
        self.capture_gate.set()  # The watch observes no foreground game capture.
        await self.turns()
        self.gold_gates[b'100'].set()
        await self.turns()
        self.assertIsNone((await self.handler(None))['read'])


if __name__ == '__main__':
    unittest.main()
