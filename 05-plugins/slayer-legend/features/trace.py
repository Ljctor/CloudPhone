"""The navigation trace: the user's own taps in the page, with the game's
screen before and after each, as a graph (trace.py). Nothing is ever
replayed.

POST /trace/capture {expected_screen?}; save the current screen, optionally report its correct identity
POST /trace/arm     {kind: navigation|forbidden|scannable|vertical|horizontal}; captures the screen before the next user gesture
POST /trace/cancel  {id}; cancels only that armed or pending annotation
POST /trace         {x, y, kind[, end: {x, y}]}: a tap the user just made; 202 at once
GET  /trace         {enabled, nodes, edges, taps, last}
GET  /trace/graph   {nodes, edges}

Kept in the plugin's data directory (trace.json); without one nothing is
recorded. Read-only for the game: it only takes screenshots.
"""

import asyncio
import base64
import binascii
import zlib
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


def before_frame(body):
    """Decode a bounded browser frame captured before Android received input."""
    if not isinstance(body, dict) or "before_frame" not in body:
        return None
    frame = body["before_frame"]
    if not isinstance(frame, dict) or frame.get("encoding") != "deflate":
        raise ValueError("invalid before frame")
    width, height, encoded = frame.get("width"), frame.get("height"), frame.get("rgb")
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= 1080 or not 1 <= height <= 2340 or width * height > 3000000
            or not isinstance(encoded, str) or len(encoded) > 900000):
        raise ValueError("invalid before frame")
    size = width * height * 3
    try:
        compressed = base64.b64decode(encoded, validate=True)
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, size + 1)
    except (ValueError, binascii.Error, zlib.error) as error:
        raise ValueError("invalid before frame") from error
    if len(pixels) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("invalid before frame")
    return width, height, pixels


