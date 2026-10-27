"""Expose the navigation guard's read-only geometry to the debug overlay."""

import json
from pathlib import Path


def navigation_debug(ports, navigation, directory):
    registry = json.loads((Path(directory) / "screen_registry.json").read_text(encoding="utf-8"))
    graph = {"tolerance": navigation.TOLERANCE, "screens": {}}
    for screen, node in navigation.SCREENS.items():
        graph["screens"][screen] = {
            "name": node.get("name", screen),
            "moves": [{key: move[key] for key in
                       ("id", "kind", "tap", "hold", "area", "swipe", "forbidden", "precondition", "needs", "assumed")
                       if key in move} for move in node.get("moves", [])],
        }
    scrolls = {screen: {"scroll": node.get("scroll", [])}
               for screen, node in registry["tree"].items() if node.get("scroll")}

    async def handle(request):
        return ports.respond({"graph": graph, "registry": {"tree": scrolls}})

    return {"routes": [("GET", "/navigation-debug", handle)]}
