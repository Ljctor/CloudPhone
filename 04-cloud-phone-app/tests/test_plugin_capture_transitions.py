"""Process changes invalidate pixels; user input during native reads forbids taps."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04-cloud-phone-app/src/overlay/gateway/src"))
from videobridge_gateway.plugins import Screenshots

spec = importlib.util.spec_from_file_location("transition_ports", ROOT / "05-plugins/slayer-legend/features/ports.py")
ports_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports_module)


class Transitions(unittest.IsolatedAsyncioTestCase):
    def ports(self, **overrides):
        async def adb(*args, **kwargs):
            return 0, ""
        context = dict(id="test", adb=adb, analyse=lambda *args: None,
                       json=lambda value: value, log=lambda *args, **kwargs: None)
        context.update(overrides)
        return ports_module.build(SimpleNamespace(**context), SimpleNamespace(guard=lambda *args: None))

    async def test_relaunch_and_start_replace_cached_pixels_without_restamping_old_reference(self):
        calls = 0
        async def capture():
            nonlocal calls
            calls += 1
            return (1, 1, bytes([calls]))
        screenshots = Screenshots(capture)
        ports = self.ports(screenshot=lambda **kwargs: screenshots.get("test", **kwargs),
                           screenshot_time=screenshots.captured_at, invalidate_screenshots=screenshots.stale)
        first = await ports.capture(60)
        stamp = ports.capture_time(first)
        self.assertIs(await ports.capture(60), first)
        ports.relaunched("process changed")
        second = await ports.capture(60)
        self.assertIsNot(second, first)
        self.assertEqual(ports.capture_time(first), stamp)
        await ports.start_game()
        self.assertIsNot(await ports.capture(60), second)
        self.assertEqual(calls, 3)
        await screenshots.close()

    async def test_relaunch_during_capture_discards_pretransition_pixels_even_on_old_gateway(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        shots = [(1, 1, b"old"), (1, 1, b"new")]
        calls = []
        async def capture(max_age=0):
            calls.append(max_age)
            shot = shots.pop(0)
            if shot[2] == b"old":
                entered.set()
                await finish.wait()
            return shot
        ports = self.ports(screenshot=capture)
        request = asyncio.create_task(ports.capture(60))
        await entered.wait()
        ports.relaunched("process changed")
        finish.set()
        self.assertEqual((await request)[2], b"new")
        self.assertEqual(calls, [60, 0])

    async def test_start_invalidates_before_and_after_even_if_command_fails(self):
        invalidations = []
        async def adb(*args, **kwargs):
            self.assertEqual(len(invalidations), 1)
            raise RuntimeError("unavailable")
        ports = self.ports(adb=adb, invalidate_screenshots=lambda: invalidations.append(True))
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            await ports.start_game()
        self.assertEqual(len(invalidations), 2)

    async def test_user_input_during_native_dump_forbids_both_dialog_taps(self):
        for action, resource in (("close_crash", "aerr_close"), ("wait_anr", "aerr_wait")):
            with self.subTest(action=action):
                entered, finish = asyncio.Event(), asyncio.Event()
                user = {"last": None}
                commands = []
                async def adb(*args, **kwargs):
                    commands.append(args)
                    if args[:2] == ("shell", "uiautomator"):
                        entered.set()
                        await finish.wait()
                        return 0, f'<node resource-id="android:id/{resource}" bounds="[0,0][100,100]" />'
                    return 0, ""
                ports = self.ports(adb=adb, last_input=lambda: user["last"])
                async def act():
                    async with ports.leased("launch", "dialog", 60):
                        await getattr(ports, action)((100, 100, b"pixels"))
                request = asyncio.create_task(act())
                await entered.wait()
                user["last"] = {"monotonic": time.monotonic(), "wall": time.time()}
                finish.set()
                with self.assertRaises(ports.Busy):
                    await request
                self.assertFalse(any(args[:2] == ("shell", "input") for args in commands))


if __name__ == "__main__":
    unittest.main()
