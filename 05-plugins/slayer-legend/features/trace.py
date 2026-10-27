"""The navigation trace: the user's own taps in the page, with the game's
screen before and after each, as a graph (trace.py). Nothing is ever
replayed.

POST /trace/arm     {kind: navigation|forbidden|scannable|vertical|horizontal}; captures the screen before the next user gesture
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
AFTER_SECONDS = 0.15
AFTER_INTERVAL = 0.15
AFTER_LIMIT = 2.0
ARM_SECONDS = 30.0
ANNOTATION_KINDS = ("navigation", "forbidden", "scannable", "vertical", "horizontal")


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

    def persist_manual(entry, side=None, frame=None):
        """Keep the before image as soon as armed, with atomic private metadata."""
        if image_dir is None:
            raise OSError("manual capture storage unavailable")
        image_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        capture_id = entry["id"]
        if side is not None:
            target = image_dir / f"{capture_id}-{side}.png"
            temporary = target.with_suffix(".png.tmp")
            try:
                with temporary.open("wb") as file:
                    file.write(images.png(frame[1]))
                os.chmod(temporary, 0o600)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        target = image_dir / f"{capture_id}.json"
        temporary = target.with_suffix(".json.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(entry, file)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def manual_error(entry, reason):
        if entry is None:
            return
        entry.update(capture_status="error", error=reason)
        try:
            persist_manual(entry)
        except OSError as e:
            ports.log("warning", f"Manual annotation not saved: {e!r}")

    def finish(pending, after):
        """Records the pending tap with its after screen and saves."""
        if recorded["pending"] is pending:
            recorded["pending"] = None
        # Leaving the game preserves the annotation and before capture,
        # but cannot supply a valid after image.
        entry = pending["manual"]
        if pending["before"] is None or after is None:
            manual_error(entry, "game not visible after annotation")
            return
        now = ports.clock.wall()
        if entry:
            entry.update(at=now, tap=pending["tap"], after=after[0][0], capture_status="complete")
            if "after_stable" in pending:
                entry["after_stable"] = pending["after_stable"]
            try:
                persist_manual(entry, "after", after)
            except OSError as e:
                manual_error(entry, "after screenshot could not be saved")
                ports.log("warning", f"Manual click screenshots not saved: {e!r}")
            # Marking an area never turns it into a navigation edge.
            if entry["kind"] != "navigation":
                return
        if recorded["graph"].record(pending["before"][0], after[0], pending["tap"], now):
            try:
                graphs.save(recorded["graph"], path)
            except OSError as e:
                ports.log("warning", f"Trace not saved: {e!r}")

    async def after(pending):
        def alike(left, right):
            return left[0][0] == right[0][0] and graphs.distance(left[0][1], right[0][1]) < graphs.MATCH

        previous, elapsed = None, 0.0
        interval = AFTER_SECONDS
        while elapsed < AFTER_LIMIT:
            await ports.clock.sleep(interval)
            elapsed += interval
            async with recorded["lock"]:
                if recorded["pending"] is not pending:
                    return
                try:
                    frame = await screen_now()
                    entry = pending["manual"]
                    annotation_only = entry and entry["kind"] != "navigation"
                    stable = frame is not None and previous is not None and alike(previous, frame)
                    changed = frame is not None and pending["before"] is not None and not alike(pending["before"], frame)
                    if frame is None or annotation_only or stable and changed or elapsed >= AFTER_LIMIT:
                        pending["after_stable"] = bool(stable or annotation_only)
                        finish(pending, frame)
                        return
                    previous = frame
                except Exception as e:
                    recorded["pending"] = None
                    manual_error(pending["manual"], "after capture failed")
                    ports.log("warning", f"Trace failed: {e!r}")
                    return
            interval = min(AFTER_INTERVAL, AFTER_LIMIT - elapsed)

    async def tap_made(tap):
        """Takes the screen at once. It is this tap's "before" and also the
        "after" of a tap still waiting for its delay (the screen just before
        the next tap is what the previous one led to); that earlier tap is
        recorded now, so taps quicker than the delay apart chain without a second
        screenshot. Under a lock: taps are handled one at a time, in
        order."""
        async with recorded["lock"]:
            try:
                armed = recorded["armed"]
                recorded["armed"] = None
                if armed and ports.clock.wall() > armed["until"]:
                    manual_error(armed["entry"], "annotation expired")
                    armed = None
                now = armed["screen"] if armed else await screen_now()
                previous = recorded["pending"]
                if previous is not None:
                    previous["task"].cancel()
                    finish(previous, now)
                pending = {"tap": tap, "before": now,
                           "manual": armed["entry"] if armed else None,
                           "task": None}
                recorded["pending"] = pending
                if pending["manual"]:
                    pending["manual"].update(tap=tap, capture_status="pending")
                    try:
                        persist_manual(pending["manual"])
                    except OSError as e:
                        ports.log("warning", f"Manual annotation pending state not saved: {e!r}")
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
        if recorded["graph"] is None or image_dir is None:
            return ports.respond({"error": "manual capture storage unavailable"}, status=503)
        try:
            body = await request.json()
        except ValueError:
            return ports.respond({"error": "expected annotation kind"}, status=400)
        kind = body.get("kind", "navigation") if isinstance(body, dict) else None
        if kind not in ANNOTATION_KINDS:
            return ports.respond({"error": "unknown annotation kind", "kinds": ANNOTATION_KINDS}, status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        async with recorded["lock"]:
            before = await screen_now()
            if before is None:
                return ports.respond({"error": "game not visible"}, status=409)
            capture_id = uuid.uuid4().hex
            entry = {"id": capture_id, "kind": kind, "at": ports.clock.wall(),
                     "before": before[0][0], "capture_status": "armed"}
            try:
                persist_manual(entry, "before", before)
            except OSError:
                return ports.respond({"error": "before screenshot could not be saved"}, status=503)
            if recorded["armed"]:
                manual_error(recorded["armed"]["entry"], "annotation replaced")
            recorded["armed"] = {"id": capture_id, "kind": kind, "entry": entry,
                                 "screen": before, "until": ports.clock.wall() + ARM_SECONDS}
        return ports.respond({"armed": True, "id": capture_id, "kind": kind, "seconds": ARM_SECONDS})

    async def handle_state(request):
        graph = recorded["graph"]
        return ports.respond({
            "enabled": graph is not None,
            "nodes": len(graph.nodes) if graph else 0,
            "edges": len(graph.edges) if graph else 0,
            "taps": graph.taps() if graph else 0,
            "last": graph.last if graph else None,
            "armed": ({key: recorded["armed"][key] for key in ("id", "kind", "until")}
                      if recorded["armed"] and ports.clock.wall() <= recorded["armed"]["until"] else None),
            "pending": ({key: recorded["pending"]["manual"][key] for key in ("id", "kind")}
                        if recorded["pending"] and recorded["pending"]["manual"] else None),
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
            if not isinstance(data, dict):
                continue
            capture_id = data.get("id")
            if re.fullmatch(r"[0-9a-f]{32}", str(capture_id)):
                data.setdefault("kind", "navigation")
                data.setdefault("capture_status", "complete")
                active = ((recorded["armed"] or {}).get("id") == capture_id
                          and ports.clock.wall() <= recorded["armed"]["until"]
                          or recorded["pending"] and (recorded["pending"]["manual"] or {}).get("id") == capture_id)
                if data["capture_status"] in ("armed", "pending") and not active:
                    data.update(capture_status="error", error="annotation expired or interrupted")
                for side in ("before", "after"):
                    if (image_dir / f"{capture_id}-{side}.png").is_file():
                        data[f"{side}_url"] = f"/api/v1/plugins/slayer-legend/trace/manual/{capture_id}/{side}"
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
