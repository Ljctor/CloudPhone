"""Viewers over HTTP: the viewer id of a request, the signalling sessions'
arrivals and departures as log records, and

    POST /api/v1/viewers/disconnect-others {viewer}

which closes every other session with WebSocket code 4001 (see
core/viewers.py for the rules).
"""

import asyncio
import time

from aiohttp import web

from ..core.viewers import GONE_SECONDS, Viewers
from ..logs import log

VIEWERS = Viewers()
CLOSED_BY_OTHER_VIEWER = 4001


def viewer_of(request):
    return request.query.get("viewer", "")[:64]


def log_record(record):
    if record:
        level, text, params, notify = record
        log(level, "gateway", text, notify=notify, **params)


def kicked(request):
    """True when another viewer disconnected this request's viewer lately."""
    return VIEWERS.is_kicked(viewer_of(request), time.monotonic())


async def refuse_if_kicked(ws, viewer):
    """Closes a kicked viewer's new session; True when it did."""
    if not VIEWERS.is_kicked(viewer, time.monotonic()):
        return False
    await ws.close(code=CLOSED_BY_OTHER_VIEWER, message=b"Disconnected by another viewer")
    return True


def joined(ws, viewer):
    log_record(VIEWERS.connected(ws, viewer, time.monotonic()))


def left(ws, viewer):
    """Said a few seconds later, once the page did not come back."""
    VIEWERS.closed(ws)
    asyncio.get_running_loop().call_later(
        GONE_SECONDS, lambda: log_record(VIEWERS.gone(viewer, time.monotonic())))


def disconnect_others(changed):
    """The handler of POST /api/v1/viewers/disconnect-others: ends every
    signalling session except the caller's, and refuses those viewers for a
    while. changed() is called once they are closed."""
    async def handle(request):
        try:
            data = await request.json()
            viewer = str(data.get("viewer", ""))[:64]
        except (ValueError, TypeError):
            return web.json_response({"error": "viewer is required"}, status=400)
        if not viewer:
            return web.json_response({"error": "viewer is required"}, status=400)
        others, record = VIEWERS.kick_others(viewer, time.monotonic())
        for ws in others:
            await ws.close(code=CLOSED_BY_OTHER_VIEWER, message=b"Disconnected by another viewer")
        log_record(record)
        changed()
        return web.json_response({"closed": len(others)})
    return handle
