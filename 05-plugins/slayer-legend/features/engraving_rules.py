"""Soul Weapon engraving: the weapons' patterns and the variants that fill
them (engravings.json), the pieces a variant needs and whether the user has
them, piece rotations, the gold layout and placement checks. Pure, stdlib
only; the one read is load()'s of engravings.json, which pattern_for does
when it is given no table.

A cell is [row, col], row 0 at the top and col 0 on the left. A shape is a
list of cells (engravings.json "shapes": L, J, T, O, I, S, Z, all of 4
cells). A rotation r turns a shape r quarter turns clockwise (r is 0 to 3);
a piece is never mirrored (L and J are two shapes). Whether the game turns
pieces is not confirmed (engravings.json "rotation": null). A placed piece
is (shape, rotation, anchor): the rotated shape moved so that its bounding
box's top-left cell is on anchor.

A variant is one complete filling of a weapon's pattern from the user's
sheet ("Atk", "Balanced", "Crit"), its pieces listed with their cells; it
is the plan, nothing is searched at run time. "Gold" is computed when
engravings.json is built: the most 1x4 bars (the I shape) the pattern
holds (gold()).
"""

import difflib
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engravings.json")
GOLD = "Gold"


class UnknownWeapon(KeyError):
    def __str__(self):
        return self.args[0]


def normal(cells):
    """The cells moved so their bounding box starts at [0, 0], sorted."""
    cells = [tuple(cell) for cell in cells]
    top = min(row for row, _ in cells)
    left = min(col for _, col in cells)
    return sorted([row - top, col - left] for row, col in cells)


def rotations(shape):
    """The shape turned 0, 1, 2 and 3 quarter turns clockwise, each
    normalised (some are equal: the square has one distinct rotation, the
    line and the squiggles two)."""
    turns = [normal(shape)]
    for _ in range(3):
        # A quarter turn clockwise: [row, col] goes to [col, -row].
        turns.append(normal([col, -row] for row, col in turns[-1]))
    return turns


def placed(shape, rotation, anchor):
    """The cells a piece covers: shape turned rotation times, its top-left on anchor."""
    return [[row + anchor[0], col + anchor[1]] for row, col in rotations(shape)[rotation % 4]]


def identify(cells, shapes):
    """(shape name, rotation) of a piece's cells: the shape and lowest
    rotation that give them, or None."""
    wanted = normal(cells)
    for name, shape in shapes.items():
        for rotation, turned in enumerate(rotations(shape["cells"] if isinstance(shape, dict) else shape)):
            if turned == wanted:
                return name, rotation
    return None


def solve(weapon_cells, pieces, rotate=True):
    """Some of pieces (shapes, in inventory order) covering every cell of
    weapon_cells exactly once: [{piece_index, rotation, anchor}] sorted by
    piece_index, or None. Exhaustive and deterministic: the first empty
    cell (top to bottom, then left to right) is covered first, by the first
    piece in order that fits there, with its lowest rotation (rotation 0
    only when rotate is False); a piece of a shape already tried on that
    cell is not tried again. Used when engravings.json is built (the
    tileable flags), never at run time."""
    target = {tuple(cell) for cell in weapon_cells}
    order = sorted(target)
    options = []
    for shape in pieces:
        seen, turns = set(), []
        for rotation, cells in enumerate(rotations(shape)[:4 if rotate else 1]):
            key = tuple(map(tuple, cells))
            if key not in seen:
                seen.add(key)
                turns.append((rotation, cells, min(map(tuple, cells))))
        options.append(turns)
    shapes = [tuple(map(tuple, normal(shape))) for shape in pieces]
    used = [False] * len(pieces)
    filled, chosen = set(), []

    def search():
        cell = next((c for c in order if c not in filled), None)
        if cell is None:
            return True
        tried = set()
        for index, turns in enumerate(options):
            if used[index] or shapes[index] in tried:
                continue
            tried.add(shapes[index])
            for rotation, cells, first in turns:
                anchor = (cell[0] - first[0], cell[1] - first[1])
                covered = [(row + anchor[0], col + anchor[1]) for row, col in cells]
                if all(c in target and c not in filled for c in covered):
                    used[index] = True
                    filled.update(covered)
                    chosen.append({"piece_index": index, "rotation": rotation, "anchor": list(anchor)})
                    if search():
                        return True
                    chosen.pop()
                    filled.difference_update(covered)
                    used[index] = False
        return False

    if not search():
        return None
    return sorted(chosen, key=lambda move: move["piece_index"])


