"""Debug detection rectangles are the classifier's actual read-only anchors."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import tempfile
import json
import time
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Geometry(unittest.IsolatedAsyncioTestCase):
    async def test_user_annotations_and_removal_proposals_stay_advisory(self):
        feature = load("navigation_user_feedback_test", "features/navigation_debug.py")
        screens = load("feedback_screens_test", "screens.py")
        navigation = load("feedback_navigation_test", "nav.py")
        policy = json.dumps(navigation.SCREENS, sort_keys=True)
        with tempfile.TemporaryDirectory() as temporary:
            data = Path(temporary) / 'plugin'
            manual = data / 'manual-clicks'
            manual.mkdir(parents=True)
            capture = 'a' * 32
            (manual / (capture + '.json')).write_text(json.dumps({
                'capture_status': 'complete', 'at': time.time(), 'kind': 'scannable',
                'before_scan': {'screen': 'battle', 'overlays': []}, 'rect': [.1, .2, .3, .4]}))
            (manual / ('b' * 32 + '.json')).write_text(json.dumps({
                'capture_status': 'complete', 'at': time.time(), 'kind': 'scannable',
                'before_scan': {'screen': 'battle', 'overlays': ['quest_panel'], 'quest_tab': 'repeat'},
                'rect': [.2, .3, .4, .5]}))
            with patch.dict('os.environ', {'CLOUDPHONE_REVIEW_FEEDBACK_DIR': str(Path(temporary) / 'shared')}):
                ports = NS(respond=lambda body, status=200: {'status': status, 'body': body},
                           data_path=lambda name: str(data / name))
                api = feature.navigation_debug(ports, navigation, HERE, screens)
                routes = {(method, path): handler for method, path, handler in api['routes']}
                result = await routes['GET', '/navigation/annotations'](None)
                self.assertEqual(result['body']['annotations'][0]['id'], 'manual:' + capture)
                self.assertTrue(result['body']['annotations'][0]['user'])
                self.assertEqual(result['body']['annotations'][1]['screen'], 'quest_repeat')
                self.assertFalse(result['body']['gestureAuthority'])
                async def proposal():
                    return {'screen': 'battle', 'nodeId': 'screen:battle', 'zoneId': 'policy:quest',
                            'operation': 'remove', 'kind': 'navigation', 'rect': [.9, .05, .98, .12]}
                saved = await routes['POST', '/navigation/zone-feedback'](NS(json=proposal))
                self.assertEqual(saved['status'], 201)
                self.assertTrue(saved['body']['item']['pending'])
                self.assertFalse(saved['body']['gestureAuthority'])
                result = await routes['GET', '/navigation/zone-feedback'](None)
                self.assertEqual(len(result['body']['items']), 1)
                self.assertEqual(json.dumps(navigation.SCREENS, sort_keys=True), policy)

    async def test_value_role_proposals_are_persisted_without_policy_changes(self):
        feature = load("value_role_feature", "features/navigation_debug.py")
        screens = load("value_role_screens", "screens.py")
        navigation = load("value_role_nav", "nav.py")
        policy = json.dumps(navigation.SCREENS, sort_keys=True)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'CLOUDPHONE_REVIEW_FEEDBACK_DIR': directory}):
                ports = NS(respond=lambda body, status=200: {'status': status, 'body': body},
                           data_path=lambda name: str(Path(directory) / name))
                built = feature.navigation_debug(ports, navigation, HERE, screens)
                routes = {(method, path): handler for method, path, handler in built['routes']}
                for kind in ('progression_value', 'resource_value', 'screen_identifier'):
                    body = {'screen': 'battle', 'nodeId': 'screen:battle', 'operation': 'add',
                            'kind': kind, 'rect': [.1, .2, .3, .4]}
                    async def proposal():
                        return body
                    saved = await routes['POST', '/navigation/zone-feedback'](NS(json=proposal))
                    self.assertEqual(saved['status'], 201)
                    self.assertEqual(saved['body']['item']['kind'], kind)
                    self.assertIs(saved['body']['gestureAuthority'], False)
                    for rect in (None, [.3, .2, .1, .4], [True, .2, .3, .4]):
                        body['rect'] = rect
                        self.assertEqual((await routes['POST', '/navigation/zone-feedback'](NS(json=proposal)))['status'], 400)
                rebuilt = feature.navigation_debug(ports, navigation, HERE, screens)
                read = next(handler for method, path, handler in rebuilt['routes'] if path == '/navigation/zone-feedback' and method == 'GET')
                items = (await read(None))['body']['items']
                self.assertEqual({item['kind'] for item in items}, {'progression_value', 'resource_value', 'screen_identifier'})
                self.assertTrue(all(item['gestureAuthority'] is False for item in items))
        self.assertEqual(json.dumps(navigation.SCREENS, sort_keys=True), policy)

    async def test_detector_geometry_is_separate_from_allowed_moves(self):
        feature = load("navigation_debug_test", "features/navigation_debug.py")
        screens = load("debug_screens_test", "screens.py")
        navigation = load("debug_navigation_test", "nav.py")
        api = feature.navigation_debug(NS(respond=lambda value: value), navigation, HERE, screens)
        response = await api["routes"][0][2](None)
        tree, graph = response["registry"]["tree"], response["graph"]
        landmark = tree["soul_weapon_engraving"]["landmarks"][0]
        sw, sh, x, y, _, _, _ = screens.fixture("eg_title")
        self.assertEqual(landmark["rect"], [(x + 35) / sw, (y + 4) / sh,
                                             (x + 300) / sw, (y + 30) / sh])
        self.assertIn({"id": "TOP_EMERALD", "rect": list(screens.TOP_EMERALD)}, tree["battle"]["landmarks"])
        self.assertNotIn("landmarks", graph["screens"]["soul_weapon_engraving"])
        title = tree["title"]["landmarks"][0]
        sw, sh, x, y, width, height, _ = screens.fixture("title_logo_480")
        self.assertEqual(title["rect"], [x / sw, y / sh, (x + width) / sw, (y + height) / sh])
        self.assertNotEqual(title["rect"], list(screens.START_TEXT))
        self.assertNotIn("landmarks", graph["screens"]["title"])
        self.assertEqual(graph["screens"]["battle"]["name"], 'Combat Interface')
        self.assertEqual(tree["battle"]["battle_viewport"]["size"], 'big')
        self.assertEqual(tree["adventure_map"]["battle_viewport"]["size"], 'mini')


if __name__ == "__main__":
    unittest.main()
