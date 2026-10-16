# Shared by the scripts of 02-wireguard-server. Source it from bash.
# shellcheck shell=bash disable=SC2034  # variables used by the sourcing scripts

WG_INTERFACE=${WG_INTERFACE:-wg0}
WG_DIR=/etc/wireguard
WG_CONF=$WG_DIR/$WG_INTERFACE.conf

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"
}

valid_key() {
  [[ $1 =~ ^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw480]=$ ]]
}

# Prints "FAMILY TABLE CHAIN" of the first input-hook chain whose policy is
# drop, i.e. the host's inbound firewall.
input_chain() {
  nft list chains 2>/dev/null | awk '
    $1 == "table" { family = $2; table = $3 }
    $1 == "chain" { chain = $2 }
    /hook input/ && /policy drop/ { print family, table, chain; exit }'
}

# Writes a backup next to FILE, readable only by root.
backup() {
  local file=$1 copy
  copy=$file.bak-$(date +%Y%m%d%H%M%S)
  cp -p -- "$file" "$copy"
  chmod 600 "$copy"
  printf 'Backup: %s\n' "$copy"
}
