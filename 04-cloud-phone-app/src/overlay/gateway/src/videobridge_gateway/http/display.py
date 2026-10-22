"""Screen size changes over HTTP:

    GET  /api/v1/display                           the size Android runs with,
                                                   the configured one, the
                                                   last request's state
    POST /api/v1/display {width, height, density}  asks for a new one

A request is a line written to REQUEST, which the root-path unit
cloudphone-display applies, reporting in STATUS (see core/display.py for
the rules, adapters/host_files.py for the files). The emulator settings
share change_refused() and change_request().
"""

import json
import time

from aiohttp import web

from ..adapters import host_files
from ..core import display
from ..core.display import json_int
from ..logs import log

# Set by gateway_server's main; empty paths disable the feature.
REQUEST = ""
STATUS = ""
# When this process last asked for a change of either kind (Unix time).
LAST_CHANGE = {"time": None}


def status():
    """The state of the last screen size request."""
    return display.parse_status(host_files.exists(REQUEST), host_files.read_file(STATUS, 256))


def change_request(refused):
    """A screen size or settings request the gateway refuses (invalid,
    disabled, one already running, too soon) is a warning record."""
    def wrap(handler):
        async def handle(request):
            response = await handler(request)
            if response.status >= 400:
                try:
                    error = json.loads(response.text).get("error", "")
                except (TypeError, ValueError, AttributeError):
                    error = str(response.status)
                log("warning", "gateway", refused, error=error)
            return response
        return handle
    return wrap


def change_refused(other, other_files):
    """The 409 or 429 answer when a change is running or the last one was
    too recent, else None and the new change counts from now. other is the
    settings' status, other_files their request and status paths: a change
    restarts the gateway with the emulator, so the files keep its time."""
    if display.busy(status(), other):
        return web.json_response({"error": "A change is already in progress"}, status=409)
    times = [host_files.mtime(path) for path in (REQUEST, STATUS, *other_files)]
    wait = display.wait_seconds(time.time(), display.last_change(LAST_CHANGE["time"], times))
    if wait is not None:
        return web.json_response({"error": f"Wait {wait} s before the next change"}, status=429)
    LAST_CHANGE["time"] = time.time()
    return None


def get_display(running, configured):
    """The handler of GET /api/v1/display: running() is the size the gateway
    works with, configured() the one in config.ini (current even before the
    gateway restarts)."""
    async def handle(request):
        return web.json_response(
            {
                "running": running(),
                "configured": configured(),
                "request": status(),
                "canChange": bool(REQUEST),
                "limits": display.LIMITS,
            },
            headers={"Cache-Control": "no-store"},
        )
    return handle


def set_display(settings_status, settings_files, requested):
    """The handler of POST /api/v1/display {width, height, density}: asks the
    root service to change Android's screen size, which reboots Android
    (data is kept). settings_status() and settings_files() are the other
    kind's, for the shared limit; requested() is called once it is written."""
    @change_request("Screen size change refused: {error}")
    async def handle(request):
        if not REQUEST:
            return web.json_response({"error": "Screen size changes are disabled"}, status=403)
        try:
            data = await request.json()
            wanted = {key: json_int(data[key]) for key in display.LIMITS}
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": "width, height and density are required"}, status=400)
        error = display.size_error(wanted)
        if error:
            return web.json_response({"error": error}, status=400)
        refused = change_refused(settings_status(), settings_files())
        if refused is not None:
            return refused
        host_files.write_request(REQUEST, f"{wanted['width']} {wanted['height']} {wanted['density']}\n")
        requested()
        log("normal", "gateway", "Screen size change requested: Android restarts at {size}",
            notify=True, size=f"{wanted['width']}×{wanted['height']}")
        return web.json_response({"status": "pending"}, status=202)
    return handle
