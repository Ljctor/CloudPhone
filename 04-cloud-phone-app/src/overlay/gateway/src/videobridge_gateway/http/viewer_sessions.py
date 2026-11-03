"""Ownership of per-viewer signalling teardown, independent of RTC transport.

A reconnect waits for the old handler's finally block, not just a closed socket.
Concurrent resets share one operation; cancellation of an HTTP caller cannot
cancel cleanup. New sessions are refused while their viewer is resetting.
"""

import asyncio

from aiohttp import web

# The RTC adapter bounds an opening request to 10 s and bye send to 5 s.
# HTTP never waits forever; a timeout does not abandon shared cleanup.
RESET_WAIT_SECONDS = 16


class Connection:
    def __init__(self, ws, viewer):
        self.ws = ws
        self.viewer = viewer
        self.done = asyncio.Event()
        self.closing = False
        self.failed = False
        self.retry = None

    async def close(self):
        self.closing = True
        finished = self.done.is_set()
        try:
            await self.ws.close(code=4002, message=b"Viewer reconnect")
        except Exception:
            # A broken browser transport must not abandon upstream ownership.
            # The handler still needs to finish; reset's HTTP deadline bounds
            # the caller's wait without releasing the participant early.
            pass
        await self.done.wait()
        if finished and self.failed and self.retry is not None:
            await self.retry()


class ViewerSessions:
    def __init__(self):
        self.connections = set()
        self.resets = {}
        self.closing = False

    def join(self, ws, viewer):
        if (self.closing or viewer in self.resets
                or any(item.viewer == viewer and item.failed for item in self.connections)):
            return None
        connection = Connection(ws, viewer)
        self.connections.add(connection)
        return connection

    def left(self, connection):
        if not connection.failed:
            self.connections.discard(connection)
        connection.done.set()

    async def _reset(self, viewer):
        old = tuple(item for item in self.connections if item.viewer == viewer)
        if old:
            await asyncio.gather(*(item.close() for item in old))
        for item in old:
            if item.done.is_set() and not item.failed:
                self.connections.discard(item)
        return {"closed": len(old), "failed": any(item.failed for item in old)}

    def _reset_task(self, viewer):
        task = self.resets.get(viewer)
        if task is None:
            task = asyncio.create_task(self._reset(viewer))
            self.resets[viewer] = task
            def done(value):
                if self.resets.get(viewer) is value:
                    del self.resets[viewer]
                # Retrieve failures even if every HTTP caller disappeared.
                if not value.cancelled():
                    value.exception()
            task.add_done_callback(done)
        return task

    async def reset(self, viewer):
        return await asyncio.wait_for(asyncio.shield(self._reset_task(viewer)), RESET_WAIT_SECONDS)

    async def shutdown(self, app):
        self.closing = True
        viewers = {item.viewer for item in self.connections} | set(self.resets)
        if viewers:
            await asyncio.gather(*(asyncio.shield(self._reset_task(viewer)) for viewer in viewers))

    def reset_handler(self, changed):
        async def handle(request):
            try:
                data = await request.json()
                viewer = data.get("viewer") if isinstance(data, dict) else None
            except (ValueError, TypeError):
                viewer = None
            if not isinstance(viewer, str) or not viewer.strip() or len(viewer) > 64:
                return web.json_response({"error": "viewer is required"}, status=400)
            if request.query.get("viewer", viewer) != viewer:
                return web.json_response({"error": "viewer does not match request"}, status=400)
            try:
                result = await self.reset(viewer)
            except asyncio.TimeoutError:
                return web.json_response({"error": "Old video session is still closing; retry reconnect"}, status=504)
            changed()
            if result["failed"]:
                return web.json_response({"closed": result["closed"],
                                          "error": "Old video session teardown failed"}, status=502)
            return web.json_response({"closed": result["closed"]})
        return handle
