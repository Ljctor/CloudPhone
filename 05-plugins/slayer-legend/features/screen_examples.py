"""Read-only catalogue and HTTP access to the private screen examples.

Only captures named by screen_registry.json are exposed. The web page and
gateway are available on WireGuard; captures stay outside the release and
the source tree, in the plugin's private data directory.
"""

import json
import re
from pathlib import Path

SAFE = re.compile(r"^[a-z][a-z0-9_]*$")
SCROLL_LABEL = "Défilement"


def examples(directory, data_directory, prefix):
    root = Path(directory)
    archive = Path(data_directory) / "screenshots" if data_directory else None
    registry = json.loads((root / "screen_registry.json").read_text(encoding="utf-8"))
    tree = registry["tree"]
    catalogue = {**registry.get("screens", {}), **tree}
    snapshots = {}
    for filename in ("screen_snapshots.json", "screen_snapshots_world.json"):
        snapshots.update(json.loads((root / filename).read_text(encoding="utf-8")))
    inventory_path = root / "screen_inventory.json"
    inventory = (json.loads(inventory_path.read_text(encoding="utf-8"))
                 if inventory_path.exists() else {})

    def name_of(path):
        name = Path(path).stem
        return name if SAFE.fullmatch(name) else None

    references = {}
    allowed = set()
    for screen, node in catalogue.items():
        found = []
        if node.get("example"):
            found.append((name_of(node["example"]), "Capture principale"))
        for index, path in enumerate(node.get("variants", []), 1):
            found.append((name_of(path), f"Variante {index}"))
        for section in node.get("scroll", []):
            for index, path in enumerate(section.get("captures", []), 1):
                found.append((name_of(path), f"{SCROLL_LABEL} {index}"))
        references[screen] = [(name, label) for name, label in found if name]
        allowed.update(name for name, _ in references[screen])

    def manifest():
        if archive is None:
            return {}
        try:
            data = json.loads((archive / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def describe(screen, entries):
        node = catalogue.get(screen, {})
        available = []
        for name, label in references.get(screen, []):
            entry = entries.get(name)
            if not isinstance(entry, dict) or entry.get("file") != name + ".png":
                continue
            if archive is None or not (archive / (name + ".png")).is_file():
                continue
            available.append({"url": f"{prefix}/examples/{name}", "captured": entry.get("captured"),
                              "label": label})
        details = list(snapshots.get(screen, []))
        observed_inventory = inventory.get(screen)
        if observed_inventory:
            if observed_inventory.get("rows"):
                for row in observed_inventory["rows"]:
                    entries_text = [f"Grade {grade}: +{enhancement}, {count}/5"
                                    for grade, enhancement, count in zip(
                                        row["grades"], row["enhancements"], row["counts"])]
                    details.append({"label": row["appearance"].capitalize(),
                                    "value": " · ".join(entries_text)})
                equipped = observed_inventory.get("equipped")
                if equipped:
                    details.append({"label": "Équipé", "value":
                                    f"{equipped['appearance']} +{equipped['enhancement']} · "
                                    f"{equipped['count']}/{equipped['capacity']}"})
            elif observed_inventory.get("ranks"):
                details.append({"label": "Promotions observées", "value":
                                " · ".join(f"{rank['name']} ({rank['status']})"
                                           for rank in observed_inventory["ranks"])})
            elif observed_inventory.get("status") == "never_read":
                details.append({"label": "Classes", "value": "never read"})
        for section in node.get("scroll", []):
            if section.get("measured") and section.get("captures"):
                start, end = section.get("start"), section.get("end")
                if start and end:
                    details.append({"label": "Défilement observé", "value": f"{start} → {end}"})
        return {"example": available[0] if available else None, "examples": available,
                "details": details, "inventory": observed_inventory,
                "observed": bool(available)}

    def enrich(answer):
        entries = manifest()
        for screen in answer["screens"]:
            screen.update(describe(screen["screen"], entries))
        return answer

    async def handle_example(request):
        from aiohttp import web

        name = request.match_info["name"]
        if not SAFE.fullmatch(name) or name not in allowed or archive is None:
            raise web.HTTPNotFound()
        entry = manifest().get(name)
        if not isinstance(entry, dict) or entry.get("file") != name + ".png":
            raise web.HTTPNotFound()
        path = archive / (name + ".png")
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "private, no-store",
                                               "Content-Type": "image/png"})

    return {"enrich": enrich, "routes": [("GET", "/examples/{name}", handle_example)]}
