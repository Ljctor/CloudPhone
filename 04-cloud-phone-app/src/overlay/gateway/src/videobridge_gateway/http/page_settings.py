"""The page's options over HTTP, kept on the server for every browser:

    GET  /api/v1/settings            {available, settings}
    POST /api/v1/settings {change}   merges change, answers {available, settings}

The page's own options are in FILE (--page_settings); each plugin's in
PLUGIN_DATA/<id>/page-options.json, that plugin's data directory, or in
FILE's "plugins" when it has none. The rules are in core/page_settings.py;
the files go through adapters/host_files.py (mode 600).
"""

import logging
import os

from aiohttp import web

from ..adapters import host_files
from ..core import page_settings as rules

# file: the page's own options, "" when they are not kept (then the page
# keeps its defaults); plugin_data: the plugins' data directories' parent.
STATE = {"file": "", "plugin_data": "", "own": {}, "plugins": {}}
OPTIONS_FILE = "page-options.json"


def _plugin_file(plugin_id):
    """The plugin's own options file, or None (no data directory)."""
    root = STATE["plugin_data"]
    if not root:
        return None
    directory = os.path.join(root, plugin_id)
    return os.path.join(directory, OPTIONS_FILE) if os.path.isdir(directory) else None


def _read(path):
    try:
        return rules.parse_saved(host_files.read_file(path, encoding="utf-8"))
    except ValueError:
        return {}


def load(path, plugin_data=""):
    """Reads the saved options (after the plugins made their data directories)."""
    STATE.update(file=path or "", plugin_data=plugin_data or "", own={}, plugins={})
    if not STATE["file"]:
        return
    own = _read(STATE["file"])
    plugins = own.pop("plugins", {})
    STATE["own"] = own
    STATE["plugins"] = {key: value for key, value in plugins.items()
                        if isinstance(value, dict) and rules.PLUGIN_ID.match(key)}
    if STATE["plugin_data"] and os.path.isdir(STATE["plugin_data"]):
        for plugin_id in sorted(os.listdir(STATE["plugin_data"])):
            path = _plugin_file(plugin_id) if rules.PLUGIN_ID.match(plugin_id) else None
            if path and os.path.exists(path):
                STATE["plugins"][plugin_id] = _read(path)


def describe():
    return {"available": bool(STATE["file"]), "settings": rules.answer(STATE["own"], STATE["plugins"])}


def change(given):
    """Applies a checked change and writes the files it touched."""
    own, plugins = rules.split(rules.check_change(given))
    new_own = rules.merged(STATE["own"], own) if own else STATE["own"]
    new_plugins = {plugin_id: rules.merged(STATE["plugins"].get(plugin_id, {}), options)
                   for plugin_id, options in plugins.items()}
    homeless = {plugin_id for plugin_id in new_plugins if _plugin_file(plugin_id) is None}
    for plugin_id, options in new_plugins.items():
        if plugin_id not in homeless:
            host_files.write_private(_plugin_file(plugin_id), rules.saved_text(options))
    STATE["plugins"] = {**STATE["plugins"], **new_plugins}
    if own or homeless:
        kept = {**new_own, "plugins": {plugin_id: STATE["plugins"][plugin_id] for plugin_id in STATE["plugins"]
                                       if _plugin_file(plugin_id) is None}}
        host_files.write_private(STATE["file"], rules.saved_text(kept))
    STATE["own"] = new_own


async def get_settings(request):
    return web.json_response(describe(), headers={"Cache-Control": "no-store"})


async def set_settings(request):
    if not STATE["file"]:
        return web.json_response({"error": "Settings are not kept on this server"}, status=409)
    try:
        given = await request.json()
        change(given)
    except ValueError as e:
        return web.json_response({"error": str(e) or "Expected a JSON object"}, status=400)
    except OSError as e:
        logging.warning(f"Page settings not saved: {e!r}")
        return web.json_response({"error": "Could not save the settings"}, status=500)
    return web.json_response(describe())
