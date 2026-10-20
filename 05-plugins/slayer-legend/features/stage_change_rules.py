"""How to reach a stage in the Select Region pop-up, and when the
farming loadout is in place. Pure.

A look at the pop-up is a view: {popup, region (its index, None when the
banner does not read), rows: [{stage, move: the Move button's y or None
when the row is cut by the scroll}]} (stage_select.view). From a view,
plan() says the one next move; a sequence stops after MOST_MOVES, or as
soon as a move changed nothing (progressed).
"""

PER_REGION = 20
MOST_MOVES = 10
# The list's scroll swipe: down the list (rows go up) and back up.
SWIPE_DOWN = ((0.5, 0.75), (0.5, 0.45))
SWIPE_UP = ((0.5, 0.45), (0.5, 0.75))
SWIPE_MS = 600


def region_of(stage):
    return (stage - 1) // PER_REGION


def plan(view, target):
    """The next move towards farming target: ("move", y) taps the target's
    own Move button; ("arrow", "next_region" or "previous_region");
    ("scroll", "down" or "up"); ("fail", why in French)."""
    if not view["popup"]:
        return ("fail", "Select Region n’est pas ouvert")
    if view["region"] is None:
        return ("fail", "nom de la région illisible")
    wanted = region_of(target)
    if view["region"] != wanted:
        return ("arrow", "next_region" if view["region"] < wanted else "previous_region")
    rows = [row for row in view["rows"] if row["stage"] is not None]
    if any(region_of(row["stage"]) != wanted for row in rows):
        return ("fail", "les lignes ne sont pas de la région lue")
    for row in rows:
        if row["stage"] == target:
            if row["move"] is not None:
                return ("move", row["move"])
            # Cut by the edge of the list: scroll it into view.
            return ("scroll", "down" if row is rows[-1] else "up")
    if not rows:
        return ("fail", "aucune ligne de stage lue")
    if target > rows[-1]["stage"]:
        return ("scroll", "down")
    if target < rows[0]["stage"]:
        return ("scroll", "up")
    return ("fail", f"stage {target} absent de la liste")


def progressed(before, after):
    """Whether a move changed what the pop-up shows."""
    def seen(view):
        return (view["popup"], view["region"], tuple(row["stage"] for row in view["rows"]))
    return seen(before) != seen(after)


def supported(target, names):
    """Whether target is in a region the pop-up's banner names (names: the
    region names by index, stage_select.regions)."""
    region = region_of(target) if target and target > 0 else None
    return region is not None and region < len(names) and names[region] is not None
