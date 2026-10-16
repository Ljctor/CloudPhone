#!/usr/bin/env bash
# Accepts the app's ports only on the WireGuard interface:
#   sudo 04-cloud-phone-app/scripts/firewall.sh --check   # read-only
#   sudo 04-cloud-phone-app/scripts/firewall.sh --apply
# TCP WEB_PORT (page and gateway) and UDP 32768-60999 (the WebRTC media). Uses 02-wireguard-server/scripts/nft-allow.sh.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"
require_root
[ -f "$CONF" ] || die "$CONF is missing: install part 03 first"
load_conf

tcp_rule="iifname \"wg0\" tcp dport $WEB_PORT ct state new accept"
udp_rule='iifname "wg0" udp dport 32768-60999 ct state new accept'

case ${1:-} in
  --check)
    status=0
    for rule in "$tcp_rule" "$udp_rule"; do
      if nft list ruleset | grep -qF -- "$rule"; then
        echo "ok    $rule"
      else
        echo "FAIL  $rule"
        status=1
      fi
    done
    exit "$status"
    ;;
  --apply)
    "$TREE/02-wireguard-server/scripts/nft-allow.sh" "cloudphone-web-$WEB_PORT" "$tcp_rule"
    "$TREE/02-wireguard-server/scripts/nft-allow.sh" cloudphone-webrtc "$udp_rule"
    ;;
  *) die "usage: $0 --check|--apply" ;;
esac
