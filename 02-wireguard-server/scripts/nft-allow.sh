#!/usr/bin/env bash
# Adds one accept rule to the host's inbound nftables firewall, now and at
# every boot, without touching the existing rules:
#   sudo nft-allow.sh NAME 'RULE'
# e.g.
#   sudo nft-allow.sh wireguard 'udp dport 51820 ct state new accept'
#   sudo nft-allow.sh cloudphone-web 'iifname "wg0" tcp dport { 8000, 8001 } ct state new accept'
#
# The rule is stored in /etc/nftables.d/NAME.nft, included at the end of
# /etc/nftables.conf. Nothing changes when the rule is already active and
# persistent, wherever it was written.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=common.sh
. "$HERE/common.sh"

NFT_CONF=/etc/nftables.conf
NFT_DIR=/etc/nftables.d
INCLUDE="include \"$NFT_DIR/*.nft\""

[ $# -eq 2 ] || die "usage: $0 NAME 'RULE'"
name=$1 rule=$2
[[ $name =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "NAME must be lowercase letters, digits and dashes"
[[ $rule == *accept ]] || die "RULE must end with accept"
require_root
command -v nft >/dev/null || die "nftables is not installed"

read -r family table chain <<<"$(input_chain)" || true
[ -n "${chain:-}" ] ||
  die "no inbound firewall (an input chain with policy drop) is active: set one up first (01-server-system-setup runbook 06), or see 02-wireguard-server/README.md for ufw"

live() { nft list chain "$family" "$table" "$chain" | grep -qF -- "$rule"; }
persisted() { grep -rqsF -- "$rule" "$NFT_CONF" "$NFT_DIR"; }

if live && persisted; then
  echo "Already allowed: $rule"
  exit 0
fi

if ! persisted; then
  install -d -m 755 "$NFT_DIR"
  umask 022
  cat >"$NFT_DIR/$name.nft.new" <<NFT
# Managed by 02-wireguard-server/scripts/nft-allow.sh
table $family $table {
  chain $chain {
    $rule comment "$name"
  }
}
NFT
  nft -c -f "$NFT_DIR/$name.nft.new"
  mv "$NFT_DIR/$name.nft.new" "$NFT_DIR/$name.nft"
  if ! grep -qxF "$INCLUDE" "$NFT_CONF"; then
    backup "$NFT_CONF"
    printf '\n%s\n' "$INCLUDE" >>"$NFT_CONF"
  fi
  nft -c -f "$NFT_CONF"
  echo "Persisted in $NFT_DIR/$name.nft"
fi

if ! live; then
  nft add rule "$family" "$table" "$chain" "$rule" comment "\"$name\""
  echo "Active now: $rule"
fi
systemctl enable nftables.service >/dev/null 2>&1 || true
