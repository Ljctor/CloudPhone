"""Accept small, allowlisted browser milestone batches with the page's POST token."""
import json

from aiohttp import web

from ..core.stream_diagnostics import STREAMS, check_browser_events


async def post_events(request):
    if request.content_length is not None and request.content_length > 16384:
        return web.json_response({"error": "event batch too large"}, status=413)
    body = bytearray()
    async for chunk in request.content.iter_chunked(4096):
        body.extend(chunk)
        if len(body) > 16384:
            return web.json_response({"error": "event batch too large"}, status=413)
    try:
        sid, events = check_browser_events(json.loads(body))
        accepted = STREAMS.browser_events(sid, events)
    except (ValueError, UnicodeDecodeError):
        return web.json_response({"error": "invalid diagnostic events"}, status=400)
    except KeyError:
        return web.json_response({"error": "unknown diagnostic session"}, status=404)
    except OverflowError:
        return web.json_response({"error": "diagnostic event rate exceeded"}, status=429)
    return web.json_response({"accepted": accepted}, status=202, headers={"Cache-Control": "no-store"})
