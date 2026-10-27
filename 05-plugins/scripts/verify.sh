#!/usr/bin/env bash
# Read-only validation of the installed Slayer Legend resource catalogue.
set -euo pipefail
base=${1:?Usage: verify.sh http://LISTEN_ADDRESS:WEB_PORT}
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/game" | python3 -c '
import json, sys
state = json.load(sys.stdin)
expected = {"diamond", "gold", "emerald", "cubes", "crystals", "dice",
            "soul_green", "soul_blue", "soul_red", "soul_white",
            "stone_green", "stone_blue", "stone_red", "stone_yellow",
            "feather_white", "feather_green", "feather_purple", "feather_black",
            "dragon_power", "dragon_spark", "black_mana"}
rows = state["resources"]
scan = state["scan"]
assert scan is None or {"size", "at", "screen", "overlays", "expected", "ran"} <= scan.keys()
if scan is not None:
    assert len(scan["size"]) == 2 and all(size > 0 for size in scan["size"])
    assert set(scan["ran"]) <= set(scan["expected"])
assert {row["field"] for row in rows} == expected
cube = next(row for row in rows if row["field"] == "cubes")
assert cube["pending"] is False
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
