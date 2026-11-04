"""Exact recording-time context, immutable audio and developer-only closure."""
import base64
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

HERE = Path(__file__).parent.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


oral = load("oral_under_test", HERE / "oral_feedback.py")
archive = load("oral_png_encoder", HERE / "features/screenshot_archive.py")
PNG = archive.png((2, 2, bytes(range(12))))
SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect x="1" y="1" width="1" height="1" stroke="red"/></svg>'


def context():
    return {"source": "live", "nodeId": "screen:battle", "screen": "battle", "startedAt": 1234.5,
            "capture": {"mimeType": "image/png", "base64": base64.b64encode(PNG).decode(), "width": 2, "height": 2},
            "overlay": {"svg": SVG, "dom": '<div onclick="neverExecute()">Mode + cubes</div>', "enabled": True,
                        "regions": [{"id": "mode", "rect": [.1, .2, .3, .4]}], "settings": {"cubes": True},
                        "state": {"mode": "soul"}, "displayName": "Combat Interface"},
            "view": {"width": 720, "height": 1560, "zoom": 1}, "assets": {"rendererVersion": "oral-context-v1"}}


def wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(bytes(320))
    return output.getvalue()


class OralAPI(AioHTTPTestCase):
    async def get_application(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = oral.OralFeedback(self.temporary.name)
        app = web.Application(client_max_size=1024)  # Gateway read() default must not limit streaming routes.
        for method, path, handler in oral.routes(self.store, "/voice", ("http://trusted-gateway.invalid:8100",)):
            app.router.add_route(method, path, handler)
        return app

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self.temporary.cleanup()

    async def create(self, body=None):
        response = await self.client.post("/voice/contexts", json=body or context())
        self.assertEqual(response.status, 201, await response.text())
        return await response.json()

    async def test_context_pins_bytes_geometry_dom_and_loaded_version_before_later_changes(self):
        body = context()
        body["overlay"]["dom"] += "x" * 20000
        created = await self.create(body)
        original = copy.deepcopy(body)
        body["overlay"]["regions"][0]["rect"][0] = .8
        body["assets"]["rendererVersion"] = "newer-version"
        saved = await (await self.client.get("/voice/" + created["id"])).json()
        self.assertEqual(saved["context"]["overlay"]["regions"], original["overlay"]["regions"])
        self.assertEqual(saved["context"]["assets"], original["assets"])
        self.assertEqual(saved["contextSha256"], created["contextSha256"])
        directory = self.store.path(created["id"])
        self.assertEqual((directory / "screenshot.png").read_bytes(), PNG)
        self.assertEqual((directory / "overlay.svg").read_text(), SVG)
        self.assertEqual((directory / "overlay-dom.txt").read_text(), original["overlay"]["dom"])
        response = await self.client.get("/voice/" + created["id"] + "/assets/overlay-dom.txt")
        self.assertTrue(response.headers["Content-Type"].startswith("text/plain"))
        self.assertIn("attachment", response.headers["Content-Disposition"])
        self.assertIn("sandbox", response.headers["Content-Security-Policy"])

    async def test_audio_is_bound_to_context_hash_and_cannot_replace_recorded_evidence(self):
        created = await self.create()
        endpoint = "/voice/" + created["id"] + "/audio"
        response = await self.client.post(endpoint, data=wav(), headers={"Content-Type": "audio/wav", "X-Context-SHA256": "0" * 64})
        self.assertEqual(response.status, 409)
        headers = {"Content-Type": "audio/wav", "X-Context-SHA256": created["contextSha256"]}
        response = await self.client.post(endpoint, data=wav(), headers=headers)
        self.assertEqual(response.status, 201)
        receipt = await response.json()
        self.assertEqual(receipt["status"], "pending_review")
        self.assertEqual(receipt["contextSha256"], created["contextSha256"])
        again = await (await self.client.post(endpoint, data=wav(), headers=headers)).json()
        self.assertEqual(again["sha256"], receipt["sha256"])
        self.assertEqual((await self.client.post(endpoint, data=wav() + b"different", headers=headers)).status, 409)
        saved = self.store.get(created["id"])
        self.assertEqual(saved["status"], "pending_review")
        self.assertFalse(saved["gestureAuthority"])
        before = (self.store.path(created["id"]) / "context.json").read_bytes()
        with self.assertRaises(ValueError):
            self.store.resolve(created["id"], "implemented", "fixed", None)
        self.store.resolve(created["id"], "implemented", "reader and regression corrected", "a" * 40)
        self.assertEqual(self.store.get(created["id"])["status"], "implemented")
        self.assertEqual((self.store.path(created["id"]) / "context.json").read_bytes(), before)

    async def test_rejects_svg_active_content_wrong_hash_and_cross_origin_without_losing_context(self):
        body = context()
        body["overlay"]["svg"] = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        self.assertEqual((await self.client.post("/voice/contexts", json=body)).status, 400)
        body = context()
        body["capture"]["sha256"] = "0" * 64
        self.assertEqual((await self.client.post("/voice/contexts", json=body)).status, 409)
        self.assertEqual((await self.client.post("/voice/contexts", json=context(), headers={"Origin": "https://external.invalid"})).status, 403)
        self.assertEqual(self.store.list(), [])

    async def test_audio_stream_limit_type_and_path_traversal_fail_closed(self):
        created = await self.create()
        endpoint = "/voice/" + created["id"] + "/audio"
        headers = {"Content-Type": "audio/wav", "X-Context-SHA256": created["contextSha256"]}
        with patch.object(oral, "AUDIO_LIMIT", 100):
            self.assertEqual((await self.client.post(endpoint, data=wav(), headers=headers)).status, 413)
        self.assertEqual(list(self.store.directory.glob(".audio-*")), [])
        self.assertEqual((await self.client.post(endpoint, data=b"not audio", headers=headers)).status, 400)
        self.assertEqual((await self.client.post(endpoint, data=b"html", headers={**headers, "Content-Type": "text/html"})).status, 415)
        self.assertEqual((await self.client.get("/voice/../../secret/assets/context.json")).status, 404)
        self.assertEqual(self.store.get(created["id"])["status"], "awaiting_audio")

    async def test_failed_context_write_never_publishes_partial_capture(self):
        original = self.store.write
        def fail_svg(path, body):
            if path.name == "overlay.svg":
                raise OSError("simulated storage failure")
            return original(path, body)
        with patch.object(self.store, "write", side_effect=fail_svg):
            self.assertEqual((await self.client.post("/voice/contexts", json=context())).status, 503)
        self.assertEqual(self.store.list(), [])
        self.assertEqual(list(self.store.directory.glob(".context-*")), [])

    async def test_voice_only_explicit_origin_cors_supports_fallback_without_a_gateway_restart(self):
        origin = "http://trusted-gateway.invalid:8100"
        response = await self.client.options("/voice/contexts", headers={"Origin": origin,
            "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(response.status, 204)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
        self.assertNotEqual(response.headers["Access-Control-Allow-Origin"], "*")
        response = await self.client.post("/voice/contexts", json=context(), headers={"Origin": origin})
        self.assertEqual(response.status, 201)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], origin)
        self.assertEqual((await self.client.options("/voice/contexts", headers={"Origin": "https://other.invalid"})).status, 403)
        response = await self.client.get("/voice", headers={"Origin": "https://other.invalid"})
        self.assertEqual(response.status, 403)


if __name__ == "__main__":
    unittest.main()
