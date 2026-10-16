#!/usr/bin/env bash
# Installs a WireGuard server interface (default wg0, 10.20.0.1/24, UDP 51820)
# and opens its UDP port in the host's nftables firewall.
#
# An existing interface configuration is never rewritten: on a converged
# server this script only makes sure the service runs and the port is open.
# Peers are added with add-peer.sh.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=common.sh
. "$HERE/common.sh"

address=10.20.0.1/24
port=51820

usage() {
  cat <<USAGE
Usage: sudo 02-wireguard-server/scripts/install.sh [--address CIDR] [--port PORT]

  --address CIDR  Server address and VPN network (default $address).
  --port PORT     Public UDP port (default $port).
  Set WG_INTERFACE to use another interface name than wg0.
USAGE
}

while [ $# -gt 0 ]; do
  case $1 in
    --address) address=${2:?--address needs a CIDR}; shift ;;
    --port) port=${2:?--port needs a number}; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done
[[ $address =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}/[0-9]{1,2}$ ]] || die "--address expects an IPv4 CIDR such as 10.20.0.1/24"
if ! [[ $port =~ ^[0-9]+$ ]] || [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
  die "--port expects a UDP port"
fi
require_root

log "Installing WireGuard"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends wireguard-tools nftables
install -m 644 /dev/stdin /etc/modules-load.d/wireguard.conf <<'MODULES'
wireguard
MODULES
modprobe wireguard

install -d -m 700 "$WG_DIR"
if [ -f "$WG_CONF" ]; then
  log "Keeping the existing $WG_CONF"
else
  log "Creating $WG_CONF"
  # The private key stays in its own root-only file and is never printed.
  if [ ! -f "$WG_DIR/server.key" ]; then
    (umask 077 && wg genkey >"$WG_DIR/server.key")
  fi
  (umask 077 && cat >"$WG_CONF" <<CONF
[Interface]
Address = $address
ListenPort = $port
PostUp = wg set %i private-key $WG_DIR/server.key
CONF
)
fi
chmod 600 "$WG_CONF"
chown root:root "$WG_CONF"

live_port=$(awk -F' *= *' '$1 == "ListenPort" { print $2; exit }' "$WG_CONF")
log "Opening UDP ${live_port:-$port} in the firewall"
"$HERE/nft-allow.sh" wireguard "udp dport ${live_port:-$port} ct state new accept"

log "Starting wg-quick@$WG_INTERFACE"
systemctl enable --now "wg-quick@$WG_INTERFACE.service"

cat <<DONE

WireGuard is running on $WG_INTERFACE.
  Server public key : $(wg show "$WG_INTERFACE" public-key)
  Public UDP port   : ${live_port:-$port}

Allow this UDP port in the hosting provider's network firewall too, if it has
one. Add a device with: sudo $HERE/add-peer.sh NAME PUBLIC_KEY ADDRESS
DONE
