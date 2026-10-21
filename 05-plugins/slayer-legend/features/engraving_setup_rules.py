"""The soul weapon's engraving, as the Soul Weapon Engraving screen shows
it, against the loadout's variant: what is right, what to do. Pure.

The screen (engraving_screen.py) gives the grid (each cell "piece",
"empty" or "none", and the pieces placed as sets of cells) and the 8 cards
(shape, level, locked, placed, kind). A card draws its shape in its base
orientation whatever the piece's orientation in the grid (seen on every
card of the first capture).

check() answers {ok, problems, chosen, locks, moves}:
- chosen: {shape: [card indices]}, for each shape the variant needs the
  highest-level cards of that shape, a placed one first among equals (no
  move for nothing);
- locks: the cards whose padlock reads open (locked False): each one is
  tapped once, before any drag. A padlock read neither open nor closed
  (None) is never tapped: a misread would unlock it;
- problems: what is not right yet, in French;
- moves: the drags that would fix the grid, each {card, cells, rotation}:
  a chosen card not placed, onto a variant piece whose cells are all empty.
  Only pieces in the card's base orientation (how the game turns a piece is
  not learnt: ROTATION_LEARNED), never onto or off a placed piece (how a
  piece comes out of the grid is not learnt: REMOVAL_LEARNED). What no move
  can fix stays in problems, for the alert.
ok: no problem at all, every card locked, the grid the variant's with the
chosen cards: only then the setup is done.
"""

ROTATION_LEARNED = False
REMOVAL_LEARNED = False
# The shapes' stats as the cards' icons tell them (engravings.json's
# shapes: Line EXTRA_GOLD, the coin; L-Shape ATK, the sword).
KINDS = {"I": "gold", "L": "atk"}
# At most this many drags in one setup (a grid holds at most 6 pieces).
MOST_DRAGS = 8


def needed(variant):
    """{shape: count} of the variant's pieces."""
    out = {}
    for piece in variant["pieces"]:
        out[piece["shape"]] = out.get(piece["shape"], 0) + 1
    return out


def choose(cards, variant):
    """{shape: [card indices]}: the highest-level cards of each needed
    shape, as many as the variant needs (fewer when the inventory lacks
    some); among equal levels a placed card first, then the first card."""
    out = {}
    for shape, count in needed(variant).items():
        same = [card for card in cards if card["shape"] == shape and card["level"] is not None]
        same.sort(key=lambda card: (-card["level"], not card["placed"], card["index"]))
        out[shape] = [card["index"] for card in same[:count]]
    return out


def _numbers(indices):
    return ", ".join(str(index + 1) for index in indices)


def _named(card):
    return f"{card['shape']} Lv.{card['level']} (n°{card['index'] + 1})"


def check(grid, cards, variant, pattern, name, variant_name):
    """See the module's docstring. grid: engraving_screen.grid; cards:
    engraving_screen.cards; variant: {pieces: [{shape, rotation, cells}]};
    pattern: the weapon's active cells."""
    if grid is None:
        return {"ok": False, "problems": ["grille illisible"], "chosen": {}, "locks": [], "moves": []}
    problems = []
    unread = [card["index"] for card in cards if card["shape"] is None or card["level"] is None]
    if unread:
        problems.append(f"pièce(s) illisible(s) : n°{_numbers(unread)}")
    odd = [card["index"] for card in cards
           if card["shape"] in KINDS and card["kind"] is not None and card["kind"] != KINDS[card["shape"]]]
    if odd:
        problems.append(f"forme et icône en désaccord : n°{_numbers(odd)}")
    locks = [card["index"] for card in cards if card["locked"] is False]
    unsure = [card["index"] for card in cards if card["locked"] is None]
    if locks:
        problems.append(f"pas verrouillée(s) : n°{_numbers(locks)}")
    if unsure:
        problems.append(f"cadenas pas lu fermé : n°{_numbers(unsure)}")
    shape_cells = {cell for cell, state in grid["cells"].items() if state != "none"}
    if shape_cells != {tuple(cell) for cell in pattern}:
        problems.append(f"la grille lue n’a pas la forme de {name}")
    chosen = choose(cards, variant)
    for shape, count in needed(variant).items():
        if len(chosen.get(shape, [])) < count:
            problems.append(f"il manque {count - len(chosen.get(shape, []))} pièce(s) {shape}")
    want = sorted(sorted(tuple(cell) for cell in piece["cells"]) for piece in variant["pieces"])
    have = sorted(sorted(map(tuple, piece)) for piece in grid["pieces"])
    if have != want:
        problems.append(f"les pièces posées ne sont pas celles de {variant_name}")
    by_index = {card["index"]: card for card in cards}
    wanted = {index for indices in chosen.values() for index in indices}
    placed = {card["index"] for card in cards if card["placed"]}
    extra, missing = sorted(placed - wanted), sorted(wanted - placed)
    if extra:
        problems.append("posée(s) sans être du plus haut niveau : " + ", ".join(_named(by_index[i]) for i in extra)
                        + ("" if REMOVAL_LEARNED else " (retrait pas appris)"))
    moves = []
    if not unread and not odd:
        targets = [piece for piece in variant["pieces"]
                   if all(grid["cells"].get(tuple(cell)) == "empty" for cell in piece["cells"])]
        for index in sorted(missing, key=lambda i: (-by_index[i]["level"], i)):
            card = by_index[index]
            fits = [piece for piece in targets if piece["shape"] == card["shape"]]
            target = next((piece for piece in fits if piece.get("rotation", 0) == 0 or ROTATION_LEARNED), None)
            if target is None:
                why = "rotation pas apprise" if fits else "pas de place libre de sa forme"
                problems.append(f"à poser : {_named(card)} ({why})")
                continue
            targets.remove(target)
            moves.append({"card": index, "cells": sorted(tuple(cell) for cell in target["cells"]),
                          "rotation": target.get("rotation", 0)})
    elif missing:
        problems.append("à poser : " + ", ".join(_named(by_index[i]) for i in missing))
    if moves:
        problems.append("à poser : " + ", ".join(_named(by_index[move["card"]]) for move in moves))
    return {"ok": not problems, "problems": problems, "chosen": chosen, "locks": locks,
            "moves": moves[:MOST_DRAGS]}


def alert(name, variant_name, problems):
    """The one alert of an engraving not set up, in French."""
    return f"Gravure de {name} ({variant_name}) pas prête : " + " ; ".join(problems)


def drop_point(cells, cell_centre):
    """Where a card is dropped for a piece on cells: the middle of the
    cells' bounding box (cell_centre(row, col) gives a cell's middle)."""
    rows = [r for r, _ in cells]
    cols = [c for _, c in cells]
    top_left = cell_centre(min(rows), min(cols))
    bottom_right = cell_centre(max(rows), max(cols))
    return ((top_left[0] + bottom_right[0]) / 2, (top_left[1] + bottom_right[1]) / 2)


def dragged(before, after, move):
    """Whether a drag did what it should: the move's cells now read piece,
    they form one piece, and its card now reads placed (E); nothing else of
    the grid changed."""
    if before is None or after is None:
        return False
    cells = {tuple(cell) for cell in move["cells"]}
    if any(after["grid"]["cells"].get(cell) != "piece" for cell in cells):
        return False
    if sorted(cells) not in [sorted(map(tuple, piece)) for piece in after["grid"]["pieces"]]:
        return False
    if not after["cards"][move["card"]]["placed"]:
        return False
    return all(state == after["grid"]["cells"].get(cell)
               for cell, state in before["grid"]["cells"].items() if cell not in cells)
