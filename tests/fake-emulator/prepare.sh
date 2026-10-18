#!/usr/bin/env bash
# Prepares, under build/e2e/, what the end-to-end tests need to run the
# repository's gateway and page on the fake emulator:
#
#   build/e2e/web/                         the built page (index.html, assets/)
#   build/e2e/gateway/videobridge_gateway/ the gateway's sources (symlinks to
#                                          04-cloud-phone-app/src/overlay) and
#                                          its generated gRPC stubs
#   build/e2e/venv-gateway/                the gateway's dependencies, as pinned
#                                          in 04-cloud-phone-app/constraints.txt
#   build/e2e/venv-fake/                   the fake's (tests/fake-emulator/requirements.txt)
#   build/e2e/base/                        the upstream page sources, node_modules
#                                          and stubs, taken once from build/upstream
#
# The first run builds the page and the stubs with
# packaging/build-release.sh --skip-tests (one source of truth for the
# build; it needs node/npm and downloads the pinned emulator once, for its
# .proto files), then copies what it needs to build/e2e/base. Later runs
# do not use build/upstream at all, and only rebuild the page when the overlay's
# JavaScript changed, and are quick when nothing did. The tests run this
# script themselves; it is safe to run by hand.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
HERE=$ROOT/tests/fake-emulator
OUT=$ROOT/build/e2e
UPSTREAM=$ROOT/build/upstream
OVERLAY=$ROOT/04-cloud-phone-app/src/overlay
STUBS=$UPSTREAM/gateway/src/videobridge_gateway/proto
export npm_config_registry=${npm_config_registry:-https://registry.npmjs.org/}
export PIP_DISABLE_PIP_VERSION_CHECK=1

mkdir -p "$OUT"
exec 9>"$OUT/.lock"
flock 9

log() { printf '==> %s\n' "$*" >&2; }

# The upstream page (with its node_modules) and the gRPC stubs, from the
# release build, kept in build/e2e/base so that a later release build that
# wipes build/upstream does not disturb the tests. Taken once; delete
# build/e2e/base to take them again.
# CLOUDPHONE_E2E_NO_BUILD=1: fail instead of running the release build (two
# builds at once wipe each other's build directory).
BASE=$OUT/base
if [ ! -f "$BASE/.complete" ]; then
  if [ ! -d "$UPSTREAM/js/example/node_modules" ] || [ ! -f "$STUBS/emulator_controller_pb2.py" ]; then
    if [ "${CLOUDPHONE_E2E_NO_BUILD:-}" = 1 ]; then
      echo "prepare.sh: build/upstream is missing (run packaging/build-release.sh --skip-tests first)" >&2
      exit 1
    fi
    log "First build of the page and the gRPC stubs (packaging/build-release.sh --skip-tests)"
    "$ROOT/packaging/build-release.sh" --skip-tests >&2
  fi
  log "Taking the upstream page and stubs into $BASE"
  rm -rf "$BASE"
  mkdir -p "$BASE"
  # Hard links where possible: node_modules is large.
  cp -al "$UPSTREAM/js" "$BASE/js" 2>/dev/null || cp -R "$UPSTREAM/js" "$BASE/js"
  rm -rf "$BASE/js/example/dist"
  cp -R "$STUBS" "$BASE/proto"
  touch "$BASE/.complete"
  rm -f "$OUT/web.stamp"
fi

# The page, rebuilt when a file of the overlay's page changed.
newest=$(find "$OVERLAY/js" -type f -newer "$OUT/web.stamp" -print -quit 2>/dev/null || echo rebuild)
if [ ! -f "$OUT/web.stamp" ] || [ -n "$newest" ] || [ ! -f "$OUT/web/index.html" ]; then
  log "Building the page"
  rm -rf "$OUT/js"
  mkdir -p "$OUT/js"
  (cd "$BASE/js" && find . -path ./node_modules -prune -o -path ./example/node_modules -prune -o -type f -print0 \
    | cpio -0pdm --quiet "$OUT/js")
  ln -sfn "$BASE/js/node_modules" "$OUT/js/node_modules"
  ln -sfn "$BASE/js/example/node_modules" "$OUT/js/example/node_modules"
  cp -R "$OVERLAY/js/." "$OUT/js/"
  touch "$OUT/web.stamp.new"
  (cd "$OUT/js/example" && npm run build >&2)
  rm -rf "$OUT/web"
  cp -R "$OUT/js/example/dist" "$OUT/web"
  mv "$OUT/web.stamp.new" "$OUT/web.stamp"
fi

# The gateway's package: its sources from the overlay (edits take effect at
# the next start), the stubs from the build.
package=$OUT/gateway/videobridge_gateway
mkdir -p "$package"
: >"$package/__init__.py"
# Sources removed or renamed since the last run.
find "$package" -maxdepth 1 -type l ! -exec test -e {} \; -delete
for source in "$OVERLAY"/gateway/src/videobridge_gateway/*.py; do
  ln -sfn "$source" "$package/$(basename "$source")"
done
rm -rf "$package/proto"
cp -R "$BASE/proto" "$package/proto"

# Virtual environments, recreated when their pins change.
venv() {
  local dir=$1 requirements=$2 stamp
  stamp=$(sha256sum "$requirements" | cut -d' ' -f1)
  if [ "$(cat "$dir/.pins" 2>/dev/null)" != "$stamp" ]; then
    log "Installing $(basename "$dir") from $requirements"
    rm -rf "$dir"
    python3 -m venv "$dir"
    "$dir/bin/pip" install --quiet -r "$requirements" >&2
    echo "$stamp" >"$dir/.pins"
  fi
}
venv "$OUT/venv-gateway" "$ROOT/04-cloud-phone-app/constraints.txt"
venv "$OUT/venv-fake" "$HERE/requirements.txt"
