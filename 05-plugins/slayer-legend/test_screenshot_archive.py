import importlib.util
import json
import os
import struct
import tempfile
import unittest
import zlib


HERE = os.path.dirname(__file__)
spec = importlib.util.spec_from_file_location("archive", os.path.join(HERE, "features/screenshot_archive.py"))
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ScreenshotArchive(unittest.TestCase):
    def test_one_private_png_per_recognised_screen(self):
        shot = (2, 1, bytes((255, 0, 0, 0, 255, 0)))
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "screenshots")
            record = archive.archive(path)
            self.assertIsNone(record({"screen": "battle", "overlays": ["panel"]}, shot, 1))
            self.assertEqual(record({"screen": "battle", "overlays": ["soul_weapon"]}, shot, 2), "soul_weapon")
            self.assertIsNone(record({"screen": "battle", "overlays": ["soul_weapon"]}, shot, 3))
            with open(os.path.join(path, "soul_weapon.png"), "rb") as file:
                data = file.read()
            self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
            offset = 8
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            offset += 12 + length
            length = struct.unpack(">I", data[offset:offset + 4])[0]
            self.assertEqual(zlib.decompress(data[offset + 8:offset + 8 + length]), b"\0" + shot[2])
            with open(os.path.join(path, "manifest.json"), encoding="utf-8") as file:
                self.assertEqual(json.load(file)["soul_weapon"]["captured"], 2)


if __name__ == "__main__":
    unittest.main()
