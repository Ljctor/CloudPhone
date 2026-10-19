"""The page's session and the WebRTC signalling over HTTP:

    GET /, /index.html            the page, with this start's TOKEN
    GET /api/v1/emulator/ws-jsep  the signalling WebSocket

and guard(), the middleware that refuses cross-origin requests and POSTs
without the token (see core/session.py for the rules,
adapters/videobridge.py for the emulator's side).
"""

import asyncio
import json
import logging
import os
import secrets

from aiohttp import web

from ..adapters import host_files
from ..adapters.videobridge import Bridge
from ..core import session
from . import viewers

TOKEN = secrets.token_urlsafe(32)


@web.middleware
async def guard(request, handler):
    if not session.same_origin(request.headers.get("Origin"), request.host):
        logging.warning(f"Refused {request.method} {request.path} from origin {request.headers.get('Origin')!r}")
        return web.json_response({"error": "Cross-origin requests are not accepted"}, status=403)
    if session.token_needed(request.method):
        if not session.token_valid(request.headers.get(session.TOKEN_HEADER, ""), TOKEN):
            return web.json_response({"error": "Missing or invalid page token: reload the page"}, status=403)
    return await handler(request)


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


def signalling(channel):
    """The handler of GET /api/v1/emulator/ws-jsep (WebSocket Upgrade):
    WebRTC signalling between the browser and the Video Bridge over rtc2.
    channel() is the Video Bridge's gRPC channel, None when there is none."""
    async def handle(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logging.debug("WebSocket connection opened for JSEP signaling.")
        viewer = viewers.viewer_of(request)
        if await viewers.refuse_if_kicked(ws, viewer):
            return ws

        if not channel():
            logging.error("No channel to Video Bridge. Restart the gateway (systemctl restart cloudphone-gateway).")
            await ws.close(
                code=web.WSCloseCode.INTERNAL_ERROR, message=b"Video Bridge offline"
            )
            return ws

        bridge = Bridge(channel(), session.bearer(request.app["videobridge_token"]))
        guid = None
        stream_task = None
        bye_forwarded = False
        viewers.joined(ws, viewer)

        try:
            # A new stream on the Video Bridge, with a public STUN server.
            guid = await bridge.open(session.STUN)
            logging.debug(
                f"Initialized WebRTC stream session with Video Bridge. Connection ID: {guid}"
            )

            # The emulator sends the authoritative start message on its JSEP
            # stream. Sending a second synthetic start creates two peer
            # connections and breaks both video input and hardware controls.

            # Video Bridge -> browser, in the background.
            async def stream_to_client():
                logging.debug(
                    f"Starting stream_to_client background task for connection: {guid}"
                )
                try:
                    logging.debug(
                        f"Subscribing to JSEP message stream from Video Bridge for connection: {guid}"
                    )
                    async for msg_text in bridge.messages(guid):
                        logging.debug(
                            f"Received JSEP message from Video Bridge gRPC stream: '{msg_text}'"
                        )
                        if not msg_text:
                            logging.debug(
                                "Received empty JSEP message from Video Bridge. Stopping stream reader."
                            )
                            break
                        parsed_jsep = json.loads(msg_text)
                        logging.debug(f"Forwarding JSEP message to browser: {parsed_jsep}")

                        # If it's an SDP offer/answer, or an ICE candidate message
                        await ws.send_json(parsed_jsep)
                    logging.debug("Video Bridge JSEP stream finished cleanly.")
                except asyncio.CancelledError:
                    logging.debug(f"stream_to_client task cancelled for connection: {guid}")
                except Exception:
                    logging.exception("Error in stream_to_client reader loop. Reload the video (↻) if it stopped:")

            stream_task = asyncio.create_task(stream_to_client())

            # Browser -> Video Bridge.
            async for ws_msg in ws:
                if ws_msg.type == web.WSMsgType.TEXT:
                    client_data = ws_msg.json()
                    logging.debug(
                        f"Received message from Client -> Video Bridge: {client_data}"
                    )
                    await bridge.send(guid, json.dumps(client_data))
                    logging.debug(
                        f"Successfully forwarded JSEP message to Video Bridge for connection: {guid}"
                    )

                    if session.is_bye(client_data):
                        bye_forwarded = True
                        logging.debug(
                            f"Received 'bye' signal from client. Tearing down connection: {guid}"
                        )
                        break
                elif ws_msg.type == web.WSMsgType.ERROR:
                    logging.error(f"WebSocket encountered error: {ws.exception()}. Reload the video (↻) if it stopped.")

        except Exception:
            logging.exception("Error in WebSocket session handler. Reload the video (↻) if it stopped:")
        finally:
            viewers.left(ws, viewer)
            logging.debug(f"Closing signaling WebSocket session for ID: {guid}")
            # Browsers do not always get a chance to send a final WebSocket
            # frame when a tab is suspended or killed. Explicitly tear down
            # the emulator participant so that the next viewer does not
            # compete with an orphaned WebRTC session.
            if guid and not bye_forwarded:
                try:
                    await bridge.send(guid, session.BYE)
                    logging.debug(
                        f"Forwarded teardown for abandoned connection: {guid}"
                    )
                except Exception as e:
                    logging.warning(f"Failed to tear down abandoned connection {guid}: {e!r}")
            if stream_task:
                stream_task.cancel()
                try:
                    await stream_task
                except asyncio.CancelledError:
                    pass
            await ws.close()
        return ws
    return handle
