"""The soul weapon's engraving, as the Soul Weapon Engraving screen shows
it, against the loadout's variant: what is right, and the next move. Pure.

The screen (engraving_screen.py) gives the grid (each cell "piece",
"empty" or "none", and the pieces placed, as sets of cells) and the 8 cards
(shape, level, locked, placed, kind). A card draws its shape in its base
orientation whatever the piece's orientation in the grid; the slots keep
their card when a piece is taken out or placed.

- choose(): for each shape the variant needs, its highest-level cards.
  At equal level a Gold variant prefers the gold option (coin icon),
  then a placed card, then the first. An option never outranks a level.
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
Every reason and problem is a status text ({template, params},
features/texts.py): a fixed French template, its English in templates.json.
"""

# The shapes' stats as the cards' icons tell them are not the shapes': the
# icon is the piece's Additional Option (a coin: Monster Gold).
GOLD = "gold"
# At most this many moves (locks, removals, placements) in one setup, and
# this many preview moves (turns and shifts) for one placement.
MOST_STEPS = 24
MOST_PREVIEW = 8
# The engraving switch "off" (the default, until a first run supervised
# with the user): no engraving gesture, this error instead.
NOT_SET_UP = "gravure pas mise en place : premier passage supervisé en attente"

# Pivots in normalised base-cell coordinates, inferred from reviewed real
# one-turn crops: eg_relax_preview_t-rotate-1-after and
# eg_relax_preview_l-{drop-pivot-after,rotate-1-before,rotate-1-after},
# eg_relax_preview_i-{drop-after,rotate-1-after}.
# test_engraving_geometry reconstructs these pivots from those observations.
# Other shapes stay unknown until their own real observations pass.
ROTATION_PIVOTS = {"T": (1, 0), "L": (1, 0), "I": (2, 0)}


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
        same.sort(key=lambda card: (-card["level"], gold and card.get("kind") != GOLD, not card["placed"],
                                    card["index"]))
        out[shape] = [card["index"] for card in same[:count]]
    return out


def t(template, **params):
    """A status text (features/texts.py)."""
    return {"template": template, "params": params}


def joined(texts, template="{first} ; {then}"):
    """Status texts one after the other, « a ; b » (or with the template
    "{first}, {then}", « a, b »); None for none."""
    if not texts:
        return None
    if len(texts) == 1:
        return texts[0]
    return t(template, first=texts[0], then=joined(texts[1:], template))


def _numbers(indices):
    return ", ".join(str(index + 1) for index in indices)


def _named(card):
    return t("{shape} Lv.{level} (n°{number})", shape=card["shape"], level=card["level"], number=card["index"] + 1)


def _cells(piece):
    return sorted(tuple(cell) for cell in piece)


def next_step(grid, cards, variant, shapes, gold=False, probed=()):
    """The next move (see the module's docstring). probed: the cells of the
    pieces already taken out to find a card not chosen."""
    if grid is None:
        return ("fail", t("grille illisible"))
    opened = [card["index"] for card in cards if card["locked"] is False]
    if opened:
        return ("lock", opened[0])
    unsure = [card["index"] for card in cards if card["locked"] is None]
    if unsure:
        return ("fail", t("cadenas illisible : n°{numbers}", numbers=_numbers(unsure)))
    unread = [card["index"] for card in cards if card["shape"] is None or card["level"] is None]
    if unread:
        return ("fail", t("pièce(s) illisible(s) : n°{numbers}", numbers=_numbers(unread)))
    chosen = choose(cards, variant, gold)
    for shape, count in needed(variant).items():
        if len(chosen.get(shape, [])) < count:
            return ("fail", t("il manque {count} pièce(s) {shape} dans l’inventaire",
                                count=count - len(chosen.get(shape, [])), shape=shape))
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
        return ("fail", t("{piece} posée mais pas trouvée dans la grille", piece=_named(by_index[extra[0]])))
    if missing:
        return ("fail", t("pas de place libre pour {piece}", piece=_named(by_index[missing[0]])))
    have = sorted(_cells(piece) for piece in grid["pieces"])
    if have != sorted(targets):
        return ("fail", t("la grille n’est pas celle de la variante"))
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


