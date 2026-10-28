"""ADB cancellation must not outlive its action transaction's ownership.
Processes are deterministic in-memory stand-ins; no adb or phone is used.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "04-cloud-phone-app/src/overlay/gateway/src"))
from videobridge_gateway.adapters import adb


class Process:
    def __init__(self):
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.terminal = asyncio.Event()
        self.returncode = None
        self.killed = False

    async def communicate(self):
        self.started.set()
        await self.finish.wait()
        self.returncode = -9 if self.killed else 0
        self.terminal.set()
        return b"finished", b""

    def kill(self):
        self.killed = True
        self.finish.set()

    async def wait(self):
        await self.terminal.wait()
        return self.returncode


class AdbLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.process = Process()
        self.calls = []

        async def start(*args, **kwargs):
            self.calls.append(args)
            return self.process

        self.process_patch = patch.object(adb.asyncio, "create_subprocess_exec", start)
        self.log_patch = patch.object(adb.logs, "adb_reached", lambda *args: None)
        self.process_patch.start()
        self.log_patch.start()
        self.addCleanup(self.process_patch.stop)
        self.addCleanup(self.log_patch.stop)

    async def test_cancellation_waits_for_inflight_command_terminal_even_when_cancelled_again(self):
        running = asyncio.create_task(adb.run("shell", "input", "swipe", "1", "2", "3", "4", "1200"))
        await self.process.started.wait()
        running.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        running.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        self.assertFalse(running.done())
        self.assertFalse(self.process.killed, "keep already-issued input under its original command deadline")
        self.process.finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await running
        self.assertTrue(self.process.terminal.is_set())

    async def test_cancelled_timeout_kills_and_reaps_before_delivering_cancellation(self):
        running = asyncio.create_task(adb.run("shell", "input", "tap", "1", "2", timeout=.01))
        await self.process.started.wait()
        running.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(running, 1)
        self.assertTrue(self.process.killed)
        self.assertTrue(self.process.terminal.is_set())

    async def test_ordinary_timeout_still_returns_failure_after_reaping(self):
        result = await adb.run("shell", "input", "tap", "1", "2", timeout=.01)
        self.assertEqual(result[0], -1)
        self.assertTrue(self.process.terminal.is_set())

    async def test_cancel_during_process_startup_still_waits_for_terminal(self):
        starting = asyncio.Event()
        created = asyncio.Event()

        async def start(*args, **kwargs):
            starting.set()
            await created.wait()
            return self.process

        with patch.object(adb.asyncio, "create_subprocess_exec", start):
            running = asyncio.create_task(adb.run("shell", "input", "tap", "1", "2"))
            await starting.wait()
            running.cancel()
            created.set()
            await self.process.started.wait()
            self.assertFalse(running.done())
            self.process.finish.set()
            with self.assertRaises(asyncio.CancelledError):
                await running
        self.assertTrue(self.process.terminal.is_set())

    async def test_cancelled_input_retains_real_plugin_lease_until_terminal(self):
        path = ROOT / "05-plugins/slayer-legend/features/ports.py"
        spec = importlib.util.spec_from_file_location("adb_ownership_ports", path)
        ports_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ports_module)

        async def command(*args, **kwargs):
            code, output, _ = await adb.run(*args, **kwargs)
            return code, output

        ports = ports_module.build(SimpleNamespace(
            id="test", adb=command, analyse=lambda *args: None, json=lambda value: value,
            log=lambda *args, **kwargs: None), SimpleNamespace(guard=lambda *args: None))

        async def old():
            async with ports.leased("stage_change", "old", 60):
                await ports.swipe((480, 1040, b""), "test", "drag", (.1, .2), (.3, .4), 1200)

        running = asyncio.create_task(old())
        await self.process.started.wait()
        running.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        with self.assertRaises(ports.Busy):
            async with ports.leased("stage_change", "successor", 60):
                self.fail("successor started while old Android command was in flight")
        self.process.finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await running
        self.assertTrue(self.process.terminal.is_set())
        self.assertIsNone(ports.lease.state())
        async with ports.leased("stage_change", "successor", 60):
            pass


if __name__ == "__main__":
    unittest.main()
