"""The game's navigation graph (navigation.json) and the guard every action
of the plugin goes through.

Each screen lists every known way out of it, allowed or forbidden. Before
an action, the caller names the screen it recognised and the move it
wants; guard() refuses unless that move is an allowed move of that screen,
the point is where the move says, and no forbidden move of that screen
covers the point. Deterministic: no guessing, refused by default.
"""

import json
import os

with open(os.path.join(os.path.dirname(__file__), "navigation.json"), encoding="utf-8") as _f:
    GRAPH = json.load(_f)
SCREENS = GRAPH["screens"]
TOLERANCE = GRAPH["tolerance"]


def _covers(move, x, y):
    """Whether the move's place covers the point (a forbidden move with no
    place, an Android key, covers nothing)."""
    if "area" in move:
        left, top, right, bottom = move["area"]
        return left <= x <= right and top <= y <= bottom
    point = move.get("tap") or move.get("hold")
    if point:
        return abs(point[0] - x) <= TOLERANCE and abs(point[1] - y) <= TOLERANCE
    if "swipe" in move:
        x1, y1, x2, y2 = move["swipe"]
        return abs(x1 - x) <= TOLERANCE and min(y1, y2) - TOLERANCE <= y <= max(y1, y2) + TOLERANCE
    return False


def connections(screen):
    """Every move out of a screen: [{id, to, label, forbidden, reason, …}]."""
    return SCREENS.get(screen, {}).get("moves", [])


def guard(screen, move_id, x=None, y=None, kind="tap"):
    """None when the action may be done, else why not. x and y are where it
    lands (fractions); kind is tap, hold, swipe (x, y: its start) or key."""
    if screen not in SCREENS:
        return f"unknown screen {screen!r}"
    moves = connections(screen)
    move = next((m for m in moves if m["id"] == move_id), None)
    if move is None:
        return f"{screen}: no move {move_id!r}"
    if move.get("forbidden"):
        return f"{screen}/{move_id} is forbidden: {move.get('reason')}"
    expected = "key" if "key" in move else "swipe" if "swipe" in move else "hold" if "hold" in move else "tap"
    if kind != expected:
        return f"{screen}/{move_id} is a {expected}, not a {kind}"
    if kind == "key":
        return None
    if x is None or y is None or not _covers(move, x, y):
        return f"{screen}/{move_id}: ({x}, {y}) is not where this move is"
    for other in moves:
        if other.get("forbidden") and _covers(other, x, y):
            return f"{screen}/{move_id}: ({x:.3f}, {y:.3f}) is on forbidden {other['id']} ({other.get('reason')})"
    return None


def check():
    """Problems in the graph: moves to unknown screens, forbidden moves
    without a reason, allowed moves whose place touches a forbidden one."""
    problems = []
    for name, screen in SCREENS.items():
        for move in screen["moves"]:
            if move["to"] not in SCREENS:
                problems.append(f"{name}/{move['id']}: goes to unknown {move['to']!r}")
            if move.get("forbidden") and not move.get("reason"):
                problems.append(f"{name}/{move['id']}: forbidden without a reason")
            if move.get("forbidden") or "key" in move:
                continue
            point = move.get("tap") or move.get("hold") or (move["swipe"][:2] if "swipe" in move else None)
            if point and guard(name, move["id"], point[0], point[1],
                               "swipe" if "swipe" in move else "hold" if "hold" in move else "tap"):
                problems.append(f"{name}/{move['id']}: {guard(name, move['id'], *point)}")
    return problems
