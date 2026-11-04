"""Immutable, private screenshot/overlay/audio evidence for developer review.

This module has no phone ports, network clients or transcription engine.
Recorded context and audio never grant navigation authority.
"""
import base64
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import logging
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET

CONTEXT_LIMIT = 8 * 1024 * 1024
PNG_LIMIT = 5 * 1024 * 1024
SVG_LIMIT = 256 * 1024
DOM_LIMIT = 512 * 1024
AUDIO_LIMIT = 12 * 1024 * 1024
ID = re.compile(r"[0-9a-f]{32}")
SHA = re.compile(r"[0-9a-f]{64}")
MIMES = {"audio/ogg": "ogg", "audio/webm": "webm", "audio/mp4": "m4a", "audio/mpeg": "mp3",
         "audio/wav": "wav", "audio/x-wav": "wav", "audio/3gpp": "3gp", "audio/aac": "aac"}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def bounded_text(value, limit, name):
    if not isinstance(value, str) or len(value.encode()) > limit:
        raise ValueError(name + " is missing or too large")
    return value


def validate_svg(value):
    value = bounded_text(value, SVG_LIMIT, "overlay.svg")
    if not value:
        return b""  # No SVG was visible; preserve that exact state rather than inventing one.
    if "<!DOCTYPE" in value.upper() or "<!ENTITY" in value.upper():
        raise ValueError("SVG entities are forbidden")
    try:
        root = ET.fromstring(value)
    except ET.ParseError as error:
        raise ValueError("Invalid overlay SVG") from error
    allowed = {"svg", "g", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text", "tspan",
               "defs", "pattern", "marker", "title", "desc", "style", "clipPath", "mask", "linearGradient", "radialGradient", "stop", "use"}
    if root.tag.split("}")[-1] != "svg":
        raise ValueError("Overlay must be an SVG")
    for element in root.iter():
        if element.tag.split("}")[-1] not in allowed:
            raise ValueError("Unsupported SVG element")
        for name, content in element.attrib.items():
            name = name.split("}")[-1].lower()
            if name.startswith("on") or name == "href" and not content.startswith("#"):
                raise ValueError("Active SVG content is forbidden")
        css = " ".join([element.text or "", *element.attrib.values()])
        if re.search(r"@import", css, re.I) or any(not url.strip().strip("'\"").startswith("#")
                                                   for url in re.findall(r"url\((.*?)\)", css, re.I)):
            raise ValueError("External SVG resources are forbidden")
    return value.encode()


def validate_png(data):
    if not data or len(data) > PNG_LIMIT:
        raise ValueError("Screenshot size is invalid")
    spec = importlib.util.spec_from_file_location("oral_feedback_png", Path(__file__).with_name("evidence_review.py"))
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    width, height, _ = reader.png_rgb(data)
    return width, height


def audio_header_valid(mime, first):
    if mime == "audio/ogg":
        return first.startswith(b"OggS")
    if mime == "audio/webm":
        return first.startswith(b"\x1aE\xdf\xa3")
    if mime in {"audio/mp4", "audio/3gpp"}:
        return len(first) >= 12 and first[4:8] == b"ftyp"
    if mime in {"audio/wav", "audio/x-wav"}:
        return first.startswith(b"RIFF") and first[8:12] == b"WAVE"
    if mime == "audio/mpeg":
        return first.startswith(b"ID3") or len(first) >= 2 and first[0] == 255 and first[1] & 224 == 224
    if mime == "audio/aac":
        return len(first) >= 2 and first[0] == 255 and first[1] & 246 == 240
    return False


class Conflict(ValueError):
    pass


