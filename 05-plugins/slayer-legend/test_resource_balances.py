"""Reviewed real owned-balance crops, source identities and conservative failures."""
import importlib.util
from pathlib import Path
import unittest

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('resource_balances',HERE/'resource_balances.py')
reader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def shot(*names):
    pixels=bytearray(480*1040*3)
    for name in names:
        width,height,x,y,w,h,raw=reader.fixture(name)
        for row in range(h):
            at=((y+row)*width+x)*3
            pixels[at:at+w*3]=raw[row*w*3:(row+1)*w*3]
    return 480,1040,bytes(pixels)


def erase(frame,box):
    width,height,raw=frame
    pixels=bytearray(raw)
    for y in range(box[1],box[3]):
        for x in range(box[0],box[2]):
            offset=(y*width+x)*3
            pixels[offset:offset+3]=b'\0\0\0'
    return width,height,bytes(pixels)


REAL_FIXTURES=("resource_stones_a","resource_stones_b",
               "resource_stones_c","resource_stones_d","resource_stones_e","resource_stones_f",
               "resource_feather_white","resource_feather_white_title",
               "resource_feather_green","resource_feather_green_title",
               "resource_feather_purple","resource_feather_purple_title")


class ResourceBalances(unittest.TestCase):
    def test_each_calibration_is_a_bounded_real_crop(self):
        for name in REAL_FIXTURES:
            width,height,x,y,w,h,raw=reader.fixture(name)
            self.assertEqual((width,height),(480,1040))
            self.assertEqual(len(raw),w*h*3)
            self.assertLess(w*h,width*height/10)
            self.assertGreater(y,40)

    def test_new_fields_are_passive_and_do_not_enable_resource_routes(self):
        import json
        rows=json.loads((HERE/'resources.json').read_text())
        fields={row['field']:row for row in rows}
        for field in reader.FIELDS:
            self.assertFalse(fields[field]['pending'])
            self.assertIs(fields[field]['refresh_route'],False)
            self.assertEqual(fields[field]['reader'],'resource_balances')
        self.assertTrue(fields['feather_black']['pending'])
        spec=importlib.util.spec_from_file_location('balance_game_rules',HERE/'features/game_rules.py')
        rules=importlib.util.module_from_spec(spec);spec.loader.exec_module(rules)
        facts,_=rules.noted({},reader.read(shot('resource_stones_a')),123)
        self.assertEqual(facts['stone_green']['value']['value'],4733)
        self.assertTrue(facts['stone_green']['verified'])

    def test_real_stones_change_independently_and_are_owned_balances(self):
        for name,expected in [('resource_stones_a',(611,13977,4733,4126)),
                              ('resource_stones_b',(636,13990,4742,4126)),
                              ('resource_stones_c',(636,13987,4742,4126)),
                              ('resource_stones_d',(636,13977,4742,4126)),
                              ('resource_stones_e',(621,13977,4733,4126)),
                              ('resource_stones_f',(630,13977,4733,4126))]:
            with self.subTest(name=name):
                values=reader.read(shot(name))
                self.assertEqual({field:row['value'] for field,row in values.items()},dict(zip(reader.STONES,expected)))

    def test_missing_stone_glyph_does_not_reuse_history_or_poison_other_fields(self):
        frame=erase(shot('resource_stones_a'),reader.STONE_BOXES[1])
        values=reader.read(frame)
        self.assertIsNone(values['stone_blue'])
        self.assertEqual(values['stone_red']['value'],611)
        self.assertEqual(values['stone_green']['value'],4733)

    def test_four_stone_icons_are_mandatory_so_upgrade_costs_are_not_balances(self):
        frame=shot('resource_stones_a')
        for box in reader.STONE_ICONS:
            with self.subTest(box=box):
                self.assertEqual(reader.stones(erase(frame,box)),{})

    def test_real_owned_feather_headers_include_screen_identity_and_icon(self):
        for field,value in [('feather_white',31),('feather_green',31),('feather_purple',74)]:
            names=('resource_'+field,'resource_'+field+'_title')
            self.assertEqual(reader.read(shot(*names)),{field:{'text':str(value),'value':value}})

    def test_header_identity_and_icon_each_required_and_do_not_invent_zero(self):
        for field in reader.FEATHERS:
            self.assertEqual(reader.read(shot('resource_'+field)),{})
            self.assertEqual(reader.read(shot('resource_'+field+'_title')),{})
            frame=shot('resource_'+field,'resource_'+field+'_title')
            blank=erase(frame,(424,170,464,203))
            self.assertEqual(reader.read(blank),{field:None})

    def test_unseen_glyphs_stay_unread_instead_of_matching_a_known_amount(self):
        frame=shot('resource_feather_purple','resource_feather_purple_title')
        width,height,raw=frame;pixels=bytearray(raw)
        for y in range(180,194):
            for x in range(438,446):
                offset=(y*width+x)*3;pixels[offset:offset+3]=b'\xff\xff\xff'
        self.assertEqual(reader.read((width,height,bytes(pixels))),{'feather_purple':None})

    def test_other_screens_and_uncalibrated_resolution_return_no_resource(self):
        self.assertEqual(reader.read((480,1040,bytes(480*1040*3))),{})
        self.assertEqual(reader.read((720,1560,bytes(720*1560*3))),{})


class RegistryPublication(unittest.TestCase):
    def test_real_crop_publishes_capture_time_and_unread_revokes_only_verification(self):
        import asyncio
        import tempfile
        import test_game as game_test

        frame = shot('resource_stones_a')
        readers = dict(game_test.READERS)
        with tempfile.TemporaryDirectory() as directory:
            ports, _ = game_test.fake_ports(directory, frame)
            captured = ports.clock.wall() - 2
            ports.capture_time = lambda pixels: captured
            built = game_test.create_game(ports, game_test.screens, game_test.rules, readers)
            asyncio.run(built['api']['scan'](frame))
            fact = built['api']['facts']()['stone_red']
            self.assertEqual(fact['value'], {'text': '611', 'value': 611})
            self.assertEqual(fact['seen'], captured)
            self.assertEqual(fact['source'], 'scan')
            self.assertIs(fact['verified'], True)
            self.assertIsNone(built['api']['value']('feather_black'))
            self.assertIsNone(built['api']['value']('dice'))

            # A later visible but unread number keeps dated history, not a
            # fabricated zero or a newly verified cached number.
            ports.clock.now += 16
            captured += 16
            unread = erase(frame, reader.STONE_BOXES[0])
            asyncio.run(built['api']['scan'](unread))
            fact = built['api']['facts']()['stone_red']
            self.assertEqual(fact['value']['value'], 611)
            self.assertEqual(fact['seen'], captured - 16)
            self.assertIs(fact['verified'], False)
            self.assertIs(built['api']['facts']()['stone_green']['verified'], True)

    def test_registry_limits_passive_reader_to_existing_interval(self):
        import test_game as game_test

        registry = game_test.reader_module.ReaderRegistry(
            game_test.screens, game_test.rules,
            {'resource_balances': lambda pixels, *_: reader.read(pixels)})
        frame = {'shows': {'resource_balances'}, 'ran': set(), 'changed': False}
        self.assertEqual(registry.due(frame, {'resource_balances': 100}, 114), [])
        self.assertEqual(registry.due(frame, {'resource_balances': 100}, 115),
                         ['resource_balances'])


if __name__=='__main__':
    unittest.main()
