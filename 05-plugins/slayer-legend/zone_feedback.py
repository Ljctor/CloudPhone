"""Shared advisory overlays. Pending edits never change navigation authority."""
import contextlib
import importlib.util
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

KINDS = {"navigation", "action", "forbidden", "detection", "progression_value", "resource_value", "screen_identifier", "vertical", "horizontal", "draggable"}
UNKNOWN = {"unknown", "other", "menu", "", "None"}
_identity_spec = importlib.util.spec_from_file_location("shared_evidence_identity", Path(__file__).with_name("evidence_review.py"))
_identity_module = importlib.util.module_from_spec(_identity_spec)
_identity_spec.loader.exec_module(_identity_module)


def rectangle(value):
    if (not isinstance(value, list) or len(value) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float))
            or not math.isfinite(v) or not 0 <= v <= 1 for v in value) or value[0] >= value[2] or value[1] >= value[3]):
        raise ValueError("Expected a normalized nonempty rectangle")
    return [float(v) for v in value]


def _json(path, default):
    try:
        if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            return default
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class ZoneFeedback:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.environ.get("CLOUDPHONE_REVIEW_FEEDBACK_DIR", "/var/lib/cloudphone-review"))
        self.path = self.directory / "zone-feedback.json"
        self.integration_path = self.directory / "annotation-integrations.json"

    @contextlib.contextmanager
    def locked(self, exclusive=False):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.directory / ".zone-feedback.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def read(self):
        if not self.path.exists():
            return []
        with self.locked():
            value = _json(self.path, None)
            if not isinstance(value, dict) or not isinstance(value.get("items"), list):
                raise OSError("Shared zone feedback is unreadable")
            return value["items"]

    def append(self, body, known_screens=None):
        if not isinstance(body, dict) or set(body) - {"nodeId", "zoneId", "screen", "operation", "kind", "rect", "label", "conditional", "forbidden"}:
            raise ValueError("Invalid zone proposal")
        operation, kind, screen, node = (body.get(key) for key in ("operation", "kind", "screen", "nodeId"))
        if not isinstance(operation, str) or not isinstance(kind, str) or operation not in {"add", "remove"} or kind not in KINDS:
            raise ValueError("Unsupported proposal operation or kind")
        if not isinstance(screen, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", screen):
            raise ValueError("Invalid screen")
        if not isinstance(node, str) or not re.fullmatch(r"(?:screen:[A-Za-z0-9_-]+|example:[A-Za-z0-9_-]+|manual:[0-9a-f]{32}:(?:before|after)|trace:[0-9]+)", node):
            raise ValueError("A specific evidence node is required")
        unknown = screen in UNKNOWN or known_screens is not None and screen not in known_screens
        if unknown and node.startswith("screen:"):
            raise ValueError("An anonymous screen proposal must identify its exact evidence node")
        zone = body.get("zoneId") or ("user:" + uuid.uuid4().hex if operation == "add" else None)
        if not isinstance(zone, str) or not re.fullmatch(r"[A-Za-z0-9:._-]{1,240}", zone):
            raise ValueError("Invalid zoneId")
        label = body.get("label", "")
        if not isinstance(label, str) or len(label) > 200:
            raise ValueError("Label is too long")
        if "conditional" in body and not isinstance(body["conditional"], bool):
            raise ValueError("conditional must be boolean")
        forbidden = body.get("forbidden", kind == "forbidden")
        if (not isinstance(forbidden, bool) or forbidden and kind not in {"action", "forbidden"}
                or kind == "forbidden" and not forbidden):
            raise ValueError("forbidden must be boolean and match the annotation role")
        item = {"id": uuid.uuid4().hex, "at": time.time(), "nodeId": node, "zoneId": zone, "screen": screen,
                "operation": operation, "kind": kind, "forbidden": forbidden, "rect": rectangle(body.get("rect")), "label": label,
                "pending": True, "status": "pending", "gestureAuthority": False,
                "conditional": body.get("conditional", False), "scope": "node" if unknown else "screen", "known": not unknown}
        with self.locked(exclusive=True):
            previous = _json(self.path, None) if self.path.exists() else {"version": 1, "items": []}
            if not isinstance(previous, dict) or not isinstance(previous.get("items"), list):
                raise OSError("Existing shared zone feedback is unreadable")
            def key(value):
                zone_id = value.get("zoneId", "")
                if zone_id.startswith("region:"):
                    zone_id = "manual:" + zone_id[7:]
                if zone_id.startswith("policy:") and zone_id.count(":") == 1:
                    zone_id = "policy:" + value.get("screen", "") + ":" + zone_id[7:]
                return (value.get("operation"), value.get("screen"), zone_id, value.get("kind"), value.get("forbidden", value.get("kind") == "forbidden"),
                        value.get("rect"), value.get("nodeId") if value.get("scope") == "node" else None)
            for existing in previous["items"]:
                if existing.get("pending") is True and key(existing) == key(item):
                    return existing
            if len(previous["items"]) >= 10000:
                raise OSError("Zone feedback capacity reached")
            fd, temporary = tempfile.mkstemp(prefix=".zone-feedback-", dir=self.directory)
            try:
                with os.fdopen(fd, "w") as output:
                    os.fchmod(output.fileno(), 0o600)
                    json.dump({"version": 1, "items": previous["items"] + [item]}, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
                directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return item

    @staticmethod
    def integration_geometry(annotation_id, screen, tree):
        """Only an installed, explicitly sourced display rectangle can match.

        The marker never creates a reader, navigation edge or gesture right.
        """
        for area in (tree or {}).get(screen, {}).get("scroll", []):
            source = area.get("visual_source") or {}
            linked = any(item.get("annotation") == annotation_id
                         and item.get("relation") == "same_scroll_viewport_intent"
                         and item.get("gesture_validated") is False
                         for item in source.get("intent_annotations", []) if isinstance(item, dict))
            if ((source.get("annotation") == annotation_id or linked) and source.get("role") == "display_bounds_only"
                    and source.get("gestureAuthority") is False and area.get("measured") is True):
                geometry = {"annotation": annotation_id, "screen": screen, "move": area["move"],
                            "rect": rectangle(area.get("rect")), "visual_source": source}
                digest = hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                return geometry, digest
        raise ValueError("No matching installed annotation geometry")

    def mark_integrated(self, annotation_id, screen, tree, release, verification_sha256):
        """Root's post-deployment attestation, not automatic annotation review.

        Call only after the deployed overlay was checked. Preserve the raw
        captures and review ledger; repeating this exact attestation is a no-op.
        """
        if (not isinstance(annotation_id, str) or not re.fullmatch(r"manual:[0-9a-f]{32}", annotation_id)
                or not isinstance(release, str) or not re.fullmatch(r"[0-9a-f]{7,40}", release)
                or not isinstance(verification_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", verification_sha256)):
            raise ValueError("Expected annotation id, deployed git release and verification SHA256")
        geometry, digest = self.integration_geometry(annotation_id, screen, tree)
        with self.locked(exclusive=True):
            current = _json(self.integration_path, {"version": 1, "items": {}})
            if not isinstance(current, dict) or not isinstance(current.get("items"), dict):
                raise OSError("Annotation integration state is unreadable")
            previous = current["items"].get(annotation_id)
            if isinstance(previous, dict) and previous.get("geometry_sha256") == digest and previous.get("release") == release:
                return previous
            item = {"annotation": annotation_id, "screen": screen, "move": geometry["move"],
                    "geometry_sha256": digest, "release": release, "verified_at": time.time(),
                    "verification_sha256": verification_sha256, "status": "integrated", "gestureAuthority": False}
            current["items"][annotation_id] = item
            fd, temporary = tempfile.mkstemp(prefix=".annotation-integrations-", dir=self.directory)
            try:
                with os.fdopen(fd, "w") as output:
                    os.fchmod(output.fileno(), 0o600)
                    json.dump(current, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.integration_path)
                directory = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return item

    def integrated_annotations(self, tree):
        state = _json(self.integration_path, {})
        items = state.get("items", {}) if isinstance(state, dict) else {}
        accepted = {}
        for key, item in (items.items() if isinstance(items, dict) else ()):
            if not isinstance(item, dict) or item.get("status") != "integrated" or item.get("gestureAuthority") is not False:
                continue
            try:
                _, digest = self.integration_geometry(key, item.get("screen"), tree)
            except (ValueError, TypeError):
                continue
            if item.get("geometry_sha256") == digest:
                accepted[key] = item
        return accepted

    def read_annotations(self, data_dir, known_screens=None, tree=None):
        data = Path(data_dir)
        ledger = _json(self.directory / "trace-review.json", {})
        ledger = ledger if isinstance(ledger, dict) else {}
        items, zones = ledger.get("items", {}), {}
        kinds = {"scannable": "detection"}
        def known(value):
            return isinstance(value, str) and value not in UNKNOWN and (known_screens is None or value in known_screens)
        for annotation in ledger.get("annotations", []):
            if not isinstance(annotation, dict) or annotation.get("review_status") != "processed" or not known(annotation.get("screen")):
                continue
            screen = annotation["screen"]
            item = items.get(annotation.get("id"), {}) if isinstance(items, dict) else {}
            scan = item.get("before", {}).get("scan") if isinstance(item, dict) else None
            if isinstance(scan, dict):
                screen = _identity_module.identity(scan, tree or {})
                if not known(screen):
                    continue
            try:
                rect = rectangle(annotation.get("rect"))
            except ValueError:
                continue
            kind = kinds.get(annotation.get("kind"), annotation.get("kind"))
            if kind not in KINDS:
                continue
            zone_id = annotation.get("id")
            if not isinstance(zone_id, str):
                continue
            zones[zone_id] = {"id": zone_id, "zoneId": zone_id, "screen": screen, "kind": kind,
                              "rect": rect, "nodeId": annotation.get("nodeId"), "source": "reviewed_user_evidence",
                              "user": True, "conditional": False, "forbidden": kind == "forbidden" or kind == "action" and annotation.get("forbidden") is True, "gestureAuthority": False}
        for path in sorted((data / "manual-clicks").glob("*.json")):
            if not re.fullmatch(r"[0-9a-f]{32}", path.stem):
                continue
            entry = _json(path, {})
            if not isinstance(entry, dict) or entry.get("capture_status") != "complete":
                continue
            kind = kinds.get(entry.get("kind"), entry.get("kind"))
            if kind not in KINDS:
                continue
            reviewed = items.get("manual:" + path.stem, {}) if isinstance(items, dict) else {}
            before = reviewed.get("before", {})
            scan = before.get("scan") if before.get("status") == "processed" else None
            if reviewed and before.get("status") != "processed":
                continue  # Historical misclassifications never become blanket overlays.
            if scan is None:
                if entry.get("at", 0) < max(time.time() - 300, ledger.get("updated_at", 0)):
                    continue
                scan = entry.get("before_scan", {})
            if not isinstance(scan, dict):
                continue
            screen = _identity_module.identity(scan, tree or {})
            if not known(screen):
                continue
            tap = entry.get("tap", {})
            rect = entry.get("rect")
            trajectory = None
            if kind in {"progression_value", "resource_value", "screen_identifier"} and rect is None:
                continue  # Value/identity declarations require an explicit rectangle.
            try:
                if kind in {"vertical", "horizontal", "draggable"} and isinstance(tap.get("end"), dict):
                    trajectory = [{"x": float(tap["x"]), "y": float(tap["y"])},
                                  {"x": float(tap["end"]["x"]), "y": float(tap["end"]["y"])}]
                if rect is None and trajectory:
                    rect = [min(p["x"] for p in trajectory), min(p["y"] for p in trajectory),
                            max(p["x"] for p in trajectory), max(p["y"] for p in trajectory)]
                    for axis in (0, 1):
                        if rect[axis] == rect[axis + 2]:
                            rect[axis], rect[axis + 2] = max(0, rect[axis] - .015), min(1, rect[axis + 2] + .015)
                if rect is None:
                    x, y = float(tap["x"]), float(tap["y"])
                    rect = [max(0, x - .015), max(0, y - .015), min(1, x + .015), min(1, y + .015)]
                rect = rectangle(rect)
            except (KeyError, TypeError, ValueError):
                continue
            zone_id = "manual:" + path.stem
            zone = {"id": zone_id, "zoneId": zone_id, "aliases": ["region:" + path.stem],
                    "nodeId": zone_id + ":before", "screen": screen, "kind": kind, "rect": rect,
                    "label": kind, "source": "reviewed_user_evidence" if reviewed else "user_recorded_unverified",
                    "user": True, "conditional": False, "forbidden": kind == "forbidden" or kind == "action" and entry.get("forbidden") is True, "gestureAuthority": False}
            if trajectory:
                zone["trajectory"] = trajectory
            zones[zone_id] = zone
        for item in self.read():
            if item.get("scope") == "node" or item.get("known") is False or not known(item.get("screen")):
                continue
            if item["operation"] == "add":
                zones[item["zoneId"]] = {**item, "id": item["zoneId"], "source": "user_feedback", "user": True, "proposal": "add"}
                continue
            matched = False
            anchored = any(zone["screen"] == item["screen"] and item["zoneId"] in [zone["id"], *zone.get("aliases", [])]
                           for zone in zones.values())
            for zone in zones.values():
                if zone["screen"] == item["screen"] and (item["zoneId"] in [zone["id"], *zone.get("aliases", [])]
                        or not anchored and zone["kind"] == item["kind"]
                        and zone.get("forbidden", zone["kind"] == "forbidden") == item.get("forbidden", item["kind"] == "forbidden") and max(abs(a - b) for a, b in zip(zone["rect"], item["rect"])) <= .003):
                    zone.update(proposal="remove", removedProposal=True, pending=True)
                    matched = True
            if not matched:
                zones["proposal:" + item["id"]] = {**item, "id": item["zoneId"], "source": "removal_proposal",
                                                    "proposal": "remove", "removedProposal": True, "user": True}
        integrations = self.integrated_annotations(tree)
        for zone_id, zone in list(zones.items()):
            if zone.get("proposal") == "remove" or zone.get("removedProposal"):
                continue  # An unresolved removal remains visible even after integration.
            item = integrations.get(zone_id) if isinstance(integrations, dict) else None
            if not isinstance(item, dict) or item.get("status") != "integrated":
                continue
            try:
                geometry, digest = self.integration_geometry(zone_id, zone["screen"], tree)
            except ValueError:
                continue
            source = geometry["visual_source"]
            intent_duplicate = any(link.get("annotation") == zone_id
                                   and link.get("relation") == "same_scroll_viewport_intent"
                                   and link.get("gesture_validated") is False
                                   for link in source.get("intent_annotations", []) if isinstance(link, dict))
            if (item.get("geometry_sha256") == digest and item.get("gestureAuthority") is False
                    and (zone["rect"] == geometry["rect"] or intent_duplicate)):
                del zones[zone_id]  # Only the duplicated shared overlay; raw evidence stays intact.
        return list(zones.values())
