"""The game's navigation graph (navigation.json) and the guard every action
of the plugin goes through.

Each screen lists every known way out of it, allowed or forbidden. Before
an action, the caller names the screen it recognised and the move it
wants; guard() refuses unless that move is an allowed move of that screen,
the point is where the move says, and no forbidden move of that screen
covers the point. Deterministic: no guessing, refused by default.

A move may need what the fresh capture showed (`needs`, checked against
the caller's seen): the Soul Weapon list's moves avoid its orange tags
(off_tags: seen["tags"], boxes), and its Equip needs the one tag read
"Equip" (tag), the point on it (on_tag: seen["tag_box"]) and the card's
name read as the target (selected_is_target: seen["selected"] ==
seen["target"]). A forbidden move with `on_tag` covers seen["tag_box"]
while seen["tag"] reads that text (Unequip): refused whatever the move.
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


def _inside(box, x, y):
    return bool(box) and box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _needs(screen, move, x, y, seen):
    """Why the move's needs are not met by seen (None: met)."""
    needs = move.get("needs")
    if not needs:
        return None
    where = f"{screen}/{move['id']}"
    if not isinstance(seen, dict):
        return f"{where} needs what the fresh capture shows (seen)"
    if needs.get("reduced_battle"):
        look = seen.get("look") or {}
        overlays = set(look.get("overlays") or [])
        if (look.get("screen") != "battle" or look.get("plain") is not False
                or not overlays.intersection(("panel", "equipment_weapon"))
                or overlays.difference(("panel", "equipment_weapon", "better_weapon_toast"))
                or seen.get("combat_visible") is not True):
            return f"{where} needs a fresh reduced battle with uncovered central combat"
    if "tag" in needs and seen.get("tag") != needs["tag"]:
        return f"{where} needs the tag read {needs['tag']!r}, not {seen.get('tag')!r}"
    if needs.get("selected_is_target") and (not seen.get("selected") or seen.get("selected") != seen.get("target")):
        return f"{where} needs the selected weapon read as the target ({seen.get('selected')!r}, {seen.get('target')!r})"
    if needs.get("on_tag") and not _inside(seen.get("tag_box"), x, y):
        return f"{where}: ({x}, {y}) is not on the tag read"
    if needs.get("off_tags") and any(_inside(box, x, y) for box in seen.get("tags") or []):
        return f"{where}: ({x}, {y}) is on a tag"
    return None


def guard(screen, move_id, x=None, y=None, kind="tap", verified=False, seen=None):
    """None when the action may be done, else why not. x and y are where it
    lands (fractions); kind is tap, hold, swipe (x, y: its start) or key.
    verified says the caller checked the move's precondition, if it has one;
    seen, what the fresh capture showed, for the moves that need it."""
    if screen not in SCREENS:
        return f"unknown screen {screen!r}"
    moves = connections(screen)
    move = next((m for m in moves if m["id"] == move_id), None)
    if move is None:
        return f"{screen}: no move {move_id!r}"
    if move.get("forbidden"):
        return f"{screen}/{move_id} is forbidden: {move.get('reason')}"
    # A move over an area is a tap unless it says (kind: a drag from it).
    expected = move.get("kind") or (
        "key" if "key" in move else "swipe" if "swipe" in move else "hold" if "hold" in move else "tap")
    if kind != expected:
        return f"{screen}/{move_id} is a {expected}, not a {kind}"
    if move.get("precondition") and not verified:
        return f"{screen}/{move_id} needs a check first: {move['precondition']}"
    if kind == "key":
        return None
    if x is None or y is None or not _covers(move, x, y):
        return f"{screen}/{move_id}: ({x}, {y}) is not where this move is"
    for other in moves:
        if other.get("forbidden") and _covers(other, x, y):
            return f"{screen}/{move_id}: ({x:.3f}, {y:.3f}) is on forbidden {other['id']} ({other.get('reason')})"
        if other.get("forbidden") and other.get("on_tag") and isinstance(seen, dict) \
                and seen.get("tag") == other["on_tag"] and _inside(seen.get("tag_box"), x, y):
            return (f"{screen}/{move_id}: ({x:.3f}, {y:.3f}) is on the tag read {other['on_tag']}: "
                    f"forbidden {other['id']} ({other.get('reason')})")
    return _needs(screen, move, x, y, seen)


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
            kind = "swipe" if "swipe" in move else "hold" if "hold" in move else "tap"
            # A move that needs a reading is checked with one that meets it.
            needs = move.get("needs") or {}
            seen = {"tags": [], "tag": needs.get("tag"), "selected": "target", "target": "target",
                    "tag_box": [point[0] - 0.01, point[1] - 0.01, point[0] + 0.01, point[1] + 0.01]} if point else None
            if point and needs.get("reduced_battle"):
                seen.update(look={"screen": "battle", "plain": False, "overlays": ["panel"]}, combat_visible=True)
            why = point and guard(name, move["id"], point[0], point[1], kind, verified=True, seen=seen)
            if why:
                problems.append(f"{name}/{move['id']}: {why}")
    return problems


def preconditions():
    """Every move the guard lets through only once its precondition was
    checked: [(screen, move id, precondition)]."""
    return [(name, move["id"], move["precondition"])
            for name, screen in SCREENS.items() for move in screen["moves"] if move.get("precondition")]
