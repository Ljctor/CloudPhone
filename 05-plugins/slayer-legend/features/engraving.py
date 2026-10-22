"""Soul Weapon engraving and the loadout of each farming mode: the
patterns of engravings.json, and per mode (mpw18, mpw4) the Battle
settings preset and the soul weapon with its engraving variant.

GET  /engravings                 {rotation, weapons: [{id, name, stage, grid, source, verified_in_game,
                                  wiki_check, variants}]}
GET  /engraving?id=N             the weapon's pattern, its variants with the pieces each needs
                                 (needed by shape; needed_oriented by "L:1", per piece, else null)
GET  /loadout                    {loadouts: {mpw18, mpw4}}, each {stage, preset, soul_weapon: {id, variant}}
POST /loadout                    {mode, stage, preset, soul_weapon: {id, variant}}: one mode's loadout;
                                 a field absent keeps its value, a null one clears it

The soul weapon is equipped by the stage change feature
(features/soul_weapon.py, from this loadout), and its engraving set up as
the variant (features/engraving_setup.py, api's variant). The rules
are in engraving_rules.py; the loadouts are kept in state.json
("loadouts"). They are the one place of the mpw18 and mpw4 stages: the
mode feature (POST /mode's stage18, stage4) and the watchdog read and set
them through api (loadout, stage, set_stage, adopt_stage); on_change(f)
calls f(mode, before, after) on every change of a mode's loadout (POST
/loadout or set_stage), for the mode feature to apply it at once.
"""


def engraving(ports, rules):
    table = rules.load()
    # Layouts hold turned pieces only once the game is known to turn them
    # ("rotation": true) or pieces are known to drop in every orientation
    # ("per-piece"): until then Gold has vertical bars only, and the sheet's
    # variants that turn pieces are listed but not placeable. Per piece, the
    # inventory is counted by oriented piece (needed_oriented).
    rotate = rules.any_orientation(table)
    oriented = table["shapes"] if rules.per_piece(table) else None
    loadouts = rules.kept_loadouts(ports.store.saved.get("loadouts"), table, rotate)
    ports.store.register("loadouts", lambda: loadouts)
    listeners = []

    def changed(mode, before):
        after = loadouts[mode]
        if before != after:
            for listener in listeners:
                listener(mode, before, dict(after))

    def set_stage(mode, number):
        """The stage farmed in mode (mpw18, mpw4); None clears it."""
        if loadouts[mode]["stage"] != rules.stage_or_none(number):
            before = dict(loadouts[mode])
            loadouts[mode]["stage"] = rules.stage_or_none(number)
            ports.store.save()
            changed(mode, before)

    def adopt_stage(mode, number):
        """A stage from an older state.json, kept only where none is set."""
        if loadouts[mode]["stage"] is None and rules.stage_or_none(number):
            set_stage(mode, number)

    def expected_cells(weapon_id, name):
        """The cells the weapon's variant name fills ([row, col]), None when
        unknown."""
        entry = rules.weapon_by_id(weapon_id, table)
        variant = rules.variants(entry, rotate).get(name) if entry and entry.get("grid") else None
        return sorted({tuple(cell) for piece in variant["pieces"] for cell in piece["cells"]}) if variant else None

    def variant(weapon_id, name):
        """The weapon's variant name ({name, pieces: [{shape, rotation,
        cells}]}), None when unknown."""
        entry = rules.weapon_by_id(weapon_id, table)
        return rules.variants(entry, rotate).get(name) if entry and entry.get("grid") else None

    api = {"loadout": lambda mode: dict(loadouts[mode]), "stage": lambda mode: loadouts[mode]["stage"],
           "set_stage": set_stage, "adopt_stage": adopt_stage, "expected_cells": expected_cells,
           "variant": variant, "table": table, "on_change": listeners.append}

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
            dict(variant, needed=rules.needed(variant), needs_rotation=rules.needs_rotation(variant),
                 needed_oriented=rules.needed(variant, oriented) if oriented else None)
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
            return ports.respond({"error_t": ports.t("Arme inconnue : id {id}", id=asked)}, status=404)
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
            return ports.respond({"error_t": error}, status=400)
        mode, part = asked
        before = dict(loadouts[mode])
        loadouts[mode] = part
        ports.store.save()
        changed(mode, before)
        return ports.respond(state())

    return {"api": api, "routes": [("GET", "/engravings", handle_list), ("GET", "/engraving", handle_one),
                       ("GET", "/loadout", handle_get), ("POST", "/loadout", handle_post)]}