def preview_locations(before, now, base, turns):
    """Positions compatible with the complete known shape at this rotation."""
    before, now = set(before), set(now)
    visible = now - before
    hidden = before | {(r, c) for r in range(-3, 9) for c in range(-3, 9)
                       if not (-1 <= r <= 5 and -1 <= c <= 5)}
    return fit(visible, hidden, turned(base, turns)) if visible else []


def unique_preview_cells(before, now, base, turns):
    """The full preview cellset, or None when its position is ambiguous.

    Occupied cells can hide preview cubes. A plausible fit alone does not
    identify a piece's position and must not become a calibration sample.
    """
    spots = preview_locations(before, now, base, turns)
    if len(spots) != 1:
        return None
    row, col = spots[0]
    return tuple(sorted((r + row, c + col) for r, c in turned(base, turns)))


def clockwise_rotation_pivot(before_cells, after_cells):
    """Infer a clockwise turn's pivot in (row, col) cell-centre units.

    Both arguments must be complete, uniquely identified observations of
    the same piece, separated by exactly one rotate tap and no drag. The
    caller establishes that provenance; these cells only test geometry.
    Return None for missing cells or an incompatible orientation. A pivot
    can lie between cell centres; do not round it to a grabbed cube.
    """
    before = set(map(tuple, before_cells))
    after = set(map(tuple, after_cells))
    if not before or len(before) != len(after):
        return None
    rotated = {(c, -r) for r, c in before}
    if normalised(rotated) != normalised(after):
        return None
    source, dest = min(rotated), min(after)
    dr, dc = dest[0] - source[0], dest[1] - source[1]
    # after = R(before) + pivot - R(pivot), R(r, c) = (c, -r).
    return ((dr + dc) / 2, (dc - dr) / 2)


def initial_placement_cells(base, target, pivot):
    """Unrotated cells whose measured pivot turns the piece onto target.

    pivot is relative to the normalised base's cell centres, established
    from real clockwise observations. None keeps unknown shapes closed.
    Use the first matching clockwise rotation, as preview_step does for
    symmetric shapes; later rotations can move their apparent anchor.
    """
    if not base or not target or pivot is None:
        return None
    base = normalised(base)
    target = sorted(set(map(tuple, target)))
    if len(base) != len(target):
        return None
    rotated = [(r - pivot[0], c - pivot[1]) for r, c in base]
    for _ in range(4):
        around_pivot = [(r + pivot[0], c + pivot[1]) for r, c in rotated]
        if normalised(around_pivot) == normalised(target):
            source, dest = min(around_pivot), min(target)
            dr, dc = dest[0] - source[0], dest[1] - source[1]
            return tuple(sorted((r + dr, c + dc) for r, c in base))
        rotated = [(c, -r) for r, c in rotated]
    return None


def drag_response(before_cells, after_cells, start, end):
    """Describe one observed drag, with no assumed lift or grab offset.

    All points use (row, col) grid units, including fractional gesture
    endpoints. Complete uniquely identified piece cells must precede and
    follow this one drag without rotation. None means it cannot calibrate.
    ``residual`` is observed piece displacement minus finger displacement;
    it includes lift/snap, and quantised cell readings cannot resolve its
    continuous components. ``grab`` identifies the start relative to the
    piece's top-left cell; reuse requires the same grab and orientation.
    """
    before = set(map(tuple, before_cells))
    after = set(map(tuple, after_cells))
    if not before or len(before) != len(after) or normalised(before) != normalised(after):
        return None
    source, dest = min(before), min(after)
    piece_delta = tuple(dest[i] - source[i] for i in range(2))
    finger_delta = tuple(end[i] - start[i] for i in range(2))
    return {"shape": tuple(normalised(before)),
            "grab": tuple(start[i] - source[i] for i in range(2)),
            "piece_delta": piece_delta, "finger_delta": finger_delta,
            "residual": tuple(piece_delta[i] - finger_delta[i] for i in range(2))}


