"""Real PNG decoding, conservative evidence outcomes, raw preservation."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

review = load('evidence_review', HERE / 'evidence_review.py')
archive = load('archive_png', HERE / 'features/screenshot_archive.py')

class EvidenceReview(unittest.TestCase):
    def test_nested_overlay_identity_uses_ancestry_not_detector_order(self):
        tree=json.loads((HERE/'screen_registry.json').read_text())['tree']
        # The Soul title and its Equipment parent both match on a real card.
        for overlays in (['panel','soul_weapon','equipment_weapon'],
                         ['equipment_weapon','panel','soul_weapon'],
                         ['soul_weapon','equipment_weapon','soul_weapon','better_weapon_toast']):
            self.assertEqual(review.identity({'screen':'battle','overlays':overlays},tree),'soul_weapon')
        self.assertEqual(review.identity({'screen':'soul_weapon_engraving',
                         'overlays':['soul_weapon_engraving_preview','soul_weapon_engraving']},tree),
                         'soul_weapon_engraving_preview')
        self.assertIsNone(review.identity({'screen':'battle','overlays':['soul_weapon','quest_panel']},tree))
        self.assertIsNone(review.identity({'screen':'battle','overlays':['soul_weapon','uncalibrated_overlay']},tree))
        self.assertIsNone(review.identity({'screen':'battle','overlays':['panel']},tree))
        self.assertIsNone(review.identity({'screen':'unknown','overlays':['soul_weapon']},tree))
        self.assertIsNone(review.identity({'screen':'battle','overlays':['a','b']},
                                         {'a':{'parent':'b'},'b':{'parent':'a'}}))

    def test_identity_policy_change_reclassifies_a_previously_wrong_cached_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'screenshots').mkdir();plugin=root/'plugin';plugin.mkdir()
            png=archive.png((2,2,bytes(12)))
            (root/'screenshots/soul_weapon.png').write_bytes(png)
            tree={'equipment_weapon':{'parent':'battle'},'soul_weapon':{'parent':'equipment_weapon'}}
            scan={'screen':'battle','overlays':['panel','soul_weapon','equipment_weapon']}
            screens=NS(TREE=tree,look=lambda shot:scan)
            current_version=review.IDENTITY_VERSION
            try:
                review.IDENTITY_VERSION=current_version-1
                old_revision=review.revision(plugin)
            finally:
                review.IDENTITY_VERSION=current_version
            old={'version':1,'reader_revision':old_revision,'items':{},'images':{
                review.digest(png):{'screen':'equipment_weapon','status':'processed','scan':scan}}}
            ledger,count=review.batch(root,plugin,screens,ledger=old)
            self.assertEqual(count,1)
            item=ledger['items']['example:soul_weapon']
            self.assertEqual(item['before']['screen'],'soul_weapon')
            self.assertEqual(item['status'],'processed')

    def test_exact_registered_capture_aliases_without_suffix_guessing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'screenshots').mkdir();plugin=root/'plugin';plugin.mkdir()
            registry={'tree':{'soul_weapon':{'example':'screenshots/soul_weapon.png',
                      'variants':['screenshots/soul_weapon_relax_owned.png'],
                      'scroll':[{'captures':['soul_weapon_scroll_after.png']}]}}}
            (plugin/'screen_registry.json').write_text(json.dumps(registry))
            for name in ('soul_weapon_relax_owned','soul_weapon_scroll_after','soul_weapon_unregistered'):
                (root/'screenshots'/f'{name}.png').write_bytes(archive.png((2,2,bytes(12))))
            ledger,_=review.batch(root,plugin,NS(look=lambda shot:{'screen':'soul_weapon'}))
            self.assertEqual(ledger['items']['example:soul_weapon_relax_owned']['status'],'processed')
            self.assertEqual(ledger['items']['example:soul_weapon_scroll_after']['status'],'processed')
            self.assertEqual(ledger['items']['example:soul_weapon_unregistered']['status'],'ambiguous')
            # A registered example recognised as another screen is still a conflict.
            ledger,_=review.batch(root,plugin,NS(look=lambda shot:{'screen':'battle'}))
            self.assertTrue(all(v['status']=='ambiguous' for v in ledger['items'].values()))

    def test_real_quest_tab_geometry_retains_tolerance_and_destination_guards(self):
        tree=json.loads((HERE/'screen_registry.json').read_text())['tree']
        navigation=json.loads((HERE/'navigation.json').read_text())
        transitions=(('quest_repeat','quest_daily',.2277778,.2262821,'daily'),
                     ('quest_daily','quest_achievement',.8013889,.2192308,'achievement'),
                     ('quest_achievement','quest_daily',.2236111,.2217949,'daily'),
                     ('quest_achievement','quest_repeat',.525,.2166667,'repeat'),
                     ('quest_repeat','quest_achievement',.8138889,.2275641,'achievement'),
                     ('quest_daily','quest_repeat',.5541667,.2205128,None))
        for source,target,x,y,expected in transitions:
            with self.subTest(source=source,target=target,x=x):
                self.assertEqual(review.match_move({'tap':{'x':x,'y':y}},source,target,navigation,tree),expected)
        self.assertIsNone(review.match_move({'tap':{'x':.2,'y':.225}},
                                           'quest_repeat','quest_achievement',navigation,tree))
        for flag in ('forbidden','assumed'):
            blocked=json.loads(json.dumps(navigation))
            for move in blocked['screens']['quest_panel']['moves']:
                if move['id']=='daily':move[flag]=True
            self.assertIsNone(review.match_move({'tap':{'x':.2,'y':.225}},
                                               'quest_repeat','quest_daily',blocked,tree))
        missing_via={**tree,'quest_daily':{'screen':'quest_panel'}}
        self.assertIsNone(review.match_move({'tap':{'x':.2,'y':.225}},
                                           'quest_repeat','quest_daily',navigation,missing_via))

    def test_png_round_trip_and_checksum_rejection(self):
        shot = (4, 3, bytes(range(36)))
        png = archive.png(shot)
        self.assertEqual(review.png_rgb(png), shot)
        altered = png[:-5] + bytes([png[-5] ^ 1]) + png[-4:]
        with self.assertRaises(ValueError):
            review.png_rgb(altered)

    def test_opaque_rgba_with_up_filter_preserves_capture_pixels(self):
        def chunk(kind, body):
            return review.struct.pack('>I', len(body)) + kind + body + review.struct.pack('>I', review.zlib.crc32(kind + body))
        rgba = bytes([40, 50, 60, 255]) * 2
        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', review.struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
               + chunk(b'IDAT', review.zlib.compress(b'\0' + rgba + b'\2' + bytes(8))) + chunk(b'IEND', b''))
        self.assertEqual(review.png_rgb(png), (2, 2, bytes([40, 50, 60]) * 4))

    def test_bounded_review_deduplicates_and_never_modifies_raw_or_grants_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manual = root / 'manual-clicks'; manual.mkdir()
            plugin = root / 'plugin'; plugin.mkdir()
            (plugin / 'navigation.json').write_text(json.dumps({'screens': {}}))
            png = archive.png((2, 2, bytes(12)))
            for index, kind in enumerate(('scannable', 'forbidden', 'navigation')):
                key = f'{index:032x}'
                (manual / (key + '.json')).write_text(json.dumps({'id': key, 'kind': kind,
                    'capture_status': 'complete', 'rect': [.1, .1, .3, .3], 'tap': {'x': .2, 'y': .2}}))
                (manual / (key + '-before.png')).write_bytes(png)
                (manual / (key + '-after.png')).write_bytes(png)
            originals = {p.name: p.read_bytes() for p in manual.iterdir()}
            screens = NS(look=lambda shot: {'screen': 'battle', 'overlays': [], 'plain': True})
            ledger, count = review.batch(root, plugin, screens, limit=2)
            self.assertEqual((count, ledger['summary']['pending']), (2, 1))
            ledger, count = review.batch(root, plugin, screens, ledger=ledger)
            self.assertEqual(ledger['summary']['processed'], 2)
            self.assertEqual(ledger['summary']['ambiguous'], 1)
            self.assertEqual(ledger['summary']['unique_images'], 1)
            self.assertTrue(all(a['gesture_authority'] is False and a['reader_calibrated'] is False for a in ledger['annotations']))
            self.assertEqual({p.name: p.read_bytes() for p in manual.iterdir()}, originals)
            self.assertEqual(review.batch(root, plugin, screens, ledger=ledger)[1], 0)

    def test_every_passive_edge_is_audited_without_promoting_thumbnail_evidence(self):
        edge = {'from': 1, 'to': 2, 'kind': 'tap', 'x': .2, 'y': .3}
        reviews = review.graph_reviews({'nodes': [{'id': 1}, {'id': 2}], 'edges': [edge, edge, {**edge, 'to': 999}]})
        self.assertEqual(len(reviews), 3)
        self.assertEqual(reviews['trace-edge:0']['status'], 'ambiguous')
        self.assertEqual(reviews['trace-edge:1']['duplicate_of'], 'trace-edge:0')
        self.assertEqual(reviews['trace-edge:2']['status'], 'rejected')
        self.assertTrue(all(row['gesture_authority'] is False for row in reviews.values()))

    def test_feedback_uses_separate_writable_path_and_never_grants_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'manual-clicks').mkdir()
            plugin = root / 'plugin'; plugin.mkdir()
            key = 'b' * 32
            (plugin / 'navigation.json').write_text(json.dumps({'screens': {'battle': {'moves': []}}}))
            (root / 'manual-clicks' / (key + '.json')).write_text(json.dumps({'kind': 'screen', 'capture_status': 'complete'}))
            (root / 'manual-clicks' / (key + '-before.png')).write_bytes(archive.png((2, 2, bytes(12))))
            feedback = root / 'writable-feedback.json'
            feedback.write_text(json.dumps({'version': 1, 'items': [
                {'id': 'confirmed', 'nodeId': 'manual:' + key + ':before', 'correctScreen': 'battle'},
                {'id': 'unproven', 'nodeId': 'trace:123', 'correctScreen': 'title'},
                {'id': 'configured', 'nodeId': 'screen:battle', 'correctScreen': 'battle'},
                {'id': 'missing', 'nodeId': 'screen:not_registered', 'correctScreen': 'title'}]}))
            ledger, _ = review.batch(root, plugin, NS(look=lambda shot: {'screen': 'battle'}), feedback_file=feedback)
            self.assertEqual(ledger['feedback']['confirmed']['status'], 'processed')
            self.assertEqual(ledger['feedback']['unproven']['status'], 'ambiguous')
            self.assertEqual(ledger['feedback']['configured']['status'], 'ambiguous')
            self.assertEqual(ledger['feedback']['missing']['status'], 'rejected')
            self.assertTrue(all(item['gesture_authority'] is False for item in ledger['feedback'].values()))

    def test_unknown_and_conflicting_identity_remain_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'manual-clicks').mkdir()
            plugin = root / 'plugin'; plugin.mkdir()
            key = 'a' * 32
            (root / 'manual-clicks' / (key + '.json')).write_text(json.dumps({'kind': 'screen_correction', 'expected_screen': 'title', 'capture_status': 'complete'}))
            (root / 'manual-clicks' / (key + '-before.png')).write_bytes(archive.png((2, 2, bytes(12))))
            ledger, _ = review.batch(root, plugin, NS(look=lambda shot: {'screen': 'battle'}))
            self.assertEqual(ledger['summary']['ambiguous'], 1)
            self.assertEqual(ledger['annotations'], [])

if __name__ == '__main__':
    unittest.main()