def trace(ports, screens, graphs, images=None, scan_visible=None):
    path = ports.data_path("trace.json")
    image_dir = Path(ports.data_path("manual-clicks")) if path and images else None
    # The graph, the tap waiting for its "after" screen {tap, before,
    # task}, and the lock that keeps taps in order.
    recorded = {"graph": graphs.load(path) if path else None, "pending": None,
                "armed": None, "latest": None, "lock": None}

    def signature(shot, detailed=False):
        scan = getattr(screens, "look", lambda shot: None)(shot)
        name = screens.classify(shot)
        if isinstance(scan, dict) and scan.get("screen") not in (None, "unknown"):
            # Preserve calibrated panel identities; generic battle/menu labels
            # would merge equipment tabs and the Soul Weapon card.
            overlays = [key for key in scan.get("overlays", ()) if key not in ("panel", "better_weapon_toast")]
            name = overlays[-1] if overlays else scan["screen"]
            if name == "quest_panel" and scan.get("quest_tab"):
                name = "quest_" + scan["quest_tab"]
        return (name, graphs.thumbnail(shot)), scan if detailed else None

    async def screen_now(detailed=False):
        """(screen name, thumbnail) of the screen now, or None when the game
        is not in front."""
        # Taken at once: a tap's screen, never one from before it.
        shot, focus = await asyncio.gather(ports.capture(max_age=0), ports.focused())
        if not shot or not focus:
            return None
        identity, scan = await ports.analyse(signature, shot, detailed)
        return identity, shot, scan

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

    def manual_error(entry, reason, status="error"):
        if entry is None:
            return
        entry.update(capture_status=status, error=reason)
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
            if isinstance(after[2], dict):
                entry["after_scan"] = {key: after[2][key] for key in ("screen", "overlays", "plain", "quest_tab") if key in after[2]}
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
                    frame = await screen_now(bool(pending["manual"]))
                    entry = pending["manual"]
                    annotation_only = entry and entry["kind"] != "navigation"
                    stable = frame is not None and previous is not None and alike(previous, frame)
                    changed = frame is not None and pending["before"] is not None and not alike(pending["before"], frame)
                    if frame is None or annotation_only or stable and changed or elapsed >= AFTER_LIMIT:
                        pending["after_stable"] = bool(stable or annotation_only)
                        if frame is not None and scan_visible is not None:
                            try:
                                await scan_visible(frame[1])
                            except Exception as error:
                                ports.log("warning", f"Trace visible readings failed: {error!r}")
                        finish(pending, frame)
                        return
                    previous = frame
                except Exception as e:
                    recorded["pending"] = None
                    manual_error(pending["manual"], "after capture failed")
                    ports.log("warning", f"Trace failed: {e!r}")
                    return
            interval = min(AFTER_INTERVAL, AFTER_LIMIT - elapsed)

    async def tap_made(tap, supplied_before=None, gesture=None):
        """Takes the screen at once. It is this tap's "before" and also the
        "after" of a tap still waiting for its delay (the screen just before
        the next tap is what the previous one led to); that earlier tap is
        recorded now, so taps quicker than the delay apart chain without a second
        screenshot. Under a lock: taps are handled one at a time, in
        order."""
        async with recorded["lock"]:
            try:
                if gesture is not None and recorded["latest"] != gesture:
                    return
                armed = recorded["armed"]
                recorded["armed"] = None
                if armed and ports.clock.wall() > armed["until"]:
                    manual_error(armed["entry"], "annotation expired")
                    armed = None
                if armed:
                    now = armed["screen"]
                elif supplied_before is not None:
                    identity, scan = await ports.analyse(signature, supplied_before, True)
                    now = identity, supplied_before, scan
                else:
                    now = None  # A post-input capture cannot certify the gesture's source.
                previous = recorded["pending"]
                if previous is not None:
                    previous["task"].cancel()
                    old = previous.get("gesture")
                    follows = gesture is None or (old is not None and gesture[0] == old[0] and gesture[1] == old[1] + 1)
                    if follows:
                        finish(previous, now)
                    else:
                        recorded["pending"] = None
                        manual_error(previous["manual"], "intervening gesture; destination unverified")
                pending = {"tap": tap, "before": now,
                           "manual": armed["entry"] if armed else None,
                           "gesture": gesture, "task": None}
                recorded["pending"] = pending
                if pending["manual"]:
                    pending["manual"].update(tap=tap, capture_status="pending")
                    if pending["manual"]["kind"] == "scannable" and "end" in tap:
                        pending["manual"]["rect"] = [min(tap["x"], tap["end"]["x"]),
                                                     min(tap["y"], tap["end"]["y"]),
                                                     max(tap["x"], tap["end"]["x"]),
                                                     max(tap["y"], tap["end"]["y"])]
                    try:
                        persist_manual(pending["manual"])
                    except OSError as e:
                        ports.log("warning", f"Manual annotation pending state not saved: {e!r}")
                pending["task"] = ports.spawn(after(pending))
            except Exception as e:
                ports.log("warning", f"Trace failed: {e!r}")

    def gesture_key(body):
        if not isinstance(body, dict):
            return None
        session, sequence = body.get("session"), body.get("sequence")
        if (not isinstance(session, str) or not re.fullmatch(r"[0-9a-f]{32}", session)
                or type(sequence) is not int or not 1 <= sequence <= 2147483647):
            return None
        return session, sequence

    async def handle_start(request):
        try:
            gesture = gesture_key(await request.json())
        except ValueError:
            gesture = None
        if gesture is None:
            return ports.respond({"error": "expected gesture session and sequence"}, status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        async with recorded["lock"]:
            latest = recorded["latest"]
            if latest and latest[0] == gesture[0] and latest[1] >= gesture[1]:
                return ports.respond({"accepted": False, "reason": "stale gesture"})
            recorded["latest"] = gesture
            pending = recorded["pending"]
            if pending is not None:
                pending["task"].cancel()
        return ports.respond({"accepted": True})

    async def handle_tap(request):
        if recorded["graph"] is None:
            return ports.respond({"error_t": ports.t("Pas de dossier de données : rien n’est enregistré")}, status=503)
        try:
            body = await request.json()
            tap = graphs.parse_tap(body)
            supplied_before = before_frame(body)
            gesture = gesture_key(body)
            if isinstance(body, dict) and ("session" in body or "sequence" in body) and gesture is None:
                raise ValueError("invalid gesture identity")
        except ValueError:
            tap = None
        if tap is None:
            return ports.respond({"error_t": ports.t("Attendu : {expected}, fractions de 0 à 1",
                                                     expected="{x, y, kind: tap|long|swipe[, end: {x, y}]}")},
                                 status=400)
        if gesture is not None and gesture != recorded["latest"]:
            return ports.respond({"queued": False, "reason": "stale gesture"}, status=202)
        armed = recorded["armed"]
        if armed and armed["kind"] == "scannable" and ports.clock.wall() <= armed["until"]:
            end = tap.get("end")
            if (tap["kind"] != "swipe" or end is None
                    or abs(end["x"] - tap["x"]) < .01 or abs(end["y"] - tap["y"]) < .01):
                return ports.respond({"error": "scannable annotation requires a rectangle"}, status=400)
        if gesture is None and not (armed and ports.clock.wall() <= armed["until"]):
            return ports.respond({"queued": False, "before_verified": False,
                                  "reason": "gesture observation unavailable; navigation not recorded"}, status=202)
        if supplied_before is None and not (armed and ports.clock.wall() <= armed["until"]):
            return ports.respond({"queued": False, "before_verified": False,
                                  "reason": "before frame unavailable; navigation not recorded"}, status=202)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        ports.spawn(tap_made(tap, supplied_before, gesture))
        return ports.respond({"queued": True, "before_verified": bool(supplied_before or armed),
                              **({"reason": "pre-input frame unavailable"} if not supplied_before and not armed else {})}, status=202)

    async def handle_capture(request):
        """A screenshot/report is evidence, never an armed gesture or graph edge."""
        if recorded["graph"] is None or image_dir is None:
            return ports.respond({"error": "manual capture storage unavailable"}, status=503)
        try:
            body = await request.json()
        except ValueError:
            return ports.respond({"error": "expected capture object"}, status=400)
        if not isinstance(body, dict):
            return ports.respond({"error": "expected capture object"}, status=400)
        expected = body.get("expected_screen")
        known = set(getattr(screens, "NAMES", {})) | set(getattr(screens, "TREE", {})) | {"unknown"}
        if "expected_screen" in body and (not isinstance(expected, str) or expected not in known):
            return ports.respond({"error": "unknown expected screen"}, status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        async with recorded["lock"]:
            before = await screen_now(detailed=True)
            if before is None:
                return ports.respond({"error": "game not visible"}, status=409)
            entry = {"id": uuid.uuid4().hex, "kind": "screen_correction" if expected else "screen",
                     "at": ports.clock.wall(), "before": before[0][0], "capture_status": "complete"}
            if expected:
                entry["expected_screen"] = expected
            if isinstance(before[2], dict):
                entry["before_scan"] = {key: before[2][key] for key in ("screen", "overlays", "plain", "quest_tab") if key in before[2]}
            try:
                persist_manual(entry, "before", before)
            except OSError:
                return ports.respond({"error": "screenshot could not be saved"}, status=503)
            entry["before_url"] = f"/api/v1/plugins/slayer-legend/trace/manual/{entry['id']}/before"
            return ports.respond(entry)

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
            before = await screen_now(detailed=True)
            if before is None:
                return ports.respond({"error": "game not visible"}, status=409)
            capture_id = uuid.uuid4().hex
            entry = {"id": capture_id, "kind": kind, "at": ports.clock.wall(),
                     "before": before[0][0], "capture_status": "armed"}
            if isinstance(before[2], dict):
                entry["before_scan"] = {key: before[2][key] for key in ("screen", "overlays", "plain", "quest_tab") if key in before[2]}
            try:
                persist_manual(entry, "before", before)
            except OSError:
                return ports.respond({"error": "before screenshot could not be saved"}, status=503)
            if recorded["armed"]:
                manual_error(recorded["armed"]["entry"], "annotation replaced")
            recorded["armed"] = {"id": capture_id, "kind": kind, "entry": entry,
                                 "screen": before, "until": ports.clock.wall() + ARM_SECONDS}
        return ports.respond({"armed": True, "id": capture_id, "kind": kind, "seconds": ARM_SECONDS})

    async def handle_cancel(request):
        try:
            body = await request.json()
        except ValueError:
            return ports.respond({"error": "expected annotation id"}, status=400)
        capture_id = body.get("id") if isinstance(body, dict) else None
        if not isinstance(capture_id, str) or not re.fullmatch(r"[0-9a-f]{32}", capture_id):
            return ports.respond({"error": "expected annotation id"}, status=400)
        if recorded["lock"] is None:
            recorded["lock"] = asyncio.Lock()
        async with recorded["lock"]:
            armed = recorded["armed"]
            if armed and armed["id"] == capture_id:
                recorded["armed"] = None
                manual_error(armed["entry"], "annotation cancelled", status="cancelled")
            pending = recorded["pending"]
            if pending and (pending["manual"] or {}).get("id") == capture_id:
                recorded["pending"] = None
                pending["task"].cancel()
                manual_error(pending["manual"], "annotation cancelled", status="cancelled")
        return ports.respond({"cancelled": True, "id": capture_id})

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

    return {"routes": [("POST", "/trace/start", handle_start),
                       ("POST", "/trace/capture", handle_capture),
                       ("POST", "/trace/arm", handle_arm),
                       ("POST", "/trace/cancel", handle_cancel),
                       ("POST", "/trace", handle_tap), ("GET", "/trace", handle_state),
                       ("GET", "/trace/graph", handle_graph),
                       ("GET", "/trace/manual", handle_manual),
                       ("GET", "/trace/manual/{capture_id}/{side}", handle_manual_image)]}
