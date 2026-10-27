"""The navigation trace: the user's own taps in the page, with the game's
screen before and after each, as a graph (trace.py). Nothing is ever
replayed.

POST /trace/arm     captures the screen before the next user gesture
POST /trace         {x, y, kind[, end: {x, y}]}: a tap the user just made; 202 at once
GET  /trace         {enabled, nodes, edges, taps, last}
GET  /trace/graph   {nodes, edges}

Kept in the plugin's data directory (trace.json); without one nothing is
recorded. Read-only for the game: it only takes screenshots.
"""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

# A tap's "after" screen: this long after it, or just before the next tap.
AFTER_SECONDS = 2.0
ARM_SECONDS = 30.0


def trace(ports, screens, graphs, images=None):
    path = ports.data_path("trace.json")
    image_dir = Path(ports.data_path("manual-clicks")) if path and images else None
    # The graph, the tap waiting for its "after" screen {tap, before,
    # task}, and the lock that keeps taps in order.
    recorded = {"graph": graphs.load(path) if path else None, "pending": None,
                "armed": None, "lock": None}

    def signature(shot):
        return screens.classify(shot), graphs.thumbnail(shot)

    async def screen_now():
        """(screen name, thumbnail) of the screen now, or None when the game
        is not in front."""
        # Taken at once: a tap's screen, never one from before it.
        shot, focus = await asyncio.gather(ports.capture(max_age=0), ports.focused())
        if not shot or not focus:
            return None
        return await ports.analyse(signature, shot), shot

    def keep_manual(before, after, tap, now):
        """A debug-button tap keeps both complete screenshots, even if the graph is full."""
        if image_dir is None:
            return
        image_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        capture_id = uuid.uuid4().hex
        for side, frame in (("before", before), ("after", after)):
            target = image_dir / f"{capture_id}-{side}.png"
            temporary = image_dir / f"{capture_id}-{side}.png.tmp"
            try:
                with temporary.open("wb") as file:
                    file.write(images.png(frame[1]))
                os.chmod(temporary, 0o600)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        record = {"id": capture_id, "at": now, "tap": tap,
                  "before": before[0][0], "after": after[0][0]}
        target = image_dir / f"{capture_id}.json"
        temporary = image_dir / f"{capture_id}.json.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(record, file)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def finish(pending, after):
        """Records the pending tap with its after screen and saves."""
        if recorded["pending"] is pending:
            recorded["pending"] = None
        # A tap that took the game out of the front (home, another app) is
        # not an edge of the game's graph: dropped.
        if pending["before"] is None or after is None:
            return
        now = ports.clock.wall()
        if pending["manual"]:
            try:
                keep_manual(pending["before"], after, pending["tap"], now)
            except OSError as e:
                ports.log("warning", f"Manual click screenshots not saved: {e!r}")
        if recorded["graph"].record(pending["before"][0], after[0], pending["tap"], now):
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
                armed = recorded["armed"]
                recorded["armed"] = None
                now = (armed["screen"] if armed and ports.clock.wall() <= armed["until"]
                       else await screen_now())
                previous = recorded["pending"]
                if previous is not None:
                    previous["task"].cancel()
                    finish(previous, now)
                pending = {"tap": tap, "before": now, "manual": bool(armed and now is armed["screen"]),
                           "task": None}
                recorded["pending"] = pending
                pending["task"] = ports.spawn(after(pending))
            except Exception as e:
                ports.log("warning", f"Trace failed: {e!r}")

    async def handle_tap(request):
        if recorded["graph"] is None:
            return ports.respond({"error_t": ports.t("Pas de dossier de données : rien n’est enregistré")}, status=503)
        try:
            tap = graphs.parse_tap(await request.json())
        except ValueError:
            tap = None
        if tap is None:
            return ports.respond({"error_t": ports.t("Attendu : {expected}, fractions de 0 à 1",
                                                     expected="{x, y, kind: tap|long|swipe[, end: {x, y}]}")},
                                 status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        ports.spawn(tap_made(tap))
        return ports.respond({"queued": True}, status=202)

    async def handle_arm(request):
        if recorded["graph"] is None:
            return ports.respond({"error": "trace unavailable"}, status=503)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        async with recorded["lock"]:
            before = await screen_now()
            if before is None:
                return ports.respond({"error": "game not visible"}, status=409)
            recorded["armed"] = {"screen": before, "until": ports.clock.wall() + ARM_SECONDS}
        return ports.respond({"armed": True, "seconds": ARM_SECONDS})

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

    async def handle_manual(request):
        if image_dir is None or not image_dir.is_dir():
            return ports.respond({"clicks": []})
        clicks = []
        for path in sorted(image_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            capture_id = data.get("id")
            if re.fullmatch(r"[0-9a-f]{32}", str(capture_id)):
                data["before_url"] = f"/api/v1/plugins/slayer-legend/trace/manual/{capture_id}/before"
                data["after_url"] = f"/api/v1/plugins/slayer-legend/trace/manual/{capture_id}/after"
                clicks.append(data)
        return ports.respond({"clicks": clicks})

    async def handle_manual_image(request):
        from aiohttp import web
        capture_id = request.match_info["capture_id"]
        side = request.match_info["side"]
        if image_dir is None or not re.fullmatch(r"[0-9a-f]{32}", capture_id) or side not in ("before", "after"):
            raise web.HTTPNotFound()
        path = image_dir / f"{capture_id}-{side}.png"
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "private, no-store"})

    return {"routes": [("POST", "/trace/arm", handle_arm),
                       ("POST", "/trace", handle_tap), ("GET", "/trace", handle_state),
                       ("GET", "/trace/graph", handle_graph),
                       ("GET", "/trace/manual", handle_manual),
                       ("GET", "/trace/manual/{capture_id}/{side}", handle_manual_image)]}
