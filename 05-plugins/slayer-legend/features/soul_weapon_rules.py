"""Equipping a farming mode's soul weapon on the Soul Weapon screen: what
to do next on what the screen shows. Pure.

The list on the left holds the weapons in the game's order (their ids in
engravings.json), one cell each; its cells show icons, no names, so a
weapon is known only once selected, by the name its card reads. Which way
the order runs down the list is learnt from two cells selected without a
scroll between them (their names' places in the order, their rows): then
the target's row is counted from the selected one. The direction learnt
is kept (state.json) for the next time.

view (soul_weapon.view): {open, selected (a name or None), owned (0, 1,
None), tag ("Equip", "Unequip", None), tag_box, tags, rows: [{top,
bottom, selected}], badge (True: the card shows it equipped, None: not
told)}.

plan() answers one of:
- ("done",): the target is selected and its tag reads Unequip (or the card
  shows it equipped);
- ("select", row): tap that cell (read as the target's, or one to learn
  from);
- ("scroll", "down" or "up"): the target's cell is past the list's end;
- ("equip",): the target is selected, owned (at least 1) and its tag
  reads Equip;
- ("fail", why): anything else, in French.
At most MOST_MOVES moves for the whole sequence, and it stops when a move
changes nothing (progressed).
"""

MOST_MOVES = 10
# Seconds between two looks while waiting for what a move should show,
# and how long at most.
POLL = 0.25
WAIT_MOST = 3.0


def order_names(table):
    """The weapons' names in the game's order (by id)."""
    return [entry["name"] for entry in sorted(table["weapons"], key=lambda entry: entry["id"])]


def shared(name, table):
    """Two weapons bear this name (Silence): the card cannot tell them apart."""
    return sum(1 for entry in table["weapons"] if entry["name"] == name) > 1


def place(name, names):
    """The weapon's place in the game's order, None if unknown or shared."""
    found = [i for i, n in enumerate(names) if n == name]
    return found[0] if len(found) == 1 else None


def selected_row(view):
    rows = [i for i, row in enumerate(view.get("rows") or []) if row["selected"]]
    return rows[0] if len(rows) == 1 else None


def fresh_memory(direction=None):
    """What a sequence learns as it goes: direction (+1: the order goes up
    down the list, -1: down; None: not known), the last anchor (place,
    row, scrolls) and the number of scrolls so far."""
    return {"direction": direction, "anchor": None, "scrolls": 0}


def observe(memory, view, names):
    """The memory once view is seen: a new anchor (the selected cell, its
    name read), and the direction when two anchors in one scroll position
    tell it (one place per row: else the list is not the game's order,
    "unknown")."""
    memory = dict(memory)
    row, name = selected_row(view), view.get("selected")
    where = place(name, names) if name else None
    if row is None or where is None:
        return memory
    anchor = (where, row, memory["scrolls"])
    before = memory["anchor"]
    if before and before[2] == anchor[2] and before[1] != row and memory["direction"] in (None, "unknown"):
        step = (where - before[0]) / (row - before[1])
        memory["direction"] = int(step) if step in (1, -1) else "unknown"
    memory["anchor"] = anchor
    return memory


def scrolled(memory):
    memory = dict(memory)
    memory["scrolls"] += 1
    return memory


def plan(view, target, memory, names):
    """The next move toward the target (a name of names, the game's order)
    being equipped."""
    if not view.get("open"):
        return ("fail", "écran Soul Weapon pas reconnu")
    goal = place(target, names)
    if goal is None:
        return ("fail", f"arme {target} inconnue ou de nom partagé (à équiper à la main)")
    rows = view.get("rows") or []
    row = selected_row(view)
    name = view.get("selected")
    if name == target:
        if view.get("tag") == "Unequip" or view.get("badge") is True:
            return ("done",)
        if row is None and not view.get("tags") and rows:
            # Its cell is out of view (the list opens scrolled away from
            # the selection): another cell read first, then back to it.
            return ("select", len(rows) // 2)
        if view.get("owned") == 0:
            return ("fail", f"{target} pas possédée (Owned : 0)")
        if view.get("owned") is None:
            return ("fail", f"{target} : « Owned » illisible")
        if view.get("tag") == "Equip" and view.get("tag_box"):
            return ("equip",)
        return ("fail", f"{target} : étiquette Equip / Unequip illisible")
    if not rows:
        return ("fail", "liste des armes illisible")
    if memory.get("direction") == "unknown":
        return ("fail", "la liste ne suit pas l’ordre des armes")
    if row is not None and name is None:
        return ("fail", "nom de l’arme sélectionnée illisible")
    if row is None:
        # The selection is out of view (or none): pick one cell to read.
        return ("select", len(rows) // 2)
    if memory.get("direction") is None:
        # Learn which way the order runs: the next cell.
        return ("select", row + 1 if row + 1 < len(rows) else row - 1)
    want = row + (goal - place(name, names)) * memory["direction"]
    if 0 <= want < len(rows):
        return ("select", want)
    return ("scroll", "down" if want >= len(rows) else "up")


def signature(view):
    """What a move should change."""
    return (view.get("selected"), selected_row(view), view.get("tag"),
            tuple(round(row["top"], 3) for row in view.get("rows") or []))


def progressed(before, after):
    return signature(before) != signature(after)


def tag_point(view):
    """The middle of the tag read."""
    left, top, right, bottom = view["tag_box"]
    return ((left + right) / 2, (top + bottom) / 2)


def seen(view, target):
    """What the navigation guard checks a Soul Weapon move against."""
    return {"selected": view.get("selected"), "target": target, "tag": view.get("tag"),
            "tag_box": view.get("tag_box"), "tags": list(view.get("tags") or [])}


def fresh_cache(cache, now, last_input, relaunched):
    """A reading of the weapon equipped ({id, at}) still holds: none of a
    relaunch (relaunched: its wall time) or a user input (last_input) since
    it was read."""
    if not cache:
        return False
    if relaunched is not None and relaunched >= cache["at"]:
        return False
    if last_input is not None and last_input >= cache["at"]:
        return False
    return cache["at"] <= now
