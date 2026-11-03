"""The page's session and the WebRTC signalling over HTTP:

    GET /, /index.html            the page, with this start's TOKEN
    GET /api/v1/emulator/ws-jsep  the signalling WebSocket

and guard(), the middleware that refuses cross-origin requests and POSTs
without the token, or without a one-time action token for that path (a
phone alert's button, ACTIONS: see core/actions.py) (see core/session.py for the rules,
adapters/videobridge.py for the emulator's side).
"""

import asyncio
import json
import logging
import os
import secrets
import time

from aiohttp import web

from ..adapters import host_files
from ..core import actions, session
from ..core.stream_diagnostics import STREAMS, valid_identity
from . import viewers

TOKEN = secrets.token_urlsafe(32)
# The one-time action tokens of the phone alerts' buttons (core/actions.py).
ACTIONS = {}


@web.middleware
async def guard(request, handler):
    if not session.same_origin(request.headers.get("Origin"), request.host):
        logging.warning(f"Refused {request.method} {request.path} from origin {request.headers.get('Origin')!r}")
        return web.json_response({"error": "Cross-origin requests are not accepted"}, status=403)
    if session.token_needed(request.method):
        action = request.headers.get(actions.ACTION_HEADER)
        if action is not None:
            # A phone alert's button: one POST to its own path, once.
            if not actions.redeem(ACTIONS, action, request.method, request.path, time.time()):
                logging.warning(f"Refused {request.method} {request.path}: action token unknown, spent or expired")
                return web.json_response({"error": "Action token unknown, spent or expired"}, status=403)
            return await handler(request)
        if not session.token_valid(request.headers.get(session.TOKEN_HEADER, ""), TOKEN):
            return web.json_response({"error": "Missing or invalid page token: reload the page"}, status=403)
    return await handler(request)


async def page_token(request):
    """Recover after a gateway restart without replacing this page's bundle.

    Like the index, this is same-origin readable and never cached. Fetch
    metadata also refuses cross-site navigations that omit an Origin.
    """
    if request.headers.get("Sec-Fetch-Site") in ("cross-site", "same-site"):
        return web.json_response({"error": "Same-origin token refresh required"}, status=403)
    return web.json_response({"token": TOKEN}, headers={"Cache-Control": "no-store", "Vary": "Origin, Sec-Fetch-Site"})


def index(web_root):
    """The handler of GET /: the page, with this start's token. Never
    cached, so a reload always gets the current token and the current
    bundle names."""
    async def handle(request):
        page = host_files.read_file(os.path.join(web_root, "index.html"), encoding="utf-8")
        if page is None:
            return web.Response(status=503, text="The web page is not installed.")
        return web.Response(
            text=session.page_with_token(page, TOKEN), content_type="text/html",
            headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"},
        )
    return handle


