"""Expose the navigation guard's read-only geometry to the debug overlay."""

import json
from pathlib import Path


def navigation_debug(ports, navigation, directory, screens=None):
    registry = json.loads((Path(directory) / "screen_registry.json").read_text(encoding="utf-8"))
    graph = {"tolerance": navigation.TOLERANCE, "screens": {}}
    for screen, node in navigation.SCREENS.items():
        graph["screens"][screen] = {
            "name": node.get("name", screen),
            "moves": [{key: move[key] for key in
                       ("id", "kind", "tap", "hold", "area", "swipe", "forbidden", "precondition", "needs", "assumed", "combat_return")
                       if key in move} for move in node.get("moves", [])],
        }
    tree = {screen: {"scroll": node.get("scroll", [])}
            for screen, node in registry["tree"].items() if node.get("scroll")}
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

    async def handle(request):
        return ports.respond({"graph": graph, "registry": {"tree": tree}})

    return {"routes": [("GET", "/navigation-debug", handle)]}
