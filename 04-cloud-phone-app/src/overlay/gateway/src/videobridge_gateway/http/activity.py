"""The user's last input, for the plugins (context.last_input): a touch, a
swipe or a key from any page, so that what a plugin does on its own waits
while someone plays.

    POST /api/v1/input   the page sent an input over the data channels

Touches and keys usually go over the emulator's WebRTC data channels,
straight to Android: the page tells the gateway with this route (at once
after a silence, then at most every 5 s). The HTTP fallback's touches and
keys count by themselves (seen() from their handlers). No log record: it
would be one per input.
"""

import time

from aiohttp import web

LAST = {"monotonic": None, "wall": None}


def seen():
    LAST.update(monotonic=time.monotonic(), wall=time.time())


def last():
    """{monotonic, wall} (seconds) of the last input, or None since the
    gateway started."""
    return dict(LAST) if LAST["wall"] is not None else None


async def handle_input(request):
    seen()
    return web.json_response({"status": "ok"})
