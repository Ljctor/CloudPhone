#!/usr/bin/env bash
# Read-only acceptance test of part 04, run as root on the server:
#   sudo 04-cloud-phone-app/scripts/verify.sh [--allow-any-address]
# Exits 0 and prints PASS only when every invariant holds.
#
# By default the page must listen on a single address (the WireGuard one) and
# the firewall must accept its ports only on wg0. --allow-any-address accepts
# LISTEN_ADDRESS=0.0.0.0 for hosts protected by another means.
set -uo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"

any_address=no
case ${1:-} in
  --allow-any-address) any_address=yes ;;
  '') ;;
  *) die "usage: $0 [--allow-any-address]" ;;
esac
require_root
[ -f "$CONF" ] || die "$CONF is missing: part 03 is not installed"
load_conf

host=$LISTEN_ADDRESS
[ "$host" != 0.0.0.0 ] || host=127.0.0.1

answers() { curl -fsS --max-time 5 "$1" >/dev/null; }
live_metrics() {
  curl -fsS --max-time 5 "http://$host:$WEB_PORT/api/v1/state?details=1" |
    python3 -c 'import json,sys; host=(json.load(sys.stdin).get("metrics") or {}).get("host") or {}; assert host.get("cpu") is not None and (host.get("memory") or {}).get("total")'
}
stream_diagnostics() {
  curl -fsS --max-time 5 "http://$host:$WEB_PORT/api/v1/stream-diagnostics" |
    python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["schema_version"] == 1; assert {"emulator","android","channels","signalling","media"} <= x.keys(); assert {"active","recent","hardware_inputs"} <= x["signalling"].keys(); assert x["media"]["frames_observed"] is None' || return 1
  "$PREFIX/current/venv/bin/python" - <<'PYCODE'
from videobridge_gateway.core.stream_diagnostics import check_browser_events
metrics = {name: 1.5 for name in (
    "sampleTimeMs", "packetsReceived", "totalDecodeTime", "totalProcessingDelay",
    "jitterBufferDelay", "jitterBufferTargetDelay", "jitterBufferMinimumDelay",
    "jitterBufferEmittedCount", "nackCount", "pliCount", "firCount", "jitterMs",
    "roundTripTimeMs", "framesDropped", "framesPerSecond")}
payload = {"sessionId": "abcdef123456", "events": [{"kind": "stats", **metrics}]}
assert check_browser_events(payload)[1] == payload["events"]
PYCODE
}
reconnect_contract() {
  python3 - "http://$host:$WEB_PORT" <<'PYCODE'
import json, re, sys, urllib.request, urllib.error
base = sys.argv[1]
# Inspect the installed bundle; source files are not part of a release.
page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
scripts = re.findall(r'<script[^>]+src="([^"]+)"', page)
bundle = "\n".join(urllib.request.urlopen(base + path, timeout=5).read().decode()
                   for path in scripts if path.startswith("/"))
origins = re.findall(r'(\w+)=`\$\{window\.location\.protocol\}//\$\{\w+\}`', bundle)
assert any(re.search(r"\buri:" + re.escape(name) + r"[,}]", bundle) for name in origins), "Installed video URI loses its page scheme"
with urllib.request.urlopen(base + "/api/v1/session/token", timeout=5) as response:
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert isinstance(json.load(response).get("token"), str)
with urllib.request.urlopen(base + "/api/v1/stream-diagnostics", timeout=5) as response:
    assert "attempts" in json.load(response)["signalling"]
# No reset is performed: an unauthenticated call must be refused.
request = urllib.request.Request(base + "/api/v1/stream/reset", data=b'{}',
                                 headers={"Content-Type": "application/json"})
try:
    urllib.request.urlopen(request, timeout=5)
    raise AssertionError("Unauthenticated stream reset accepted")
except urllib.error.HTTPError as error:
    assert error.code == 403
PYCODE
}
interactive_plugin_layer() {
  python3 - "http://$host:$WEB_PORT" <<'PYCODE'
import re, sys, urllib.request
base = sys.argv[1]
page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
scripts = re.findall(r'<script[^>]+src="([^"]+)"', page)
assert any("data-plugin-layer" in urllib.request.urlopen(base + path, timeout=5).read().decode()
           for path in scripts if path.startswith("/"))
PYCODE
}
plugin_inventory_contract() {
  python3 - "http://$host:$WEB_PORT" <<'PYCODE'
import re, sys, urllib.request
base = sys.argv[1]
page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
scripts = re.findall(r'<script[^>]+src="([^"]+)"', page)
bundle = "\n".join(urllib.request.urlopen(base + path, timeout=5).read().decode()
                   for path in scripts if path.startswith("/"))
for marker in ("inventory-table", "display_text", "inheritance", "#00ffff", "tablist", "tabpanel",
               "clamp(1px, calc(1vw - 2px), 4px)",
               "max(3px, env(safe-area-inset-left))", "max(3px, env(safe-area-inset-right))",
               "calc(100dvh - max(8px, env(safe-area-inset-top)) - max(8px, env(safe-area-inset-bottom)))",
               "aspectRatio"):
    assert marker in bundle, "Missing inventory/dialog renderer: " + marker
assert all(marker in bundle for marker in ("data-inventory-sprite", "data-inventory-stars", "data-inventory-element")), "Missing independent inventory sprite/badge layers"
PYCODE
}
connection_notice_contract() {
  python3 - "http://$host:$WEB_PORT" <<'PYCODE'
import re, sys, urllib.request
base = sys.argv[1]
page = urllib.request.urlopen(base + "/", timeout=5).read().decode()
scripts = re.findall(r'<script[^>]+src="([^"]+)"', page)
bundle = "\n".join(urllib.request.urlopen(base + path, timeout=5).read().decode()
                   for path in scripts if path.startswith("/"))
# Bundlers may escape accents; compare user-facing wording after decoding
# only JavaScript's fixed-width Unicode/hex character escapes.
bundle = re.sub(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
                lambda match: chr(int(match.group(1) or match.group(2), 16)), bundle)
for wording in ("Connexion au serveur", "Serveur connecté", "vidéo indisponible",
                "lecture vidéo bloquée", "Options et plugins", "Reconnecter la vidéo"):
    assert wording in bundle, "Missing connection/toolbar wording: " + wording
assert "data-cloudphone-notice" in bundle and "stateError" in bundle
with urllib.request.urlopen(base + "/api/v1/ping", timeout=2) as response:
    assert response.status == 204
    assert "no-store" in response.headers.get("Cache-Control", "")
PYCODE
}
gateway_command_lifecycle() {
  "$PREFIX/current/venv/bin/python" - <<'PYCODE'
import asyncio
from unittest.mock import patch
from videobridge_gateway.adapters import adb
from videobridge_gateway.plugins import Analysis, PluginContext, Screenshots

assert callable(PluginContext.screenshot_time)
assert callable(PluginContext.invalidate_screenshots)
assert callable(Screenshots.captured_at)
assert callable(PluginContext.detect)
assert callable(Analysis.close)
assert callable(Screenshots.stats)

async def check():
    capture_started, capture_finish = asyncio.Event(), asyncio.Event()
    async def capture():
        capture_started.set()
        await capture_finish.wait()
        return (1, 1, b"rgb")
    screenshots = Screenshots(capture)
    one = asyncio.create_task(screenshots.get("verify"))
    await capture_started.wait()
    two = asyncio.create_task(screenshots.get("verify"))
    await asyncio.sleep(0)
    capture_finish.set()
    assert await one is await two
    assert screenshots.counts == {"verify": 1}
    assert screenshots.stats()["joins"] == 1
    await screenshots.close()
    analysis = Analysis()
    assert await analysis.detector.run(lambda: "detector") == "detector"
    assert await analysis.resources.run(lambda: "resource") == "resource"
    await analysis.close()
    started, finish = asyncio.Event(), asyncio.Event()
    class Process:
        returncode = None
        async def communicate(self):
            started.set()
            await finish.wait()
            self.returncode = 0
            return b"", b""
    process = Process()
    async def create(*args, **kwargs):
        return process
    with patch.object(adb.asyncio, "create_subprocess_exec", create), patch.object(adb.logs, "adb_reached"):
        task = asyncio.create_task(adb.run("offline lifecycle check", timeout=1))
        await started.wait()
        task.cancel()
        for _ in range(3):
            await asyncio.sleep(0)
        drained_early = task.done()
        finish.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("command cancellation was lost")
        assert not drained_early and process.returncode == 0

asyncio.run(check())
PYCODE
}
listens_only_on() {
  local port=$1 addresses
  addresses=$(ss -Hltn | awk -v p=":$port" 'substr($4, length($4) - length(p) + 1) == p { print $4 }')
  [ "$addresses" = "$LISTEN_ADDRESS:$port" ]
}
# Drain the producer: grep -q can close the pipe early and make nft fail
# with SIGPIPE under pipefail, incorrectly reporting a missing rule.
nft_has() { nft list ruleset 2>/dev/null | grep -F "$1" >/dev/null; }

