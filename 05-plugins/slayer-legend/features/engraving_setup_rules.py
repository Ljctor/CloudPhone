"""The soul weapon's engraving, as the Soul Weapon Engraving screen shows
it, against the loadout's variant: what is right, and the next move. Pure.

The screen (engraving_screen.py) gives the grid (each cell "piece",
"empty" or "none", and the pieces placed, as sets of cells) and the 8 cards
(shape, level, locked, placed, kind). A card draws its shape in its base
orientation whatever the piece's orientation in the grid; the slots keep
their card when a piece is taken out or placed.

- choose(): for each shape the variant needs, its highest-level cards; a
  Gold variant (Gold-maxed, Gold-balanced) takes the cards whose option is
  gold first (the coin icon), then by level; among equals a placed card,
  then the first.
- next_step(): the next move, from a fresh reading:
  ("lock", index): a card reads open (always first: a piece is never left
  unlocked); ("remove", cells): a placed piece that is not where the
  variant puts one, or, while a card placed is not a chosen one, a piece
  of its shape not taken out yet (which card holds which piece is not
  shown: the one taken out tells); ("place", index, cells): a chosen card
  not placed onto the variant's empty cells of its shape; ("done",) once
  the grid is the variant's with the chosen cards and all 8 read locked;
  ("fail", why).
- preview_step(): while a piece is previewed (dragged onto the grid): turn
  it, move it, confirm it when it lies on its cells and the check reads
  valid, or cancel.
- check(): what is still not right, for the one alert.
"""

# The shapes' stats as the cards' icons tell them are not the shapes': the
# icon is the piece's Additional Option (a coin: Monster Gold).
GOLD = "gold"
# At most this many moves (locks, removals, placements) in one setup, and
# this many preview moves (turns and shifts) for one placement.
MOST_STEPS = 24
MOST_PREVIEW = 8


def normalised(cells):
    rows = min(r for r, _ in cells)
    cols = min(c for _, c in cells)
    return sorted((r - rows, c - cols) for r, c in cells)


def turned(cells, quarter_turns):
    """The cells turned clockwise quarter_turns times, normalised (the
    preview's rotate button, eg7 to eg8, and engravings.json's rotation)."""
    out = list(cells)
    for _ in range(quarter_turns % 4):
        out = [(c, -r) for r, c in out]
    return normalised(out)


def shape_name(cells, shapes):
    """The shape name of a placed piece's cells, None when none fits."""
    for name, shape in shapes.items():
        base = normalised([tuple(cell) for cell in shape["cells"]])
        if any(turned(base, k) == normalised(cells) for k in range(4)):
            return name
    return None


def needed(variant):
    """{shape: count} of the variant's pieces."""
    out = {}
    for piece in variant["pieces"]:
        out[piece["shape"]] = out.get(piece["shape"], 0) + 1
    return out


def gold_variant(name):
    return str(name or "").startswith("Gold")


def choose(cards, variant, gold=False):
    """{shape: [card indices]}: the chosen cards of each needed shape (see
    the module's docstring); fewer when the inventory lacks some."""
    out = {}
    for shape, count in needed(variant).items():
        same = [card for card in cards if card["shape"] == shape and card["level"] is not None]
        same.sort(key=lambda card: (gold and card.get("kind") != GOLD, -card["level"], not card["placed"],
                                    card["index"]))
        out[shape] = [card["index"] for card in same[:count]]
    return out


def _numbers(indices):
    return ", ".join(f"#{index + 1}" for index in indices)


def _named(card):
    return f"{card['shape']} Lv.{card['level']} (#{card['index'] + 1})"


def _cells(piece):
    return sorted(tuple(cell) for cell in piece)


def next_step(grid, cards, variant, shapes, gold=False, probed=()):
    """The next move (see the module's docstring). probed: the cells of the
    pieces already taken out to find a card not chosen."""
    if grid is None:
        return ("fail", "grid unreadable")
    opened = [card["index"] for card in cards if card["locked"] is False]
    if opened:
        return ("lock", opened[0])
    unsure = [card["index"] for card in cards if card["locked"] is None]
    if unsure:
        return ("fail", f"padlock unreadable: {_numbers(unsure)}")
    unread = [card["index"] for card in cards if card["shape"] is None or card["level"] is None]
    if unread:
        return ("fail", f"piece unreadable: {_numbers(unread)}")
    chosen = choose(cards, variant, gold)
    for shape, count in needed(variant).items():
        if len(chosen.get(shape, [])) < count:
            return ("fail", f"{count - len(chosen.get(shape, []))} piece(s) {shape} missing in the inventory")
    targets = [_cells(piece["cells"]) for piece in variant["pieces"]]
    for piece in grid["pieces"]:
        if _cells(piece) not in targets:
            return ("remove", _cells(piece))
    by_index = {card["index"]: card for card in cards}
    wanted = {index for indices in chosen.values() for index in indices}
    placed = {card["index"] for card in cards if card["placed"]}
    missing = sorted(wanted - placed, key=lambda i: (-by_index[i]["level"], i))
    for index in missing:
        card = by_index[index]
        for piece in variant["pieces"]:
            cells = _cells(piece["cells"])
            if piece["shape"] == card["shape"] and all(grid["cells"].get(cell) == "empty" for cell in cells):
                return ("place", index, cells)
    extra = sorted(placed - wanted)
    if extra:
        shape = by_index[extra[0]]["shape"]
        done = [_cells(cells) for cells in probed]
        for piece in grid["pieces"]:
            if shape_name(piece, shapes) == shape and _cells(piece) not in done:
                return ("remove", _cells(piece))
        return ("fail", f"{_named(by_index[extra[0]])} placed but not found in the grid")
    if missing:
        return ("fail", f"no free place for {_named(by_index[missing[0]])}")
    have = sorted(_cells(piece) for piece in grid["pieces"])
    if have != sorted(targets):
        return ("fail", "the grid is not the variant's")
    return ("done",)


