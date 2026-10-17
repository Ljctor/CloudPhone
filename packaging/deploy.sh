#!/bin/sh
# Builds nothing: stages the current release tarball on a server and runs the
# install scripts of the parts given (default: 04), listening on the
# WireGuard address:
#   packaging/deploy.sh SERVER [PART...]      e.g. packaging/deploy.sh myserver 03 04
# SERVER is an ssh destination (host alias or USER@HOST). AS_ROOT and the
# tarball choice are those of stage-release.sh. LISTEN overrides 10.20.0.1.
set -eu

target=${1:?usage: $0 SERVER [PART...]}
shift
[ $# -gt 0 ] || set -- 04
root=$(cd "$(dirname "$0")/.." && pwd)
as_root=${AS_ROOT:-sudo -n -u master sudo -n}
listen=${LISTEN:-10.20.0.1}

release=$("$root/packaging/stage-release.sh" "$target")
for part in "$@"; do
  case $part in
    03) script=03-android-emulator/scripts/install.sh; args= ;;
    04) script=04-cloud-phone-app/scripts/install.sh; args="--listen $listen" ;;
    *) echo "ERROR: unknown part '$part' (03 or 04)" >&2; exit 1 ;;
  esac
  echo "== part $part" >&2
  ssh -o BatchMode=yes "$target" "$as_root $release/$script $args"
done
