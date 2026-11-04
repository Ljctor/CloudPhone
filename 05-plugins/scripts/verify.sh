#!/usr/bin/env bash
# Read-only validation of the installed Slayer Legend resource catalogue.
set -euo pipefail
# Optional review upgrades keep their app and reader snapshot on the same release.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend/review_app" -p test_review_install.py -q
# Review scrolls stay in measured lists; visible-tab variants retain calibrated returns.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend/review_app" -p test_review_server.py -q
base=${1:?Usage: verify.sh http://LISTEN_ADDRESS:WEB_PORT}
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/navigation/oral-feedback?limit=1" | python3 -c '
import json, sys
queue = json.load(sys.stdin)
assert isinstance(queue["items"], list) and len(queue["items"]) <= 1
assert all(item.get("gestureAuthority") is False for item in queue["items"])
print("Private oral developer-review queue: OK")
'
# Owned balance crops and identity guards; no gameplay input.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_resource_balances.py -q
# Real reviewed crops distinguish red drag ghosts from actionable controls;
# this check stays deterministic and never gestures on the installed game.
python3 "$(dirname "$0")/../slayer-legend/test_screen_model.py" EngravingPreview Registry
# Quick debug scans retain acquisition provenance through slow classification and caching.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_screen_quick.py -q
# Inventory order, capture provenance and exact bonus text, without gameplay.
node "$(dirname "$0")/../slayer-legend/test_page_inventory.mjs"
# Root section declarations keep Overlay free of a menu logo.
node "$(dirname "$0")/../slayer-legend/test_page_game.mjs"
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_title_logo.py -q
# Real Latent Power and Character landmarks; Enhance/Growth/Promotion use their
# identified close tab, with ambiguous identities and unknown returns refused.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_menu_recovery.py -q
# Silent process loss, bounded reopen attempts, and the original launch deadline.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_launch.py -q
# Farming entry joins/resumes launch before its farm lease, including focused startup
# after loadout cancellation and a retry that encounters Sign In.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_mode_entry_readiness.py -q
# Real AUTO-labelled control tile versus Android volume-overlay Roman false positives.
python3 "$(dirname "$0")/../slayer-legend/test_fixtures.py" ProgressBar Readings.test_actual_android_volume_bar_is_not_a_game_badge
python3 "$(dirname "$0")/../slayer-legend/test_reading.py" Controls.test_badge
python3 "$(dirname "$0")/../slayer-legend/test_soul_weapon.py" Tag ActualNativeCaptures Readers NativeReaders \
  Sequence.test_after_a_relaunch_no_detached_repair_or_notification \
  Sequence.test_slow_readback_confirms_select_and_equip_without_repeating_gestures \
  Sequence.test_select_without_effect_stops_with_bounded_observation \
  Sequence.test_scroll_filters_live_top_point_outside_lane_for_both_endpoints \
  Sequence.test_input_during_select_readback_stops_before_second_observation
python3 "$(dirname "$0")/../slayer-legend/test_soul_weapon.py" \
  Engraving.test_opening_can_outlast_the_card_polling_deadline \
  Engraving.test_timed_out_opening_is_recovered_before_the_next_stage_navigation \
  Engraving.test_recovery_before_stage_refuses_unknown_identity_or_unread_locks \
  Engraving.test_periodic_grid_check_keeps_valid_equipment_proof_when_target_cell_is_offscreen \
  Engraving.test_offscreen_selection_after_relaunch_cannot_reuse_equipment_proof \
  Engraving.test_retained_equipment_proof_still_repairs_current_grid_and_locks \
  Engraving.test_complete_farm_receipt_requires_both_completion_and_lock_proofs \
  Engraving.test_user_input_during_final_readback_cannot_publish_fresh_equipment_proof \
  Engraving.test_user_unlock_during_return_from_engraving_leaves_no_fresh_setup_proof \
  Engraving.test_relaunch_during_final_readback_cannot_publish_fresh_equipment_proof
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_screen.py -q
# Reviewed failed and recovered L previews retain distinct landing geometry.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_geometry.py -q
# Existing-weapon repairs require durable intent before their first gesture.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_recovery.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_reuse.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_coverage.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_equip_engraving.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_engraving_detection.py -q
python3 "$(dirname "$0")/../slayer-legend/test_nav.py" Graph.test_low_preview_bar_stays_within_its_calibrated_reader_area Graph.test_preview_endpoint_uses_catalogue_move_area_without_clamping Graph.test_consistent
python3 "$(dirname "$0")/../slayer-legend/test_capture_time.py" CaptureTime.test_move_geometry_port_is_wired_and_missing_provider_fails_closed
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_agent_soul_weapon.py -q
# Repair ownership survives bounded child tasks; revoked mode/input cannot navigate or publish proof.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_watchdog_repair_ownership.py -q
# Full repairs commit the current Mode receipt before their event.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_watchdog_current_receipt.py -q
python3 "$(dirname "$0")/../slayer-legend/test_stage_change.py" \
  Sequence.test_discordant_badges_read_settings_instead_of_freezing_a_false_blocker \
  Sequence.test_isolated_preflight_badge_mismatch_does_not_block_before_confirmation \
  Sequence.test_user_input_during_parking_after_preset_refusal_stays_deferred \
  Sequence.test_user_input_during_readback_defers_success_and_stale_failure \
  Sequence.test_recognized_settings_closes_without_changing_preset \
  Sequence.test_accessible_preset_mismatch_stops_before_stage_navigation \
  Sequence.test_correct_visible_preset_does_not_block_stage_change \
  Sequence.test_unread_preset_is_not_treated_as_a_known_mismatch_before_stage
# Due proof is pending, failures/overdue remain blockers; complete receipts acknowledge only setup faults.
python3 "$(dirname "$0")/../slayer-legend/test_watchdog.py"
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_hourly_resources.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_rate_completions.py -q
# Six historical rates require exact configuration and verified acquisition episodes.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_rate_history.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_gold_native.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_native_cache.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_cube_native.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_soul_native.py -q
# Selected Equipment text remains readable beside another tab's red badge.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_equipment_l3.py -q
# Optional resource visits yield to failed or incomplete farming setup.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_resource_refresh.py -q
# Overlay groups hourly analysis and display settings; rate icons stay distinct.
node "$(dirname "$0")/../slayer-legend/test_page_gold.mjs"
# Autosave/revisions and fixed history slots reject rates for another visible target.
node "$(dirname "$0")/../slayer-legend/test_page_mode.mjs"
# Recovery messages stay bound to their weapon/variant; accepted fields and
# supported placement do not repeat an unverified capability status.
node "$(dirname "$0")/../slayer-legend/test_page_engraving.mjs"
# Placement capability comes from executor calibration; inventory remains unverified.
python3 "$(dirname "$0")/../slayer-legend/test_engraving.py" Routes.test_installed_applicability_uses_executor_calibration_not_inventory_history
node "$(dirname "$0")/../slayer-legend/test_page_engraving_requirements.mjs"
node "$(dirname "$0")/../slayer-legend/test_page_trace.mjs"
# Startup idle requires a complete current setup receipt, never a healthy frame.
# Receipt, ready state and event commit together; Busy/readiness retries renew their snapshot.
# Resumed setup clears only its expired input hold and reports moving before farming.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_mode_setup_status.py -q
# POST /loadout requires complete stage/preset/weapon proof, including weapon-only edits.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_loadout_receipt.py -q
# Gear Farming / Gold Farming retain their internal mode IDs and renamed outcomes.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_mode_rules.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_transaction_ownership.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_game.py -q
# Measured visual button bounds are exported independently of gesture envelopes.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_navigation_debug.py -q
# Forbidden navigation and forbidden rectangular action stay distinct advisory feedback after reload.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_trace_feature.py -q
# Evidence matching: exact registered capture aliases and destination-specific panel tabs.
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_evidence_review.py -q
python3 -m unittest discover -s "$(dirname "$0")/../slayer-legend" -p test_zone_feedback.py -q
# Passive phone simulation: full navigation hotspots, action/forbidden priority, inert slides/drags.
# Review URLs keep their service mount both at / and /navigation-review/.
node "$(dirname "$0")/../slayer-legend/review_app/test_model.mjs"
node "$(dirname "$0")/../slayer-legend/test_page_navigation_debug.mjs"
# Direct microphone recording keeps its start frame through replay/cancel/retry.
node "$(dirname "$0")/../slayer-legend/test_page_oral_feedback.mjs"
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/game" | python3 -c '
import json, math, re, sys
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
        assert "currencies" in scan["expected"]
        assert ("cubes" in scan["expected"]) == ("weapon_detail" in scan["overlays"])
# Observation may be idle, disabled, away from the game, or newly started.
# Validate bounded work and truthful optional measurements without demanding
# a capture, a recent fact, zero historical failures, or a running game.
def count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0

def duration(value):
    return value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)
                             and math.isfinite(value) and value >= 0)

