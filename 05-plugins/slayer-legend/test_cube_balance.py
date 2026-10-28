"""Cube balance OCR on a crop of a real 720x1560 weapon detail capture."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location("cube_test_" + name.replace("/", "_"),
                                                  os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cubes = load("cube_balance")
rules = load("features/game_rules")


def captured_counter(name="cube_balance_720"):
    with open(os.path.join(HERE, f"fixtures/{name}.txt"), encoding="ascii") as source:
        lines = [line.strip() for line in source if not line.startswith("#")]
    width, height, x0, y0, w, h = map(int, lines[0].split())
    pixels = bytearray(bytes((20, 16, 14)) * width * height)
    for row, data in enumerate(lines[1:]):
        start = ((y0 + row) * width + x0) * 3
        pixels[start:start + w * 3] = bytes.fromhex(data)
    return width, height, pixels


class CubeBalance(unittest.TestCase):
    def test_real_weapon_detail_counter_is_exact(self):
        width, height, pixels = captured_counter()
        self.assertEqual(cubes.read((width, height, pixels)),
                         {"text": "2,874,661,318", "value": 2874661318})

    def test_later_counter_with_touching_digits_is_exact(self):
        width, height, pixels = captured_counter("cube_balance_720_b")
        self.assertEqual(cubes.read((width, height, pixels)),
                         {"text": "2,875,027,398", "value": 2875027398})

    def test_middle_bar_distinguishes_eight_from_zero(self):
        width, height, pixels = captured_counter("cube_balance_720_c")
        self.assertEqual(cubes.read((width, height, pixels)),
                         {"text": "2,876,028,358", "value": 2876028358})

    def test_successive_native_balances_keep_zero_and_eight_distinct(self):
        for name, text, value in (("cube_balance_720_d", "3,850,085,694", 3850085694),
                                  ("cube_balance_720_e", "3,850,167,614", 3850167614)):
            with self.subTest(name=name):
                self.assertEqual(cubes.read(captured_counter(name)), {"text": text, "value": value})

    def test_real_successive_balances_produce_a_rate_at_observation_times(self):
        rate_rules = load("features/gold_rules")
        window = rate_rules.empty()
        # Values come from two actual native captures. Times are controlled
        # test observations; no filesystem time is claimed as capture evidence.
        for at, name in ((100.0, "cube_balance_720_d"), (110.0, "cube_balance_720_e")):
            reading = cubes.read(captured_counter(name))
            self.assertIsNotNone(reading)
            window = rate_rules.counted(window, {**reading, "full": True, "step": 1}, at)
        rate, samples = rate_rules.rate(window["samples"], 110.0)
        self.assertEqual(rate, 8192)
        self.assertEqual(rate * 3600, 29491200)
        self.assertEqual(samples[-1][0], 110.0)

    def test_unreadable_digit_does_not_produce_a_balance(self):
        width, height, pixels = captured_counter("cube_balance_720_b")
        for y in range(433, 451):
            for x in range(667, 678):
                pixels[(y * width + x) * 3:(y * width + x + 1) * 3] = bytes((20, 16, 14))
        self.assertIsNone(cubes.read((width, height, pixels)))

    def test_a_number_without_the_cube_icon_is_not_a_balance(self):
        width, height, pixels = captured_counter()
        for y in range(421, 458):
            for x in range(486, 535):
                pixels[(y * width + x) * 3:(y * width + x + 1) * 3] = bytes((20, 16, 14))
        self.assertIsNone(cubes.read((width, height, pixels)))

    def test_resource_fact_is_exposed_and_kept(self):
        self.assertFalse(rules.FIELDS["cubes"]["pending"])
        self.assertEqual(rules.TREE["weapon_detail"]["via"], "equipment_weapon/inspect_weapon")
        self.assertIn("cubes", rules.readers_for({"screen": "battle", "overlays": ["panel"]}))
        self.assertIn("cubes", rules.readers_for({"screen": "battle", "overlays": [], "plain": True}))
        read = cubes.read(captured_counter())
        facts, _ = rules.noted({}, {"cubes": read}, 1234.0)
        row = next(row for row in rules.answer(facts)["resources"] if row["field"] == "cubes")
        self.assertEqual((row["value"], row["seen"], row["verified"], row["source"]),
                         (read, 1234.0, True, "scan"))
        self.assertEqual(rules.persisted(facts)["cubes"], facts["cubes"])


if __name__ == "__main__":
    unittest.main()
