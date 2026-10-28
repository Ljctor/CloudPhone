"""Debug detection rectangles are the classifier's actual read-only anchors."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, HERE / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Geometry(unittest.IsolatedAsyncioTestCase):
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
        self.assertNotIn("title", tree, "unverified Title has no fake detection rectangle")


if __name__ == "__main__":
    unittest.main()
