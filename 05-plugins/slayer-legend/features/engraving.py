"""Soul Weapon engraving and the loadout of each farming mode: the
patterns of engravings.json, and per mode (mpw18, mpw4) the Battle
settings preset and the soul weapon with its engraving variant.

GET  /engravings                 {rotation, weapons: [{id, name, stage, grid, source, verified_in_game,
                                  wiki_check, variants}]}
GET  /engraving?id=N             the weapon's pattern, its variants with the pieces each needs
GET  /loadout                    {loadouts: {mpw18, mpw4}}, each {stage, preset, soul_weapon: {id, variant}}
POST /loadout                    {mode, stage, preset, soul_weapon: {id, variant}}: one mode's loadout;
                                 a field absent keeps its value, a null one clears it

Read-only for the game: nothing is equipped or placed yet; a later phase
compares the grid on the engraving screen with the pattern and reads the
pieces there first (engraving_rules.feasible, missing_alert). The rules
are in engraving_rules.py; the loadouts are kept in state.json
("loadouts"). They are the one place of the mpw18 and mpw4 stages: the
mode feature (POST /mode's stage18, stage4) and the watchdog read and set
them through api (loadout, stage, set_stage, adopt_stage).
"""


def engraving(ports, rules):
    table = rules.load()
    # Pieces are turned only once the game is known to turn them: until
    # then Gold has vertical bars only, and the sheet's variants that turn
    # pieces are listed but not placeable.
    rotate = rules.rotation_allowed(table)
    loadouts = rules.kept_loadouts(ports.store.saved.get("loadouts"), table, rotate)
    ports.store.register("loadouts", lambda: loadouts)

    def set_stage(mode, number):
        """The stage farmed in mode (mpw18, mpw4); None clears it."""
        if loadouts[mode]["stage"] != rules.stage_or_none(number):
            loadouts[mode]["stage"] = rules.stage_or_none(number)
            ports.store.save()

    def adopt_stage(mode, number):
        """A stage from an older state.json, kept only where none is set."""
        if loadouts[mode]["stage"] is None and rules.stage_or_none(number):
            set_stage(mode, number)

    api = {"loadout": lambda mode: dict(loadouts[mode]), "stage": lambda mode: loadouts[mode]["stage"],
           "set_stage": set_stage, "adopt_stage": adopt_stage}

    def summary(entry):
        return {key: entry.get(key) for key in ("id", "name", "stage", "grid", "source", "verified_in_game",
                                                "wiki_check")} | {
            "variants": list(rules.variants(entry, rotate)) if entry.get("grid") else []}

    def detail(entry):
        answer = {key: entry.get(key) for key in ("id", "name", "aliases", "stage", "colour", "grid", "cells",
                                                  "completion", "source", "wiki_check", "verified_in_game",
                                                  "tileable_with_rotation", "tileable_without", "note")}
        answer["rotation"] = table.get("rotation")
        answer["variants"] = [
            dict(variant, needed=rules.needed(variant), needs_rotation=rules.needs_rotation(variant))
            for variant in (rules.variants(entry, rotate).values() if entry.get("grid") else [])]
        return answer

    async def handle_list(request):
        return ports.respond({"rotation": table.get("rotation"),
                              "shapes": {name: shape["name"] for name, shape in table["shapes"].items()},
                              "weapons": [summary(entry) for entry in table["weapons"]]})

    async def handle_one(request):
        # By id only: names are for display (two weapons share one).
        asked = request.query.get("id", "")
        try:
            entry = rules.weapon_by_id(int(asked), table)
        except ValueError:
            entry = None
        if entry is None:
            return ports.respond({"error": f"Arme inconnue : id {asked}"}, status=404)
        return ports.respond(detail(entry))

    def state():
        out = {}
        for mode, part in loadouts.items():
            chosen = part["soul_weapon"]
            entry = rules.weapon_by_id(chosen["id"], table) if chosen else None
            variant = rules.variants(entry, rotate)[chosen["variant"]] if entry else None
            out[mode] = dict(part, weapon=entry["name"] if entry else None,
                             placeable=variant["placeable"] if variant else None)
        return {"loadouts": out}

    async def handle_get(request):
        return ports.respond(state())

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        mode = body.get("mode") if isinstance(body, dict) else None
        asked, error = rules.loadout(body, table, rotate, loadouts.get(mode) if isinstance(mode, str) else None)
        if error:
            return ports.respond({"error": error}, status=400)
        mode, part = asked
        loadouts[mode] = part
        ports.store.save()
        return ports.respond(state())

    return {"api": api, "routes": [("GET", "/engravings", handle_list), ("GET", "/engraving", handle_one),
                       ("GET", "/loadout", handle_get), ("POST", "/loadout", handle_post)]}
