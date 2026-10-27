"""Fast navigation reads do not wait for the game's numeric scan."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

spec = importlib.util.spec_from_file_location("screen_quick_feature", Path(__file__).parent / "features/screen.py")
feature = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feature)


class QuickScreen(unittest.IsolatedAsyncioTestCase):
    async def test_fresh_capture_change_and_concurrent_cache_without_readers(self):
        now, image, captures = [1.0], ["battle"], []

        async def capture(max_age):
            captures.append(max_age)
            await asyncio.sleep(0)
            return image[0]

        async def focused():
            return True

        async def analyse(fn, *args):
            return fn(*args)

        async def forbidden_scan(*args):
            self.fail("navigation must not wait for numeric readers")

        ports = NS(clock=NS(monotonic=lambda: now[0], wall=lambda: now[0]), capture=capture,
                   focused=focused, analyse=analyse, respond=lambda value: value,
                   store=NS(saved={}), game={"scan": forbidden_scan})
        screens = NS(look=lambda shot: {"screen": shot, "overlays": [], **(
            {"quest_tab": "repeat"} if shot == "quest_panel" else {})})
        api = feature.screen(ports, screens, None, None, NS(number_or_none=lambda *args: None), None)
        route = next(handler for method, path, handler in api["routes"] if path == "/screen")
        request = NS(query={"quick": "1"})
        results = await asyncio.gather(*(route(request) for _ in range(4)))
        self.assertEqual(len(captures), 1)
        self.assertEqual(results[0]["scan"]["screen"], "battle")
        self.assertEqual(captures[0], .25)
        image[0] = "equipment_weapon"
        now[0] += .26
        result = await route(request)
        self.assertEqual(result["scan"]["screen"], "equipment_weapon")
        self.assertEqual(len(captures), 2)
        image[0] = "quest_panel"
        now[0] += .26
        result = await route(request)
        self.assertEqual(result["scan"]["quest_tab"], "repeat")
