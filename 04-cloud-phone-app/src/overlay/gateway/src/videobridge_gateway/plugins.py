"""
Optional features installed beside the app, one directory per plugin:

    PLUGINS_DIR/<id>/plugin.json   {"id": "<id>", "title": "...", "version": "...", "api": 1}
    PLUGINS_DIR/<id>/page.js       optional ES module loaded by the page; it
                                   may import the other *.js files beside it
    PLUGINS_DIR/<id>/gateway.py    optional, defines setup(context)

The directory belongs to root (an install script puts plugins there), so the
gateway runs their code like its own. A plugin that fails to load is logged
and skipped; the gateway and the other plugins keep working. When its
manifest could be read, GET /api/v1/plugins still lists it, with "error" and
without "page".

"api" is the plugin API the plugin was written for, API_VERSION here (a
number, or a "major.minor" string): a plugin whose major differs is refused.
Without it, 1 (the API before the field existed). Additions to the API keep
the major; a change that breaks plugins raises it.

Plugins share one screenshot: context.screenshot(max_age=S) gives the last
capture when it is younger than S seconds, or joins the capture under way,
instead of asking the emulator again. The captures each plugin started are
counted (GET /api/v1/state?details=1, "plugins"). Pixel analysis goes
through context.analyse(fn, *args), in a worker thread, so that the gateway
keeps answering while it runs.

What the user does: context.last_input() is the last touch, swipe or key
from any page ({monotonic, wall} seconds, None since the gateway started;
see http/activity.py), context.viewers() the viewers connected now, so
that what a plugin does on its own can wait while someone plays. Both are
additions to API 1: a plugin for older gateways checks they exist. So is
context.add_delete(path, handler), beside add_get and add_post. And
buttons in a phone alert: context.action_token(path, seconds) gives a
one-time token for one POST to the plugin's path (core/actions.py: short-
lived, spent once, never the page token, which must not reach ntfy.sh),
context.revoke_action(token) withdraws it, and context.notify(text,
actions=[{label, path, body, token}]) puts the buttons in the alert, each
posting body to the gateway's address as the phone reaches it.
context.log(level, text, notify=False, **params) is one record of the
gateway's log tagged with the plugin's id as its source (logs.log), so that
the page shows a plugin's records apart: an addition to API 1 too.

A plugin may keep files in its own data directory, DATA_DIR/<id>
(--plugin_data, /var/lib/cloudphone/plugins on a server), created by the
gateway, owned by its user, mode 700, kept across upgrades: context.data_dir,
None when the gateway has none.

The page lists plugins with GET /api/v1/plugins and imports each page.js from
/plugins/<id>/page.js (every top-level *.js file is served there). A plugin's own API lives under /api/v1/plugins/<id>/,
behind the same origin and page-token checks as the rest of the API.
"""

import asyncio
import concurrent.futures
import functools
import importlib.util
import json
import logging
import os
import re
import time

from aiohttp import web

from . import logs
from .core import actions as action_tokens

# The plugin API's major version (see "api" above).
API_VERSION = 1
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
SCRIPT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\.js$")
# Worker threads for the plugins' pixel analysis, shared by every plugin.
ANALYSIS = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="plugin-analysis")


class Screenshots:
    """Android's screen, shared by every plugin. A caller accepting a
    capture max_age seconds old gets the last one if it is that young, or
    joins the capture under way if it started that recently; otherwise a
    new capture starts. A plugin's own touch (adb shell input) makes the
    earlier captures stale. Counts the captures each plugin started."""

    def __init__(self, capture):
        self._capture = capture
        self._generation = 0
        self._last = None      # (start, generation, value)
        self._flight = None    # (start, generation, task)
        self.counts = {}

    def stale(self):
        self._generation += 1

    def _young(self, entry, now, max_age):
        return entry is not None and entry[1] == self._generation and now - entry[0] < max_age

    async def get(self, plugin_id, max_age=0):
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._young(self._last, now, max_age):
            return self._last[2]
        if self._young(self._flight, now, max_age):
            return await asyncio.shield(self._flight[2])
        entry = (now, self._generation, loop.create_task(self._capture()))
        self._flight = entry
        self.counts[plugin_id] = self.counts.get(plugin_id, 0) + 1

        def done(task):
            if self._flight is entry:
                self._flight = None
            if not task.cancelled() and task.exception() is None and task.result():
                if self._last is None or self._last[0] <= entry[0]:
                    self._last = (entry[0], entry[1], task.result())

        entry[2].add_done_callback(done)
        return await asyncio.shield(entry[2])


