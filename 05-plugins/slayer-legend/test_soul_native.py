"""Exact native Soul OCR on reviewed real rows and an independent heldout.

Source masks come from the game's font and metrics, not balance-conditioned
cuts. Earlier tiny manual transcriptions confused8/9/7 and were corrected
against original pixels before these regression labels were accepted.
"""
import unittest
from unittest.mock import patch

from test_fixtures import load, screen

native = load('soul_native')
souls = load('soul_counters')

ROWS = {
    'souls_native_480_b': ('254,201,546,354', '36,385,679,793', '37,280,529,183'),
    'souls_native_480_c': ('254,347,147,922', '36,489,037,307', '37,309,679,681'),
    'souls_native_480_e': ('254,430,020,810', '36,517,059,803', '37,340,859,020'),
    # Independently captured AFTER the reader family was fixed. Green's
    # tiny text is certified by unique whole-line source-raster agreement;
    # its exact value was not a reliable manual transcription on its own.
    'souls_native_480_unseen': ('256,678,455,641', '36,950,731,564', '37,592,023,104'),
    'souls_native_480_changed': ('256,781,295,113', '36,980,936,696', '37,592,023,104'),
}


def rows_of(shot, colour):
    width, _, pixels = shot
    left, top, right, bottom = native.BOXES[colour]
    return [[min(pixels[(y*width+x)*3:(y*width+x)*3+3]) for x in range(left,right)]
            for y in range(top,bottom)]


class NativeSouls(unittest.TestCase):
    def test_real_rows_and_independent_holdout(self):
        for fixture, expected in ROWS.items():
            shot=screen(fixture)
            for colour,text in zip(native.BOXES,expected):
                with self.subTest(fixture=fixture,colour=colour):
                    result=native.read(shot,colour)
                    self.assertIsNotNone(result)
                    self.assertEqual(result,{'text':text,'value':int(text.replace(',','')),'step':1,'full':True})
                    candidates=native.candidates(rows_of(shot,colour))
                    self.assertLess(candidates[0][0],.0001)
                    self.assertGreater(candidates[1][0]-candidates[0][0],.0002)

    def test_native_integration_detects_full_width_row(self):
        result=souls.read(screen('souls_native_480_e'))
        self.assertIsNotNone(result)
        for colour,text in zip(native.BOXES,ROWS['souls_native_480_e']):
            self.assertEqual(result[colour]['text'],text)
        self.assertIsNone(native.read(screen('souls_native_480_e'),'white'))

    def test_missing_digit_cannot_become_a_smaller_plausible_balance(self):
        rows=rows_of(screen('souls_native_480_e'),'blue')
        # Erase a whole observed glyph in the middle of the row, retaining
        # the actual commas and all other digits.
        for row in rows:
            row[29:34]=[17]*5
        self.assertIsNone(native.decode(rows))

    def test_a_damaged_comma_is_not_reinterpreted_as_another_group(self):
        rows=rows_of(screen('souls_native_480_e'),'red')
        for y in range(14,19):
            rows[y][12:16]=[17]*4
        self.assertIsNone(native.decode(rows))

    def test_non_counter_and_closed_gate_are_unread(self):
        self.assertIsNone(native.decode([[17]*66 for _ in range(25)]))
        self.assertIsNone(native.decode([[255]*66 for _ in range(25)]))
        self.assertIsNone(souls.read(screen('gold_parked')))
        with patch.object(native,'NATIVE_DIGITS_CALIBRATED',False):
            self.assertIsNone(native.read(screen('souls_native_480_e'),'green'))

    def test_leading_zero_cannot_be_repaired_into_a_valid_balance(self):
        # Render a deliberately invalid grouped prefix using independent
        # font metrics. Grammar must reject0, never promote it to8.
        width,height=66,25
        mask=bytes(width*height)
        pen=0
        for char in '07,340,859,020':
            mask=native._screen(mask,native._raster(native.GLYPHS[17][char],3.039,16.,pen,0,width,height))
            pen+=native.GLYPHS[17][char][4]
        values=bytes(17+round(238*alpha/255) for alpha in mask)
        rows=[list(values[y*width:(y+1)*width]) for y in range(height)]
        self.assertIsNone(native.decode(rows))

    def test_unsupported_resolution_and_non_rectangular_input_are_unread(self):
        self.assertIsNone(native.read((720,1560,b''),'green'))
        self.assertIsNone(native.decode([[17,255],[17]]))


if __name__ == '__main__':
    unittest.main()
