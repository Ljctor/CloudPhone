"""Bounded native-counter work reuse preserves actual pixels and readings."""
import unittest
from unittest.mock import patch

from test_gold_native import fixture, native, SHADES


class NativeCache(unittest.TestCase):
    def test_changed_gold_histograms_reuse_the_same_gray_level_losses(self):
        source = native._source_decoder()
        source._level_errors.cache_clear()
        source._fit_axes.cache_clear()
        for name in ('gold_native_480_font17', 'gold_native_480_font17_leading'):
            shot = fixture(name)
            _, box, peak = next(native._candidates(shot, SHADES[1]))
            source._fit_axes.cache_clear()
            before = source._level_errors.cache_info()
            self.assertEqual(source._axes(shot, box, peak), (.18, .41))
            after = source._level_errors.cache_info()
            if before.currsize:
                self.assertGreater(after.hits, before.hits)
            self.assertLessEqual(after.currsize, 128)
        self.assertEqual(source._fit_axes.cache_info().maxsize, 128)
        self.assertEqual(source._level_errors.cache_info().maxsize, 128)

    def test_gold_prepares_pixels_once_for_both_brightness_hypotheses(self):
        with patch.object(native, '_candidate_data', wraps=native._candidate_data) as prepare:
            result = native.read(fixture('gold_native_480_font17'), SHADES)
        self.assertEqual(result['text'], '346,954,589,095,103,022,285')
        self.assertEqual(prepare.call_count, 1)

    def test_raster_cache_keeps_parameters_distinct_and_pixels_exact(self):
        font = native._source_decoder()._font
        render = font.raster
        render.cache_clear()
        glyph = font.glyph_bank()[17]['3']
        cases = (
            (glyph, 3.039, 16., 0, 0, 8, 25),
            (glyph, 3.539, 16., 0, 0, 8, 25),
            (glyph, 3.039, 16.5, 1, 1, 8, 25),
            (font.glyph_bank()[18]['8'], -.66, 6.455, 0, 0, 6, 8),
        )
        expected = [render.__wrapped__(*args) for args in cases]
        self.assertEqual([render(*args) for args in cases], expected)
        before = render.cache_info()
        self.assertEqual([render(*args) for args in cases], expected)
        after = render.cache_info()
        self.assertEqual(after.hits - before.hits, len(cases))
        self.assertEqual(after.maxsize, 32768)
        self.assertLessEqual(after.currsize, 32768)


if __name__ == '__main__':
    unittest.main()
