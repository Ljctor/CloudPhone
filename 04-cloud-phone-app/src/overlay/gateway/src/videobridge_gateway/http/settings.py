"""Emulator settings over HTTP:

    GET  /api/v1/emulator-settings    what Android runs with, the allowed
                                      choices, the last request's state
    POST /api/v1/emulator-settings {renderer, cores, memoryMb[, width,
                                    height, density]}

A request is a line written to REQUEST, which the root-path unit
cloudphone-settings applies, reporting in STATUS (see core/settings.py for
the rules, adapters/host_files.py for the files). It shares the screen
size's limit, display.change_refused().
"""

import os

from aiohttp import web

from ..adapters import host_files
from ..core import settings
from ..core.display import LIMITS as DISPLAY_LIMITS, json_int, size_error
from ..logs import log
from . import display

# Set by gateway_server's main; empty paths disable the feature.
REQUEST = ""
STATUS = ""


def status():
    """The state of the last emulator settings request."""
    return settings.parse_status(host_files.exists(REQUEST), host_files.read_file(STATUS))


def files():
    """The request and status paths, for the screen size's limit."""
    return REQUEST, STATUS


def get_settings(current, configured, meminfo):
    """The handler of GET /api/v1/emulator-settings: current() is what the
    running emulator was started with, configured() the screen size in
    config.ini, meminfo() the host's memory (kB values)."""
    async def handle(request):
        return web.json_response({
            "canChange": bool(REQUEST),
            "current": current(),
            "display": configured(),
            "limits": settings.limits(os.cpu_count() or 1, meminfo()),
            "request": status(),
        }, headers={"Cache-Control": "no-store"})
    return handle


def set_settings(meminfo, requested):
    """The handler of POST /api/v1/emulator-settings: asks the root service
    to change them, which restarts Android once (data is kept). The screen
    size is optional and all three of its values come together.
    requested() is called once the request is written."""
    @display.change_request("Android settings change refused: {error}")
    async def handle(request):
        if not REQUEST:
            return web.json_response({"error": "Emulator settings changes are disabled"}, status=403)
        try:
            data = await request.json()
            renderer, cores, memory = data["renderer"], json_int(data["cores"]), json_int(data["memoryMb"])
            if not isinstance(renderer, str):
                raise TypeError("renderer is not a string")
        except (ValueError, KeyError, TypeError):
            return web.json_response({"error": "renderer, cores and memoryMb are required"}, status=400)
        error = settings.request_error(renderer, cores, memory, settings.limits(os.cpu_count() or 1, meminfo()))
        if error:
            return web.json_response({"error": error}, status=400)
        size = ""
        given = [key for key in DISPLAY_LIMITS if data.get(key) is not None]
        if given:
            try:
                if len(given) != len(DISPLAY_LIMITS):
                    raise ValueError
                wanted = {key: json_int(data[key]) for key in DISPLAY_LIMITS}
            except (ValueError, TypeError):
                return web.json_response({"error": "width, height and density go together"}, status=400)
            error = size_error(wanted)
            if error:
                return web.json_response({"error": error}, status=400)
            size = f" {wanted['width']} {wanted['height']} {wanted['density']}"
        refused = display.change_refused(status(), files())
        if refused is not None:
            return refused
        host_files.write_request(REQUEST, f"{renderer} {cores} {memory}{size}\n")
        requested()
        log("normal", "gateway", "Android settings change requested ({settings}): Android restarts",
            notify=True, settings=f"{renderer}, {cores} × CPU, {memory} MiB"
            + (f", {wanted['width']}×{wanted['height']}" if size else ""))
        return web.json_response({"status": "pending"}, status=202)
    return handle
