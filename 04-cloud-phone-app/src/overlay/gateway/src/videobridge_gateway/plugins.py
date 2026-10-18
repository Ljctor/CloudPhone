"""
Optional features installed beside the app, one directory per plugin:

    PLUGINS_DIR/<id>/plugin.json   {"id": "<id>", "title": "...", "version": "..."}
    PLUGINS_DIR/<id>/page.js       optional ES module loaded by the page; it
                                   may import the other *.js files beside it
    PLUGINS_DIR/<id>/gateway.py    optional, defines setup(context)

The directory belongs to root (an install script puts plugins there), so the
gateway runs their code like its own. A plugin that fails to load is logged
and skipped; the gateway and the other plugins keep working.

A plugin may keep files in its own data directory, DATA_DIR/<id>
(--plugin_data, /var/lib/cloudphone/plugins on a server), created by the
gateway, owned by its user, mode 700, kept across upgrades: context.data_dir,
None when the gateway has none.

The page lists plugins with GET /api/v1/plugins and imports each page.js from
/plugins/<id>/page.js (every top-level *.js file is served there). A plugin's own API lives under /api/v1/plugins/<id>/,
behind the same origin and page-token checks as the rest of the API.
"""

import asyncio
import importlib.util
import json
import logging
import os
import re

from aiohttp import web

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SCRIPT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\.js$")


class PluginContext:
    """What a plugin's gateway.py may use. Passed to setup(context)."""

    def __init__(self, app, plugin_id, directory, screenshot, adb, notify=None, title=None, data_dir=None):
        self.app = app
        self.id = plugin_id
        self.directory = directory
        # Where the plugin may write its own files (its code directory
        # belongs to root), or None.
        self.data_dir = data_dir
        self.prefix = f"/api/v1/plugins/{plugin_id}"
        self._screenshot = screenshot
        self._adb = adb
        self._notify = notify
        self._title = title or plugin_id

    def add_get(self, path, handler):
        """GET /api/v1/plugins/<id><path>."""
        self.app.router.add_get(f"{self.prefix}{path}", handler)

    def add_post(self, path, handler):
        """POST /api/v1/plugins/<id><path>; the page token is checked."""
        self.app.router.add_post(f"{self.prefix}{path}", handler)

    async def screenshot(self):
        """Android's screen as (width, height, RGB888 bytes), or None."""
        return await self._screenshot()

    async def adb(self, *args, timeout=10):
        """Runs `adb -s <emulator> ARGS...`; returns (exit code, stdout)."""
        return await self._adb(*args, timeout=timeout)

    async def notify(self, text):
        """Sends text to the user's phone when they turned alerts on (ntfy,
        see notify.py), titled with the plugin's name; True when sent."""
        return bool(self._notify) and await self._notify(text, title=self._title)

    def json(self, value, status=200):
        return web.json_response(value, status=status, headers={"Cache-Control": "no-store"})


def read_manifest(directory):
    with open(os.path.join(directory, "plugin.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    plugin_id = manifest.get("id")
    if not isinstance(plugin_id, str) or not ID_RE.match(plugin_id):
        raise ValueError(f"invalid plugin id {plugin_id!r}")
    if plugin_id != os.path.basename(directory):
        raise ValueError(f"plugin id {plugin_id!r} differs from its directory name")
    return {
        "id": plugin_id,
        "title": str(manifest.get("title", plugin_id))[:64],
        "version": str(manifest.get("version", ""))[:32],
    }


def plugin_data_dir(data_dir, plugin_id):
    """DATA_DIR/<id>, created if needed, or None (no DATA_DIR, or not writable)."""
    if not data_dir:
        return None
    path = os.path.join(data_dir, plugin_id)
    try:
        os.makedirs(path, mode=0o700, exist_ok=True)
    except OSError as e:
        logging.warning(f"Plugin {plugin_id}: no data directory {path}: {e}")
        return None
    return path


def load_plugins(app, plugins_dir, screenshot, adb, notify=None, data_dir=None):
    """Registers every plugin found in plugins_dir; returns their manifests.
    data_dir: the parent of the plugins' data directories, or None."""
    loaded = []
    if not plugins_dir or not os.path.isdir(plugins_dir):
        return loaded
    for name in sorted(os.listdir(plugins_dir)):
        directory = os.path.join(plugins_dir, name)
        if not os.path.isdir(directory):
            continue
        try:
            manifest = read_manifest(directory)
            plugin_id = manifest["id"]
            for script in sorted(os.listdir(directory)):
                if SCRIPT_RE.match(script) and os.path.isfile(os.path.join(directory, script)):
                    app.router.add_get(f"/plugins/{plugin_id}/{script}",
                                       page_handler(os.path.join(directory, script)))
            if os.path.isfile(os.path.join(directory, "page.js")):
                manifest["page"] = f"/plugins/{plugin_id}/page.js"
            code = os.path.join(directory, "gateway.py")
            if os.path.isfile(code):
                spec = importlib.util.spec_from_file_location(f"cloudphone_plugin_{plugin_id.replace('-', '_')}", code)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.setup(PluginContext(app, plugin_id, directory, screenshot, adb, notify, manifest.get("title"),
                                           plugin_data_dir(data_dir, plugin_id)))
            loaded.append(manifest)
            logging.info(f"Plugin {plugin_id} {manifest['version']} loaded")
        except Exception as e:
            logging.error(f"Plugin in {directory} not loaded: {e!r}")

    async def handle_list(request):
        return web.json_response({"plugins": loaded}, headers={"Cache-Control": "no-store"})

    app.router.add_get("/api/v1/plugins", handle_list)
    return loaded


def page_handler(path):
    async def handle(request):
        try:
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError:
            return web.Response(status=404)
        return web.Response(text=body, content_type="text/javascript", headers={"Cache-Control": "no-cache"})
    return handle


async def run_adb(adb_path, serial, *args, timeout=10):
    """(exit code, stdout) of an adb command, or (-1, "") on timeout/error."""
    try:
        process = await asyncio.create_subprocess_exec(
            adb_path, "-s", serial, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        logging.warning(f"adb could not start: {e}")
        return -1, ""
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return -1, ""
    return process.returncode, out.decode("utf-8", "replace")
