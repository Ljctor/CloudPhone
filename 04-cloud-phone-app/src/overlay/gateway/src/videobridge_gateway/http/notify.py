"""Phone alerts over HTTP:

    GET  /api/v1/notify                        {available, enabled, topic, url}
    POST /api/v1/notify {enabled[, newTopic]}  turns them on or off
    POST /api/v1/notify/test                   one test alert

and send(), which the gateway's events and the plugins call (see
core/alerts.py for the rules, adapters/ntfy.py for the post). The state is
kept in FILE through adapters/host_files.py.
"""

import logging

from aiohttp import web

from ..adapters import host_files, ntfy
from ..core import alerts

# file: the saved state's path, set by load(); empty: alerts unavailable.
STATE = {"file": "", "enabled": False, "topic": None}


def load(path):
    """Reads the saved state; a missing or broken file means off."""
    STATE["file"] = path or ""
    if not path:
        return
    try:
        text = host_files.read_file(path, encoding="utf-8")
    except ValueError:
        text = None
    STATE.update(alerts.parse_saved(text))


def configure(enabled, new_topic=False):
    STATE.update(alerts.configure(STATE, enabled, new_topic))
    if STATE["file"]:
        host_files.write_private(STATE["file"], alerts.saved_text(STATE))
    return alerts.describe(STATE, bool(STATE["file"]))


async def send(text, title="Cloud Phone", tags=None, force=False, actions=None):
    """Posts one alert; True when ntfy.sh took it. Never raises. actions:
    its buttons ({label, url, body, headers}: see alerts.actions_header)."""
    url = alerts.url(STATE, force)
    if url is None:
        return False
    try:
        headers = alerts.headers(title, tags, actions)
    except ValueError as e:
        logging.warning(f"Alert's buttons left out: {e}")
        headers = alerts.headers(title, tags)
    return await ntfy.post(url, text, headers)


async def get_notify(request):
    """GET /api/v1/notify: phone alerts through ntfy.sh, {available,
    enabled, topic, url}."""
    return web.json_response(alerts.describe(STATE, bool(STATE["file"])), headers={"Cache-Control": "no-store"})


async def set_notify(request):
    """POST /api/v1/notify {enabled[, newTopic]}: turns alerts on or off;
    the first time (or with newTopic) it makes the random topic."""
    if not STATE["file"]:
        return web.json_response({"error": "Alerts are not set up on this server"}, status=409)
    try:
        data = await request.json()
        enabled, new_topic = data["enabled"], data.get("newTopic", False)
        if not isinstance(enabled, bool) or not isinstance(new_topic, bool):
            raise TypeError("not booleans")
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "Expected {enabled: true|false[, newTopic: true]}"}, status=400)
    try:
        state = configure(enabled, new_topic)
    except OSError as e:
        logging.warning(f"Alerts not saved: {e!r}")
        return web.json_response({"error": "Could not save the setting"}, status=500)
    logging.info(f"Phone alerts {'on' if enabled else 'off'} (requested by {request.remote})")
    return web.json_response(state)


async def test_notify(request):
    """POST /api/v1/notify/test: one test alert."""
    if not STATE["topic"]:
        return web.json_response({"error": "No topic yet: turn alerts on first"}, status=409)
    sent = await send("Test : les alertes du Cloud Phone arrivent bien", force=True)
    return web.json_response({"sent": sent}, status=200 if sent else 502)
