"""Calibrated game readers and their pure screen/interval registry.

The gateway injects the existing calibrated modules into reader_table;
ReaderRegistry gives the observation pipeline one recognition/read boundary.
"""


def reader_table(
    screens,
    stage,
    select,
    counter,
    souls,
    weapon,
    engraving,
    controls,
    screen_rules,
    table,
    weapons,
    cubes=None,
    currencies=None,
    equipment=None,
):
    """{reader id: fn(shot, base, overlays, plain) -> {field: value}}: the
    plugin's existing readers (stage.py, stage_select.py, gold.py,
    soul_counters.py, soul_weapon.py, engraving_screen.py,
    battle_controls.py), wired. table: stages.json; weapons: the soul
    weapons' table (engravings.json)."""
    names = select.regions(table)
    weapon_names = weapon.names_of(weapons) if weapons else []

    def shades(overlays):
        # Under the Soul Weapon screen the battle is shaded.
        return (
            (screens.PARKED_SHADE, 1.0)
            if screens.SOUL_WEAPON in overlays
            else (1.0, screens.PARKED_SHADE)
        )

    def battle_stage(shot, base, overlays, plain):
        number = None
        for shade in shades(overlays):
            number = select.battle_stage(shot, names, shade)
            if number:
                break
        return {"stage": number, "stage_numeral": stage.read_battle(shot)}

    def progress(shot, base, overlays, plain):
        return {"progress": stage.progress(shot)}

    def gold(shot, base, overlays, plain):
        reading = counter.read(
            shot,
            (
                (1.0, screens.PARKED_SHADE)
                if screens.SOUL_WEAPON in overlays or base == "battle" and "panel" in overlays
                else (1.0,)
            ),
        )
        if base == "saver":
            place = ("saver", stage.read_saver(shot)[0])
        else:
            place = ("battle", stage._ink(stage._crop(shot, stage.BATTLE_NAME)))
        return {
            "gold": {"text": reading["text"], "value": reading["value"]} if reading else None,
            "gold_reading": reading,
            "gold_place": place,
        }

    def cube_row(shot, base, overlays, plain):
        return {"cubes": cubes.read(shot) if cubes else None}

    def currency_bar(shot, base, overlays, plain):
        return {
            field: currencies.read(shot, field) if currencies else None
            for field in ("emerald", "diamond")
        }

    def saver_stage(shot, base, overlays, plain):
        _, number = screen_rules.answer(table, stage, "saver", stage.read_saver(shot), None)
        return {"stage": number}

    def badge(shot, base, overlays, plain):
        return {"preset": controls.badge(shot)}

    def battle_settings(shot, base, overlays, plain):
        return {"preset": controls.selected(shot)}

    def souls_row(shot, base, overlays, plain):
        row = souls.read(shot) if souls else None
        shown = {
            colour: {"text": count["text"], "value": count["value"]}
            for colour, count in (row or {}).items()
            if count
        } or None
        return {"souls": shown, "souls_reading": row}

    def soul_weapon(shot, base, overlays, plain):
        selected = weapon.name(shot, weapon_names) if weapon_names else None
        tag, _ = weapon.tag(shot)
        equipped = selected if selected and tag == "Unequip" else None
        return {"soul_weapon_selected": selected, "soul_weapon_equipped": equipped}

    def equipment_row(shot, base, overlays, plain):
        if not equipment:
            return {}
        tab = weapon.tab(shot)
        if tab == "weapon":
            return {"weapon_l3": equipment.read(shot)}
        if tab == "accessories":
            return {"accessory_l3": equipment.read(shot)}
        return {}

    def region(shot, base, overlays, plain):
        view = select.view(shot, names)
        # A Move button means selectable, not cleared. Only an observed
        # battle stage can raise the highest-stage lower bound.
        return {"region": names[view["region"]] if view["region"] is not None else None}

    def engraving_grid(shot, base, overlays, plain):
        selected = engraving.weapon(shot, weapon_names, weapon.CARD_FONT) if engraving else None
        matching = (
            [entry for entry in weapons["weapons"] if entry["name"] == selected] if selected else []
        )
        if len(matching) != 1 or matching[0].get("grid") != 5:
            return {"engraving": None}
        read = engraving.grid(shot, 5) if engraving else None
        # No cell of the grid seen (another screen's pixels): nothing read.
        if not read or all(state == "none" for state in read["cells"].values()):
            return {"engraving": None}
        active = {tuple(cell) for cell in matching[0]["cells"]}
        visible = {cell for cell, state in read["cells"].items() if state != "none"}
        if visible != active:
            return {"engraving": None}
        cells = [
            [read["cells"][(row, col)] if (row, col) in active else "none" for col in range(5)]
            for row in range(5)
        ]
        return {
            "engraving": {
                "weapon": selected,
                "cells": cells,
                "pieces": [[list(cell) for cell in piece] for piece in read["pieces"]],
            }
        }

    return {
        "battle_stage": battle_stage,
        "progress": progress,
        "gold": gold,
        "cubes": cube_row,
        "currencies": currency_bar,
        "saver_stage": saver_stage,
        "badge": badge,
        "battle_settings": battle_settings,
        "souls": souls_row,
        "soul_weapon": soul_weapon,
        "equipment_l3": equipment_row,
        "region": region,
        "engraving": engraving_grid,
    }


def read_all(
    screens,
    rules,
    readers,
    shot,
    last_runs=None,
    now=0.0,
    timings=None,
    force=(),
    done=(),
    previous_look=None,
):
    """Exercise the production registry synchronously on calibration fixtures.

    Runtime scheduling and publication belong to ObservationPipeline. This
    helper uses the same recognition, eligibility and reader calls without
    creating tasks or publishing facts.
    """
    import time

    registry = ReaderRegistry(screens, rules, readers)
    look = registry.identify(shot)
    changed = previous_look is not None and registry.identity(previous_look) != registry.identity(
        look
    )
    frame = {"look": look, "shows": registry.shown(look), "ran": set(done), "changed": changed}
    readings, ran = {}, []
    for reader in registry.due(frame, last_runs or {}, now, force):
        began = time.perf_counter()
        for field, value in registry.read(reader, shot, look).items():
            if value is not None or field not in readings:
                readings[field] = value
        if timings is not None:
            timings[reader] = time.perf_counter() - began
        ran.append(reader)
    return look, readings, ran


class ReaderRegistry:
    """Screen recognition and calibrated reader selection, with no async work or state writes."""

    def __init__(self, screens, rules, readers):
        self.screens = screens
        self.rules = rules
        self.readers = readers

    def identify(self, shot):
        look = self.screens.look(shot)
        return {
            **look,
            "classified": self.screens.classify(shot) if look["screen"] == "unknown" else None,
        }

    def identity(self, look):
        return self.rules.seen_screen(look, look.get("classified")), look.get("quest_tab")

    def shown(self, look):
        return set(self.rules.readers_for(look, look.get("classified")))

    def read(self, reader, shot, look):
        return self.readers[reader](shot, *self.rules.seen_screen(look, look.get("classified")))

    def due(self, frame, last_runs, now, force=()):
        return [
            reader
            for reader in self.readers
            if reader in frame["shows"]
            and reader not in frame["ran"]
            and (frame["changed"] or self.rules.due(reader, last_runs.get(reader), now, force))
        ]
