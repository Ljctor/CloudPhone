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
        return ("cancel", t("aperçu pas vu"))
    if shape != normalised(target):
        # A turn needs no position (in place, eg7 to eg8).
        return ("rotate",) if turns < 3 else ("cancel", t("aucune rotation ne correspond"))
    spots = fit(visible, hidden, shape)
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
