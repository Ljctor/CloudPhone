"""Native Cube OCR: independently measured glyphs and new real balances."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('cube_native_test_' + name.replace('/', '_'), HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cubes = load('cube_balance')
native = cubes.native
rules = load('features/gold_rules')


def fixture(name):
    lines = (HERE / 'fixtures' / (name + '.txt')).read_text().splitlines()
    width, height, left, top, w, h = map(int, lines[1].split())
    pixels = bytearray(bytes((20, 16, 14)) * width * height)
    raw = bytes.fromhex(''.join(lines[2:]))
    for y in range(h):
        offset = ((top + y) * width + left) * 3
        pixels[offset:offset + w * 3] = raw[y * w * 3:(y + 1) * w * 3]
    return width, height, pixels


class NativeCubes(unittest.TestCase):
    def test_reviewed_native_balances(self):
        for name, text in (
            ('cube_balance_480_base', '9,836,747,942'),
            ('cube_balance_480_five', '9,840,365,222'),
        ):
            with self.subTest(name=name):
                self.assertEqual(cubes.read(fixture(name)), {'text': text, 'value': int(text.replace(',', ''))})

    def test_missing_digits_are_actual_independent_native_footprints(self):
        shot = fixture('cube_balance_480_zero_one')
        mask = native._mask(shot)
        for char, left, right in (('0', 401, 408), ('1', 440, 444)):
            glyph = tuple(tuple(row[left - 357:right - 357]) for row in mask)
            self.assertIn(glyph, native.PATTERNS[char])
        mask = native._mask(fixture('cube_balance_480_five'))
        self.assertIn(tuple(tuple(row[426 - 357:433 - 357]) for row in mask), native.PATTERNS['5'])
        mask = native._mask(fixture('cube_balance_480_changed'))
        three = tuple(tuple(row[419 - 357:426 - 357]) for row in mask)
        self.assertIn(three, native.PATTERNS['3'])
        self.assertNotIn(three, native.PATTERNS['8'], 'the observed open left side cannot train an eight alias')
        self.assertEqual(set(native.PATTERNS), set('0123456789,'))
        self.assertTrue(all(len(owners) == 1 for owners in native.OWNERS.values()))
        for char, variants in native.PATTERNS.items():
            for glyph in variants:
                if char == ',':
                    self.assertFalse(any(value for row in glyph[:8] for value in row))
                else:
                    self.assertFalse(any(value for row in glyph[10:] for value in row), 'comma fragments do not train a digit')

    def test_independent_untrained_amounts(self):
        for name, text in (
            ('cube_balance_480_pair_a', '9,840,296,102'),
            ('cube_balance_480_unseen', '9,840,380,582'),
            ('cube_balance_480_pair_b', '9,840,395,942'),
        ):
            with self.subTest(name=name):
                self.assertEqual(cubes.read(fixture(name)), {'text': text, 'value': int(text.replace(',', ''))})

    def test_real_counts_feed_rate_arithmetic_at_observation_times(self):
        window = rules.empty()
        # Controlled test times; actual acquisition times are not fabricated
        # from files or supplied to the running plugin by these tests.
        for at, name in ((100.0, 'cube_balance_480_pair_a'), (110.0, 'cube_balance_480_pair_b')):
            reading = cubes.read(fixture(name))
            window = rules.counted(window, {**reading, 'full': True, 'step': 1}, at)
        rate, _ = rules.rate(window['samples'], 110.0)
        self.assertEqual(rate, 9984)
        self.assertEqual(rate * 3600, 35942400)

    def test_integer_grammar_also_accepts_zero_and_small_counts(self):
        # Grammar-only composition from measured cells. This is deliberately
        # not claimed as a real screenshot or new font calibration evidence.
        def cells(text):
            rows = [[] for _ in range(14)]
            for char in text:
                glyph = native.PATTERNS[char][0]
                for y in range(14):
                    rows[y].extend(glyph[y])
                    rows[y].append(False)
            return rows
        for text in ('0', '1', '12', '125', '1,250'):
            with self.subTest(text=text):
                self.assertEqual(native.decode(cells(text)), {'text': text, 'value': int(text.replace(',', ''))})
        for text in ('00', '01', '012', '1234', '1,25', '1,250,'):
            with self.subTest(text=text):
                self.assertIsNone(native.decode(cells(text)))

    def test_missing_icon_truncation_and_foreign_text_fail_closed(self):
        width, height, pixels = fixture('cube_balance_480_pair_a')
        no_icon = bytearray(pixels)
        for y in range(280, 308):
            for x in range(326, 357):
                offset = (y * width + x) * 3
                no_icon[offset:offset + 3] = bytes((20, 16, 14))
        self.assertIsNone(cubes.read((width, height, no_icon)))
        incomplete = bytearray(pixels)
        for y in range(286, 304):
            for x in range(450, 464):
                offset = (y * width + x) * 3
                incomplete[offset:offset + 3] = bytes((20, 16, 14))
        self.assertIsNone(cubes.read((width, height, incomplete)))
        width, height, pixels = fixture('cube_balance_480_zero_one')
        shifted = bytearray(bytes((20, 16, 14)) * width * height)
        for y in range(280, 308):
            a = ((y + 30) * width + 326) * 3
            b = (y * width + 326) * 3
            shifted[a:a + 141 * 3] = pixels[b:b + 141 * 3]
        self.assertIsNone(cubes.read((width, height, shifted)))

    def test_noisy_segmentation_does_not_gain_confidence_from_another_exact_digit(self):
        # This complete real balance has an unresolved alternative despite
        # independently exact other digits. Refusing it is preferable to
        # substituting an eight/three alias or loosening the error ceiling.
        self.assertIsNone(cubes.read(fixture('cube_balance_480_zero_one')))


if __name__ == '__main__':
    unittest.main()
