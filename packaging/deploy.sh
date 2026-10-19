#!/bin/sh
# Builds nothing: stages the current release tarball on a server and runs the
# install scripts of the parts given (default: 04), listening on the
# WireGuard address:
#   packaging/deploy.sh [--force] SERVER [PART...]   e.g. packaging/deploy.sh myserver 03 04 05
# It refuses a tarball that build-release.sh built from another commit than
# the checkout's HEAD (a stale build); --force deploys it anyway.
# SERVER is an ssh destination (host alias or USER@HOST). AS_ROOT and the
# tarball choice are those of stage-release.sh. LISTEN overrides 10.20.0.1.
# A first install of part 03 asks to accept the Android SDK licences: run
# this from a terminal to answer, or set ACCEPT_ANDROID_SDK_LICENSE=yes after
# reading them.
set -eu

force=
[ "${1:-}" = --force ] && { force=1; shift; }
target=${1:?usage: $0 [--force] SERVER [PART...]}
shift
[ $# -gt 0 ] || set -- 04
root=$(cd "$(dirname "$0")/.." && pwd)

tarball=$root/dist/cloudphone-$(cat "$root/VERSION")-linux-x86_64.tar.gz
built=$(head -1 "$tarball.commit" 2>/dev/null || true)
head=$(git -C "$root" rev-parse HEAD 2>/dev/null || true)
if [ -z "$force" ] && [ -n "$head" ] && [ "$built" != "$head" ]; then
  echo "ERROR: $tarball was built from ${built:-an unknown commit}, not HEAD ($head):" >&2
  echo "run packaging/build-release.sh first, or pass --force" >&2
  exit 1
fi
if grep -q "uncommitted changes" "$tarball.commit" 2>/dev/null; then
  echo "WARNING: the tarball was built with uncommitted changes" >&2
fi
as_root=${AS_ROOT:-sudo -n -u master sudo -n}
listen=${LISTEN:-10.20.0.1}

release=$("$root/packaging/stage-release.sh" "$target")
for part in "$@"; do
  case $part in
    03)
      script=03-android-emulator/scripts/install.sh
      args=
      [ "${ACCEPT_ANDROID_SDK_LICENSE:-}" = yes ] && args=--accept-android-sdk-license
      ;;
    04) script=04-cloud-phone-app/scripts/install.sh; args="--listen $listen" ;;
    05) script=05-plugins/scripts/install.sh; args= ;;
    *) echo "ERROR: unknown part '$part' (03, 04 or 05)" >&2; exit 1 ;;
  esac
  echo "== part $part" >&2
  # A terminal lets install.sh ask its questions (licences).
  tty=-T
  [ -t 0 ] && tty=-t
  ssh -o BatchMode=yes $tty "$target" "$as_root $release/$script $args"
done
