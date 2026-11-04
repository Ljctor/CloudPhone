#!/usr/bin/env python3
"""Private, passive review of recorded navigation evidence. No phone control."""
import argparse
import asyncio
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
import sys
import hashlib
import importlib.util

from aiohttp import web

_zone_path = Path(__file__).with_name("zone_feedback.py")
if not _zone_path.is_file():
    _zone_path = Path(__file__).parent.parent / "zone_feedback.py"
_zone_spec = importlib.util.spec_from_file_location("cloudphone_shared_zone_feedback", _zone_path)
zone_feedback = importlib.util.module_from_spec(_zone_spec)
_zone_spec.loader.exec_module(zone_feedback)

CAPTURE = re.compile(r"[0-9a-f]{32}")
THUMB = re.compile(r"[0-9a-f]{312}")
KINDS = {"tap", "long", "swipe"}
ANNOTATIONS = {"navigation", "action", "forbidden", "scannable", "vertical", "horizontal", "draggable", "screen", "screen_correction"}
STEM = re.compile(r"[A-Za-z0-9_-]{1,100}")


def text(value, limit=200):
    return "".join(c for c in str(value) if c >= " " and c != "\x7f")[:limit]


def point(x, y):
    try:
        x, y = float(x), float(y)
        return {"x": x, "y": y} if all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)) else None
    except (ValueError, TypeError):
        return None


def read_json(path, default):
    try:
        if path.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def safe_image(directory, capture_id, side):
    if not CAPTURE.fullmatch(capture_id) or side not in {"before", "after"}:
        return None
    path = directory / f"{capture_id}-{side}.png"
    if path.is_symlink() or not path.is_file() or path.resolve().parent != directory.resolve():
        return None
    return path