def landing_response(cells, endpoint):
    """Learn endpoint-to-piece offset from one complete observed landing.

    Unlike drag_response this does not assume that the game preserves the
    touched cube under the finger. The caller associates it with the card,
    orientation and gesture type (inventory drop or preview drag). Unknown
    or ambiguous observations must not be passed as complete cells.
    """
    cells = set(map(tuple, cells))
    if not cells:
        return None
    anchor = min(cells)
    return {"shape": tuple(normalised(cells)),
            "endpoint_offset": tuple(endpoint[i] - anchor[i] for i in range(2))}


def landing_endpoint(target, response):
    """Endpoint reproducing a measured landing at target, or None.

    No response means no calibrated endpoint. The caller must also match
    the card and gesture type; this function checks the exact orientation.
    """
    target = set(map(tuple, target))
    if not target or not response or tuple(normalised(target)) != response["shape"]:
        return None
    anchor = min(target)
    return tuple(anchor[i] + response["endpoint_offset"][i] for i in range(2))


def preview_step(before, now, valid, base, turns, target):
    """The next preview move: ("rotate",), ("move", from_cell, to_cell),
    ("confirm",) or ("cancel", why). before: the cubes before the drag
    (cells); now: the cubes read (cells); valid: the bar's check; base: the
    card's shape in its base orientation; turns: the rotate taps so far;
    target: the cells to fill."""
    visible = {cell for cell in now if cell not in before}
    shape = turned(base, turns)
    if not visible:
        return ("cancel", t("aperçu pas vu"))
    if shape != normalised(target):
        # A turn needs no position (in place, eg7 to eg8).
        return ("rotate",) if turns < 3 else ("cancel", t("aucune rotation ne correspond"))
    spots = preview_locations(before, now, base, turns)
    if not spots:
        return ("cancel", t("aperçu pas situé"))
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
    return ("cancel", t("emplacement lu invalide") if valid is False else t("coche illisible"))


def check(grid, cards, variant, pattern, name, variant_name, gold=False):
    """What is still not right, status texts ([] when ready): the grid's
    shape, every card locked, the pieces placed the variant's and the
    chosen cards."""
    if grid is None:
        return [t("grille illisible")]
    problems = []
    unlocked = [card["index"] for card in cards if card["locked"] is not True]
    if unlocked:
        problems.append(t("pas lue(s) verrouillée(s) : n°{numbers}", numbers=_numbers(unlocked)))
    if {cell for cell, state in grid["cells"].items() if state != "none"} != {tuple(c) for c in pattern}:
        problems.append(t("la grille lue n’a pas la forme de {name}", name=name))
    if any(card["shape"] is None or card["level"] is None for card in cards):
        problems.append(t("une pièce illisible"))
        return problems
    chosen = choose(cards, variant, gold)
    for shape, count in needed(variant).items():
        if len(chosen.get(shape, [])) < count:
            problems.append(t("il manque {count} pièce(s) {shape}", count=count - len(chosen.get(shape, [])), shape=shape))
    want = sorted(_cells(piece["cells"]) for piece in variant["pieces"])
    if sorted(_cells(piece) for piece in grid["pieces"]) != want:
        problems.append(t("les pièces posées ne sont pas celles de {variant}", variant=variant_name))
    by_index = {card["index"]: card for card in cards}
    wanted = {index for indices in chosen.values() for index in indices}
    placed = {card["index"] for card in cards if card["placed"]}
    if placed - wanted:
        problems.append(t("posée(s) sans être la meilleure : {pieces}",
                          pieces=joined([_named(by_index[i]) for i in sorted(placed - wanted)], "{first}, {then}")))
    if wanted - placed:
        problems.append(t("pas posée(s) : {pieces}",
                          pieces=joined([_named(by_index[i]) for i in sorted(wanted - placed)], "{first}, {then}")))
    return problems


def alert(name, variant_name, problems):
    """The one error alert of an engraving not set up: a status text, the
    sequence's failure (its English, the phone alert's)."""
    return t("Gravure de {name} ({variant}) pas prête : {problems}", name=name, variant=variant_name,
             problems=joined(problems))
