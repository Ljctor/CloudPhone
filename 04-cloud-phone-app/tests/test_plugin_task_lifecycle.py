"""Plugin shutdown owns sleeping producers and cancelled-await worker jobs."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest

from aiohttp import web

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04-cloud-phone-app/src/overlay/gateway/src"))
from videobridge_gateway.plugins import Analysis

spec = importlib.util.spec_from_file_location("runtime_test_ports", ROOT / "05-plugins/slayer-legend/features/ports.py")
ports_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports_module)


class Tasks(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_drains_background_tasks_before_executor_cleanup(self):
        app = web.Application()
        analysis = Analysis()
        records = []
        async def adb(*args, **kwargs):
            return 0, ""
        ports = ports_module.build(SimpleNamespace(
            id="test", app=app, analyse=analysis.resources.run, adb=adb,
            json=lambda value: value, log=lambda *args: records.append(args)),
            SimpleNamespace(guard=lambda *args: None))
        stopped = asyncio.Event()
        async def producer():
            try:
                await asyncio.sleep(3600)
            finally:
                stopped.set()
        producer_task = ports.spawn(producer())
        entered, finish = threading.Event(), threading.Event()
        def pixels():
            entered.set()
            finish.wait(5)
        worker_task = ports.track_task(asyncio.create_task(ports.analyse(pixels)))
        while not entered.is_set():
            await asyncio.sleep(.001)
        async def cleanup(application):
            self.assertTrue(producer_task.done())
            self.assertTrue(worker_task.done())
            self.assertTrue(stopped.is_set())
            finish.set()
            await analysis.close()
        app.on_cleanup.append(cleanup)
        app.freeze()
        await app.shutdown()
        await app.cleanup()
        self.assertFalse(any(thread.name.startswith("plugin-") for thread in threading.enumerate()))
        with self.assertRaisesRegex(RuntimeError, "shutting down"):
            ports.spawn(producer())
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
