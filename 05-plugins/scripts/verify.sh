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
assert all("seen" in row and "verified" in row for row in rows)
assert all(screen.get("path") for screen in state["screens"])
assert not any(row["field"] in expected for screen in state["screens"] for row in screen["fields"])
print("Resource catalogue and game navigation paths: OK")
'