check "release $RELEASE_VERSION is the active one" cmp -s "$TREE/VERSION" "$PREFIX/current/VERSION"
check "cloudphone-gateway is enabled" systemctl is-enabled --quiet cloudphone-gateway.service
check "cloudphone-gateway is active" systemctl is-active --quiet cloudphone-gateway.service
check "no separate cloudphone-web service is left" test ! -e /etc/systemd/system/cloudphone-web.service
check "web page answers on $host:$WEB_PORT" answers "http://$host:$WEB_PORT/"
check "page serves interactive plugin overlay" interactive_plugin_layer
check "page renders inventory bonus text and shared tabbed plugin dialogs" plugin_inventory_contract
check "page distinguishes server reachability from missing video and keeps toolbar controls" connection_notice_contract
check "installed gateway drains cancelled commands and exposes capture timestamps" gateway_command_lifecycle
check "gateway answers on $host:$WEB_PORT" answers "http://$host:$WEB_PORT/api/v1/emulator/status"
check "gateway reports live CPU and memory" live_metrics
check "gateway reports bounded stream diagnostics" stream_diagnostics
check "reconnect exposes fresh tokens and attempt diagnostics with guarded reset" reconnect_contract
check "gateway serves its log records" bash -c \
  "curl -fsS --max-time 5 http://$host:$WEB_PORT/api/v1/logs | grep -q '\"records\"'"