def signalling(channel, sessions, bridge_factory=None):
    """The handler of GET /api/v1/emulator/ws-jsep (WebSocket Upgrade):
    WebRTC signalling between the browser and the Video Bridge over rtc2.
    channel() is the Video Bridge's gRPC channel, None when there is none."""
    async def handle(request):
        ws = web.WebSocketResponse(timeout=1)
        await ws.prepare(request)
        viewer = viewers.viewer_of(request)
        attempt = request.query.get("attempt")
        if not valid_identity(viewer) or not valid_identity(attempt, 12):
            attempt = None
        sid = STREAMS.begin(viewer, attempt)
        if await viewers.refuse_if_kicked(ws, viewer):
            STREAMS.event(sid, "viewer_refused")
            STREAMS.close(sid)
            return ws

        if not channel():
            STREAMS.event(sid, "bridge_unavailable")
            await ws.close(
                code=web.WSCloseCode.INTERNAL_ERROR, message=b"Video Bridge offline"
            )
            STREAMS.close(sid)
            return ws

        connection = sessions.join(ws, viewer)
        if connection is None:
            STREAMS.event(sid, "viewer_refused")
            await ws.close(code=4002, message=b"Viewer reconnect in progress")
            STREAMS.close(sid)
            return ws
        bridge = None
        guid = None
        opening = None
        stream_task = None
        bye_forwarded = False
        viewers.joined(ws, viewer)

        try:
            if bridge_factory is None:
                from ..adapters.videobridge import Bridge
                factory = Bridge
            else:
                factory = bridge_factory
            bridge = factory(channel(), session.bearer(request.app["videobridge_token"]))
            STREAMS.event(sid, "bridge_open_requested")
            opening = asyncio.create_task(bridge.open(session.STUN))
            guid = await asyncio.shield(opening)
            STREAMS.event(sid, "bridge_opened")
            if ws.closed or connection.closing:
                return ws

            async def stream_to_client():
                STREAMS.event(sid, "bridge_subscribed")
                try:
                    async for msg_text in bridge.messages(guid):
                        if not msg_text:
                            STREAMS.event(sid, "bridge_empty_message")
                            break
                        parsed_jsep = json.loads(msg_text)
                        STREAMS.message(sid, "to_browser", parsed_jsep)
                        if isinstance(parsed_jsep, dict):
                            parsed_jsep = {**parsed_jsep, "diagnostics": {"sessionId": sid}}
                        await ws.send_json(parsed_jsep)
                    STREAMS.event(sid, "bridge_stream_ended")
                    await ws.close()
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    # Exception text may contain gRPC metadata or JSEP: retain only its class.
                    STREAMS.event(sid, "bridge_reader_error", error_type=type(error).__name__)
                    await ws.close(code=web.WSCloseCode.INTERNAL_ERROR)

            stream_task = asyncio.create_task(stream_to_client())
            async for ws_msg in ws:
                if ws_msg.type == web.WSMsgType.TEXT:
                    client_data = ws_msg.json()
                    STREAMS.message(sid, "to_bridge", client_data)
                    await bridge.send(guid, json.dumps(client_data))
                    if session.is_bye(client_data):
                        bye_forwarded = True
                        STREAMS.event(sid, "client_bye")
                        break
                elif ws_msg.type == web.WSMsgType.ERROR:
                    STREAMS.event(sid, "websocket_error")
        except Exception as error:
            STREAMS.event(sid, "handler_error", error_type=type(error).__name__)
        finally:
            async def teardown():
                nonlocal guid
                try:
                    # Cancellation during RequestRtcStream must not orphan a
                    # participant whose GUID arrives after its browser left.
                    # The adapter bounds this request to ten seconds.
                    if guid is None and opening is not None:
                        try:
                            guid = await opening
                        except (Exception, asyncio.CancelledError):
                            # No GUID was obtained, so there is no known
                            # participant on which a bye can be retried.
                            pass
                    # Stop inbound gRPC before closing the websocket, including
                    # a stale browser whose reader cannot receive any more.
                    if stream_task:
                        stream_task.cancel()
                        try:
                            await stream_task
                        except asyncio.CancelledError:
                            pass
                        except Exception:
                            connection.failed = True
                    # A vanished tab cannot send bye: release its participant.
                    # Retain known failed GUIDs so another reset can retry the
                    # adapter's bounded send rather than falsely returning 0.
                    async def send_bye():
                        try:
                            await bridge.send(guid, session.BYE)
                            connection.failed = False
                            STREAMS.event(sid, "teardown_sent")
                        except Exception as error:
                            connection.failed = True
                            STREAMS.event(sid, "teardown_error", error_type=type(error).__name__)
                    if guid and not bye_forwarded:
                        connection.retry = send_bye
                        await send_bye()
                    await ws.close()
                finally:
                    STREAMS.close(sid)
                    viewers.left(ws, viewer)
                    sessions.left(connection)

            # An HTTP/WebSocket owner may itself be cancelled. Its upstream
            # participant still needs a terminal teardown before reset finishes.
            cleanup = asyncio.create_task(teardown())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        continue
                raise
        return ws
    return handle
