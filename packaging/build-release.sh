#!/usr/bin/env bash
# Builds the Cloud Phone release tarball:
#   dist/cloudphone-<VERSION>-linux-x86_64.tar.gz
#
# Needs: git, curl, node >= 18 with npm, python3 >= 3.10 with venv, make.
# Downloads are cached in build/cache and verified against versions.env.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PKG=$ROOT/packaging
# shellcheck source=versions.env
. "$PKG/versions.env"
VERSION=$(cat "$ROOT/VERSION")
BUILD=$ROOT/build
CACHE=$BUILD/cache
DIST=$ROOT/dist
NAME=cloudphone-$VERSION-linux-x86_64
STAGE=$BUILD/stage/$NAME
UPSTREAM=$BUILD/upstream
TARGET_PYTHONS=(3.10 3.11 3.12 3.13)
export npm_config_registry=${npm_config_registry:-https://registry.npmjs.org/}
SOURCE_DATE_EPOCH=$(git -C "$ROOT" log -1 --format=%ct 2>/dev/null || date +%s)
export SOURCE_DATE_EPOCH

refresh_constraints=no
run_tests=yes

usage() {
  cat <<EOF
Usage: packaging/build-release.sh [--skip-tests] [--refresh-constraints]

  --skip-tests            Do not run the JavaScript unit tests.
  --refresh-constraints   Resolve the newest gateway dependencies and rewrite
                          packaging/constraints.txt before packaging.
EOF
}

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case $1 in
    --skip-tests) run_tests=no ;;
    --refresh-constraints) refresh_constraints=yes ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

for tool in git curl node npm make python3 sha256sum tar gzip; do
  command -v "$tool" >/dev/null || die "missing build tool: $tool"
done
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 18 ] || die "Node.js 18 or newer is required"
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || die "Python 3.10 or newer is required"

# cached_fetch URL SHA256 FILENAME -> prints the cached path
cached_fetch() {
  local url=$1 sha=$2 file=$CACHE/$3
  mkdir -p "$CACHE"
  if ! printf '%s  %s\n' "$sha" "$file" | sha256sum -c --quiet - 2>/dev/null; then
    curl -fL --retry 3 --progress-bar -o "$file.part" "$url" >&2
    mv "$file.part" "$file"
    printf '%s  %s\n' "$sha" "$file" | sha256sum -c --quiet - ||
      die "checksum mismatch for ${url##*/}"
  fi
  printf '%s\n' "$file"
}

extract_zip() {
  python3 -m zipfile -e "$1" "$2"
}

log "Fetching upstream android-emulator-container-scripts at $UPSTREAM_COMMIT"
rm -rf "$UPSTREAM"
git init -q "$UPSTREAM"
git -C "$UPSTREAM" fetch -q --depth 1 "$UPSTREAM_REPO" "$UPSTREAM_COMMIT"
git -C "$UPSTREAM" checkout -q FETCH_HEAD
cp -R "$ROOT/apps/android-emulator-web/overlay/." "$UPSTREAM/"

log "Fetching protoc"
protoc_zip=$(cached_fetch "$PROTOC_URL" "$PROTOC_SHA256" "${PROTOC_URL##*/}")
rm -rf "$BUILD/protoc"
extract_zip "$protoc_zip" "$BUILD/protoc"
chmod 755 "$BUILD/protoc/bin/protoc"
# The upstream Makefile looks protoc up in PATH and expects the well-known
# types in /usr/local/include; this wrapper provides both.
mkdir -p "$BUILD/protoc/wrapper"
cat >"$BUILD/protoc/wrapper/protoc" <<EOF
#!/bin/sh
exec "$BUILD/protoc/bin/protoc" -I"$BUILD/protoc/include" "\$@"
EOF
chmod 755 "$BUILD/protoc/wrapper/protoc"

log "Building the web control page"
(
  cd "$UPSTREAM/js"
  npm ci --no-audit --no-fund
  PATH=$BUILD/protoc/wrapper:$PATH make protoc PYTHON=python3
  if [ "$run_tests" = yes ]; then
    npm test
  fi
  cd example
  npm ci --no-audit --no-fund
  npm run build
)

log "Building the streaming gateway"
emulator_zip=$(cached_fetch "$EMULATOR_URL" "$EMULATOR_SHA256" "${EMULATOR_URL##*/}")
# setup.py generates its gRPC stubs from the protos shipped with the pinned
# emulator, laid out as the Bazel workspace it expects.
protos=$BUILD/bazel-root/hardware/google/aemu/protos/services
rm -rf "$BUILD/bazel-root"
mkdir -p "$protos/emulator-controller" "$protos/webrtc"
python3 - "$emulator_zip" "$protos" <<'EOF'
import sys, zipfile
archive, protos = sys.argv[1:3]
with zipfile.ZipFile(archive) as z:
    for name, service in [("emulator_controller.proto", "emulator-controller"),
                          ("rtc_service_v2.proto", "webrtc"),
                          ("ice_config.proto", "webrtc")]:
        with open(f"{protos}/{service}/{name}", "wb") as out:
            out.write(z.read(f"emulator/lib/{name}"))
