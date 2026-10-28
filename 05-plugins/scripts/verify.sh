#!/usr/bin/env bash
# Read-only validation of the installed Slayer Legend resource catalogue.
set -euo pipefail
base=${1:?Usage: verify.sh http://LISTEN_ADDRESS:WEB_PORT}
# Real reviewed crops distinguish red drag ghosts from actionable controls;
# this check stays deterministic and never gestures on the installed game.
python3 "$(dirname "$0")/../slayer-legend/test_screen_model.py" EngravingPreview
python3 "$(dirname "$0")/../slayer-legend/test_soul_weapon.py" Tag ActualNativeCaptures
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
assert any(field["field"] == "exp" and field["value"] is None and field["pending"]
           for field in screens["character_enhance"]["fields"])
assert screens["black_orb_obtain"]["pending"] is True
assert next(row for row in rows if row["field"] == "feather_black")["pending"] is True
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
assert {"text", "value", "rate", "rate_text", "span", "window", "read", "box", "shade", "souls"} <= state.keys()
assert 0.2 <= state["shade"] <= 1.0
assert {"green", "blue", "red", "white"} <= state["souls"].keys()
assert {"cubes", "weapon_l3", "accessory_l3"} <= state["resources"].keys()
for rate in state["resources"].values():
    assert {"rate", "read", "status"} <= rate.keys()
    assert rate["status"] in ("measured", "measuring", "unread", "stale")
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
assert "drawText(cubeValue, GOLD_COUNTER_FONT" in script
assert "api.layer.offsetHeight / 1560" in script
assert "freshnessColour(age)" in script
assert "outline: 2" in script
assert "combatCountersVisible" in script
assert "cubeRow.style.opacity" in script and "row.style.opacity" in script
assert "left:36.1%;top:18.25%;transform:translateY(-50%)" in script
assert "estimatedCubes(cube, gold.answer" in script
assert "CUBE_NUMBER_LEFT = 298 / 720" in script
assert all("[" + chr(39) + name + chr(39) not in script
           for name in ("stone_green", "stone_yellow", "stone_red", "stone_blue"))
assert "weapon_l3" in script and "accessory_l3" in script
assert "EQUIPMENT_L3_ICONS.weapon" in script and "EQUIPMENT_L3_ICONS.accessory" in script
assert "soul_white" not in script
assert "* 3600" in script and "}/h" in script
assert "const RATE_TOP = 18.5" in script
assert "const RATE_STEP = 1.65" in script
assert "row.style.width =" in script and "gap:2px" in script
print("Hourly overlay counters: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_gold_counter_font.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "export const GOLD_COUNTER_FONT" in script
assert "export const GOLD_COUNTER_SOURCES" in script
print("Gold-matched Cube font asset: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_freshness.js" | python3 -c '
import sys
assert "export function freshnessColour" in sys.stdin.read()
print("Shared value freshness colour: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_game.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "timestamp: ()" in script and "freshnessColour(" in script
print("Resource timestamps and freshness: OK")
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
assert "quest_panel" in graph["screens"]
print("Navigation debug geometry: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/resource-refresh" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert isinstance(state["active"], bool)
assert isinstance(state["supervised_verified"], bool)
assert {"result", "intention", "last_attempt", "last_complete", "next_at", "read", "missing"} <= state.keys()
assert isinstance(state["read"], dict) and isinstance(state["missing"], list)
assert state["intention"] is None or state["intention"]["kind"] == "resource_refresh"
print("Resource refresh supervision and intention state: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_navigation_debug.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "trace/arm" in script and "Écran : {screen}" in script
assert "response.body" in script and "/trace/cancel" in script
assert "data-capture-layout" in script and "page_navigation_tracking.js" in script
assert "data-debug-drag-handle" in script and "data-debug-toggle" in script
assert "data-capture-open" in script and "page_navigation_preview.js" in script
print("Navigation debug overlay asset: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/trace/manual" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert isinstance(state["clicks"], list)
print("Private manual click archive: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/screen?quick=1" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert {"screen", "scan"} <= state.keys()
assert {"screen", "overlays", "plain", "at"} <= state["scan"].keys()
assert isinstance(state["scan"]["overlays"], list)
print("Fast screen recognition: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_navigation_debug.js" | python3 -c '
import sys
script = sys.stdin.read()
for token in ("getScreen(api)", "Ajouter un bouton de navigation", "Déclarer un bouton de navigation interdit", "Marquer un élément scannable", "Marquer un slider vertical", "Marquer un slider horizontal", "❮", "❯"):
    assert token in script, token
print("Navigation annotation controls: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_mode.js" | python3 -c '
import sys
script = sys.stdin.read()
for token in ("ok: '\''#ffffff'\''", "hold: '\''#409cff'\''", "setup: '\''#ffa31a'\''", "error: '\''#ff4040'\''", "INPUT_PAUSE_MS = 5000", "tone === '\''ok'\'' ? TIMER_COLOUR : colour"):
    assert token in script, token
print("Mode overlay colours and user pause: OK")
'

curl -fsS "${base%/}/plugins/slayer-legend/page_navigation_tracking.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "locatePatch" in script and "getImageData" in script
print("Visual navigation tracking asset: OK")
'

curl -fsS "${base%/}/plugins/slayer-legend/page_navigation_preview.js" | python3 -c '
import sys
script = sys.stdin.read()
for token in ("data-recorded-rect", "data-recorded-tap", "data-recorded-swipe", "data-capture-raw"):
    assert token in script, token
print("Annotated capture preview: OK")
'

curl -fsS "${base%/}/plugins/slayer-legend/page_screen_scan.js" | python3 -c '
import sys
assert "/screen?quick=1" in sys.stdin.read()
print("Shared live screen scan: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/farming" | python3 -c '
import json, sys
soul = json.load(sys.stdin)["soul_weapon"]
assert "recovery" in soul
assert soul["recovery"] is None or isinstance(soul["recovery"], dict)
print("Persistent engraving recovery state: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/loadout" | python3 -c '
import json, sys
for target in json.load(sys.stdin)["loadouts"].values():
    assert isinstance(target["revision"], str) and len(target["revision"]) == 24
    support = target["automation"]
    assert support["scope"] == "static" and support["runtime_verified"] is False
    assert isinstance(support["supported"], bool)
print("Loadout applicability is distinct from runtime verification: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_power.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "confirmed" in script and "Arrêt non confirmé" in script
print("Server-confirmed plugin power control: OK")
'
curl -fsS "${base%/}/plugins/slayer-legend/page_engraving.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "Appliquer" in script and "Modifications non appliquées" in script
print("Explicit complete loadout application: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/mode" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert {"setup_blocker_t", "setup_result"} <= state.keys()
blocker = state["setup_blocker_t"]
assert blocker is None or isinstance(blocker, dict) and "template" in blocker
result = state["setup_result"]
if result is not None:
    assert {"mode", "revision", "target", "at", "result", "message_t"} <= result.keys()
    assert result["mode"] in ("mpw18", "mpw4")
    assert isinstance(result["revision"], str) and len(result["revision"]) == 24
    assert isinstance(result["target"], dict) and isinstance(result["at"], (int, float))
print("Explicit setup blocker and target-bound attempt result: OK")
'
