"""Local HTTP/WS lifecycle tests; no Android or real gRPC calls."""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "overlay", "gateway", "src")
sys.path.insert(0, SRC)
from videobridge_gateway.http import session, stream_diagnostics
from videobridge_gateway.http.viewer_sessions import ViewerSessions
from videobridge_gateway.core.stream_diagnostics import Diagnostics


class FakeBridge:
    def __init__(self):
        self.opened = asyncio.Event()
        self.release_open = asyncio.Event()
        self.reader_cancelled = asyncio.Event()
        self.bye = asyncio.Event()
        self.fail_bye = False
        self.sent = []

    async def open(self, stun):
        self.opened.set()
        await self.release_open.wait()
        return "private-guid"

    async def messages(self, guid):
        try:
            yield json.dumps({"start": {}})
            await asyncio.Event().wait()
        finally:
            self.reader_cancelled.set()

    async def send(self, guid, text):
        self.sent.append(json.loads(text))
        if "bye" in json.loads(text):
            if self.fail_bye:
                raise RuntimeError("private failure details")
            self.bye.set()


class Reconnect(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.sessions = ViewerSessions()
        self.bridges = []
        def factory(channel, metadata):
            bridge = FakeBridge()
            self.bridges.append(bridge)
            return bridge
        self.evidence = Diagnostics()
        self.patcher = patch.object(session, "STREAMS", self.evidence)
        self.patcher.start()
        self.events_patcher = patch.object(stream_diagnostics, "STREAMS", self.evidence)
        self.events_patcher.start()
        app = web.Application(middlewares=[session.guard])
        app["videobridge_token"] = ""
        app.router.add_get("/ws", session.signalling(lambda: True, self.sessions, factory))
        app.router.add_get("/token", session.page_token)
        app.router.add_post("/events", stream_diagnostics.post_events)
        app.router.add_post("/reset", self.sessions.reset_handler(lambda: None))
        app.on_shutdown.append(self.sessions.shutdown)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        for bridge in self.bridges:
            bridge.release_open.set()
            bridge.fail_bye = False
        await self.client.close()
        self.patcher.stop()
        self.events_patcher.stop()

    async def connect(self, viewer):
        ws = await self.client.ws_connect("/ws?viewer=" + viewer + "&attempt=attempt-0123456789")
        while not self.bridges or not self.bridges[-1].opened.is_set():
            await asyncio.sleep(0)
        return ws, self.bridges[-1]

    async def test_reset_waits_for_late_guid_and_only_closes_current_viewer(self):
        own, first = await self.connect("own-viewer")
        other, second = await self.connect("other-viewer")
        second.release_open.set()
        await other.receive_json()
        reset = asyncio.create_task(self.sessions.reset("own-viewer"))
        await asyncio.sleep(0.02)
        self.assertFalse(reset.done())
        first.release_open.set()
        result = await asyncio.wait_for(reset, 3)
        self.assertEqual(result, {"closed": 1, "failed": False})
        self.assertTrue(first.bye.is_set())
        self.assertFalse(second.bye.is_set())
        self.assertFalse(other.closed)
        await own.close()
        await other.close()

    async def test_cancelled_reset_caller_keeps_cleanup_and_refuses_racing_join(self):
        ws, bridge = await self.connect("own-viewer")
        reset = asyncio.create_task(self.sessions.reset("own-viewer"))
        await asyncio.sleep(0.02)
        reset.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await reset
        self.assertIsNone(self.sessions.join(object(), "own-viewer"))
        bridge.release_open.set()
        self.assertEqual((await asyncio.wait_for(self.sessions.reset("own-viewer"), 3))["closed"], 1)
        self.assertTrue(bridge.bye.is_set())
        self.assertEqual(len(self.sessions.connections), 0)
        await ws.close()

    async def test_reader_cancelled_and_failed_bye_remains_retryable(self):
        ws, bridge = await self.connect("own-viewer")
        bridge.release_open.set()
        await ws.receive_json()
        bridge.fail_bye = True
        result = await self.sessions.reset("own-viewer")
        self.assertTrue(result["failed"])
        self.assertTrue(bridge.reader_cancelled.is_set())
        self.assertIsNone(self.sessions.join(object(), "own-viewer"))
        bridge.fail_bye = False
        result = await self.sessions.reset("own-viewer")
        self.assertEqual(result, {"closed": 1, "failed": False})
        self.assertEqual(len(self.sessions.connections), 0)
        await ws.close()

    async def test_pre_websocket_telemetry_accepts_context_and_preserves_late_event(self):
        identity = {"viewer": "own-viewer", "attemptId": "attempt-0123456789"}
        headers = {"X-CloudPhone-Token": session.TOKEN}
        response = await self.client.post("/events", headers=headers, json={**identity, "events": [
            {"kind": "client", "state": "started", "storageAvailable": False, "tokenPresent": True}]})
        self.assertEqual(response.status, 202)
        ws, bridge = await self.connect("own-viewer")
        bridge.release_open.set()
        message = await ws.receive_json()
        sid = message["diagnostics"]["sessionId"]
        await self.sessions.reset("own-viewer")
        response = await self.client.post("/events", headers=headers, json={**identity, "sessionId": sid, "events": [
            {"kind": "frame", "state": "first-frame-timeout", "readyState": 0, "width": 0, "paused": True}]})
        self.assertEqual(response.status, 202)
        history = self.evidence.snapshot()["recent"][0]["browser_events"]
        self.assertEqual([event["state"] for event in history], ["started", "first-frame-timeout"])
        response = await self.client.post("/events", headers=headers, json={**identity, "events": [
            {"kind": "error", "message": "private exception"}]})
        self.assertEqual(response.status, 400)
        await ws.close()

    async def test_token_refresh_and_reset_origin_and_auth_guards(self):
        token = await self.client.get("/token")
        self.assertEqual(token.headers["Cache-Control"], "no-store")
        self.assertEqual((await token.json())["token"], session.TOKEN)
        for headers in ({"Origin": "https://elsewhere.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
            response = await self.client.get("/token", headers=headers)
            self.assertEqual(response.status, 403)
        response = await self.client.post("/reset", json={"viewer": "own-viewer"})
        self.assertEqual(response.status, 403)
        headers = {"X-CloudPhone-Token": session.TOKEN}
        response = await self.client.post("/reset", json={"viewer": "own-viewer"}, headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"closed": 0})
        response = await self.client.post("/reset?viewer=other", json={"viewer": "own-viewer"}, headers=headers)
        self.assertEqual(response.status, 400)


if __name__ == "__main__":
    unittest.main()