class PluginContext:
    """What a plugin's gateway.py may use. Passed to setup(context)."""

    def __init__(self, app, plugin_id, directory, screenshot, adb, notify=None, title=None, data_dir=None,
                 screenshots=None, activity=None, actions=None):
        self.app = app
        self.id = plugin_id
        self.directory = directory
        # Where the plugin may write its own files (its code directory
        # belongs to root), or None.
        self.data_dir = data_dir
        self.prefix = f"/api/v1/plugins/{plugin_id}"
        self._screenshots = screenshots or Screenshots(screenshot)
        self._adb = adb
        self._notify = notify
        self._title = title or plugin_id
        self._activity = activity
        # The gateway's one-time action tokens (http/session.py's ACTIONS).
        self._actions = actions if actions is not None else {}

    def add_get(self, path, handler):
        """GET /api/v1/plugins/<id><path>."""
        self.app.router.add_get(f"{self.prefix}{path}", handler)

    def add_post(self, path, handler):
        """POST /api/v1/plugins/<id><path>; the page token is checked."""
        self.app.router.add_post(f"{self.prefix}{path}", handler)

    def add_delete(self, path, handler):
        """DELETE /api/v1/plugins/<id><path>; the page token is checked.
        An addition to API 1."""
        self.app.router.add_delete(f"{self.prefix}{path}", handler)

    async def screenshot(self, max_age=0):
        """Android's screen as (width, height, RGB888 bytes), or None. With
        max_age (seconds), a capture that young may be given instead of a
        new one (shared by every plugin)."""
        return await self._screenshots.get(self.id, max_age)

    async def adb(self, *args, timeout=10):
        """Runs `adb -s <emulator> ARGS...`; returns (exit code, stdout)."""
        try:
            return await self._adb(*args, timeout=timeout)
        finally:
            if args[:2] == ("shell", "input"):
                # The screen is about to change: no capture from before.
                self._screenshots.stale()

    async def analyse(self, fn, *args):
        """fn(*args) in a worker thread, for work that would hold the event
        loop (pixel loops over a screenshot): the gateway keeps answering
        meanwhile. fn must not touch the event loop nor shared state the
        plugin's handlers change; it returns what it found."""
        return await asyncio.get_running_loop().run_in_executor(ANALYSIS, functools.partial(fn, *args))

    async def notify(self, text, actions=None):
        """Sends text to the user's phone when they turned alerts on (ntfy,
        see http/notify.py), titled with the plugin's name; True when sent.
        actions: its buttons, [{label, path, body, token}] (token: from
        action_token for that path), at most 3."""
        if not self._notify:
            return False
        if not actions:
            return await self._notify(text, title=self._title)
        base = self.app.get("public_url") or ""
        buttons = [{"label": action["label"], "url": f"{base}{self.prefix}{action['path']}",
                    "body": action.get("body"),
                    "headers": {action_tokens.ACTION_HEADER: action["token"]}} for action in actions]
        return await self._notify(text, title=self._title, actions=buttons)

    def action_token(self, path, seconds):
        """A one-time token for one POST to /api/v1/plugins/<id><path>
        within seconds (at most core/actions.MAX_SECONDS), for a phone
        alert's buttons."""
        return action_tokens.issue(self._actions, f"{self.prefix}{path}", time.time(), seconds)

    def revoke_action(self, token):
        """The alert is out of date: its token no longer works."""
        action_tokens.revoke(self._actions, token)

    def last_input(self):
        """The user's last touch, swipe or key, from any page: {monotonic,
        wall} (seconds), or None since the gateway started."""
        return self._activity.last() if self._activity else None

    def viewers(self):
        """The viewers connected now."""
        return self._activity.viewers() if self._activity else 0

    def log(self, level, text, notify=False, **params):
        """One record of the gateway's log whose source is the plugin's id:
        level "normal", "warning" or "error"; notify: also a toast on the
        page. With params, text is a template filled with them. An addition
        to API 1."""
        logs.log(level, self.id, text, notify, **params)

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
        "api": manifest.get("api", 1),
    }


def api_major(api):
    """The major of a manifest's "api" (1, or "1.2"), or None if malformed."""
    if isinstance(api, int) and not isinstance(api, bool):
        return api
    if isinstance(api, str) and re.match(r"^[0-9]{1,4}(\.[0-9]{1,4})?$", api):
        return int(api.split(".")[0])
    return None


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


def load_plugins(app, plugins_dir, screenshot, adb, notify=None, data_dir=None, activity=None, actions=None):
    """Registers every plugin found in plugins_dir; returns their manifests.
    data_dir: the parent of the plugins' data directories, or None.
    activity: last() and viewers(), the user's activity (http/activity.py).
    actions: the one-time action tokens the guard accepts (http/session.py)."""
    loaded = []
    screenshots = Screenshots(screenshot)
    app["plugin_screenshots"] = screenshots
    if not plugins_dir or not os.path.isdir(plugins_dir):
        return loaded
    for name in sorted(os.listdir(plugins_dir)):
        directory = os.path.join(plugins_dir, name)
        if not os.path.isdir(directory):
            continue
        manifest = None
        try:
            manifest = read_manifest(directory)
            plugin_id = manifest["id"]
            api = manifest.pop("api")
            if api_major(api) != API_VERSION:
                raise ValueError(f"written for plugin API {api!r}, this gateway has API {API_VERSION}: "
                                 "install the plugin from the same release")
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
                screenshots.counts.setdefault(plugin_id, 0)
                module.setup(PluginContext(app, plugin_id, directory, screenshot, adb, notify, manifest.get("title"),
                                           plugin_data_dir(data_dir, plugin_id), screenshots, activity, actions))
            loaded.append(manifest)
            logging.info(f"Plugin {plugin_id} {manifest['version']} loaded")
        except Exception as e:
            logging.error(f"Plugin in {directory} not loaded: {e!r}. Fix or remove it, then restart the gateway.")
            if manifest is not None:
                manifest.pop("api", None)
                manifest.pop("page", None)
                loaded.append({**manifest, "error": (str(e) or repr(e))[:200]})

    async def handle_list(request):
        return web.json_response({"plugins": loaded}, headers={"Cache-Control": "no-store"})

    app.router.add_get("/api/v1/plugins", handle_list)
    return loaded


def plugin_stats(app):
    """{id: {screenshots}}: the captures each plugin started since the
    gateway started."""
    screenshots = app.get("plugin_screenshots")
    counts = screenshots.counts if screenshots else {}
    return {plugin_id: {"screenshots": counts[plugin_id]} for plugin_id in sorted(counts)}


def page_handler(path):
    async def handle(request):
        try:
            with open(path, "r", encoding="utf-8") as f:
                body = f.read()
        except OSError:
            return web.Response(status=404)
        return web.Response(text=body, content_type="text/javascript", headers={"Cache-Control": "no-cache"})
    return handle

