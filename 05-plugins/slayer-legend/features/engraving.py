"""Soul Weapon engraving and the loadout of each farming mode: the
patterns of engravings.json, and per mode (mpw18, mpw4) the Battle
settings preset and the soul weapon with its engraving variant.

GET  /engravings                 {rotation, weapons: [{id, name, stage, grid, source, verified_in_game,
                                  wiki_check, variants}]}
GET  /engraving?id=N|weapon=Name the weapon's pattern, its variants with the pieces each needs
GET  /loadout                    {loadouts: {mpw18, mpw4}}, each {preset, soul_weapon: {id, variant}}
POST /loadout                    {mode, preset, soul_weapon: {id, variant}}: one mode's loadout

Read-only for the game: nothing is equipped or placed yet; a later phase
compares the grid on the engraving screen with the pattern and reads the
pieces there first (engraving_rules.feasible, missing_alert). The rules
are in engraving_rules.py; the loadouts are kept in state.json
("loadouts").
"""


def engraving(ports, rules):
    table = rules.load()
    # Rotation not confirmed in game (null): the sheet's variants and the
    # gold layout with rotation are offered, marked as not checked.
    rotate = table.get("rotation") is not False
    loadouts = rules.kept_loadouts(ports.store.saved.get("loadouts"), table, rotate)
    ports.store.register("loadouts", lambda: loadouts)

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
        asked = request.query.get("id")
        if asked:
            try:
                entry = rules.weapon_by_id(int(asked), table)
            except ValueError:
                entry = None
            if entry is None:
                return ports.respond({"error": f"Arme inconnue : id {asked}"}, status=404)
        else:
            try:
                entry = rules.pattern_for(request.query.get("weapon", ""), table)
            except rules.UnknownWeapon as e:
                return ports.respond({"error": str(e)}, status=404)
        return ports.respond(detail(entry))

    def state():
        out = {}
        for mode, part in loadouts.items():
            chosen = part["soul_weapon"]
            entry = rules.weapon_by_id(chosen["id"], table) if chosen else None
            out[mode] = dict(part, weapon=entry["name"] if entry else None)
        return {"loadouts": out}

    async def handle_get(request):
        return ports.respond(state())

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        asked, error = rules.loadout(body, table, rotate)
        if error:
            return ports.respond({"error": error}, status=400)
        mode, part = asked
        loadouts[mode] = part
        ports.store.save()
        return ports.respond(state())

    return {"routes": [("GET", "/engravings", handle_list), ("GET", "/engraving", handle_one),
                       ("GET", "/loadout", handle_get), ("POST", "/loadout", handle_post)]}