observation = state["observation"]
for field in ("detected", "discarded", "errors", "archive_errors", "reader_running",
              "reader_waiting", "reader_queued", "reader_workers"):
    assert count(observation[field]), field
assert observation["detected"] == state["scans"]
assert observation["reader_concurrency"] == 2
assert observation["reader_running"] <= observation["reader_concurrency"]
assert observation["detection_queued"] in (0, 1)
assert observation["archive_queued"] in (0, 1)
for field in ("detection_seconds", "archive_seconds", "age_seconds"):
    assert duration(observation[field]), field
assert (observation["age_seconds"] is None) == (scan is None)
metrics = observation["readers"]
assert isinstance(metrics, dict)
for reader, metric in metrics.items():
    assert isinstance(reader, str)
    for field in ("runs", "errors", "discarded", "running", "queued"):
        assert count(metric.get(field, 0)), (reader, field)
    for field in ("seconds", "queue_seconds", "age_seconds"):
        assert duration(metric.get(field)), (reader, field)
    if "at" in metric:
        assert duration(metric["at"]) and metric["at"] > 0
assert sum(metric.get("running", 0) for metric in metrics.values()) == observation["reader_running"]
assert sum(metric.get("queued", 0) for metric in metrics.values()) == observation["reader_waiting"]
producer = observation["producer"]
assert count(producer["captures"])
assert isinstance(producer["foreground"], bool)
assert producer["interval_seconds"] is None or producer["interval_seconds"] in (0.5, 1.5, 15)
assert duration(producer.get("capture_seconds"))
if producer["captures"]:
    assert producer["at"] is None or (duration(producer["at"]) and producer["at"] > 0)
