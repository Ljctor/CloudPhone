#!/usr/bin/env bash
# Read-only validation of the installed Slayer Legend resource catalogue.
set -euo pipefail
base=${1:?Usage: verify.sh http://LISTEN_ADDRESS:WEB_PORT}
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/game" | python3 -c '
import json, re, sys
state = json.load(sys.stdin)
expected = {"diamond", "gold", "emerald", "cubes", "crystals", "dice",
            "soul_green", "soul_blue", "soul_red", "soul_white",
            "stone_green", "stone_blue", "stone_red", "stone_yellow",
            "feather_white", "feather_green", "feather_purple", "feather_black",
            "dragon_power", "dragon_spark", "black_mana"}
rows = state["resources"]
for row in rows:
    value = row["value"]
    if isinstance(value, dict) and re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d+", value.get("text", "")):
        assert int(value["text"].replace(",", "")) == value["value"]
scan = state["scan"]
assert scan is None or {"size", "at", "screen", "overlays", "expected", "ran"} <= scan.keys()
if scan is not None:
    assert len(scan["size"]) == 2 and all(size > 0 for size in scan["size"])
    assert set(scan["ran"]) <= set(scan["expected"])
    if scan["screen"] == "battle":
        assert "cubes" in scan["expected"]
        assert "currencies" in scan["expected"]
assert {row["field"] for row in rows} == expected
cube = next(row for row in rows if row["field"] == "cubes")
assert cube["pending"] is False
assert all(next(row for row in rows if row["field"] == field)["pending"] is False
           for field in ("emerald", "diamond"))
assert cube["value"] is None or (
    isinstance(cube["value"], dict)
    and isinstance(cube["value"].get("value"), int)
    and cube["value"].get("text", "").replace(",", "").isdigit()
    and cube["value"]["text"] == format(cube["value"]["value"], ",")
)
assert len(rows) == len(expected)
fields = [row["field"] for row in rows]
assert fields.index("soul_white") == fields.index("soul_red") + 1
assert all("seen" in row and "verified" in row for row in rows)
assert all(screen.get("path") for screen in state["screens"] if screen["screen"] != "battle")
assert next(screen for screen in state["screens"] if screen["screen"] == "battle")["path"] == []
assert not {"top_menu", "top_ranking", "top_settings", "top_mail"} & {screen["screen"] for screen in state["screens"]}
assert not any(row["field"] in expected for screen in state["screens"] for row in screen["fields"])
screens = {screen["screen"]: screen for screen in state["screens"]}
assert screens["skill"]["label"] == "Skill"
assert screens["quest_panel"]["label"] == "Quest"
assert screens["scroll"]["inventory"]["status"] == "never_read"
assert screens["equipment_weapon"]["path"][-1] == "Equipment: Weapon"
assert screens["black_orb"]["path"][-1] == "Black Orb"
assert all("example" in screen and "examples" in screen and "details" in screen
           for screen in state["screens"])
assert sum(bool(screen["details"]) for screen in state["screens"]) >= 50
assert all(screens[name]["path"] for name in (
    "adventure_story_main", "dungeon_shelter", "dungeon_rift",
    "dungeon_forest", "dungeon_kingdom", "dungeon_training", "mine_feathers"))
battle = {row["field"]: row for row in screens["battle"]["fields"]}
assert battle["highest"]["shown"] == "lower_bound"
if isinstance(battle["stage"]["value"], int) and isinstance(battle["highest"]["value"], int):
    assert battle["highest"]["value"] >= battle["stage"]["value"]
engraving = next(row for row in screens["soul_weapon_engraving"]["fields"] if row["field"] == "engraving")
assert engraving["value"] is None or engraving["value"].get("weapon")
for screen_name in ("equipment_weapon", "equipment_accessories"):
    items = screens[screen_name]["inventory"]["items"]
    assert len(items) == 25
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["source"]["capture"] and item["source"]["box"] for item in items)
    assert all(item["displayed_fraction"]["denominator"] > 0 for item in items)
for screen_name, field in (("equipment_weapon", "weapon_l3"),
                           ("equipment_accessories", "accessory_l3")):
    row = next(row for row in screens[screen_name]["fields"] if row["field"] == field)
    assert row["pending"] is False
    assert row["value"] is None or isinstance(row["value"], int) and row["value"] >= 0
assert screens["character_class"]["inventory"]["status"] in ("never_read", "read")
print("Resource catalogue, equipment inventory and game navigation: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/gold" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert {"text", "value", "rate", "rate_text", "span", "window", "read", "box", "souls"} <= state.keys()
assert {"green", "blue", "red", "white"} <= state["souls"].keys()
assert state["window"] in (60, 300)
assert (state["rate"] is None) == (state["rate_text"] is None)
if state["rate"] is not None:
    assert state["span"] > 0
if state["rate_text"] is not None:
    assert "~" not in state["rate_text"]
if state["value"] is not None and state["text"] and state["text"].isdigit() and len(state["text"]) > 3:
    assert isinstance(state["value"], int)
    assert state["window"] == 60
print("Gold rate endpoint: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_numbers.js" | python3 -c '
import sys
assert "export function shortNumber" in sys.stdin.read()
print("Abbreviated option counter asset: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_gold.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "drawText(cubeValue, gold.font" in script
assert "const cell = api.layer.offsetHeight / 1040;" in script
assert "hourly * age / 3600" in script
assert "['stone_green'" not in script and "['stone_yellow'" not in script
assert "['stone_red'" not in script and "['stone_blue'" not in script
assert "weapon_l3" in script and "accessory_l3" in script
assert "EQUIPMENT_L3_ICONS.weapon" in script and "EQUIPMENT_L3_ICONS.accessory" in script
assert "soul_white" not in script
assert "* 3600" in script and "}/h" in script
assert "const RATE_TOP = 18.5" in script
assert "const RATE_STEP = 1.65" in script
print("Hourly overlay counters: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_cube_font.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "export const CUBE_FONT" in script
assert chr(34) + "," + chr(34) + ":" in script
print("Cube counter font asset: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/navigation-debug" | python3 -c '
import json, sys
state = json.load(sys.stdin)
graph = state["graph"]
assert "battle" in graph["screens"] and "equipment_weapon" in graph["screens"]
assert graph["screens"]["battle"]["name"]
assert any(move.get("swipe") for move in graph["screens"]["equipment_weapon"]["moves"])
assert state["registry"]["tree"]["equipment_weapon"]["scroll"]
print("Navigation debug geometry: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_navigation_debug.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "trace/arm" in script and "Écran : {screen}" in script
print("Navigation debug overlay asset: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/trace/manual" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert isinstance(state["clicks"], list)
print("Private manual click archive: OK")
'