class OralFeedback:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("CLOUDPHONE_REVIEW_FEEDBACK_DIR", "/var/lib/cloudphone-review")) / "oral-feedback"

    @contextlib.contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def path(self, item_id):
        if not isinstance(item_id, str) or not ID.fullmatch(item_id):
            raise ValueError("Invalid evidence ID")
        result = self.directory / item_id
        if result.is_symlink():
            raise ValueError("Invalid evidence path")
        return result

    @staticmethod
    def write(path, body):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())

    @staticmethod
    def sync(directory):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def create(self, body):
        if not isinstance(body, dict) or set(body) - {"source", "nodeId", "screen", "capture", "overlay", "view", "assets", "startedAt"}:
            raise ValueError("Invalid recording context")
        if body.get("source") not in {"live", "review"}:
            raise ValueError("Context source must be live or review")
        bounded_text(body.get("nodeId"), 240, "nodeId")
        bounded_text(body.get("screen"), 240, "screen")
        started = body.get("startedAt")
        if isinstance(started, bool) or not isinstance(started, (int, float)) or not math.isfinite(started) or started <= 0:
            raise ValueError("startedAt must identify the capture time")
        capture, overlay = body.get("capture"), body.get("overlay")
        if not isinstance(capture, dict) or capture.get("mimeType") != "image/png" or not isinstance(overlay, dict):
            raise ValueError("PNG screenshot and exact overlay are required")
        if not isinstance(overlay.get("regions"), list) or len(overlay["regions"]) > 2000 or not isinstance(overlay.get("enabled"), bool):
            raise ValueError("Exact rendered regions and overlay visibility are required")
        for key in ("view", "assets"):
            if not isinstance(body.get(key), dict):
                raise ValueError(key + " snapshot is required")
        if not isinstance(body["assets"].get("rendererVersion"), str) or not body["assets"]["rendererVersion"]:
            raise ValueError("Loaded rendererVersion is required")
        try:
            png = base64.b64decode(capture.get("base64", ""), validate=True)
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid PNG encoding") from error
        width, height = validate_png(png)
        if (not all(isinstance(capture.get(key), int) and not isinstance(capture[key], bool) for key in ("width", "height"))
                or (capture.get("width"), capture.get("height")) != (width, height)):
            raise ValueError("Screenshot dimensions differ from its bytes")
        png_sha = digest(png)
        if capture.get("sha256") is not None and capture["sha256"] != png_sha:
            raise Conflict("Screenshot bytes differ from the displayed capture hash")
        svg = validate_svg(overlay.get("svg"))
        dom = bounded_text(overlay.get("dom", ""), DOM_LIMIT, "overlay.dom").encode()
        context = json.loads(canonical(body))
        context["capture"].pop("base64", None)
        context["capture"]["sha256"] = png_sha
        context["overlay"].pop("svg", None)
        context["overlay"].pop("dom", None)
        context["overlay"].update(svgSha256=digest(svg), domSha256=digest(dom))
        if len(canonical(context)) > 512 * 1024:
            raise ValueError("Context metadata is too large")
        overlay_sha = digest(canonical(context["overlay"]))
        context_sha = digest(canonical(context))
        item_id = uuid.uuid4().hex
        manifest = {"id": item_id, "createdAt": time.time(), "contextSha256": context_sha, "overlaySha256": overlay_sha,
                    "context": context, "gestureAuthority": False, "assetVersionBasis": "client_reported_loaded_renderer"}
        with self.locked():
            if sum(1 for path in self.directory.iterdir() if ID.fullmatch(path.name)) >= 2000:
                raise OSError("Evidence capacity reached")
            temporary = Path(tempfile.mkdtemp(prefix=".context-", dir=self.directory))
            try:
                self.write(temporary / "screenshot.png", png)
                self.write(temporary / "overlay.svg", svg)
                self.write(temporary / "overlay-dom.txt", dom)
                self.write(temporary / "context.json", canonical(manifest))
                self.sync(temporary)
                os.replace(temporary, self.path(item_id))
                self.sync(self.directory)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        return {"id": item_id, "contextSha256": context_sha, "overlaySha256": overlay_sha, "captureSha256": png_sha,
                "status": "awaiting_audio", "gestureAuthority": False}

    def get(self, item_id):
        directory = self.path(item_id)
        manifest = json.loads((directory / "context.json").read_text())
        manifest["status"] = "awaiting_audio"
        audio = directory / "audio" / "audio.json"
        if audio.is_file():
            manifest["audio"] = json.loads(audio.read_text())
            manifest["status"] = "pending_review"
        reviews = directory / "reviews.json"
        manifest["reviews"] = json.loads(reviews.read_text()) if reviews.is_file() else []
        if manifest["reviews"]:
            manifest["status"] = manifest["reviews"][-1]["status"]
        return manifest

    def list(self, limit=100, after=None):
        if not self.directory.is_dir():
            return []
        if not 1 <= limit <= 100 or after is not None and not ID.fullmatch(after):
            raise ValueError("Invalid review queue pagination")
        result = []
        for path in sorted(self.directory.iterdir()):
            if not ID.fullmatch(path.name) or path.is_symlink() or after and path.name <= after:
                continue
            item = self.get(path.name)
            summary = {key: item[key] for key in ("id", "createdAt", "status", "contextSha256", "gestureAuthority")}
            summary.update({key: item["context"][key] for key in ("source", "nodeId", "screen")})
            summary["audio"] = item.get("audio")
            summary["review"] = item["reviews"][-1] if item["reviews"] else None
            result.append(summary)
            if len(result) >= limit:
                break
        return result

    def attach(self, item_id, temporary, mime, context_sha, size, audio_sha, first):
        mime = mime.split(";", 1)[0].lower()
        if mime not in MIMES or not audio_header_valid(mime, first) or not 0 < size <= AUDIO_LIMIT:
            raise ValueError("Unsupported or invalid audio attachment")
        with self.locked():
            manifest = self.get(item_id)
            if not isinstance(context_sha, str) or context_sha != manifest["contextSha256"]:
                raise Conflict("Audio context hash mismatch")
            if "audio" in manifest:
                if manifest["audio"]["sha256"] == audio_sha:
                    return {"id": item_id, **manifest["audio"], "status": manifest["status"]}
                raise Conflict("Audio already attached; immutable evidence cannot be replaced")
            directory = self.path(item_id)
            filename = "audio." + MIMES[mime]
            receipt = {"mimeType": mime, "bytes": size, "sha256": audio_sha, "filename": filename,
                       "contextSha256": context_sha, "receivedAt": time.time(), "transcription": "not_requested"}
            staging = Path(tempfile.mkdtemp(prefix=".audio-", dir=directory))
            try:
                os.replace(temporary, staging / filename)
                self.write(staging / "audio.json", canonical(receipt))
                self.sync(staging)
                os.rename(staging, directory / "audio")
                self.sync(directory)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            return {"id": item_id, **receipt, "status": "pending_review", "gestureAuthority": False}

    def resolve(self, item_id, status, reason, commit=None):
        """Developer-only local workflow: a classifier never resolves a report."""
        if status not in {"implemented", "rejected"} or not isinstance(reason, str) or not reason.strip() or len(reason) > 4000:
            raise ValueError("A terminal review needs an explicit developer reason")
        if status == "implemented" and (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{7,40}", commit)):
            raise ValueError("Implementation requires commit evidence")
        with self.locked():
            manifest = self.get(item_id)
            event = {"at": time.time(), "status": status, "reason": reason, "commit": commit, "gestureAuthority": False}
            path = self.path(item_id) / "reviews.json"
            fd, temporary = tempfile.mkstemp(prefix=".review-", dir=path.parent)
            try:
                with os.fdopen(fd, "wb") as output:
                    os.fchmod(output.fileno(), 0o600)
                    output.write(canonical(manifest["reviews"] + [event]))
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
                self.sync(path.parent)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return event


def routes(store, prefix="/navigation/oral-feedback", allowed_origins=()):
    """Same-origin HTTP adapters for the gateway and independent reviewer."""
    from aiohttp import web
    import asyncio

    def same_origin(request):
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}" and origin not in allowed_origins:
            raise web.HTTPForbidden(text="Cross-origin feedback refused")

    async def bounded_body(request, limit):
        data = bytearray()
        async for chunk in request.content.iter_chunked(64 * 1024):
            if len(data) + len(chunk) > limit:
                raise web.HTTPRequestEntityTooLarge(max_size=limit, actual_size=len(data) + len(chunk))
            data.extend(chunk)
        return bytes(data)

    async def create(request):
        same_origin(request)
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="JSON context required")
        try:
            body = json.loads(await bounded_body(request, CONTEXT_LIMIT))
            return web.json_response(await asyncio.to_thread(store.create, body), status=201)
        except Conflict as error:
            raise web.HTTPConflict(text=str(error))
        except (ValueError, TypeError, KeyError, RecursionError) as error:
            logging.getLogger(__name__).warning("Recording context rejected: %s", str(error)[:200])
            raise web.HTTPBadRequest(text="Invalid immutable recording context")
        except OSError:
            raise web.HTTPServiceUnavailable(text="Recording context could not be saved")

    async def attach(request):
        same_origin(request)
        mime = request.content_type
        if mime not in MIMES:
            raise web.HTTPUnsupportedMediaType(text="Supported audio attachment required")
        temporary = None
        try:
            item_id = request.match_info["item_id"]
            context_sha = request.headers.get("X-Context-SHA256", "")
            if not SHA.fullmatch(context_sha):
                raise web.HTTPBadRequest(text="Immutable context hash is required")
            store.path(item_id)
            store.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix=".audio-", dir=store.directory)
            size, first, checksum = 0, bytearray(), hashlib.sha256()
            with os.fdopen(fd, "wb") as output:
                os.fchmod(output.fileno(), 0o600)
                async for chunk in request.content.iter_chunked(64 * 1024):
                    size += len(chunk)
                    if size > AUDIO_LIMIT:
                        raise web.HTTPRequestEntityTooLarge(max_size=AUDIO_LIMIT, actual_size=size)
                    if len(first) < 32:
                        first.extend(chunk[:32 - len(first)])
                    checksum.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            result = await asyncio.to_thread(store.attach, item_id, temporary, mime, context_sha, size, checksum.hexdigest(), bytes(first))
            return web.json_response(result, status=201)
        except Conflict as error:
            raise web.HTTPConflict(text=str(error))
        except FileNotFoundError:
            raise web.HTTPNotFound()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid audio attachment")
        except OSError:
            raise web.HTTPServiceUnavailable(text="Audio attachment could not be saved")
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    async def listing(request):
        try:
            limit = int(request.query.get("limit", "100"))
            items = await asyncio.to_thread(store.list, limit, request.query.get("after"))
            return web.json_response({"items": items, "next": items[-1]["id"] if len(items) == limit else None})
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid queue pagination")

    async def item(request):
        try:
            return web.json_response(await asyncio.to_thread(store.get, request.match_info["item_id"]))
        except (FileNotFoundError, ValueError):
            raise web.HTTPNotFound()

    async def asset(request):
        try:
            manifest = await asyncio.to_thread(store.get, request.match_info["item_id"])
            name = request.match_info["name"]
            allowed = {"screenshot.png", "overlay.svg", "overlay-dom.txt", "context.json"}
            if "audio" in manifest:
                allowed.add(manifest["audio"]["filename"])
            if name not in allowed:
                raise web.HTTPNotFound()
            path = store.path(manifest["id"]) / ("audio" if "audio" in manifest and name == manifest["audio"]["filename"] else "") / name
            if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(store.path(manifest["id"]).resolve()):
                raise web.HTTPNotFound()
            mime = "image/png" if name == "screenshot.png" else manifest.get("audio", {}).get("mimeType") if "audio" in manifest and name == manifest["audio"]["filename"] else "text/plain; charset=utf-8"
            return web.FileResponse(path, headers={"Content-Type": mime,
                "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store",
                "Content-Security-Policy": "sandbox; default-src 'none'", "X-Content-Type-Options": "nosniff"})
        except (ValueError, FileNotFoundError):
            raise web.HTTPNotFound()

    def protected(handler):
        async def handle(request):
            same_origin(request)
            try:
                response = await handler(request)
            except web.HTTPException as error:
                cors_headers(request, error)
                raise
            cors_headers(request, response)
            return response
        return handle

    def cors_headers(request, response):
        origin = request.headers.get("Origin")
        if origin in allowed_origins:
            response.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Context-SHA256, X-CloudPhone-Token",
                "Access-Control-Max-Age": "600"})

    async def options(request):
        requested = request.headers.get("Access-Control-Request-Method", "GET")
        headers = {name.strip().lower() for name in request.headers.get("Access-Control-Request-Headers", "").split(",") if name.strip()}
        if requested not in {"GET", "POST"} or headers - {"content-type", "x-context-sha256", "x-cloudphone-token"}:
            raise web.HTTPForbidden(text="Unsupported voice preflight")
        return web.Response(status=204)

    result = [("POST", prefix + "/contexts", create), ("POST", prefix + "/{item_id}/audio", attach),
              ("GET", prefix, listing), ("GET", prefix + "/{item_id}", item),
              ("GET", prefix + "/{item_id}/assets/{name}", asset)]
    if allowed_origins:
        result += [("OPTIONS", path, options) for path in dict.fromkeys(path for _, path, _ in result)]
    return [(method, path, protected(handler)) for method, path, handler in result]