print("Bounded server observation telemetry: OK")
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
# Only these two dated progression records feed Overview; the UI does not
# expose an Adventure section or a current dungeon selection.
assert {name for name in screens if name.startswith("dungeon")} == {
    "dungeon_forest", "dungeon_training"}
assert not any(name.startswith(("quest", "adventure", "mine"))
               or name == "quit_dialog" for name in screens)
assert {name for name in screens if name.startswith("shop")} == {
    "shop_summon", "shop_summon_equipment", "shop_summon_relic"}
assert screens["scroll"]["inventory"]["status"] == "never_read"
assert screens["equipment_weapon"]["path"][-1] == "Equipment: Weapon"
assert screens["black_orb"]["path"][-1] == "Black Orb"
assert any(field["field"] == "exp" and field["value"] is None and field["pending"]
           for field in screens["character_enhance"]["fields"])
assert screens["black_orb_obtain"]["pending"] is True
assert next(row for row in rows if row["field"] == "feather_black")["pending"] is True
assert all("example" in screen and "examples" in screen and "details" in screen
           for screen in state["screens"])
assert all(screens[name]["path"] for name in (
    "equipment_weapon", "equipment_accessories", "companion_advancement",
    "beast", "shop_summon"))
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
assert state["farming_drop"] in (None, "weapon", "accessory")
assert state["farming_read"] is None or isinstance(state["farming_read"], (int, float))
assert isinstance(state["observed_at"], (int, float)) and state["observed_at"] > 0
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
assert "observeResponse(answer, started)" in script
assert "now = responseTime(answer)" in script
assert "if (!Number.isFinite(now)) return base" in script
assert "api.tr(" + chr(39) + "non visible" + chr(39) + ")" not in script
assert "never read" in script
assert "outline: 2" in script
assert "combatCountersVisible" in script
assert "screenObservationAge(scan)" in script
assert "cubeRow.style.opacity" in script and "row.style.opacity" in script
assert "left:36.1%;top:18.25%;transform:translateY(-50%)" in script
assert "estimatedCubes(cube, gold.answer" in script
assert "CUBE_NUMBER_LEFT = 298 / 720" in script
assert "showLabel(Boolean(gold.font && enabled()))" in script
assert "(fresh || soulsFresh)" not in script
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
script = sys.stdin.read()
assert "export function freshnessColour" in script
assert "export function observeResponse" in script
assert "export function responseTime" in script
assert "received - started <= 2" in script
assert "started: received" in script
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
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/navigation/zone-feedback" | python3 -c '
import json, sys
state = json.load(sys.stdin)
assert state["gestureAuthority"] is False and isinstance(state["items"], list)
assert all(item["gestureAuthority"] is False for item in state["items"])
print("Zone proposals remain separate from navigation authority: OK")
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
for token in ("getScreen(api)", "Ajouter un bouton de navigation", "Déclarer un bouton de navigation interdit", "Marquer une valeur de progression", "Marquer une valeur de ressource", "Marquer un identifiant d\u2019écran", "Marquer un slider vertical", "Marquer un slider horizontal", "❮", "❯"):
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
script = sys.stdin.read()
assert "/screen?quick=1" in script
assert "export function screenObservationAge" in script
assert "performance.now() / 1000" in script
assert "state.observations.has(value.scan.at)" in script
assert "value.scan.age" in script and "observed.set(value.scan" in script
assert "received - started <= 2" in script
assert "? received : state.observations.get(value.scan.at)" in script
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
assert "scheduleSave" in script and "Enregistrement automatique en attente" in script
assert "button: " + chr(39) + "Appliquer" + chr(39) not in script
assert "Réessayer cette configuration" in script and "Recharger et réessayer" in script
assert "result?.result === '\''done'\''" in script and "currentResult" in script
print("Automatic complete loadout saving and verified outcomes: OK")
'
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/mode" | python3 -c '
import json, sys
state = json.load(sys.stdin)
import math
assert state["default"] in ("free", "mpw18", "mpw4", "soul"), "Agent mode cannot be a default"
assert (state["until"] is None) == (state["mode"] == state["default"])
if state["until"] is not None:
    assert isinstance(state["until"], (int, float)) and not isinstance(state["until"], bool)
    assert math.isfinite(state["until"])
