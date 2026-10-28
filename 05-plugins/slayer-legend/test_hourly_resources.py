"""Hourly resource sampling uses actual fresh reader outputs and capture times.
No device, navigation or historical game facts stand in for observations.
"""
import asyncio
import importlib.util
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
