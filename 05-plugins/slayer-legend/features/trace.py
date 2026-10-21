"""The navigation trace: the user's own taps in the page, with the game's
screen before and after each, as a graph (trace.py). Nothing is ever
replayed.

POST /trace         {x, y, kind[, end: {x, y}]}: a tap the user just made; 202 at once
GET  /trace         {enabled, nodes, edges, taps, last}
GET  /trace/graph   {nodes, edges}

Kept in the plugin's data directory (trace.json); without one nothing is
recorded. Read-only for the game: it only takes screenshots.
"""

import asyncio

# A tap's "after" screen: this long after it, or just before the next tap.
AFTER_SECONDS = 2.0


def trace(ports, screens, graphs):
    path = ports.data_path("trace.json")
    # The graph, the tap waiting for its "after" screen {tap, before,
    # task}, and the lock that keeps taps in order.
    recorded = {"graph": graphs.load(path) if path else None, "pending": None, "lock": None}

    def signature(shot):
        return screens.classify(shot), graphs.thumbnail(shot)

    async def screen_now():
        """(screen name, thumbnail) of the screen now, or None when the game
        is not in front."""
        # Taken at once: a tap's screen, never one from before it.
        shot, focus = await asyncio.gather(ports.capture(max_age=0), ports.focused())
        if not shot or not focus:
            return None
        return await ports.analyse(signature, shot)

    def finish(pending, after):
        """Records the pending tap with its after screen and saves."""
        if recorded["pending"] is pending:
            recorded["pending"] = None
        # A tap that took the game out of the front (home, another app) is
        # not an edge of the game's graph: dropped.
        if pending["before"] is None or after is None:
            return
        if recorded["graph"].record(pending["before"], after, pending["tap"], ports.clock.wall()):
            try:
                graphs.save(recorded["graph"], path)
            except OSError as e:
                ports.log("warning", f"Trace not saved: {e!r}")

    async def after(pending):
        await ports.clock.sleep(AFTER_SECONDS)
        async with recorded["lock"]:
            # A newer tap may have finished it already.
            if recorded["pending"] is pending:
                try:
                    finish(pending, await screen_now())
                except Exception as e:
                    recorded["pending"] = None
                    ports.log("warning", f"Trace failed: {e!r}")

    async def tap_made(tap):
        """Takes the screen at once. It is this tap's "before" and also the
        "after" of a tap still waiting for its 2 s (the screen just before
        the next tap is what the previous one led to); that earlier tap is
        recorded now, so taps quicker than 2 s apart chain without a second
        screenshot. Under a lock: taps are handled one at a time, in
        order."""
        async with recorded["lock"]:
            try:
                now = await screen_now()
                previous = recorded["pending"]
                if previous is not None:
                    previous["task"].cancel()
                    finish(previous, now)
                pending = {"tap": tap, "before": now, "task": None}
                recorded["pending"] = pending
                pending["task"] = ports.spawn(after(pending))
            except Exception as e:
                ports.log("warning", f"Trace failed: {e!r}")

    async def handle_tap(request):
        if recorded["graph"] is None:
            return ports.respond({"error": "No data directory: nothing is recorded"}, status=503)
        try:
            tap = graphs.parse_tap(await request.json())
        except ValueError:
            tap = None
        if tap is None:
            return ports.respond({"error": "Expected {x, y, kind: tap|long|swipe[, end: {x, y}]}, fractions 0-1"},
                                 status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        ports.spawn(tap_made(tap))
        return ports.respond({"queued": True}, status=202)

    async def handle_state(request):
        graph = recorded["graph"]
        return ports.respond({
            "enabled": graph is not None,
            "nodes": len(graph.nodes) if graph else 0,
            "edges": len(graph.edges) if graph else 0,
            "taps": graph.taps() if graph else 0,
            "last": graph.last if graph else None,
        })

    async def handle_graph(request):
        graph = recorded["graph"]
        return ports.respond(graph.public() if graph else {"nodes": [], "edges": []})

    return {"routes": [("POST", "/trace", handle_tap), ("GET", "/trace", handle_state),
                       ("GET", "/trace/graph", handle_graph)]}
