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
assert {row["field"] for row in rows} == expected
assert len(rows) == len(expected)
fields = [row["field"] for row in rows]
assert fields.index("soul_white") == fields.index("soul_red") + 1
assert all("seen" in row and "verified" in row for row in rows)
assert all(screen.get("path") for screen in state["screens"] if screen["screen"] != "battle")
assert next(screen for screen in state["screens"] if screen["screen"] == "battle")["path"] == []
assert not {"top_menu", "top_ranking", "top_settings", "top_mail"} & {screen["screen"] for screen in state["screens"]}
assert not any(row["field"] in expected for screen in state["screens"] for row in screen["fields"])
screens = {screen["screen"]: screen for screen in state["screens"]}
battle = {row["field"]: row for row in screens["battle"]["fields"]}
assert battle["highest"]["shown"] == "lower_bound"
if isinstance(battle["stage"]["value"], int) and isinstance(battle["highest"]["value"], int):
    assert battle["highest"]["value"] >= battle["stage"]["value"]
engraving = next(row for row in screens["soul_weapon_engraving"]["fields"] if row["field"] == "engraving")
assert engraving["value"] is None or engraving["value"].get("weapon")
print("Resource catalogue and game navigation paths: OK")
'
