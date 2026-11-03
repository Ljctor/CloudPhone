"""Real native Gold OCR: calibrated glyphs and independently unseen balances."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('native_test_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gold = load('gold')
native = gold.native
SHADES = (1.0, 157 / 255)
CALIBRATION = {
    'gold_native_480_bright': '13,711,274,173,449,328,901',
    'gold_native_480_a': '34,288,757,064,031,960,292',
    'gold_native_480_b': '34,489,964,534,133,710,705',
    'gold_native_480_c': '34,688,379,806,374,503,271',
    'gold_native_480_d': '85,908,541,979,841,668,463',
    'gold_native_480_e': '86,070,235,619,608,045,691',
}
# Collected after model calibration; none of these glyph cells trained it.
UNSEEN = {
    'gold_native_480_unseen_a': '122,447,158,576,279,681,026',
    'gold_native_480_unseen_b': '123,037,243,057,562,106,335',
}
# Captured after the old mask calibration. A shared source-font renderer
# independently verifies complete amounts, including the smaller Font17
# selected when the same fixed text rectangle contains wider digits.
SOURCE_PHASES = {
    'gold_native_480_font17': '346,954,589,095,103,022,285',
    'gold_native_480_font17_leading': '347,040,047,272,059,610,981',
    'gold_native_480_font18': '347,395,587,133,021,577,022',
}


def fixture(name):
    lines = (HERE / 'fixtures' / (name + '.txt')).read_text().splitlines()
    width, height, left, top, w, h = map(int, lines[1].split())
    crop = bytes.fromhex(''.join(lines[2:]))
    # Only the reviewed counter+coin crop is retained. The omitted display
    # stays blank; white lets exterior-background flooding reach its edge.
    pixels = bytearray(b'\xff\xff\xff' * width * height)
    for y in range(h):
        offset = ((top + y) * width + left) * 3
        pixels[offset:offset + w * 3] = crop[y * w * 3:(y + 1) * w * 3]
    return width, height, bytes(pixels)


class NativeGold(unittest.TestCase):
    def assert_read(self, name, text):
        reading = gold.read(fixture(name), SHADES)
        self.assertIsNotNone(reading, name)
        self.assertEqual(reading['text'], text)
        self.assertEqual(reading['value'], int(text.replace(',', '')))
        self.assertIs(type(reading['value']), int, 'huge balances never lose digits to float rounding')
        self.assertTrue(reading['full'])
        self.assertEqual(reading['step'], 1)

    def test_calibration_captures(self):
        for name, text in CALIBRATION.items():
            with self.subTest(name=name):
                self.assert_read(name, text)

    def test_independent_new_amounts(self):
        for name, text in UNSEEN.items():
            with self.subTest(name=name):
                self.assert_read(name, text)

    def test_source_font_sizes_and_weak_leading_background(self):
        for name, text in SOURCE_PHASES.items():
            with self.subTest(name=name):
                self.assert_read(name, text)
    def test_source_crop_cache_is_bounded_and_reuses_unchanged_signal(self):
        source = native._source_decoder()
        source._decode.cache_clear()
        capture = fixture('gold_native_480_font17')
        first = native.read(capture, SHADES)
        self.assertIsNotNone(first)
        before = source._decode.cache_info()
        self.assertEqual(native.read(capture, SHADES), first)
        after = source._decode.cache_info()
        self.assertGreater(after.hits, before.hits)
        self.assertEqual(after.maxsize, 96)
        self.assertLessEqual(after.currsize, 96)
        self.assertEqual(native.MAX_GLYPH_ERROR, .065)
        self.assertEqual(native.MAX_LINE_ERROR, .025)
        self.assertEqual(native.MIN_MARGIN, 10)

    def test_ambiguous_actual_frame_is_unknown(self):
        self.assertIsNone(native.read(fixture('gold_native_480_ambiguous'), SHADES))

    def test_source_font_has_every_digit_and_comma(self):
        source = native._source_decoder()
        for size in (17, 18, 19):
            self.assertEqual(set(source._BANK[size]), set('0123456789,'))

    def test_counter_needs_its_coin_and_complete_number(self):
        width, height, data = fixture('gold_native_480_unseen_a')
        pixels = bytearray(data)
        for y in range(145, 177):
            for x in range(145, 194):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = b'\xff\xff\xff'
        self.assertIsNone(native.read((width, height, bytes(pixels)), SHADES), 'no adjacent coin means no Gold reading')
        pixels = bytearray(data)
        for y in range(150, 170):
            for x in range(296, 315):
                offset = (y * width + x) * 3
                pixels[offset:offset + 3] = b'\xff\xff\xff'
        self.assertIsNone(native.read((width, height, bytes(pixels)), SHADES), 'truncated final group is not an amount')

    def test_other_resolution_does_not_open_the_old_gate(self):
        self.assertFalse(gold.FULL_DIGITS_CALIBRATED)
        self.assertIsNone(native.read((720, 1560, b''), SHADES))


if __name__ == '__main__':
    unittest.main()