def fit(visible, hidden, cells):
    """Where the preview of cells (normalised) lies: the offsets (row, col)
    putting them over every visible new cube, the rest on hidden places
    (cubes already placed, or off the screen's reading). [offset, ...]"""
    if not visible:
        return []
    out = []
    anchor = min(visible)
    for r, c in cells:
        offset = (anchor[0] - r, anchor[1] - c)
        placed = {(a + offset[0], b + offset[1]) for a, b in cells}
        if visible <= placed and all(cell in hidden for cell in placed - visible) and offset not in out:
            out.append(offset)
    return out


def preview_step(before, now, valid, base, turns, target):
    """The next preview move: ("rotate",), ("move", from_cell, to_cell),
    ("confirm",) or ("cancel", why). before: the cubes before the drag
    (cells); now: the cubes read (cells); valid: the bar's check; base: the
    card's shape in its base orientation; turns: the rotate taps so far;
    target: the cells to fill."""
    visible = {cell for cell in now if cell not in before}
    hidden = set(before) | {(r, c) for r in range(-3, 9) for c in range(-3, 9) if not (-1 <= r <= 5 and -1 <= c <= 5)}
    shape = turned(base, turns)
    if not visible:
        return ("cancel", "preview not seen")
    if shape != normalised(target):
        # A turn needs no position (in place, eg7 to eg8).
        return ("rotate",) if turns < 3 else ("cancel", "no rotation matches")
    spots = fit(visible, hidden, shape)
    if not spots:
        return ("cancel", "preview not located")
    # Several fits (cubes hidden): the one hiding fewest under placed cubes
    # (off the reading rather than overlapping); the next look checks it.
    before = set(before)
    spots.sort(key=lambda o: sum((r + o[0], c + o[1]) in before for r, c in shape))
    offset = spots[0]
    cells = sorted((r + offset[0], c + offset[1]) for r, c in shape)
    want = sorted(tuple(cell) for cell in target)
    if cells != want:
        shift = (want[0][0] - cells[0][0], want[0][1] - cells[0][1])
        start = sorted(cell for cell in visible if 0 <= cell[0] <= 4 and 0 <= cell[1] <= 4) or sorted(visible)
        return ("move", start[0], (start[0][0] + shift[0], start[0][1] + shift[1]))
    if valid is True:
        return ("confirm",)
    return ("cancel", "spot read invalid" if valid is False else "check unreadable")


def check(grid, cards, variant, pattern, name, variant_name, gold=False):
    """What is still not right, in English ([] when ready): the grid's
    shape, every card locked, the pieces placed the variant's and the
    chosen cards."""
    if grid is None:
        return ["grid unreadable"]
    problems = []
    unlocked = [card["index"] for card in cards if card["locked"] is not True]
    if unlocked:
        problems.append(f"not read locked: {_numbers(unlocked)}")
    if {cell for cell, state in grid["cells"].items() if state != "none"} != {tuple(c) for c in pattern}:
        problems.append(f"the grid read is not {name}'s")
    if any(card["shape"] is None or card["level"] is None for card in cards):
        problems.append("a piece unreadable")
        return problems
    chosen = choose(cards, variant, gold)
    for shape, count in needed(variant).items():
        if len(chosen.get(shape, [])) < count:
            problems.append(f"{count - len(chosen.get(shape, []))} piece(s) {shape} missing")
    want = sorted(_cells(piece["cells"]) for piece in variant["pieces"])
    if sorted(_cells(piece) for piece in grid["pieces"]) != want:
        problems.append(f"the pieces placed are not {variant_name}'s")
    by_index = {card["index"]: card for card in cards}
    wanted = {index for indices in chosen.values() for index in indices}
    placed = {card["index"] for card in cards if card["placed"]}
    if placed - wanted:
        problems.append("placed, not the best: " + ", ".join(_named(by_index[i]) for i in sorted(placed - wanted)))
    if wanted - placed:
        problems.append("not placed: " + ", ".join(_named(by_index[i]) for i in sorted(wanted - placed)))
    return problems


def alert(name, variant_name, problems):
    """The one error alert of an engraving not set up."""
    return f"Engraving of {name} ({variant_name}) not ready: " + "; ".join(problems)
