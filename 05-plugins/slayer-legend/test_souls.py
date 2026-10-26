"""The souls counters and the rates per second: the counters' notation
(gold.parse: abbreviated and full digits), the souls row read on crops of
real captures (fixtures/souls_row*, the Soul Weapon screen open), the gold
counter shaded under that screen (fixtures/gold_parked*), and the window
rules (features/gold_rules.py) on scripted readings: the window's length
follows the resolution read, spending souls is left out.
Run: python3 -m unittest test_souls"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_souls_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gold = load("gold")
souls = load("soul_counters")
rules = load("features/gold_rules")
screens = load("screens")
fixtures = load("test_fixtures")
C = 1000.0 ** 3


class Notation(unittest.TestCase):
    def test_leading_zero_display(self):
        self.assertEqual(gold.normalize_text("02.0C"), "2.0C")
        self.assertEqual(gold.normalize_text("00012"), "12")
        self.assertEqual(gold.normalize_text("0.70C"), "0.70C")
        self.assertEqual(gold.normalize_text("000.5C"), "0.5C")
        self.assertEqual(gold.parse("02.0C")["value"], gold.parse("2.0C")["value"])

    def test_abbreviated(self):
        self.assertEqual(gold.parse("94.6C"), {"value": 94.6 * C, "step": 0.1 * C, "full": False})
        self.assertEqual(gold.parse("4.64C"), {"value": 4.64 * C, "step": 0.01 * C, "full": False})
        self.assertEqual(gold.parse("111F")["value"], 111 * 1000.0 ** 6)
        self.assertEqual(gold.parse("111F")["step"], 1000.0 ** 6)
        self.assertEqual(gold.parse("1.5A")["value"], 1500)

    def test_full_digits(self):
        for text in ("94600000000", "94,600,000,000", "94.600.000.000", "94 600 000 000", "94 600 000 000"):
            self.assertEqual(gold.parse(text), {"value": 94_600_000_000.0, "step": 1.0, "full": True}, text)
        # Up to 3 digits read the same in both notations.
        self.assertEqual(gold.parse("999"), {"value": 999.0, "step": 1.0, "full": False})

    def test_neither(self):
        for text in (None, "", "C", ".5C", "5.C", "1.2.3C", "9?.6C", "1.2", "1234,567", "12,34", "94.6c", "4,"):
            self.assertIsNone(gold.parse(text), text)


class SoulsRow(unittest.TestCase):
    def test_the_four_counters(self):
        read = souls.read(fixtures.screen("souls_row"))
        self.assertEqual({colour: count["text"] for colour, count in read.items()},
                         {"green": "94.6C", "blue": "19.4C", "red": "16.1C", "white": "4.64C"})
        self.assertEqual(read["green"]["value"], 94.6 * C)
        self.assertEqual(read["green"]["step"], 0.1 * C)
        self.assertEqual(read["white"]["step"], 0.01 * C)
        self.assertEqual(souls.read(fixtures.screen("souls_row_b"))["green"]["text"], "94.7C")

    def test_not_shown(self):
        self.assertIsNone(souls.read(fixtures.screen("bar_parked_partial")))
        self.assertIsNone(souls.read(fixtures.screen("gold_parked")))

    def test_full_digits_gated(self):
        # Until a capture of them is a fixture (test_gates.py: souls_full).
        self.assertFalse(souls.FULL_DIGITS_CALIBRATED)
        self.assertFalse(gold.FULL_DIGITS_CALIBRATED)

    def test_the_glyphs_drawn_are_listed(self):
        # The cut ones come from the fixtures; the drawn ones wait for a
        # capture showing them.
        self.assertEqual(sorted(souls.CUT), [".", "1", "4", "6", "7", "9", "C"])
        self.assertFalse(set(souls.CUT) & set(souls.DRAWN))


class GoldParked(unittest.TestCase):
    def test_shaded_under_the_soul_weapon_screen(self):
        shades = (1.0, screens.PARKED_SHADE)
        for name, text in (("gold_parked", "28.9F"), ("gold_parked_dark", "28.3F")):
            shot = fixtures.screen(name)
            self.assertIsNone(gold.read(shot), name)
            self.assertEqual(gold.read(shot, shades)["text"], text, name)


def window_after(values, long=rules.WINDOW, spent="restart", every=rules.SECONDS):
    """The window after one reading of each text (or None), every seconds
    apart, all on the same stage (each read twice: a value counts once two
    readings agree)."""
    window, now = rules.empty(), 0.0
    for text in values:
        for _ in range(2):
            now += every / 2
            window, counts = rules.where(window, "battle", [[True]])
            if counts and text:
                window = rules.counted(window, {"text": text, **gold.parse(text)}, now, long, spent)
    return window, now


class Rates(unittest.TestCase):
    def rate(self, window, now, long=rules.WINDOW):
        return rules.rate(window["samples"], now, rules.window_for(window["step"], long))

    def test_the_window_follows_the_resolution(self):
        self.assertEqual(rules.window_for(None), rules.WINDOW)
        self.assertEqual(rules.window_for(0.1 * C), rules.WINDOW)
        self.assertEqual(rules.window_for(0.1 * C, rules.SOULS_WINDOW), rules.SOULS_WINDOW)
        self.assertEqual(rules.window_for(1.0), rules.SHORT)
        self.assertEqual(rules.window_for(1.0, rules.SOULS_WINDOW), rules.SHORT)

    def test_abbreviated_souls_keep_their_long_window(self):
        # One step of 0.1C every 150 s for 40 minutes: the rate over 30 min.
        texts = [f"{94.6 + 0.1 * (k * rules.SECONDS // 150):.1f}C" for k in range(240)]
        window, now = window_after(texts, rules.SOULS_WINDOW, "skip")
        rate, samples = self.rate(window, now, rules.SOULS_WINDOW)
        self.assertGreaterEqual(samples[-1][0] - samples[0][0], rules.SOULS_WINDOW - rules.SECONDS)
        self.assertAlmostEqual(rate / (0.1 * C / 150), 1, delta=0.1)

    def test_full_digits_take_the_short_window(self):
        # 1234 souls a second, read in full digits: the rate after a minute.
        texts = [str(94_600_000_000 + 1234 * k * rules.SECONDS) for k in range(30)]
        window, now = window_after(texts, rules.SOULS_WINDOW, "skip")
        rate, samples = self.rate(window, now, rules.SOULS_WINDOW)
        self.assertLessEqual(samples[-1][0] - samples[0][0], rules.SHORT)
        self.assertAlmostEqual(rate, 1234)

    def test_full_digits_keep_small_gains_at_a_large_balance(self):
        balance = 10 ** 30
        self.assertEqual(gold.parse(str(balance + 1234))["value"], balance + 1234)
        rate, _ = rules.rate([(0, balance), (10, balance + 12340), (20, balance + 24680)], 20, 60)
        self.assertAlmostEqual(rate, 1234)

    def test_spending_souls_is_left_out(self):
        texts = ["10.0C", "10.1C", "10.2C", "2.00C", "2.10C", "2.20C"]
        window, now = window_after(texts, rules.SOULS_WINDOW, "skip")
        rate, samples = self.rate(window, now, rules.SOULS_WINDOW)
        # The drop counts as nothing earned over its interval; the count
        # goes on from there.
        self.assertEqual([round(value / C, 2) for _, value in samples], [10.0, 10.1, 10.2, 10.2, 10.3, 10.4])
        self.assertGreater(rate, 0)
        self.assertEqual(window["offset"], 8_200_000_000)

    def test_spending_gold_starts_its_window_again(self):
        window, now = window_after(["10.0C", "10.1C", "2.00C", "2.10C"])
        self.assertEqual([value for _, value in window["samples"]], [2.0 * C, 2.1 * C])

    def test_a_new_stage_starts_the_window_and_its_offset_again(self):
        window, now = window_after(["10.0C", "2.00C"], rules.SOULS_WINDOW, "skip")
        self.assertGreater(window["offset"], 0)
        window = rules.elsewhere(rules.elsewhere(window))
        self.assertEqual((window["samples"], window["offset"]), ([], 0.0))


if __name__ == "__main__":
    unittest.main()
