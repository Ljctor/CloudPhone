"""A cached capture must not become newer when another feature reads it."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

spec = importlib.util.spec_from_file_location("capture_ports", Path(__file__).parent / "features/ports.py")
ports_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports_module)


class CaptureTime(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_uses_request_start_and_preserves_cache_age(self):
        now = [100.0]
        shot = (1, 1, b"rgb")
        async def screenshot(**kwargs):
            now[0] += 3
            return shot
        context = NS(id="test", screenshot=screenshot, adb=None, analyse=None, notify=None,
                     json=None, log=lambda *args: None)
        ports = ports_module.build(context, None)
        ports.clock.wall = lambda: now[0]
        await ports.capture(max_age=2)
        self.assertEqual(ports.capture_time(shot), 98)
        now[0] = 150
        await ports.capture(max_age=60)
        self.assertEqual(ports.capture_time(shot), 98)
        self.assertIsNone(ports.capture_time((1, 1, b"other")))

    async def test_gateway_acquisition_time_wins_over_response_time(self):
        shot = (1, 1, b"rgb")
        async def screenshot(**kwargs):
            return shot
        context = NS(id="test", screenshot=screenshot, screenshot_time=lambda shot: 12,
                     adb=None, analyse=None, notify=None, json=None, log=lambda *args: None)
        ports = ports_module.build(context, None)
        await ports.capture()
        self.assertEqual(ports.capture_time(shot), 12)


if __name__ == "__main__":
    unittest.main()
