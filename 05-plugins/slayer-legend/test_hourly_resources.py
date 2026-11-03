"""Hourly resource sampling uses actual fresh reader outputs and capture times.
No device, navigation or historical game facts stand in for observations.
"""
import asyncio
import importlib.util
import json
import copy
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location("hourly_" + name, HERE / "features" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


feature = load("gold")
rules = load("gold_rules")


class HourlyResources(unittest.TestCase):
    def measure(self, values, *, repeated=False, ocr_delay=0):
        clock = [100.0]
        queued = []
        forces = []
        source = list(values)
        pixels = object()
        captures = []
        observed = {}

        async def capture(max_age):
            if not source:
                return None
            reading = source.pop(0)
            if reading is None:
                return None
            shot = (480, 1040, pixels if repeated else object())
            at = 100.0 if repeated else clock[0]
            observed[id(shot[2])] = at
            captures.append(shot)
            return shot

        async def scan(shot, force):
            forces.append(force)
            index = 0 if repeated else len(captures) - 1
            current = values[index]
            clock[0] += ocr_delay
            return {"gold_place": ("battle", [[True]]), **current}

        async def focused():
            return True

        async def sleep(seconds):
            clock[0] += seconds

        ports = NS(clock=NS(wall=lambda: clock[0], monotonic=lambda: clock[0], sleep=sleep),
                   capture=capture, capture_time=lambda shot: observed[id(shot[2])], focused=focused,
                   game={"scan": scan, "value": lambda field: 999999},
                   spawn=lambda coro: queued.append(coro), respond=lambda value: value,
                   log=lambda *args: None)
        sampled_rules = NS(**{key: getattr(rules, key) for key in dir(rules) if not key.startswith("_")})
        # These fixtures describe counts ten seconds apart, independently
        # of the production sampling interval.
        sampled_rules.GOLD_SECONDS = sampled_rules.SECONDS = 10
        sampled_rules.IDLE = len(values) * (sampled_rules.SECONDS + ocr_delay)
        counter = NS(rate_text=lambda rate: str(rate), DIGITS={"0": []}, LETTERS={}, SIGNS={})
        part = feature.gold(ports, None, None, counter, sampled_rules)
        handler = next(fn for method, path, fn in part["routes"] if path == "/gold")

        async def run():
            await handler(None)
            await queued.pop(0)
            return await handler(None)

        try:
            answer = asyncio.run(run())
        finally:
            for coro in queued:
                coro.close()
        self.assertTrue(all(set(force) == {"gold", "souls", "cubes", "equipment_l3"} for force in forces))
        self.assertEqual(answer["observed_at"], clock[0])
        return answer["resources"]

    def test_true_successive_counts_and_zero_rates(self):
        result = self.measure([{"cubes": {"value": 100, "text": "100"}, "weapon_l3": 3, "accessory_l3": 0},
                               {"cubes": {"value": 110, "text": "110"}, "weapon_l3": 4, "accessory_l3": 0}])
        self.assertEqual(result["cubes"]["rate"], 1)
        self.assertEqual(result["weapon_l3"]["rate"], .1)
        self.assertEqual(result["accessory_l3"]["rate"], 0)
        self.assertEqual(result["cubes"]["read"], 110)

    def test_hidden_counter_retains_dated_last_rate_without_fake_freshness(self):
        result = self.measure([{"cubes": {"value": 100}}, {"cubes": {"value": 110}}, None, None])
        self.assertEqual(result["cubes"]["rate"], 1)
        self.assertEqual(result["cubes"]["read"], 110)
        self.assertEqual(result["cubes"]["status"], "measured", "dated model remains usable between scheduled visits")
        self.assertEqual(result["cubes"]["span"], 10)

    def test_resource_model_expires_only_at_its_measurement_window(self):
        result = self.measure([{"cubes": {"value": 100}}, {"cubes": {"value": 110}}] + [None] * 181)
        self.assertEqual(result["cubes"]["status"], "stale")
        self.assertEqual(result["cubes"]["read"], 110, "expiry must not fabricate a fresh observation")

    def test_old_game_facts_never_become_samples_and_unread_is_not_zero(self):
        result = self.measure([{}, {}, {}, {}])
        for field in result.values():
            self.assertIsNone(field["rate"])
            self.assertIsNone(field["read"])
            self.assertEqual(field["status"], "unread")

    def test_cached_capture_is_not_a_second_sample(self):
        result = self.measure([{"weapon_l3": 3}] * 3, repeated=True)
        self.assertIsNone(result["weapon_l3"]["rate"])
        self.assertEqual(result["weapon_l3"]["span"], 0)

    def test_spending_or_combining_starts_a_new_window(self):
        result = self.measure([{"weapon_l3": n} for n in (3, 4, 0, 1)])
        self.assertEqual(result["weapon_l3"]["rate"], .1)
        self.assertEqual(result["weapon_l3"]["span"], 10)

    def test_acquisition_time_not_ocr_completion_defines_sample_time(self):
        result = self.measure([{"cubes": {"value": 100}}, {"cubes": {"value": 113}}], ocr_delay=3)
        self.assertEqual(result["cubes"]["rate"], 1)
        self.assertEqual(result["cubes"]["span"], 13)
        self.assertEqual(result["cubes"]["read"], 113)


class PersistentHourlyResources(unittest.TestCase):
    PLACE = [[True, False], [True, False]]

    def feature(self, saved=None, now=100):
        clock = [now]
        snapshots = {}
        writes = []
        def save():
            writes.append(json.loads(json.dumps({key: fn() for key, fn in snapshots.items()})))
        store = NS(saved=saved or {}, register=lambda key, fn: snapshots.update({key: fn}), save=save)
        ports = NS(store=store, clock=NS(wall=lambda: clock[0], monotonic=lambda: clock[0]))
        part = feature.gold(ports, None, None, NS(rate_text=lambda value: value), rules)
        def observe(at, counts, place=None):
            clock[0] = at
            part['api']['observe_resources']((480, 1040, b'pixels'),
                {'gold_place': ('battle', place or self.PLACE), **counts}, at)
        return part['api'], observe, snapshots, writes, clock

    def test_exact_samples_survive_restart_without_retimestamping_or_rounding(self):
        api, observe, snapshots, writes, _ = self.feature()
        origin = 10 ** 40 + 17
        observe(100, {'cubes': {'value': origin}})
        observe(400, {'cubes': {'value': origin + 300}})
        self.assertEqual(len(writes), 2, 'first baseline and second slope are immediately persisted')
        saved = json.loads(json.dumps({'hourly_resources': snapshots['hourly_resources']()}))
        restored, again, _, _, _ = self.feature(saved, now=410)
        self.assertIsNone(restored['resources']()['cubes']['rate'], 'restoration alone cannot confirm the current stage')
        again(410, {})  # Fresh stage only, with the counter still hidden.
        row = restored['resources']()['cubes']
        self.assertEqual((row['rate'], row['read'], row['span']), (1, 400, 300))
        self.assertEqual(row['value'], origin + 300)
        restored['observe_resources']((480, 1040, b'pixels'),
            {'gold_place': ('battle', self.PLACE), 'cubes': {'value': origin + 999}}, 400)
        self.assertEqual(restored['resources']()['cubes']['read'], 400, 'cached acquisition cannot become a new sample')
        again(700, {'cubes': {'value': origin + 600}})
        row = restored['resources']()['cubes']
        self.assertEqual((row['rate'], row['span']), (1, 600))

    def test_one_observed_baseline_survives_until_the_next_visit(self):
        _, observe, snapshots, _, _ = self.feature()
        observe(100, {'weapon_l3': 3, 'accessory_l3': 0})
        saved = {'hourly_resources': snapshots['hourly_resources']()}
        restored, again, _, _, _ = self.feature(saved, now=200)
        self.assertIsNone(restored['resources']()['weapon_l3']['rate'])
        again(400, {'weapon_l3': 4, 'accessory_l3': 0})
        self.assertAlmostEqual(restored['resources']()['weapon_l3']['rate'], 1 / 300)
        self.assertEqual(restored['resources']()['accessory_l3']['rate'], 0)
        self.assertEqual(restored['resources']()['weapon_l3']['read'], 400)

    def test_restored_stage_and_spending_boundaries_restart_the_window(self):
        _, observe, snapshots, _, _ = self.feature()
        observe(100, {'weapon_l3': 3})
        observe(200, {'weapon_l3': 4})
        saved = {'hourly_resources': snapshots['hourly_resources']()}
        restored, again, persisted, _, _ = self.feature(saved, now=210)
        other_stage = [[False, True], [False, True]]
        again(300, {}, other_stage)
        self.assertIsNone(restored['resources']()['weapon_l3']['rate'])
        self.assertNotIn('weapon_l3', persisted['hourly_resources']()['resources'])
        again(320, {'weapon_l3': 52}, other_stage)
        self.assertEqual(restored['resources']()['weapon_l3']['span'], 0)
        again(330, {'weapon_l3': 53}, other_stage)
        self.assertAlmostEqual(restored['resources']()['weapon_l3']['rate'], .1)
        again(340, {'weapon_l3': 0}, other_stage)
        self.assertIsNone(restored['resources']()['weapon_l3']['rate'])
        restarted, _, _, _, _ = self.feature({'hourly_resources': persisted['hourly_resources']()}, now=350)
        self.assertEqual(restarted['resources']()['weapon_l3']['value'], 0)
        self.assertIsNone(restarted['resources']()['weapon_l3']['rate'])

    def test_untrusted_expired_future_or_wrong_resource_models_are_not_baselines(self):
        _, observe, snapshots, _, _ = self.feature()
        observe(100, {'cubes': {'value': 123}})
        good = snapshots['hourly_resources']()
        cases = [({'version': 2}, 110), ({**good, 'version': True}, 110), (good, 1901), (good, 90)]
        corruptions = [dict(resource='weapon_l3'), dict(source='setup'), dict(read=101),
                       dict(stage_ink=['12']), dict(stage_ink=['1' * 513]), dict(stage_ink=['0']),
                       dict(samples=[[100, True]]), dict(samples=[[100, 123.0]]),
                       dict(samples=[[100, -1]]), dict(samples=[[100, 10 ** 100]]),
                       dict(samples=[[10 ** 1000, 123]]), dict(samples=[[-10 ** 1000, 123]]),
                       dict(samples=[[100, 123], [100, 123]]),
                       dict(samples=[[100, 123], [101, 122]], read=101),
                       dict(samples=[[100, 123]] * (feature.RESOURCE_SAMPLE_LIMIT + 1))]
        for replacement in corruptions:
            bad = copy.deepcopy(good)
            bad['resources']['cubes'].update(replacement)
            cases.append((bad, 110))
        for saved, now in cases:
            with self.subTest(saved=saved, now=now):
                api, _, _, _, _ = self.feature({'hourly_resources': saved}, now=now)
                row = api['resources']()['cubes']
                self.assertIsNone(row['read'])
                self.assertIsNone(row['rate'])

    def test_only_recent_exact_observations_are_persisted_and_store_size_is_bounded(self):
        api, observe, snapshots, writes, clock = self.feature()
        for bad in (True, 3.0, -1, float('nan'), 10 ** 100):
            observe(100, {'weapon_l3': bad})
        self.assertFalse(writes)
        api['observe_resources']((480, 1040, b'pixels'),
            {'gold_place': ('battle', self.PLACE), 'weapon_l3': 3}, 101)
        self.assertIsNone(api['resources']()['weapon_l3']['read'], 'future captures must not seed a baseline')
        for index in range(feature.RESOURCE_SAMPLE_LIMIT + 10):
            observe(100 + index, {'weapon_l3': index})
        model = snapshots['hourly_resources']()['resources']['weapon_l3']
        self.assertLessEqual(len(model['samples']), feature.RESOURCE_SAMPLE_LIMIT)
        self.assertEqual(model['read'], clock[0])
        self.assertEqual(set(snapshots['hourly_resources']()['resources']), {'weapon_l3'})


class ObservedStageDrop(unittest.TestCase):
    def answer(self, *, number=1, verified=True, source="scan", age=0, screen="battle", input_after=False):
        now = 100.0
        queued = []
        fact = {"value": number, "seen": now - age, "verified": verified, "source": source}
        ports = NS(clock=NS(wall=lambda: now, monotonic=lambda: now),
                   game={"facts": lambda: {"stage": fact},
                         "view": lambda: {"at": now, "look": {"screen": screen}}},
                   last_input=lambda: {"wall": now + 1} if input_after else None,
                   spawn=lambda coroutine: queued.append(coroutine), respond=lambda value: value)
        counter = NS(rate_text=lambda rate: str(rate))
        table = {"fields": ["name", "drop"], "stages": [["Observed weapon stage", "W"],
                                                          ["Observed accessory stage", "A"]]}
        part = feature.gold(ports, None, None, counter, rules, table=table)
        handler = next(fn for method, path, fn in part["routes"] if path == "/gold")
        try:
            result = asyncio.run(handler(None))
        finally:
            for coroutine in queued:
                coroutine.close()
        return {key: value for key, value in result.items() if key.startswith("farming_")}

    def test_catalogue_drop_uses_only_the_recently_observed_stage(self):
        self.assertEqual(self.answer(), {"farming_stage": 1, "farming_drop": "weapon", "farming_read": 100})
        self.assertEqual(self.answer(number=2, screen="saver"),
                         {"farming_stage": 2, "farming_drop": "accessory", "farming_read": 100})

    def test_stale_unverified_pre_input_or_unmapped_stage_does_not_choose_a_counter(self):
        for kwargs in ({"age": 30.1}, {"verified": False}, {"source": "setup"}, {"number": 999},
                       {"number": 0}, {"screen": "unknown"}, {"input_after": True}, {"age": -1}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.answer(**kwargs),
                                 {"farming_stage": None, "farming_drop": None, "farming_read": None})


if __name__ == "__main__":
    unittest.main()
