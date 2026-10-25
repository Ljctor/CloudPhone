"""The page's options kept on the server (core/page_settings.py and
http/page_settings.py of the gateway), offline: a change merged key by
key, null removing a key, a plugin's options in its own data directory
and the page's own in the gateway's file, both read back as a restarted
gateway does, bad changes refused. aiohttp is stubbed: only the files and
the rules run.
Run: python3 -m unittest discover -s 04-cloud-phone-app/tests -p "test_*.py"
"""

import json
import os
import sys
import tempfile
import types
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "overlay", "gateway", "src")
sys.path.insert(0, SRC)
if "aiohttp" not in sys.modules:
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        web = types.SimpleNamespace(json_response=lambda body, status=200, headers=None: (status, body))
        sys.modules["aiohttp"] = types.SimpleNamespace(web=web)
        sys.modules["aiohttp.web"] = web

from videobridge_gateway.core import page_settings as rules  # noqa: E402
from videobridge_gateway.http import page_settings  # noqa: E402


class Rules(unittest.TestCase):
    def test_a_change_replaces_its_keys_and_null_removes_one(self):
        current = {"touchMarker": True, "language": "fr", "foldedSections": {"logs": True}}
        merged = rules.merged(current, {"language": "en", "touchMarker": None})
        self.assertEqual(merged, {"language": "en", "foldedSections": {"logs": True}})

    def test_bad_changes_are_refused(self):
        for change in ([], {}, "x", {"plugins": []}, {"plugins": {"Bad Id": {}}}, {"plugins": {"ok": 3}},
                       {"big": "x" * (rules.MOST + 1)}):
            with self.assertRaises(ValueError, msg=repr(change)[:60]):
                rules.check_change(change)

    def test_a_broken_file_reads_as_nothing(self):
        for text in (None, "", "{not json", "[1, 2]"):
            self.assertEqual(rules.parse_saved(text), {})


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.dir.name, "page-settings.json")
        self.plugins = os.path.join(self.dir.name, "plugins")
        os.makedirs(os.path.join(self.plugins, "slayer-legend"))
        page_settings.load(self.file, self.plugins)

    def tearDown(self):
        self.dir.cleanup()

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_a_restarted_gateway_reads_back_every_option(self):
        page_settings.change({"touchMarker": False, "language": "en"})
        page_settings.change({"plugins": {"slayer-legend": {"mode": "free", "stage18": "920"}}})
        page_settings.change({"plugins": {"slayer-legend": {"stage18": "925"}, "gone": {"draw": True}}})
        # The gateway restarts.
        page_settings.load(self.file, self.plugins)
        settings = page_settings.describe()["settings"]
        self.assertEqual(settings, {"touchMarker": False, "language": "en", "plugins": {
            "slayer-legend": {"mode": "free", "stage18": "925"}, "gone": {"draw": True}}})
        # A plugin's options in its data directory; a plugin without one in the gateway's file.
        self.assertEqual(self.read(os.path.join(self.plugins, "slayer-legend", "page-options.json")),
                         {"mode": "free", "stage18": "925"})
        self.assertEqual(self.read(self.file), {"touchMarker": False, "language": "en",
                                                "plugins": {"gone": {"draw": True}}})
        self.assertEqual(os.stat(self.file).st_mode & 0o777, 0o600)

    def test_two_browsers_changing_two_options_keep_both(self):
        page_settings.change({"plugins": {"slayer-legend": {"mode": "free"}}})
        page_settings.change({"plugins": {"slayer-legend": {"defaultMode": "mpw4"}}})
        self.assertEqual(page_settings.describe()["settings"]["plugins"]["slayer-legend"],
                         {"mode": "free", "defaultMode": "mpw4"})

    def test_without_a_file_nothing_is_kept(self):
        page_settings.load("", "")
        self.assertEqual(page_settings.describe(), {"available": False, "settings": {"plugins": {}}})