def tiling(weapon_cells, shapes, rotate=True):
    """solve() with as many of each shape as the pattern could need: an
    exact fill from some multiset of the shapes, or None."""
    count = len(weapon_cells) // min(len(shape) for shape in shapes) if shapes else 0
    return solve(weapon_cells, [shape for shape in shapes for _ in range(count)], rotate)


def gold(weapon_cells, rotate=True):
    """The most 1x4 bars that fit in the pattern without overlap: {count,
    bars: [cells of each bar]}. Vertical bars are the I shape unturned;
    horizontal ones need rotation (rotate). Exact (every packing is looked
    at); of the packings with the most bars, the one whose sorted list of
    bars (each bar's cells sorted) is lexicographically smallest."""
    target = {tuple(cell) for cell in weapon_cells}
    bars = []
    for row, col in sorted(target):
        for step in ((1, 0), (0, 1)) if rotate else ((1, 0),):
            bar = [(row + step[0] * k, col + step[1] * k) for k in range(4)]
            if all(cell in target for cell in bar):
                bars.append(bar)
    bars.sort()
    best = {"count": 0, "bars": []}
    taken = set()
    chosen = []

    def search(start):
        if len(chosen) + (len(target) - len(taken)) // 4 < best["count"]:
            return
        key = sorted(chosen)
        if len(chosen) > best["count"] or (len(chosen) == best["count"] and key < best["bars"]):
            best.update(count=len(chosen), bars=key)
        for index in range(start, len(bars)):
            bar = bars[index]
            if not any(cell in taken for cell in bar):
                taken.update(bar)
                chosen.append(bar)
                search(index + 1)
                chosen.pop()
                taken.difference_update(bar)

    search(0)
    return {"count": best["count"], "bars": [[list(cell) for cell in bar] for bar in best["bars"]]}


def check(weapon_cells, placed_cells):
    """What a placement still lacks and what is wrong with it.
    placed_cells: one list of cells per piece placed. Answers {missing:
    pattern cells no piece covers, outside: covered cells not in the
    pattern, overlap: cells two pieces cover, complete: every pattern cell
    covered once and nothing else}; each list sorted, without repeats."""
    target = {tuple(cell) for cell in weapon_cells}
    count = {}
    for cells in placed_cells:
        for cell in {tuple(c) for c in cells}:
            count[cell] = count.get(cell, 0) + 1
    missing = sorted(target - count.keys())
    outside = sorted(count.keys() - target)
    overlap = sorted(cell for cell, n in count.items() if n > 1)
    return {"missing": [list(c) for c in missing], "outside": [list(c) for c in outside],
            "overlap": [list(c) for c in overlap], "complete": not (missing or outside or overlap)}


def variants(entry, rotate=True):
    """The weapon's variants by name: the sheet's, then "Gold" (with
    rotate, horizontal bars too). Each {name, pieces: [{shape, rotation,
    cells, colour}]}; colour is the sheet's label for the piece (None for
    Gold)."""
    out = {variant["name"]: variant for variant in entry.get("variants", [])}
    layout = (entry.get("gold") or {}).get("with_rotation" if rotate else "without_rotation")
    if layout:
        out[GOLD] = {"name": GOLD, "computed": "gold", "count": layout["count"],
                     "pieces": [{"shape": "I", "rotation": 0 if bar[0][1] == bar[1][1] else 1, "cells": bar,
                                 "colour": None} for bar in layout["bars"]]}
    return out


def needed(variant):
    """The pieces a variant needs: {shape: how many}, shapes sorted. A
    piece's rotation is where it goes, not what it is."""
    count = {}
    for piece in variant["pieces"]:
        count[piece["shape"]] = count.get(piece["shape"], 0) + 1
    return dict(sorted(count.items()))


def feasible(need, available):
    """(ok, missing): whether the pieces available ({shape: count}, read
    off the engraving screen) cover what is needed, and {shape: how many
    short} when not."""
    missing = {shape: count - available.get(shape, 0) for shape, count in sorted(need.items())
               if count > available.get(shape, 0)}
    return not missing, missing


def needs_rotation(variant):
    """Whether a variant turns any piece (then it cannot be placed if the
    game does not rotate pieces)."""
    return any(piece["rotation"] for piece in variant["pieces"])


