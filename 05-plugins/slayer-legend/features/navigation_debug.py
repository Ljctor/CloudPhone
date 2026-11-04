"""Expose the navigation guard's read-only geometry to the debug overlay."""

import json
import math
import importlib.util
import asyncio
from pathlib import Path


def navigation_debug(ports, navigation, directory, screens=None, geometry=None):
    registry = json.loads((Path(directory) / "screen_registry.json").read_text(encoding="utf-8"))
    known_screens = set(navigation.SCREENS) | set(registry["tree"]) | set(registry["screens"])
    feedback_spec = importlib.util.spec_from_file_location("slayer_shared_zone_feedback", Path(directory) / "zone_feedback.py")
    feedback_module = importlib.util.module_from_spec(feedback_spec)
    feedback_spec.loader.exec_module(feedback_module)
    feedback = feedback_module.ZoneFeedback()
    data_path = getattr(ports, "data_path", None)
    data_directory = data_path("") if callable(data_path) else None
    graph = {"tolerance": navigation.TOLERANCE, "screens": {}}
    for screen, node in navigation.SCREENS.items():
        graph["screens"][screen] = {
            "name": registry["screens"].get(screen, {}).get("label", node.get("name", screen)),
            "moves": [{key: move[key] for key in
                       ("id", "kind", "tap", "hold", "area", "swipe", "forbidden", "precondition", "needs", "assumed", "combat_return", "semantic_kind")
                       if key in move} for move in node.get("moves", [])],
        }
    tree = {screen: {key: node[key] for key in ("name", "parent", "scroll", "battle_viewport") if key in node}
            for screen, node in registry["tree"].items()}
    for screen, node in registry["screens"].items():
        tree.setdefault(screen, {})["battle_viewport"] = node["battle_viewport"]
        if "label" in node:
            tree[screen]["name"] = node["label"]
    for screen in graph["screens"]:
        tree.setdefault(screen, {}).setdefault("battle_viewport", {
            "size": "unknown", "rect": None, "source": None, "calibrated": False, "shaded": None})
    # Guard envelopes are not UI button bounds. These positions depend on
    # fresh piece/tag readers and cannot be painted as broad grid/list boxes.
    dynamic = {"character_enhance": {"enhance_stat"}, "soul_weapon": {"equip", "unequip"},
               "soul_weapon_engraving": {"lock", "piece", "drag_piece", "remove_piece"},
               "soul_weapon_engraving_piece": {"padlock"},
               "soul_weapon_engraving_preview": {"rotate", "confirm", "cancel", "move"}}
    for screen, ids in dynamic.items():
        for move in graph["screens"].get(screen, {}).get("moves", []):
            if move["id"] in ids:
                move["debug_dynamic"] = True
    engraving = (geometry or {}).get("engraving")
    if engraving is not None:
        for move in graph["screens"].get("soul_weapon_engraving", {}).get("moves", []):
            if move["id"] == "lock":
                move["debug_rects"] = [[left + 52 / engraving.WIDTH, top + 1 / engraving.HEIGHT,
                                         left + 68 / engraving.WIDTH, top + 14 / engraving.HEIGHT]
                                        for left, top in (engraving.card_box(index) for index in range(8))]
            elif move["id"] in ("piece", "drag_piece"):
                # The calibrated drawing body, excluding the top-right lock.
                move["debug_rects"] = [[left + 14 / engraving.WIDTH, top + 15 / engraving.HEIGHT,
                                         left + 50 / engraving.WIDTH, top + 56 / engraving.HEIGHT]
                                        for left, top in (engraving.card_box(index) for index in range(8))]
    if screens is not None:
        for screen, node in registry["screens"].items():
            landmarks = []
            for index, anchor in enumerate(node.get("anchors", [])):
                if "patch" in anchor:
                    width, height, x, y, w, h, _ = screens.fixture(anchor["patch"])
                    bx, by, bw, bh = anchor.get("box", (0, 0, w, h))
                    rect = [(x + bx) / width, (y + by) / height,
                            (x + bx + bw) / width, (y + by + bh) / height]
                    label = anchor["patch"]
                elif "share" in anchor:
                    rect = list(getattr(screens, anchor["share"]))
                    label = anchor["share"]
                else:
                    continue  # A reader has no single calibrated rectangle.
                if not any(item["rect"] == rect for item in landmarks):
                    landmarks.append({"id": label, "rect": rect})
            if landmarks:
                tree.setdefault(screen, {})["landmarks"] = landmarks

    def dynamic_geometry(shot, captured_at):
        """Read-only, capture-bound rectangles; no new navigation authority."""
        zones = []
        identity = None
        weapon = (geometry or {}).get("soul_weapon")
        def point(move, kind, at):
            zones.append({"id": move, "move": move, "kind": kind, "forbidden": kind == "action",
                          "rect": [at[0] - 16 / 480, at[1] - 14 / 1040,
                                   at[0] + 16 / 480, at[1] + 14 / 1040]})
        if engraving is not None and engraving.title(shot):
            bar = engraving.bar(shot)
            if engraving.popup(shot):
                identity = "soul_weapon_engraving_piece"
                if engraving.popup_padlock(shot) is not None:
                    left, top, right, bottom = engraving.POPUP_LOCK_BOX
                    zones.append({"id": "padlock", "move": "padlock", "kind": "action", "forbidden": True,
                                  "rect": [left / engraving.WIDTH, top / engraving.HEIGHT,
                                           right / engraving.WIDTH, bottom / engraving.HEIGHT]})
            elif bar:
                identity = "soul_weapon_engraving_preview"
                for move in ("rotate", "confirm", "cancel"):
                    point(move, "tap" if move == "cancel" else "action", bar[move])
            else:
                identity = "soul_weapon_engraving"
                grid = engraving.grid(shot, 5)
                for cell, value in (grid or {}).get("cells", {}).items():
                    if value != "piece":
                        continue
                    centre = engraving.cell_centre(*cell)
                    zones.append({"id": f"remove_piece-{cell[0]}-{cell[1]}", "move": "remove_piece",
                                  "kind": "draggable", "conditional": True,
                                  "rect": [centre[0] - 12 / engraving.WIDTH, centre[1] - 12 / engraving.HEIGHT,
                                           centre[0] + 12 / engraving.WIDTH, centre[1] + 12 / engraving.HEIGHT]})
        elif weapon is not None and weapon.title(shot):
            identity = "soul_weapon"
            text, box = weapon.tag(shot)
            if text in ("Equip", "Unequip") and box:
                zones.append({"id": text.lower(), "move": text.lower(), "kind": "action",
                              "forbidden": True, "rect": list(box)})
        elif screens is not None and callable(getattr(screens, "character_enhance_actions", None)):
            paid = screens.character_enhance_actions(shot)
            if paid:
                identity = "character_enhance"
                zones.extend({**zone, "kind": "action"} for zone in paid)
        return {"screen": identity, "at": captured_at, "zones": zones}

    async def handle(request):
        if getattr(request, "query", {}).get("dynamic") == "1":
            if not await ports.focused():
                return ports.respond({"dynamic": None})
            shot = await ports.capture(max_age=.25)
            capture_time = getattr(ports, "capture_time", None)
            captured_at = capture_time(shot) if shot and callable(capture_time) else None
            if (not isinstance(captured_at, (int, float)) or isinstance(captured_at, bool)
                    or not math.isfinite(captured_at) or captured_at <= 0):
                return ports.respond({"dynamic": None})
            return ports.respond({"dynamic": await ports.analyse(dynamic_geometry, shot, captured_at)})
        return ports.respond({"graph": graph, "registry": {"tree": tree}})

    async def annotations(request):
        try:
            return ports.respond({"annotations": await asyncio.to_thread(feedback.read_annotations, data_directory, known_screens, tree=registry["tree"])
                                  if data_directory else [], "gestureAuthority": False})
        except OSError:
            return ports.respond({"annotations": [], "error": "Annotation storage unavailable"}, status=503)

    async def read_feedback(request):
        try:
            return ports.respond({"items": await asyncio.to_thread(feedback.read), "gestureAuthority": False})
        except OSError:
            return ports.respond({"error": "Feedback storage unavailable"}, status=503)

    async def write_feedback(request):
        try:
            body = await request.json()
            item = await asyncio.to_thread(feedback.append, body, known_screens=known_screens)
            return ports.respond({"item": item, "gestureAuthority": False}, status=201)
        except (ValueError, TypeError):
            return ports.respond({"error": "Invalid developer feedback proposal"}, status=400)
        except OSError:
            return ports.respond({"error": "Feedback storage unavailable"}, status=503)

    return {"routes": [("GET", "/navigation-debug", handle),
                       ("GET", "/navigation/annotations", annotations),
                       ("GET", "/navigation/zone-feedback", read_feedback),
                       ("POST", "/navigation/zone-feedback", write_feedback)]}
