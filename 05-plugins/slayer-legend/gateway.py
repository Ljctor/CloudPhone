"""Slayer Legend plugin, gateway side (loaded by the gateway's plugin loader).

This file only builds the ports from the gateway's context
(features/ports.py: screenshots, analysis, the guarded tap, hold and
swipe, alerts, the clock, state.json) and wires the features together.
Each feature is in features/, with its rules beside it as a pure module
(features/<feature>_rules.py); the screens are read by the analysis
modules beside this file (screens.py, stage.py, gold.py, mine.py,
gold_scroll.py, emerald_mask.py, trace.py, stage_select.py,
battle_controls.py, soul_weapon.py, soul_counters.py, with the pixel font of pixel_font.py) and every move on the game
goes through the navigation guard (nav.py, navigation.json).

Routes, under /api/v1/plugins/slayer-legend:

GET  /emerald-mask[?counter=diamond]   features/counters.py
GET  /game                             features/game.py (the game's state, scanned)
GET  /screen[?known=N], /stages        features/screen.py
GET  /launch, POST /launch             features/launch.py
GET  /trace, /trace/graph, POST /trace features/trace.py
GET  /gold, /gold-font                 features/gold.py
GET  /mine, POST /mine, /mine/timer    features/mine.py
GET  /mode, POST /mode, /mode/timer    features/mode.py
GET  /engravings, /engraving?id=N      features/engraving.py
GET  /loadout, POST /loadout           features/engraving.py
GET, POST, DELETE /lease               features/lease.py (ports.Lease)
GET  /enabled, POST /enabled           features/power.py (the plugin's on/off switch)
GET  /watchdog                         features/watchdog.py
GET  /farming, POST /farming           features/stage_change.py (its real/plan switches; the soul
                                       weapon's and the engraving's real/off, features/soul_weapon.py)
GET  /templates                        templates.json as it is: {French template: English}, the
                                       English of every status text the plugin answers with
                                       ({template, params}, features/texts.py), for the page

A refused request answers {error_t}, a status text; a status the page
shows is {..._t} (message_t, text_t), never a French sentence. Records
and phone alerts are English.

The mode and its timer, the mine's floor, area, timer and on/off, each
farming mode's loadout (its stage, Battle settings preset, soul weapon
and engraving), the highest stage seen farmed and the watchdog's repairs
of the last hour are kept in the plugin's data directory (state.json,
written when they change) and restored when the gateway starts: farming
and a timed mode go on after a gateway restart.
"""

import importlib.util
import json
import os


def load_sibling(directory, name):
    """A module beside this file ("mine") or in features/ ("features/mine")."""
    spec = importlib.util.spec_from_file_location(f"cloudphone_plugin_slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(directory, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(context):
    def module(name):
        return load_sibling(context.directory, name)

    def feature(name):
        return module(f"features/{name}")

    ports = feature("ports").build(context, module("nav"))
    screens, stage, values = module("screens"), module("stage"), feature("values")
    with open(os.path.join(context.directory, "stages.json"), encoding="utf-8") as f:
        table = json.load(f)
    timer = feature("timer_rules")
    engraving = feature("engraving").engraving(ports, feature("engraving_rules"))
    screen_rules = feature("screen_rules")
    # The scan: every capture read once, the game's state for the features.
    game_feature = feature("game")
    game = game_feature.game(ports, screens, feature("game_rules"), game_feature.reader_table(
        screens, stage, module("stage_select"), module("gold"), module("soul_counters"), module("soul_weapon"),
        module("engraving_screen"), module("battle_controls"), screen_rules, table, engraving["api"]["table"]))
    ports.game = game["api"]
    mine = feature("mine").mine(ports, screens, module("mine"), feature("mine_rules"), timer, values)
    launch = feature("launch").launch(ports, screens, feature("launch_rules"))
    soul = {"feature": feature("soul_weapon").soul_weapon, "reader": module("soul_weapon"),
            "rules": feature("soul_weapon_rules"), "table": engraving["api"]["table"],
            "loadout": engraving["api"]["loadout"],
            "engraving": {"setup": feature("engraving_setup").engraving_setup, "screen": module("engraving_screen"),
                          "rules": feature("engraving_setup_rules"), "variant": engraving["api"]["variant"]}}
    farming = feature("stage_change").stage_change(ports, screens, module("stage_select"), module("battle_controls"),
                                                   feature("stage_change_rules"), table, soul)
    mode = feature("mode").mode(ports, feature("mode_rules"), timer, values, mine["api"], screens,
                                module("gold_scroll"), engraving["api"], farming["api"])
    gold = feature("gold").gold(ports, screens, stage, module("gold"), feature("gold_rules"), module("soul_counters"))
    features = [
        game,
        feature("power").power(ports),
        feature("lease").lease(ports),
        feature("counters").counters(ports, module("emerald_mask")),
        feature("screen").screen(ports, screens, stage, screen_rules, values, table),
        launch,
        feature("trace").trace(ports, screens, module("trace")),
        gold,
        mine,
        farming,
        mode,
        engraving,
        feature("watchdog").watchdog(ports, screens, stage, feature("watchdog_rules"),
                                     lambda number: screen_rules.name_numeral(table, stage, number),
                                     mode["api"], mine["api"], launch["api"], engraving["api"]["loadout"],
                                     farming["api"], gold["api"]),
    ]
    # Every feature registered its part of state.json: an old highest.json
    # becomes state.json now.
    ports.store.flush()
    with open(os.path.join(context.directory, "templates.json"), encoding="utf-8") as f:
        templates = json.load(f)

    async def handle_templates(request):
        return context.json(templates)

    features.append({"routes": [("GET", "/templates", handle_templates)]})
    for part in features:
        context.app.on_startup.extend(part.get("startup", []))
        for method, path, handler in part["routes"]:
            add = {"GET": context.add_get, "POST": context.add_post,
                   "DELETE": getattr(context, "add_delete", None)}[method]
            # An older gateway without add_delete: that route is left out.
            if add:
                add(path, handler)
