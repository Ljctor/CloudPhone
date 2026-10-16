#!/usr/bin/env bash
# Read-only acceptance test of part 02, run as root on the server:
#   sudo 02-wireguard-server/scripts/verify.sh [--address CIDR] [--port PORT] [--no-peer]
# Exits 0 and prints PASS only when every invariant holds. --no-peer skips the
# "at least one device is authorized" check, for the step before adding one.
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=common.sh
. "$HERE/common.sh"

address=10.20.0.1/24
port=51820
need_peer=yes
while [ $# -gt 0 ]; do
  case $1 in
    --address) address=${2:?}; shift ;;
    --port) port=${2:?}; shift ;;
    --no-peer) need_peer=no ;;
    *) die "usage: $0 [--address CIDR] [--port PORT] [--no-peer]" ;;
  esac
  shift
done
require_root

failures=0
check() {
  local label=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'ok    %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    failures=$((failures + 1))
  fi
}
installed() { dpkg-query -W -f='${Status}' wireguard-tools | grep -qx 'install ok installed'; }
has_address() { ip -4 -o address show dev "$WG_INTERFACE" | grep -qF " $address "; }
has_peer() { [ -n "$(wg show "$WG_INTERFACE" peers)" ]; }
port_open() {
  read -r family table chain <<<"$(input_chain)"
  [ -n "${chain:-}" ] && nft list chain "$family" "$table" "$chain" | grep -Eq "udp dport $port .*accept"
}
udp_listening() { ss -Hlun | awk -v p=":$port" 'substr($4, length($4) - length(p) + 1) == p { f = 1 } END { exit !f }'; }

check "wireguard-tools is installed" installed
check "$WG_CONF is root-only" test "$(stat -c %U:%G:%a "$WG_CONF")" = root:root:600
check "wg-quick@$WG_INTERFACE is enabled" systemctl is-enabled --quiet "wg-quick@$WG_INTERFACE.service"
check "wg-quick@$WG_INTERFACE is active" systemctl is-active --quiet "wg-quick@$WG_INTERFACE.service"
check "$WG_INTERFACE has address $address" has_address
check "$WG_INTERFACE listens on UDP $port" test "$(wg show "$WG_INTERFACE" listen-port)" = "$port"
check "UDP $port is listening" udp_listening
[ "$need_peer" = no ] || check "at least one peer is authorized" has_peer
check "firewall accepts UDP $port" port_open

if [ "$failures" -eq 0 ]; then
  echo "PASS: WireGuard server is converged"
else
  printf '%d check(s) failed\n' "$failures" >&2
  exit 1
fi
