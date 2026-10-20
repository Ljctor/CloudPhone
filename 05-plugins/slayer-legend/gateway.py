"""Slayer Legend plugin, gateway side (loaded by the gateway's plugin loader).

This file only builds the ports from the gateway's context
(features/ports.py: screenshots, analysis, the guarded tap, hold and
swipe, alerts, the clock, state.json) and wires the features together.
Each feature is in features/, with its rules beside it as a pure module
(features/<feature>_rules.py); the screens are read by the analysis
modules beside this file (screens.py, stage.py, gold.py, mine.py,
gold_scroll.py, emerald_mask.py, trace.py) and every move on the game
goes through the navigation guard (nav.py, navigation.json).

Routes, under /api/v1/plugins/slayer-legend:

GET  /emerald-mask[?counter=diamond]   features/counters.py
GET  /screen[?known=N], /stages        features/screen.py
GET  /launch, POST /launch             features/launch.py
GET  /trace, /trace/graph, POST /trace features/trace.py
GET  /gold, /gold-font                 features/gold.py
GET  /mine, POST /mine, /mine/timer    features/mine.py
GET  /mode, POST /mode, /mode/timer    features/mode.py
GET  /engravings, /engraving?id=N      features/engraving.py
GET  /loadout, POST /loadout           features/engraving.py
GET, POST, DELETE /lease               features/lease.py (ports.Lease)

The mode and its timer, the mine's floor, area, timer and on/off, each
farming mode's loadout (its stage, Battle settings preset, soul weapon
and engraving) and the highest stage seen farmed are kept in the plugin's data directory
(state.json, written when they change) and restored when the gateway
starts: farming and a timed mode go on after a gateway restart.
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
    mine = feature("mine").mine(ports, screens, module("mine"), feature("mine_rules"), timer, values)
    features = [
        feature("lease").lease(ports),
        feature("counters").counters(ports, module("emerald_mask")),
        feature("screen").screen(ports, screens, stage, feature("screen_rules"), values, table),
        feature("launch").launch(ports, screens, feature("launch_rules")),
        feature("trace").trace(ports, screens, module("trace")),
        feature("gold").gold(ports, screens, stage, module("gold"), feature("gold_rules")),
        mine,
        feature("mode").mode(ports, feature("mode_rules"), timer, values, mine["api"], screens,
                             module("gold_scroll"), engraving["api"]),
        engraving,
    ]
    # Every feature registered its part of state.json: an old highest.json
    # becomes state.json now.
    ports.store.flush()
    for part in features:
        context.app.on_startup.extend(part.get("startup", []))
        for method, path, handler in part["routes"]:
            add = {"GET": context.add_get, "POST": context.add_post,
                   "DELETE": getattr(context, "add_delete", None)}[method]
            # An older gateway without add_delete: that route is left out.
            if add:
                add(path, handler)
