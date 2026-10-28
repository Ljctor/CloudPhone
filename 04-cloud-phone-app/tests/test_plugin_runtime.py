"""Bounded capture and worker ownership under contention and cancellation."""
import asyncio
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/overlay/gateway/src"))
from videobridge_gateway.plugins import Analysis, Screenshots


class Runtime(unittest.IsolatedAsyncioTestCase):
    async def test_zero_age_joins_and_cancelled_waiter_does_not_cancel_capture(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        calls = 0
        async def capture():
            nonlocal calls
            calls += 1
            entered.set()
            await finish.wait()
            return (1, 1, bytes([calls]))
        cache = Screenshots(capture)
        first = asyncio.create_task(cache.get("one"))
        await entered.wait()
        second = asyncio.create_task(cache.get("two"))
        await asyncio.sleep(0)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        finish.set()
        shot = await second
        self.assertEqual(calls, 1)
        self.assertIs(await cache.get("three", 10), shot)
        self.assertIsNot(await cache.get("three"), shot)
        self.assertEqual(calls, 2)
        await cache.close()

    async def test_stale_flight_is_serialised_and_replaced_for_all_waiters(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        calls = active = peak = 0
        async def capture():
            nonlocal calls, active, peak
            calls += 1
            active += 1
            peak = max(active, peak)
            value = (1, 1, bytes([calls]))
            entered.set()
            await finish.wait()
            active -= 1
            return value
        cache = Screenshots(capture)
        first = asyncio.create_task(cache.get("one"))
        await entered.wait()
        cache.stale()
        others = [asyncio.create_task(cache.get("two")) for _ in range(20)]
        await asyncio.sleep(0)
        self.assertEqual(calls, 1)
        finish.set()
        values = await asyncio.gather(first, *others)
        self.assertEqual(calls, 2)
        self.assertEqual(peak, 1)
        self.assertTrue(all(value is values[0] for value in values))
        await cache.close()

    async def test_browser_input_invalidates_cache_and_flight_before_delivery(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        user = {"value": None}
        calls = 0
        async def capture():
            nonlocal calls
            calls += 1
            shot = (1, 1, bytes([calls]))
            entered.set()
            await finish.wait()
            return shot
        cache = Screenshots(capture, lambda: user["value"])
        request = asyncio.create_task(cache.get("one"))
        await entered.wait()
        user["value"] = {"monotonic": 1, "wall": 100}
        finish.set()
        shot = await request
        self.assertEqual(shot[2], bytes([2]))
        self.assertEqual(calls, 2)
        user["value"] = {"monotonic": 2, "wall": 101}
        self.assertIsNot(await cache.get("one", 60), shot)
        self.assertEqual(calls, 3)
        await cache.close()

    async def test_detector_has_own_lane_and_cancel_keeps_worker_capacity(self):
        analysis = Analysis()
        entered, finish = threading.Event(), threading.Event()
        def blocking():
            entered.set()
            finish.wait(5)
        first = asyncio.create_task(analysis.detector.run(blocking))
        while not entered.is_set():
            await asyncio.sleep(.001)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        second = asyncio.create_task(analysis.detector.run(lambda: 42))
        await asyncio.sleep(.01)
        self.assertFalse(second.done())
        self.assertEqual(await analysis.resources.run(lambda: "independent"), "independent")
        self.assertEqual(analysis.detector.stats()["running"], 1)
        finish.set()
        self.assertEqual(await second, 42)
        await analysis.close()
        self.assertFalse(any(thread.name.startswith("plugin-") for thread in threading.enumerate()))

    async def test_heavy_saturation_does_not_queue_detector_behind_resource_work(self):
        analysis = Analysis()
        finish = threading.Event()
        entered = []
        def blocking():
            entered.append(True)
            finish.wait(5)
        heavy = [asyncio.create_task(analysis.resources.run(blocking)) for _ in range(4)]
        while len(entered) < 2:
            await asyncio.sleep(.001)
        self.assertEqual(await analysis.detector.run(lambda: 42), 42)
        self.assertEqual(analysis.resources.stats()["running"], 2)
        self.assertEqual(analysis.resources.stats()["waiting"], 2)
        finish.set()
        await asyncio.gather(*heavy)
        await analysis.close()


if __name__ == "__main__":
    unittest.main()
