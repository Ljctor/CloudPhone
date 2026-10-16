#!/usr/bin/env bash
# Authorizes one device on the WireGuard server, without restarting the
# tunnel of the other devices:
#   sudo add-peer.sh NAME PUBLIC_KEY ADDRESS
# e.g.
#   sudo add-peer.sh laptop 'base64-public-key=' 10.20.0.3
#
# Only the device's PUBLIC key is given here: generate the key pair on the
# device itself (the WireGuard app does it), so its private key never leaves
# it. Prints the configuration to enter on the device.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=common.sh
. "$HERE/common.sh"

[ $# -eq 3 ] || die "usage: $0 NAME PUBLIC_KEY ADDRESS"
name=$1 key=$2 peer_address=${3%/32}
[[ $name =~ ^[A-Za-z0-9._-]+$ ]] || die "NAME must be letters, digits, dot, dash or underscore"
valid_key "$key" || die "PUBLIC_KEY is not a WireGuard public key"
[[ $peer_address =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "ADDRESS expects an IPv4 address such as 10.20.0.3"
require_root
[ -f "$WG_CONF" ] || die "$WG_CONF is missing: run install.sh first"

server_cidr=$(awk -F' *= *' '$1 == "Address" { print $2; exit }' "$WG_CONF")
network=$(python3 -c 'import ipaddress, sys; print(ipaddress.ip_interface(sys.argv[1]).network)' "$server_cidr")
python3 -c 'import ipaddress, sys; sys.exit(ipaddress.ip_address(sys.argv[1]) not in ipaddress.ip_network(sys.argv[2]) or sys.argv[1] == sys.argv[3])' \
  "$peer_address" "$network" "${server_cidr%/*}" ||
  die "ADDRESS must be a free address of $network, other than the server's"
if grep -qF "$key" "$WG_CONF"; then
  die "this public key is already a peer"
fi
if grep -Eq "^AllowedIPs *= *${peer_address//./\\.}/32\$" "$WG_CONF"; then
  die "$peer_address is already used by another peer"
fi

backup "$WG_CONF"
cat >>"$WG_CONF" <<CONF

[Peer]
# $name
PublicKey = $key
AllowedIPs = $peer_address/32
CONF
wg set "$WG_INTERFACE" peer "$key" allowed-ips "$peer_address/32"

port=$(wg show "$WG_INTERFACE" listen-port)
cat <<DONE

Peer $name added. On the device, finish its tunnel with:

  [Interface]
  Address = $peer_address/32
  PrivateKey = (generated on the device)

  [Peer]
  PublicKey = $(wg show "$WG_INTERFACE" public-key)
  Endpoint = SERVER_PUBLIC_ADDRESS:$port
  AllowedIPs = $network
  PersistentKeepalive = 25
DONE