EOF
gateway=$UPSTREAM/gateway
# setuptools lists packages before the build hook generates the stubs, so the
# proto package must already exist or the stubs are left out of the wheel.
mkdir -p "$gateway/src/videobridge_gateway/proto"
touch "$gateway/src/videobridge_gateway/proto/__init__.py"
rm -rf "$BUILD/venv" "$BUILD/wheels"
python3 -m venv "$BUILD/venv"
"$BUILD/venv/bin/pip" install --quiet --disable-pip-version-check build
BAZEL_ROOT=$BUILD/bazel-root "$BUILD/venv/bin/python" -m build --wheel \
  --outdir "$BUILD/wheels" "$gateway"
wheel=$(ls "$BUILD"/wheels/*.whl)
wheel_files=$(python3 -m zipfile -l "$wheel")
for stub in emulator_controller_pb2 emulator_controller_pb2_grpc rtc_service_v2_pb2 ice_config_pb2; do
  [[ $wheel_files == *"videobridge_gateway/proto/$stub.py"* ]] ||
    die "the gateway wheel lacks proto/$stub.py"
done

if [ "$refresh_constraints" = yes ]; then
  log "Resolving the newest gateway dependencies"
  rm -rf "$BUILD/venv-resolve"
  python3 -m venv "$BUILD/venv-resolve"
  "$BUILD/venv-resolve/bin/pip" install --quiet --disable-pip-version-check "$wheel"
  {
    echo "# Runtime dependencies of the streaming gateway, as built and tested."
    echo "# Regenerate with packaging/build-release.sh --refresh-constraints."
    "$BUILD/venv-resolve/bin/pip" freeze --exclude goldfish-videobridge-gateway
  } >"$PKG/constraints.txt"
fi

log "Smoke-testing the gateway in a clean environment"
rm -rf "$BUILD/venv-smoke"
python3 -m venv "$BUILD/venv-smoke"
"$BUILD/venv-smoke/bin/pip" install --quiet --disable-pip-version-check \
  -c "$PKG/constraints.txt" "$wheel"
"$BUILD/venv-smoke/bin/python" -c 'import videobridge_gateway.gateway_server'
"$BUILD/venv-smoke/bin/videobridge-gateway" --help >/dev/null

log "Checking that binary wheels exist for Python ${TARGET_PYTHONS[*]}"
for py in "${TARGET_PYTHONS[@]}"; do
  rm -rf "$BUILD/wheel-check"
  "$BUILD/venv/bin/pip" download --quiet --disable-pip-version-check \
    --only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 \
    --python-version "$py" --no-deps -d "$BUILD/wheel-check" \
    -r <(grep -v '^#' "$PKG/constraints.txt") ||
    die "a pinned gateway dependency has no wheel for Python $py"
done

log "Assembling $NAME"
rm -rf "$BUILD/stage"
mkdir -p "$STAGE"/{etc,libexec,systemd,share/wheels,docs,licenses}
install -m 755 "$PKG/install.sh" "$PKG/uninstall.sh" "$STAGE/"
install -m 644 "$PKG/versions.env" "$ROOT/VERSION" "$STAGE/"
install -m 644 "$PKG/files/cloudphone.conf" "$STAGE/etc/"
install -m 644 "$ROOT/runbooks/phase-3-cloud-phone/assets/emulator_access.json" "$STAGE/etc/"
install -m 755 "$PKG"/files/libexec/* "$STAGE/libexec/"
install -m 644 "$PKG"/files/systemd/*.service "$STAGE/systemd/"
cp -R "$UPSTREAM/js/example/dist" "$STAGE/share/web"
install -m 644 "$wheel" "$STAGE/share/wheels/"
install -m 644 "$PKG/constraints.txt" "$STAGE/share/"
install -m 644 "$ROOT/docs/INSTALL.md" "$ROOT/docs/WIREGUARD.md" "$STAGE/docs/"
install -m 644 "$UPSTREAM/LICENSE" "$STAGE/licenses/android-emulator-container-scripts-LICENSE"
chmod -R u=rwX,go=rX "$STAGE/share" "$STAGE/docs" "$STAGE/licenses"

# Build machines leak their paths into bundles easily; a release must not.
rm -rf "$BUILD/wheel-scan"
extract_zip "$wheel" "$BUILD/wheel-scan"
if grep -rIlF -e "$HOME" -e "$BUILD" "$STAGE" "$BUILD/wheel-scan"; then
  die "the files above contain a build-machine path; refusing to package them"
fi

(cd "$STAGE" && find . -type f -print0 | sort -z | xargs -0 sha256sum) >"$BUILD/SHA256SUMS"
mv "$BUILD/SHA256SUMS" "$STAGE/SHA256SUMS"

log "Writing dist/$NAME.tar.gz"
mkdir -p "$DIST"
tar --sort=name --owner=0 --group=0 --numeric-owner --mtime="@$SOURCE_DATE_EPOCH" \
  -C "$BUILD/stage" -cf - "$NAME" | gzip -9n >"$DIST/$NAME.tar.gz"
(cd "$DIST" && sha256sum "$NAME.tar.gz" >"$NAME.tar.gz.sha256")
echo
du -h "$DIST/$NAME.tar.gz"
cat "$DIST/$NAME.tar.gz.sha256"
