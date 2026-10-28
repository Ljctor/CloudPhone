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
    python3 -c 'import json,sys; x=json.load(sys.stdin); assert x["schema_version"] == 1; assert {"emulator","android","channels","signalling","media"} <= x.keys(); assert {"active","recent","hardware_inputs"} <= x["signalling"].keys(); assert x["media"]["frames_observed"] is None'
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
gateway_command_lifecycle() {
  "$PREFIX/current/venv/bin/python" - <<'PYCODE'
import asyncio
from unittest.mock import patch
from videobridge_gateway.adapters import adb
from videobridge_gateway.plugins import PluginContext, Screenshots

assert callable(PluginContext.screenshot_time)
assert callable(Screenshots.captured_at)

async def check():
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
nft_has() { nft list ruleset 2>/dev/null | grep -qF "$1"; }

check "release $RELEASE_VERSION is the active one" cmp -s "$TREE/VERSION" "$PREFIX/current/VERSION"
check "cloudphone-gateway is enabled" systemctl is-enabled --quiet cloudphone-gateway.service
check "cloudphone-gateway is active" systemctl is-active --quiet cloudphone-gateway.service
check "no separate cloudphone-web service is left" test ! -e /etc/systemd/system/cloudphone-web.service
check "web page answers on $host:$WEB_PORT" answers "http://$host:$WEB_PORT/"
check "page serves interactive plugin overlay" interactive_plugin_layer
check "installed gateway drains cancelled commands and exposes capture timestamps" gateway_command_lifecycle
check "gateway answers on $host:$WEB_PORT" answers "http://$host:$WEB_PORT/api/v1/emulator/status"
check "gateway reports live CPU and memory" live_metrics
check "gateway reports bounded stream diagnostics" stream_diagnostics
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
