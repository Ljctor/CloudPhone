#!/usr/bin/env bash
# Removes one device from the WireGuard server, now and at the next boot:
#   sudo revoke-peer.sh PUBLIC_KEY
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=common.sh
. "$HERE/common.sh"

[ $# -eq 1 ] || die "usage: $0 PUBLIC_KEY"
key=$1
valid_key "$key" || die "PUBLIC_KEY is not a WireGuard public key"
require_root
[ -f "$WG_CONF" ] || die "$WG_CONF is missing"
grep -qF "$key" "$WG_CONF" || die "no peer with this public key in $WG_CONF"

backup "$WG_CONF"
python3 - "$WG_CONF" "$key" <<'PY'
import re, sys
path, key = sys.argv[1:3]
text = open(path).read()
# Sections start at a "[Name]" line; drop the [Peer] section holding the key.
sections = re.split(r"(?m)^(?=\[)", text)
kept = [s for s in sections
        if not (s.startswith("[Peer]")
                and re.search(r"(?m)^PublicKey *= *" + re.escape(key) + r" *$", s))]
if len(kept) != len(sections) - 1:
    sys.exit("expected exactly one [Peer] section with this key")
open(path, "w").write("".join(kept).rstrip("\n") + "\n")
PY
wg set "$WG_INTERFACE" peer "$key" remove
echo "Peer revoked."