assert {"setup_blocker_t", "setup_result", "setup_request"} <= state.keys()
request = state["setup_request"]
assert request is None or (request["mode"] == state["mode"]
                           and len(request["if_revision"]) == 24 and not state["setup"])
blocker = state["setup_blocker_t"]
assert blocker is None or isinstance(blocker, dict) and "template" in blocker
result = state["setup_result"]
if result is not None:
    assert {"mode", "revision", "target", "at", "result", "message_t"} <= result.keys()
    assert result["mode"] in ("mpw18", "mpw4", "soul")
    assert isinstance(result["revision"], str) and len(result["revision"]) == 24
    assert isinstance(result["target"], dict) and isinstance(result["at"], (int, float))
print("Explicit setup blocker and target-bound attempt result: OK")
'

# Passive modes already explain their status in the mode row.
curl -fsS "${base%/}/plugins/slayer-legend/page_watchdog.js" | python3 -c '
import sys
script = sys.stdin.read()
assert "mode === " + chr(39) + "agent" + chr(39) in script
print("Agent mode status is not duplicated: OK")
'
# Historical rows are finite capture-dated measurements, never copied from another mode.
curl -fsS "${base%/}/api/v1/plugins/slayer-legend/rate-history" | python3 -c '
import json, math, sys
value = json.load(sys.stdin)
assert value["version"] == 1
for mode in ("mpw18", "mpw4", "soul", "free", "mine"):
    config = value["configs"][mode]
    rows = config["fields"]
    assert len(rows) == 6
    assert [row["field"] for row in rows[:2]] == ["gold", "cubes"]
    assert rows[2]["field"] in ("weapon_l3", "accessory_l3", "gear_l3")
    assert [row["field"] for row in rows[3:]] == ["soul_green", "soul_blue", "soul_red"]
    if mode in ("free", "mine"):
        assert config["supported"] is False
    for row in rows:
        rate = row["rate_per_hour"]
        if rate is None:
            assert row["measured_at"] is None
        else:
            assert type(rate) in (int, float) and math.isfinite(rate) and rate >= 0
            assert row["source"] == "observed_window"
            assert row["window_start"] < row["window_end"] == row["measured_at"]
'
