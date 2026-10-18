"""Navigation trace: a graph of the game's screens (nodes) and of the user's
taps between them (edges), built from what the user does in the page.

Pure logic, no gateway: gateway.py takes the screenshots and calls this.

A screen is kept as a signature, never as a screenshot (a screenshot may
show the user's account): the name classify() gives it, and a grey
thumbnail of THUMB_WIDTH x THUMB_HEIGHT cells, each quantised to LEVELS
levels and written as one hex digit. Two signatures with the same name
whose thumbnails differ by less than MATCH (mean difference per cell,
0..1) are the same node.

Positions are fractions of the screen (0..1), from the top left.
"""

import json
import os

THUMB_WIDTH, THUMB_HEIGHT = 12, 26
LEVELS = 16
# Mean difference per cell (0..1) under which two thumbnails are the same
# screen. The battle screen moves (monsters, damage numbers): a guess, to
# tune once there are recorded graphs to look at.
MATCH = 0.06
MAX_NODES = 500
MAX_EDGES = 5000
# Taps on the same edge closer than this (fraction of the screen, on each
# axis) are the same button: one edge, counted.
TAP_MERGE = 0.03
KINDS = ("tap", "long", "swipe")

# Known buttons that must never be pressed by the plugin: Breakdown
# destroys items for good, Change re-rolls the engraving pieces the user
# chose, purchases spend real money or gems. The plugin never replays the
# recorded edges at all; this list is here for whatever later reads the
# graph to navigate: an edge from these screens near these points must not
# be followed. Points are where the buttons were seen (2026-10-18, 480x1040).
FORBIDDEN = [
    {"name": "Breakdown", "screen": "Soul Weapon card (Equipment → Weapon)", "point": (0.81, 0.841),
     "why": "destroys the item"},
    {"name": "Breakdown", "screen": "equipment cards (weapons, accessories)", "point": None,
     "why": "destroys the item; orange, bottom right of the card"},
    {"name": "Change x 8", "screen": "Soul Weapon Engraving", "point": (0.50, 0.955),
     "why": "re-rolls every unlocked engraving piece at random"},
    {"name": "buy / purchase", "screen": "Shop and every shop or offer pop-up", "point": None,
     "why": "spends money, gems or rare currencies"},
]