check "gateway keeps its log records in $STATE/logs" bash -c \
  "[ \"\$(stat -c %U \"$STATE/logs\")\" = \"$SERVICE_USER\" ] && compgen -G \"$STATE/logs/records-*.jsonl*\" >/dev/null"
check "gateway's start record names release $RELEASE_VERSION" bash -c \
  "curl -fsS --max-time 5 'http://$host:$WEB_PORT/api/v1/logs?contains=Gateway%20started&limit=1' | grep -qF 'version $RELEASE_VERSION'"
check "gateway keeps the page's options on the server" bash -c \
  "curl -fsS --max-time 5 http://$host:$WEB_PORT/api/v1/settings | grep -q '\"available\": true'"
check "gateway logs to the journal as cloudphone-gateway" bash -c \
  "[ \"\$(systemctl show -p SyslogIdentifier --value cloudphone-gateway.service)\" = cloudphone-gateway ]"
check "page carries a token" bash -c "curl -fsS --max-time 5 http://$host:$WEB_PORT/ | grep -q 'name=\"cloudphone-token\"'"
check "a POST without the token is refused" bash -c \
  "[ \"\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST -d '{}' http://$host:$WEB_PORT/api/v1/emulator/key)\" = 403 ]"
check "stream diagnostics POST without the token is refused" bash -c \
  "[ \"\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST -H 'Content-Type: application/json' -d '{}' http://$host:$WEB_PORT/api/v1/stream-diagnostics/events)\" = 403 ]"
check "a request from another origin is refused" bash -c \
  "[ \"\$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -H 'Origin: http://example.com' http://$host:$WEB_PORT/api/v1/state)\" = 403 ]"
check "no CORS header is sent" bash -c \
  "! curl -fsSI --max-time 5 http://$host:$WEB_PORT/api/v1/ping | grep -qi '^access-control-allow-origin'"
if [ "$any_address" = no ]; then
  check "LISTEN_ADDRESS is a private address, not 0.0.0.0" test "$LISTEN_ADDRESS" != 0.0.0.0
  check "page and gateway listen only on $LISTEN_ADDRESS" listens_only_on "$WEB_PORT"
  check "firewall accepts TCP $WEB_PORT on wg0" nft_has "iifname \"wg0\" tcp dport $WEB_PORT "
  check "firewall accepts WebRTC media (UDP 32768-60999) on wg0" \
    nft_has 'iifname "wg0" udp dport 32768-60999'
fi

finish "Cloud Phone app is converged"