class Evidence:
    def __init__(self, data_dir, feedback_path, static_dir=None, ledger_path=None, plugin_dir=None, processor=None):
        self.data_dir = Path(data_dir)
        self.manual_dir = self.data_dir / "manual-clicks"
        self.feedback_path = Path(feedback_path)
        self.static_dir = Path(static_dir or Path(__file__).parent)
        self.ledger_path = Path(ledger_path) if ledger_path else None
        self.plugin_dir = Path(plugin_dir or Path(__file__).parent.parent)
        self.lock = asyncio.Lock()
        self.images = {}
        self.processor = Path(processor) if processor else None
        self.review_event = asyncio.Event()
        self.review_state = {"enabled": bool(processor), "state": "idle", "lastRun": None}
        self.zones = zone_feedback.ZoneFeedback(self.feedback_path.parent)

    def known_screens(self):
        registry = read_json(self.plugin_dir / "screen_registry.json", {})
        navigation = read_json(self.plugin_dir / "navigation.json", {})
        return (set(registry.get("screens", {})) | set(registry.get("tree", {})) | set(navigation.get("screens", {}))) - zone_feedback.UNKNOWN

    def revision(self):
        paths = [self.feedback_path, self.zones.path, self.ledger_path, self.data_dir / "trace.json",
                 self.data_dir / "manual-clicks", self.data_dir / "screenshots"]
        paths += list(self.manual_dir.glob("*.json"))
        values = []
        for path in paths:
            if path is None:
                continue
            try:
                stat = path.stat()
                values.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                continue
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def source_stamp(self):
        paths = [self.feedback_path, self.data_dir / "trace.json"]
        paths += list(self.manual_dir.glob("*.json")) + list(self.manual_dir.glob("*.png"))
        paths += list((self.data_dir / "screenshots").glob("*.png"))
        paths += list(self.plugin_dir.glob("*.py")) + list(self.plugin_dir.glob("*.json"))
        paths += list((self.plugin_dir / "fixtures").glob("*.txt"))
        result = []
        for path in sorted(paths):
            try:
                stat = path.stat()
                result.append((str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                continue
        return tuple(result)

    async def review_loop(self):
        previous, process = None, None
        try:
            while True:
                stamp = await asyncio.to_thread(self.source_stamp)
                ledger = await asyncio.to_thread(read_json, self.ledger_path, {})
                pending = isinstance(ledger, dict) and ledger.get("summary", {}).get("pending", 0) > 0
                if stamp != previous or pending:
                    self.review_state["state"] = "processing"
                    try:
                        process = await asyncio.create_subprocess_exec(
                            sys.executable, str(self.processor), "--data-dir", str(self.data_dir),
                            "--plugin-dir", str(self.plugin_dir), "--ledger", str(self.ledger_path),
                            "--feedback-file", str(self.feedback_path), "--once", "--batch-size", "16",
                            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                        if hasattr(os, "setpriority"):
                            try:
                                os.setpriority(os.PRIO_PROCESS, process.pid, 10)
                            except OSError:
                                pass
                        result = await asyncio.wait_for(process.wait(), timeout=120)
                        if result:
                            raise RuntimeError("review failed")
                        previous = stamp
                        self.review_state.update(state="idle", lastRun=time.time())
                    except asyncio.CancelledError:
                        raise
                    except (OSError, RuntimeError, asyncio.TimeoutError):
                        self.review_state["state"] = "error"
                    finally:
                        if process and process.returncode is None:
                            process.kill()
                            await process.wait()
                        process = None
                self.review_event.clear()
                latest = await asyncio.to_thread(read_json, self.ledger_path, {})
                remaining = latest.get("summary", {}).get("pending", 0) if isinstance(latest, dict) else 0
                delay = 2 if remaining > 0 and self.review_state["state"] != "error" else 30
                try:
                    await asyncio.wait_for(self.review_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

    def graph(self):
        raw = read_json(self.data_dir / "trace.json", {})
        if not isinstance(raw, dict):
            raw = {}
        nodes, edges, images, warnings = [], [], {}, []
        known = set()
        for item in raw.get("nodes", [])[:20000]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int) or isinstance(item["id"], bool):
                continue
            node_id = f"trace:{item['id']}"
            if node_id in known:
                continue
            screen = text(item.get("screen", "unknown"))
            node = {"id": node_id, "screen": screen, "label": screen, "image": None,
                    "source": "trace", "regions": [], "count": item.get("count", 0)}
            thumb = item.get("thumb")
            if isinstance(thumb, str) and THUMB.fullmatch(thumb):
                node["thumbnail"] = {"width": 12, "height": 26, "pixels": thumb}
            nodes.append(node)
            known.add(node_id)
        for index, item in enumerate(raw.get("edges", [])[:100000]):
            if not isinstance(item, dict):
                continue
            source, target = f"trace:{item.get('from')}", f"trace:{item.get('to')}"
            start = point(item.get("x"), item.get("y"))
            kind = item.get("kind", "tap")
            if source not in known or target not in known or not start or kind not in KINDS:
                continue
            edge = {"id": f"trace-edge:{index}", "from": source, "to": target, "kind": kind,
                    "start": start, "count": item.get("count", 1), "source": "trace", "status": "recorded"}
            end = point(item.get("x2"), item.get("y2"))
            if end:
                edge["end"] = end
            edges.append(edge)
        manual_count = 0
        for path in sorted(self.manual_dir.glob("*.json")):
            if not CAPTURE.fullmatch(path.stem):
                continue
            item = read_json(path, None)
            if not isinstance(item, dict) or item.get("id") != path.stem:
                continue
            capture_id = path.stem
            manual_count += 1
            annotation = item.get("kind", "unknown")
            annotation = annotation if annotation in ANNOTATIONS else "unknown"
            status = item.get("capture_status", "unknown")
            status = status if status in {"complete", "cancelled", "error", "armed", "pending"} else "unknown"
            sides = {}
            for side in ("before", "after"):
                image = safe_image(self.manual_dir, capture_id, side)
                # A source screen can still be reviewed when its image is missing.
                if side == "after" and not image and side not in item:
                    continue
                node_id = f"manual:{capture_id}:{side}"
                screen = text(item.get(side, "unknown"))
                node = {"id": node_id, "screen": screen, "label": screen, "source": "manual",
                        "image": f"/api/image/{node_id}" if image else None, "regions": [],
                        "captureId": capture_id, "side": side, "annotation": annotation, "status": status}
                if image:
                    images[node_id] = image
                expected = item.get("expected_screen")
                if isinstance(expected, str):
                    node["expectedScreen"] = text(expected)
                scan = item.get(f"{side}_scan")
                if isinstance(scan, dict):
                    node["scan"] = {"screen": text(scan.get("screen", "unknown")),
                                    "overlays": [text(v) for v in scan.get("overlays", []) if isinstance(v, str)]}
                    if isinstance(scan.get("plain"), bool):
                        node["scan"]["plain"] = scan["plain"]
                rect = item.get("rect")
                if side == "before" and isinstance(rect, list) and len(rect) == 4:
                    a, b = point(*rect[:2]), point(*rect[2:])
                    if a and b and a["x"] < b["x"] and a["y"] < b["y"]:
                        node["regions"].append({"id": f"region:{capture_id}", "kind": "detection" if annotation == "scannable" else annotation,
                                                "rect": [a["x"], a["y"], b["x"], b["y"]],
                                                "label": annotation, "source": "recorded"})
                nodes.append(node)
                known.add(node_id)
                sides[side] = node_id
            tap = item.get("tap")
            if (annotation in {"navigation", "vertical", "horizontal", "draggable"}
                    and isinstance(tap, dict) and "before" in sides and "after" in sides):
                start = point(tap.get("x"), tap.get("y"))
                kind = tap.get("kind", "tap")
                if start and kind in KINDS:
                    edge = {"id": f"manual-edge:{capture_id}", "from": sides["before"], "to": sides["after"],
                            "kind": kind, "start": start, "source": "manual", "annotation": annotation, "annotationKind": annotation,
                            "status": status, "stable": item.get("after_stable") is True, "count": 1}
                    end = tap.get("end")
                    end = point(end.get("x"), end.get("y")) if isinstance(end, dict) else None
                    if end:
                        edge["end"] = end
                    edges.append(edge)
        for path in sorted((self.data_dir / "screenshots").glob("*.png")):
            if not STEM.fullmatch(path.stem) or path.is_symlink() or path.resolve().parent != (self.data_dir / "screenshots").resolve():
                continue
            node_id = f"example:{path.stem}"
            nodes.append({"id": node_id, "screen": path.stem, "label": path.stem, "source": "example",
                          "image": f"/api/image/{node_id}", "regions": [], "archivedLabel": path.stem})
            known.add(node_id)
            images[node_id] = path
        self.add_review(nodes, edges)
        configured_nodes, configured_edges = self.add_configured(nodes, edges)
        self.apply_zones(nodes, edges)
        self.images = images
        if any(node["source"] == "trace" for node in nodes):
            warnings.append("Passive trace nodes contain recorded 12×26 signatures, not full screenshots.")
        missing = sum(node["source"] == "manual" and node["image"] is None for node in nodes)
        if missing:
            warnings.append(f"{missing} manual evidence frame(s) have no stored screenshot.")
        if configured_edges:
            warnings.append("Configured routes come from the declared navigation catalogue; they are not observed transitions and remain to verify.")
        ledger = read_json(self.ledger_path, {}) if self.ledger_path else {}
        summary = ledger.get("summary", {}) if isinstance(ledger, dict) else {}
        summary = {key: value for key, value in summary.items() if isinstance(value, int) and not isinstance(value, bool)}
        return {"version": 1, "nodes": nodes, "edges": edges, "warnings": warnings,
                "stats": {"traceNodes": sum(node["source"] == "trace" for node in nodes),
                          "manualRecords": manual_count, "exampleImages": sum(node["source"] == "example" for node in nodes),
                          "images": len(images), "edges": len(edges), "configuredNodes": configured_nodes,
                          "configuredEdges": configured_edges},
                "feedback": self.feedback(), "review": {**self.review_state, "summary": summary}}

    def apply_zones(self, nodes, edges):
        shared = self.zones.read_annotations(self.data_dir, self.known_screens())
        pending = self.zones.read()
        for node in nodes:
            for region in node["regions"]:
                region["user"] = region.get("source") in {"recorded", "reviewed_user_evidence", "user_recorded_unverified"}
                region.setdefault("conditional", False)
                region.setdefault("zoneId", "manual:" + node["captureId"] if region["user"] and node.get("captureId")
                                  else region["id"])
            for zone in shared:
                if zone["screen"] != node["screen"]:
                    continue
                if node.get("review", {}).get("status") != "processed" and node["id"] != zone.get("nodeId"):
                    continue
                if not any(region["id"] == zone["id"] or region.get("zoneId") == zone.get("zoneId", zone["id"])
                           for region in node["regions"]):
                    node["regions"].append(dict(zone))
            for proposal in pending:
                if proposal["screen"] != node["screen"] or proposal.get("scope") == "node" and proposal["nodeId"] != node["id"]:
                    continue
                if proposal["operation"] == "add":
                    if not any(region.get("zoneId", region["id"]) == proposal["zoneId"] for region in node["regions"]):
                        node["regions"].append({**proposal, "id": proposal["zoneId"], "user": True, "source": "user_feedback", "proposal": "add"})
                    continue
                matched = False
                for region in node["regions"]:
                    aliases = {region["id"], region.get("zoneId", region["id"])}
                    if region["id"].startswith("policy:"):
                        aliases.add("policy:" + node["screen"] + ":" + region["id"][7:])
                    if proposal["zoneId"] in aliases or region["kind"] == proposal["kind"] and max(abs(a-b) for a,b in zip(region["rect"], proposal["rect"])) <= .003:
                        region.update(removedProposal=True, proposal="remove", pending=True)
                        matched = True
                if not matched:
                    node["regions"].append({**proposal, "id": proposal["zoneId"], "user": True,
                                            "source": "removal_proposal", "removedProposal": True, "proposal": "remove"})
        by_id = {node["id"]: node for node in nodes}
        for edge in edges:
            if any(proposal["operation"] == "remove" and proposal["zoneId"] == "edge:" + edge["id"]
                   and proposal["screen"] == by_id[edge["from"]]["screen"] for proposal in pending):
                edge["removedProposal"] = True

    def add_configured(self, nodes, edges):
        """Expose the existing declared graph as an explicitly separate layer.
        Representative images are real archived frames; configured routes do
        not assert those frames were observed consecutively or validate input.
        """
        registry = read_json(self.plugin_dir / "screen_registry.json", {})
        navigation = read_json(self.plugin_dir / "navigation.json", {})
        manifest = read_json(self.data_dir / "screenshots" / "manifest.json", {})
        manifest = manifest if isinstance(manifest, dict) else {}
        by_id = {node["id"]: node for node in nodes}
        declared = navigation.get("screens", {})
        screens = set(declared) | set(registry.get("screens", {}))
        created, edge_count = 0, 0
        for screen in sorted(screens):
            if not STEM.fullmatch(screen):
                continue
            spec = registry.get("screens", {}).get(screen, {})
            named = declared.get(screen, {})
            representative = None
            filename = spec.get("example")
            if isinstance(filename, str) and filename.startswith("screenshots/"):
                filename = filename[len("screenshots/"):]
            else:
                archive = manifest.get(screen, {})
                filename = archive.get("file") if isinstance(archive, dict) else None
            if isinstance(filename, str) and filename.endswith(".png") and STEM.fullmatch(filename[:-4]):
                representative = by_id.get(f"example:{filename[:-4]}")
            if representative is None:
                representative = next((node for node in nodes if node.get("image") and node.get("source") in {"example", "manual"}
                                       and node.get("review", {}).get("status") == "processed" and node["screen"] == screen), None)
            verified = bool(representative and representative.get("review", {}).get("status") == "processed"
                            and representative["screen"] == screen)
            node = {"id": f"screen:{screen}", "screen": screen,
                    "label": text(spec.get("label", named.get("name", screen))),
                    "image": representative.get("image") if representative else None, "source": "configured",
                    "status": "configured" if verified else "configured_unverified", "regions": [],
                    "review": {"status": "processed" if verified else "ambiguous",
                               "reason": "current_reader_confirms_representative" if verified else "configured_screen_identity_to_verify"},
                    "battleViewport": {"size": "unknown", "rect": None, "calibrated": False, "shaded": None}}
            if representative:
                node["representativeNodeId"] = representative["id"]
                node["regions"] = [dict(region) for region in representative.get("regions", [])]
                node["scan"] = dict(representative.get("scan", {}))
                if verified:
                    node["battleViewport"] = dict(representative["battleViewport"])
            if screen == "battle" and not (verified and node.get("scan", {}).get("plain") is True):
                node["label"] = text(named.get("name", "battle"))
            nodes.append(node)
            by_id[node["id"]] = node
            created += 1
        for source, spec in declared.items():
            for move in spec.get("moves", []):
                target = move.get("to")
                source_id, target_id = f"screen:{source}", f"screen:{target}"
                if (move.get("forbidden") or move.get("semantic_kind") != "navigation" or source == target
                        or source_id not in by_id or target_id not in by_id):
                    continue
                position = move.get("tap") or move.get("hold")
                area = move.get("area")
                if position is None and isinstance(area, list) and len(area) == 4 and point(*area[:2]) and point(*area[2:]):
                    position = [(area[0] + area[2]) / 2, (area[1] + area[3]) / 2]
                if not isinstance(position, list) or len(position) != 2:
                    continue
                start = point(*position)
                if start is None:
                    continue
                edges.append({"id": f"configured:{source}:{move.get('id')}", "from": source_id, "to": target_id,
                              "kind": "long" if move.get("hold") else "tap", "start": start,
                              "source": "configured", "status": "to_verify", "annotationKind": "navigation",
                              "label": text(move.get("label", move.get("id"))), "holdMs": move.get("hold_ms", 0),
                              "conditional": bool(move.get("precondition")),
                              "assumed": move.get("assumed") is True, "review": {
                                  "status": "ambiguous", "reason": "declared_route_not_an_observed_transition", "gestureAuthority": False}})
                edge_count += 1
        for screen, spec in registry.get("tree", {}).items():
            for index, scroll in enumerate(spec.get("scroll", [])):
                if not isinstance(scroll, dict) or scroll.get("measured") is not True:
                    continue
                gesture, captures = scroll.get("gesture"), scroll.get("captures")
                if not isinstance(gesture, list) or len(gesture) != 4 or not isinstance(captures, list):
                    continue
                start, end = point(*gesture[:2]), point(*gesture[2:])
                previous = f"screen:{screen}"
                if not start or not end or previous not in by_id:
                    continue
                direction = scroll.get("direction")
                if direction not in {"vertical", "horizontal"}:
                    continue
                for step, filename in enumerate(captures):
                    if not isinstance(filename, str) or not filename.endswith(".png") or not STEM.fullmatch(filename[:-4]):
                        break
                    target = f"example:{filename[:-4]}"
                    if target not in by_id or not by_id[target].get("image"):
                        break
                    edges.append({"id": f"configured-scroll:{screen}:{index}:{step}", "from": previous, "to": target,
                                  "kind": "swipe", "start": start, "end": end, "source": "configured", "status": "to_verify",
                                  "annotationKind": direction, "label": text(scroll.get("content", "Declared scroll")),
                                  "review": {"status": "ambiguous", "reason": "declared_ordered_capture_route_to_verify", "gestureAuthority": False}})
                    previous = target
                    edge_count += 1
        return created, edge_count

    def add_review(self, nodes, edges):
        ledger = read_json(self.ledger_path, {}) if self.ledger_path else {}
        ledger = ledger if isinstance(ledger, dict) else {}
        items = ledger.get("items", {})
        items = items if isinstance(items, dict) else {}
        edge_reviews = ledger.get("graph", {}).get("edge_reviews", {})
        for edge in edges:
            review = edge_reviews.get(edge["id"], {}) if edge["source"] == "trace" else items.get("manual:" + edge["id"].split(":", 1)[1], {})
            if isinstance(review, dict) and "status" in review:
                edge["review"] = {key: text(review[key]) for key in ("status", "reason", "duplicate_of") if key in review}
                edge["review"]["gestureAuthority"] = False
        by_id = {node["id"]: node for node in nodes}
        for node in nodes:
            base = ":".join(node["id"].split(":")[:2])
            item = items.get(base, {})
            if not isinstance(item, dict):
                continue
            review = item.get(node.get("side", "before"), {})
            if not isinstance(review, dict) or not review:
                continue
            node["review"] = {key: text(review[key]) for key in ("screen", "status", "reason", "sha256") if key in review}
            node["review"]["processingStatus"] = text(item.get("status", "unknown"))
            if review.get("status") == "processed" and isinstance(review.get("screen"), str):
                node["recordedScreen"] = node["screen"]
                node["screen"] = node["label"] = text(review["screen"])
                scan = review.get("scan")
                if isinstance(scan, dict):
                    node["scan"] = {"screen": text(scan.get("screen", "unknown")),
                                    "overlays": [text(v) for v in scan.get("overlays", []) if isinstance(v, str)],
                                    "plain": scan.get("plain") is True}
        for annotation in ledger.get("annotations", []):
            if not isinstance(annotation, dict) or annotation.get("review_status") != "processed":
                continue
            node = by_id.get(annotation.get("nodeId"))
            rect = annotation.get("rect")
            if node is None or not isinstance(rect, list) or len(rect) != 4:
                continue
            a, b = point(*rect[:2]), point(*rect[2:])
            if not a or not b:
                continue
            kind = annotation.get("kind", "detection")
            kind = "detection" if kind == "scannable" else kind
            region = {"id": text(annotation.get("id", "review")), "kind": kind,
                      "rect": [a["x"], a["y"], b["x"], b["y"]], "label": text(kind),
                      "source": "reviewed_user_evidence", "readerCalibrated": False}
            if not any(r["rect"] == region["rect"] and r["kind"] == kind for r in node["regions"]):
                node["regions"].append(region)
        registry = read_json(self.plugin_dir / "screen_registry.json", {})
        navigation = read_json(self.plugin_dir / "navigation.json", {})
        for node in nodes:
            node["battleViewport"] = {"size": "unknown", "rect": None, "calibrated": False, "shaded": None}
            if node["source"] == "trace" or node.get("review", {}).get("status") != "processed":
                continue
            screen = node["screen"]
            spec = registry.get("screens", {}).get(screen, {})
            metadata = spec.get("battle_viewport", registry.get("tree", {}).get(screen, {}).get("battle_viewport", {}))
            if isinstance(metadata, dict) and metadata.get("calibrated") is True:
                node["battleViewport"] = {key: metadata.get(key) for key in ("size", "rect", "calibrated", "shaded")}
            if screen == "battle" and node.get("scan", {}).get("plain") is True:
                node["label"] = text(spec.get("label", "Combat Interface"))
            if spec.get("status") != "registered":
                continue
            for anchor in spec.get("anchors", []):
                patch = anchor.get("patch")
                if not isinstance(patch, str) or not STEM.fullmatch(patch):
                    continue
                path = self.plugin_dir / "fixtures" / f"{patch}.txt"
                try:
                    if path.is_symlink():
                        continue
                    header = next(line for line in path.read_text().splitlines() if line and not line.startswith("#"))
                    width, height, x, y, w, h = map(int, header.split())
                    rect = [x / width, y / height, (x + w) / width, (y + h) / height]
                except (OSError, ValueError, StopIteration, ZeroDivisionError):
                    continue
                node["regions"].append({"id": f"landmark:{patch}", "kind": "detection", "rect": rect,
                                        "label": patch, "source": "calibrated_landmark"})
            dynamic = {"soul_weapon": {"equip", "unequip"}, "soul_weapon_engraving": {"lock", "piece", "drag_piece", "remove_piece"},
                       "soul_weapon_engraving_piece": {"padlock"}, "soul_weapon_engraving_preview": {"rotate", "confirm", "cancel", "move"},
                       "character_enhance": {"enhance_stat"}}
            for move in navigation.get("screens", {}).get(screen, {}).get("moves", []):
                if move.get("assumed") or move.get("id") in dynamic.get(screen, set()):
                    continue
                rect = move.get("area")
                tap = move.get("tap") or move.get("hold")
                if rect is None and isinstance(tap, list) and len(tap) == 2 and point(*tap):
                    rect = [max(0, tap[0] - .015), max(0, tap[1] - .015), min(1, tap[0] + .015), min(1, tap[1] + .015)]
                if not isinstance(rect, list) or len(rect) != 4 or not point(*rect[:2]) or not point(*rect[2:]):
                    continue
                node["regions"].append({"id": f"policy:{move.get('id')}", "rect": rect,
                                        "kind": "forbidden" if move.get("forbidden") else move.get("semantic_kind", "action"),
                                        "label": text(move.get("label", move.get("id"))), "source": "navigation_guard_envelope",
                                        "conditional": bool(move.get("precondition"))})

    def feedback(self):
        data = read_json(self.feedback_path, {"version": 1, "items": []})
        return data.get("items", []) if isinstance(data, dict) and isinstance(data.get("items"), list) else []

    def append_feedback(self, body, graph):
        if not isinstance(body, dict) or set(body) - {"nodeId", "edgeId", "text", "correctScreen"}:
            raise ValueError("Expected nodeId, optional edgeId/correctScreen, and text")
        if body.get("nodeId") not in {node["id"] for node in graph["nodes"]}:
            raise ValueError("Unknown nodeId")
        if "edgeId" in body and body["edgeId"] not in {edge["id"] for edge in graph["edges"]}:
            raise ValueError("Unknown edgeId")
        if "edgeId" in body and not any(edge["id"] == body["edgeId"] and body["nodeId"] in (edge["from"], edge["to"]) for edge in graph["edges"]):
            raise ValueError("Edge does not touch node")
        if not isinstance(body.get("text"), str) or not body["text"].strip() or len(body["text"]) > 4000:
            raise ValueError("Feedback text must contain 1–4000 characters")
        if "correctScreen" in body and (not isinstance(body["correctScreen"], str) or len(body["correctScreen"]) > 200):
            raise ValueError("correctScreen must contain at most 200 characters")
        entry = {"id": uuid.uuid4().hex, "at": time.time(), "nodeId": body["nodeId"], "text": body["text"].strip()}
        for key in ("edgeId", "correctScreen"):
            if key in body:
                entry[key] = body[key]
        if self.feedback_path.exists():
            old = read_json(self.feedback_path, None)
            if not isinstance(old, dict) or not isinstance(old.get("items"), list):
                raise OSError("Existing feedback is unreadable")
        items = self.feedback() + [entry]
        self.feedback_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temporary = tempfile.mkstemp(prefix=".review-feedback-", dir=self.feedback_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                os.fchmod(file.fileno(), 0o600)
                json.dump({"version": 1, "items": items}, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.feedback_path)
            directory = os.open(self.feedback_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.review_event.set()
        return entry


@web.middleware
async def private_headers(request, handler):
    if request.method == "POST":
        if request.content_type != "application/json":
            raise web.HTTPUnsupportedMediaType(text="JSON required")
        origin = request.headers.get("Origin")
        if origin and origin != f"{request.scheme}://{request.host}":
            raise web.HTTPForbidden(text="Cross-origin writes refused")
    response = await handler(request)
    response.headers.update({"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                             "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"})
    return response


def make_app(evidence):
    app = web.Application(middlewares=[private_headers], client_max_size=16 * 1024)

    async def reviewer_lifetime(app):
        if evidence.processor is None or evidence.ledger_path is None:
            yield
            return
        task = asyncio.create_task(evidence.review_loop(), name="passive-evidence-review")
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    app.cleanup_ctx.append(reviewer_lifetime)

    async def graph(request):
        async with evidence.lock:
            return web.json_response(await asyncio.to_thread(evidence.graph))

    async def image(request):
        node_id = request.match_info["node_id"]
        if node_id.startswith("example:") and STEM.fullmatch(node_id[8:]):
            path = evidence.data_dir / "screenshots" / f"{node_id[8:]}.png"
            if path.is_symlink() or not path.is_file() or path.resolve().parent != (evidence.data_dir / "screenshots").resolve():
                raise web.HTTPNotFound()
            return web.FileResponse(path, headers={"Content-Type": "image/png"})
        if not re.fullmatch(r"manual:[0-9a-f]{32}:(before|after)", node_id):
            raise web.HTTPNotFound()
        _, capture_id, side = node_id.split(":")
        path = safe_image(evidence.manual_dir, capture_id, side)
        metadata = read_json(evidence.manual_dir / f"{capture_id}.json", {})
        if path is None or not isinstance(metadata, dict) or metadata.get("id") != capture_id:
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Content-Type": "image/png"})

    async def overlays(request):
        async with evidence.lock:
            data = await asyncio.to_thread(evidence.graph)
        node = next((node for node in data["nodes"] if node["id"] == request.match_info["node_id"]), None)
        if node is None:
            raise web.HTTPNotFound()
        return web.json_response({"nodeId": node["id"], "regions": node["regions"]})

    async def feedback(request):
        if request.method == "GET":
            return web.json_response({"items": await asyncio.to_thread(evidence.feedback)})
        try:
            body = await request.json()
            async with evidence.lock:
                data = await asyncio.to_thread(evidence.graph)
                entry = await asyncio.to_thread(evidence.append_feedback, body, data)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid feedback or unknown evidence ID")
        except OSError:
            raise web.HTTPServiceUnavailable(text="Feedback could not be saved")
        return web.json_response(entry, status=201)

    async def zone_proposals(request):
        if request.method == "GET":
            try:
                items = await asyncio.to_thread(evidence.zones.read)
            except OSError:
                raise web.HTTPServiceUnavailable(text="Shared proposals are unavailable")
            return web.json_response({"items": items})
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected proposal object")
            async with evidence.lock:
                data = await asyncio.to_thread(evidence.graph)
                node = next((node for node in data["nodes"] if node["id"] == body.get("nodeId")), None)
                if node is None or body.get("screen") != node["screen"]:
                    raise ValueError("Proposal must identify its exact screen and evidence node")
                if body.get("operation") == "remove":
                    zone = next((region for region in node["regions"]
                                 if body.get("zoneId") in (region["id"], region.get("zoneId"))), None)
                    if zone is None:
                        edge = next((edge for edge in data["edges"] if "edge:" + edge["id"] == body.get("zoneId")
                                     and edge["from"] == node["id"]), None)
                        if edge:
                            x, y = edge["start"]["x"], edge["start"]["y"]
                            zone = {"kind": edge.get("annotationKind", "navigation"),
                                    "rect": [max(0, x - .025), max(0, y - .012), min(1, x + .025), min(1, y + .012)]}
                    if zone is None or body.get("kind") != zone["kind"]:
                        raise ValueError("Unknown removal target")
                    proposed = zone_feedback.rectangle(body.get("rect"))
                    if max(abs(a-b) for a,b in zip(proposed, zone["rect"])) > .003:
                        raise ValueError("Removal geometry differs from its target")
                item = await asyncio.to_thread(evidence.zones.append, body, evidence.known_screens())
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(text="Invalid zone proposal or evidence target")
        except OSError:
            raise web.HTTPServiceUnavailable(text="Zone proposal could not be saved")
        return web.json_response(item, status=201)

    async def revision(request):
        return web.json_response({"revision": await asyncio.to_thread(evidence.revision)})

    async def static(request):
        filename = request.match_info.get("filename", "index.html")
        if filename not in {"index.html", "style.css", "app.js", "model.js", "page_zone_style.js"}:
            raise web.HTTPNotFound()
        path = evidence.static_dir / filename
        if filename == "page_zone_style.js" and not path.is_file():
            path = evidence.plugin_dir / filename
        if path.is_symlink() or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    app.router.add_get("/api/graph", graph)
    app.router.add_get("/api/image/{node_id}", image)
    app.router.add_get("/api/overlays/{node_id}", overlays)
    app.router.add_get("/api/feedback", feedback)
    app.router.add_post("/api/feedback", feedback)
    app.router.add_get("/api/zone-feedback", zone_proposals)
    app.router.add_post("/api/zone-feedback", zone_proposals)
    app.router.add_get("/api/revision", revision)
    app.router.add_get("/", static)
    app.router.add_get("/{filename}", static)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="Private WireGuard or loopback address")
    parser.add_argument("--port", type=int, default=7890)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--feedback-file", type=Path, required=True)
    parser.add_argument("--static-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--plugin-dir", type=Path, default=Path(__file__).parent.parent)
    parser.add_argument("--process-reviews", action="store_true", help="Run bounded passive evidence review batches")
    args = parser.parse_args()
    try:
        address = ipaddress.ip_address(args.host)
    except ValueError:
        parser.error("--host must be an explicit private IP address")
    if address.is_unspecified or not address.is_private or address.is_multicast:
        parser.error("--host must be a private, non-wildcard address")
    evidence = Evidence(args.data_dir, args.feedback_file, args.static_dir, args.ledger, args.plugin_dir,
                        Path(__file__).with_name("evidence_review.py") if args.process_reviews else None)
    web.run_app(make_app(evidence), host=args.host, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