def thumbnail(shot):
    """The shot's grey thumbnail as a hex string, row by row, one digit per
    cell: the mean grey of a grid of sampled pixels in the cell."""
    width, height, pixels = shot
    cells = []
    for row in range(THUMB_HEIGHT):
        top, bottom = row * height // THUMB_HEIGHT, max(row * height // THUMB_HEIGHT + 1, (row + 1) * height // THUMB_HEIGHT)
        for column in range(THUMB_WIDTH):
            left = column * width // THUMB_WIDTH
            right = max(left + 1, (column + 1) * width // THUMB_WIDTH)
            # About 8 x 8 samples per cell: enough for a mean, cheap in Python.
            step_x, step_y = max(1, (right - left) // 8), max(1, (bottom - top) // 8)
            total = count = 0
            for y in range(top, bottom, step_y):
                for x in range(left, right, step_x):
                    i = (y * width + x) * 3
                    total += pixels[i] * 299 + pixels[i + 1] * 587 + pixels[i + 2] * 114
                    count += 1
            grey = total / (count * 1000) if count else 0
            cells.append(min(LEVELS - 1, int(grey * LEVELS / 256)))
    return "".join(f"{v:x}" for v in cells)


def distance(a, b):
    """Mean difference per cell of two thumbnails, 0 (same) to 1."""
    if len(a) != len(b) or not a:
        return 1.0
    return sum(abs(int(x, 16) - int(y, 16)) for x, y in zip(a, b)) / (len(a) * (LEVELS - 1))


class Graph:
    """Nodes {id, screen, thumb, first, count} and edges {from, to, x, y,
    kind, count, last} (+ x2, y2 for a swipe's end)."""

    def __init__(self, data=None):
        data = data or {}
        self.nodes = list(data.get("nodes", []))
        self.edges = list(data.get("edges", []))
        self.next_id = max((n["id"] for n in self.nodes), default=0) + 1
        self.last = data.get("last")

    def node_for(self, screen, thumb, now):
        """The node of this signature (count + 1), a new one if no node is
        close enough, or None when the graph is full."""
        best, best_distance = None, MATCH
        for node in self.nodes:
            if node["screen"] != screen:
                continue
            d = distance(node["thumb"], thumb)
            if d < best_distance:
                best, best_distance = node, d
        if best is None:
            if len(self.nodes) >= MAX_NODES:
                return None
            best = {"id": self.next_id, "screen": screen, "thumb": thumb, "first": now, "count": 0}
            self.next_id += 1
            self.nodes.append(best)
        best["count"] += 1
        return best["id"]

    def add_edge(self, source, target, tap, now):
        """Counts tap ({x, y, kind[, end: {x, y}]}) from node source to node
        target; True when recorded (False when the graph is full)."""
        end = tap.get("end") if tap["kind"] == "swipe" else None
        for edge in self.edges:
            if (edge["from"], edge["to"], edge["kind"]) != (source, target, tap["kind"]):
                continue
            if abs(edge["x"] - tap["x"]) > TAP_MERGE or abs(edge["y"] - tap["y"]) > TAP_MERGE:
                continue
            if end and (abs(edge.get("x2", 0) - end["x"]) > TAP_MERGE or abs(edge.get("y2", 0) - end["y"]) > TAP_MERGE):
                continue
            edge["count"] += 1
            edge["last"] = now
            break
        else:
            if len(self.edges) >= MAX_EDGES:
                return False
            edge = {"from": source, "to": target, "x": round(tap["x"], 3), "y": round(tap["y"], 3),
                    "kind": tap["kind"], "count": 1, "last": now}
            if end:
                edge["x2"], edge["y2"] = round(end["x"], 3), round(end["y"], 3)
            self.edges.append(edge)
        self.last = {"time": now, "from": source, "to": target, "kind": tap["kind"]}
        return True

    def record(self, before, after, tap, now):
        """before and after: (screen name, thumbnail). True when recorded."""
        source = self.node_for(*before, now)
        target = self.node_for(*after, now)
        if source is None or target is None:
            return False
        return self.add_edge(source, target, tap, now)

    def taps(self):
        return sum(edge["count"] for edge in self.edges)

    def public(self):
        """What GET /trace/graph returns."""
        return {
            "nodes": [{key: node[key] for key in ("id", "screen", "count", "thumb")} for node in self.nodes],
            "edges": [{key: edge[key] for key in ("from", "to", "x", "y", "kind", "count", "x2", "y2") if key in edge}
                      for edge in self.edges],
        }

    def to_json(self):
        return {"version": 1, "nodes": self.nodes, "edges": self.edges, "last": self.last}


def parse_tap(body):
    """{x, y, kind[, end: {x, y}]} checked, or None."""
    try:
        tap = {"x": float(body["x"]), "y": float(body["y"]), "kind": body.get("kind") or "tap"}
        if tap["kind"] == "swipe" and isinstance(body.get("end"), dict):
            tap["end"] = {"x": float(body["end"]["x"]), "y": float(body["end"]["y"])}
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    points = [tap] + ([tap["end"]] if "end" in tap else [])
    if tap["kind"] not in KINDS or not all(0 <= p["x"] <= 1 and 0 <= p["y"] <= 1 for p in points):
        return None
    return tap


def load(path):
    """The graph saved at path; an empty one when there is none. A file that
    cannot be read is kept aside as <path>.bad."""
    try:
        with open(path, encoding="utf-8") as f:
            return Graph(json.load(f))
    except FileNotFoundError:
        return Graph()
    except (OSError, ValueError, KeyError, TypeError):
        try:
            os.replace(path, f"{path}.bad")
        except OSError:
            pass
        return Graph()


def save(graph, path):
    """Writes the graph atomically (a crash leaves the old file), mode 600."""
    temporary = f"{path}.tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(graph.to_json(), f, separators=(",", ":"))
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
