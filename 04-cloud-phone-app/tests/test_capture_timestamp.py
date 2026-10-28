"""Capture freshness follows acquisition, including cached and joined reads."""
import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/overlay/gateway/src"))
from videobridge_gateway.plugins import Screenshots


class CaptureTime(unittest.IsolatedAsyncioTestCase):
    async def test_slow_capture_join_and_cache_preserve_acquisition_time(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        shot = (1, 1, b"rgb")

        async def capture():
            entered.set()
            await finish.wait()
            return shot

        cache = Screenshots(capture)
        with patch("videobridge_gateway.plugins.time.time", return_value=100):
            first = asyncio.create_task(cache.get("one"))
            await entered.wait()
        second = asyncio.create_task(cache.get("two", max_age=60))
        await asyncio.sleep(0)
        with patch("videobridge_gateway.plugins.time.time", return_value=900):
            finish.set()
            self.assertIs(await first, shot)
            self.assertIs(await second, shot)
            self.assertIs(await cache.get("three", max_age=60), shot)
        self.assertEqual(cache.captured_at(shot), 100)
        self.assertEqual(cache.counts, {"one": 1})
        self.assertIsNone(cache.captured_at((2, 2, b"unknown")))

    async def test_metadata_retention_is_bounded_and_identity_specific(self):
        async def capture():
            return tuple([1, 1, b"rgb"])
        cache = Screenshots(capture)
        shots = [await cache.get("one") for _ in range(5)]
        self.assertIsNone(cache.captured_at(shots[0]))
        self.assertIsNotNone(cache.captured_at(shots[-1]))


if __name__ == "__main__":
    unittest.main()
