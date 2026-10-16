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
listens_only_on() {
  local port=$1 addresses
  addresses=$(ss -Hltn | awk -v p=":$port" 'substr($4, length($4) - length(p) + 1) == p { print $4 }')
  [ "$addresses" = "$LISTEN_ADDRESS:$port" ]
}
nft_has() { nft list ruleset 2>/dev/null | grep -qF "$1"; }

check "release $RELEASE_VERSION is the active one" cmp -s "$TREE/VERSION" "$PREFIX/current/VERSION"
for unit in cloudphone-gateway cloudphone-web; do
  check "$unit is enabled" systemctl is-enabled --quiet "$unit.service"
  check "$unit is active" systemctl is-active --quiet "$unit.service"
done
check "web page answers on $host:$WEB_PORT" answers "http://$host:$WEB_PORT/"
check "gateway answers on $host:$GATEWAY_PORT" answers "http://$host:$GATEWAY_PORT/api/v1/emulator/status"
if [ "$any_address" = no ]; then
  check "LISTEN_ADDRESS is a private address, not 0.0.0.0" test "$LISTEN_ADDRESS" != 0.0.0.0
  check "web page listens only on $LISTEN_ADDRESS" listens_only_on "$WEB_PORT"
  check "gateway listens only on $LISTEN_ADDRESS" listens_only_on "$GATEWAY_PORT"
  check "firewall accepts TCP $WEB_PORT-$GATEWAY_PORT on wg0" \
    nft_has "iifname \"wg0\" tcp dport { $WEB_PORT, $GATEWAY_PORT }"
  check "firewall accepts WebRTC media (UDP 32768-60999) on wg0" \
    nft_has 'iifname "wg0" udp dport 32768-60999'
fi

finish "Cloud Phone app is converged"