def missing_alert(weapon, variant, missing, shapes):
    """The phone alert when pieces are missing: nothing is placed."""
    what = ", ".join(f"{count} × {shapes[shape]['name']} ({shape})" for shape, count in sorted(missing.items()))
    return f"Gravure de {weapon} ({variant}) : il manque {what}. Rien n’a été placé."


def load(path=DATA):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fold(text):
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


def pattern_for(name, table=None):
    """The weapon's entry of engravings.json by its name: exact, then
    ignoring case, spaces and hyphens, then by an alias (an older or the
    wiki's name). UnknownWeapon for a name it does not have, or one that
    two weapons share (then the error gives their ids). table: the file
    already read (read here when None). An entry may have no pattern:
    "grid" None (no engraving)."""
    weapons = (table if table is not None else load())["weapons"]
    for test in (lambda entry: entry["name"] == name,
                 lambda entry: fold(entry["name"]) == fold(name),
                 lambda entry: any(fold(alias) == fold(name) for alias in entry.get("aliases", []))):
        found = [entry for entry in weapons if test(entry)]
        if len(found) > 1:
            raise UnknownWeapon(f"Soul weapon name {name!r} is shared by ids "
                                f"{', '.join(str(entry['id']) for entry in found)}: ask by id")
        if found:
            return found[0]
    near = difflib.get_close_matches(str(name), [entry["name"] for entry in weapons], n=3)
    raise UnknownWeapon(f"Unknown soul weapon {name!r}"
                        + (f"; did you mean {', '.join(near)}?" if near else f" ({len(weapons)} weapons known)"))


def weapon_by_id(weapon_id, table):
    """The weapon's entry by its stable id, or None."""
    return next((entry for entry in table["weapons"] if entry["id"] == weapon_id), None)


MODES = ("mpw18", "mpw4")
PRESETS = ("I", "II", "III", "IV", "V")


def soul_weapon(chosen, table, rotate=True):
    """{id, variant} checked: (it, None) or (None, the error in French).
    The variant is one of the weapon's (variants())."""
    try:
        weapon_id, name = chosen["id"], chosen["variant"]
    except (KeyError, TypeError):
        return None, "Arme : attendu {id, variant}"
    if not isinstance(weapon_id, int) or isinstance(weapon_id, bool):
        return None, "id : un nombre entier"
    entry = weapon_by_id(weapon_id, table)
    if entry is None:
        return None, f"Arme inconnue : id {weapon_id}"
    if not entry.get("grid"):
        return None, f"{entry['name']} n’a pas de gravure"
    names = variants(entry, rotate)
    if name not in names:
        return None, f"Variante inconnue pour {entry['name']} : {name} (au choix : {', '.join(names)})"
    result = check(entry["cells"], [piece["cells"] for piece in names[name]["pieces"]])
    if result["outside"] or result["overlap"]:
        return None, f"La variante {name} de {entry['name']} sort de la grille ou se chevauche"
    return {"id": weapon_id, "variant": name}, None


def loadout(body, table, rotate=True):
    """POST /loadout's {mode, preset, soul_weapon: {id, variant}}: ((mode,
    {preset, soul_weapon}), None) or (None, the error in French). mode:
    mpw18 or mpw4; preset: the Battle settings preset, I to V; either of
    those two may be null (not set)."""
    if not isinstance(body, dict):
        return None, "Attendu : {mode, preset, soul_weapon: {id, variant}}"
    mode = body.get("mode")
    if mode not in MODES:
        return None, f"mode : {' ou '.join(MODES)}"
    preset = body.get("preset")
    if preset is not None and preset not in PRESETS:
        return None, f"Préréglage de combat : {', '.join(PRESETS)}"
    chosen = body.get("soul_weapon")
    if chosen is not None:
        chosen, error = soul_weapon(chosen, table, rotate)
        if error:
            return None, error
    return (mode, {"preset": preset, "soul_weapon": chosen}), None


def kept_loadouts(saved, table, rotate=True):
    """The loadouts state.json kept, each checked again (the data file may
    have changed): {mode: {preset, soul_weapon}}, what is no longer valid
    left out."""
    out = {mode: {"preset": None, "soul_weapon": None} for mode in MODES}
    for mode in MODES:
        part = saved.get(mode) if isinstance(saved, dict) else None
        if not isinstance(part, dict):
            continue
        asked, error = loadout(dict(part, mode=mode), table, rotate)
        if not error:
            out[mode] = asked[1]
        elif part.get("preset") in PRESETS:
            out[mode]["preset"] = part["preset"]
    return out
