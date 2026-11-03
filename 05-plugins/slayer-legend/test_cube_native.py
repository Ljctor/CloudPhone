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

    def test_independent_source_family(self):
        self.assertEqual(set(native.BANK), set(range(13, 41)))
        for glyphs in native.BANK.values():
            self.assertEqual(set(glyphs), set('0123456789,'))
        for name, expected_size in (('cube_balance_480_six_phase', 30),
                                    ('cube_balance_480_eleven', 32),
                                    ('cube_balance_480_eleven_three', 31)):
            with self.subTest(name=name):
                alternatives = native.paths(native._mask(fixture(name)))
                self.assertEqual(alternatives[0][0], 0, 'whole line must match one independent font pose')
                self.assertEqual(alternatives[0][2], expected_size)

    def test_independent_untrained_amounts(self):
        for name, text in (
            ('cube_balance_480_pair_a', '9,840,296,102'),
            ('cube_balance_480_unseen', '9,840,380,582'),
            ('cube_balance_480_pair_b', '9,840,395,942'),
        ):
            with self.subTest(name=name):
                self.assertEqual(cubes.read(fixture(name)), {'text': text, 'value': int(text.replace(',', ''))})

    def test_measured_auto_size_and_semantic_ambiguity(self):
        for name, text in (
            ('cube_balance_480_six_phase', '9,845,856,422'),
            ('cube_balance_480_eleven', '9,845,910,182'),
            ('cube_balance_480_boundary', '9,845,917,862'),
            ('cube_balance_480_zero_one', '9,840,342,182'),
            ('cube_balance_480_ambiguous', '9,845,871,782'),
            ('cube_balance_480_automatic', '9,847,018,662'),
            ('cube_balance_480_eleven_three', '9,840,319,142'),
            ('cube_balance_480_changed', '9,839,236,262'),
        ):
            with self.subTest(name=name):
                self.assertEqual(cubes.read(fixture(name)), {'text': text, 'value': int(text.replace(',', ''))})
        # These earlier heuristic ambiguities resolve with zero whole-line
        # error using independent source advances and a shared raster phase.

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
        # Grammar checks are not screenshot calibration evidence.
        for text in ('0', '1', '12', '125', '1,250', '123,456,789,012,345'):
            self.assertTrue(native.valid(text))
        for text in ('00', '01', '012', '1234', '1,25', '1,250,'):
            self.assertFalse(native.valid(text))

    def test_small_counts_use_the_same_source_geometry(self):
        # Source-model grammar exercise, not new screenshot calibration.
        for text in ('0', '125', '1,250'):
            glyphs = native.BANK[40]
            pen = 0
            origin = 100 - sum(glyphs[c][4] for c in text) * .5
            alpha = bytes(106 * 22)
            for char in text:
                alpha = native.font.screen(alpha, native.font.raster(
                    glyphs[char], origin, 14.25, pen, 0, 106, 22))
                pen += glyphs[char][4]
            rows = [[int(v >= 100) for v in alpha[y * 106:(y + 1) * 106]] for y in range(22)]
            self.assertEqual(native.decode(rows), {'text': text, 'value': int(text.replace(',', ''))})

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

    def test_damaged_and_close_alternatives_still_reject(self):
        rows = native._mask(fixture('cube_balance_480_six_phase'))
        _, text, size, origin, baseline = native.paths(rows)[0]
        alternative = text.replace('845', '345', 1)
        rendered = bytes(len(rows) * len(rows[0]))
        pen = 0
        for char in alternative:
            rendered = native.font.screen(rendered, native.font.raster(
                native.BANK[size][char], origin, baseline, pen, 0, len(rows[0]), len(rows)))
            pen += native.BANK[size][char][4]
        different = [(y, x) for y, row in enumerate(rows) for x, value in enumerate(row)
                     if value != (rendered[y * len(row) + x] >= 100)]
        self.assertEqual(len(different), 7)
        damaged = [row[:] for row in rows]
        for y, x in different[:2]:
            damaged[y][x] = not damaged[y][x]
        candidates = native.paths(damaged)
        self.assertLessEqual(candidates[0][0], native.MAX_PIXEL_ERROR)
        self.assertLess(candidates[1][0] - candidates[0][0], native.MIN_MARGIN)
        self.assertIsNone(native.decode(damaged), 'a close runner-up must reject even within the error ceiling')
        corrupted = [row[:] for row in rows]
        for y, x in ((0, 0), (1, 0), (2, 0)):
            corrupted[y][x] = True
        self.assertIsNone(native.decode(corrupted))


if __name__ == '__main__':
    unittest.main()
