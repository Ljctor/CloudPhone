# Shared by the install and verify scripts of 03-android-emulator and
# 04-cloud-phone-app. Source it from bash after setting TREE to the root of
# the repository checkout or of the unpacked release (they have the same
# layout).
# shellcheck shell=bash disable=SC2034  # variables used by the sourcing scripts

# shellcheck source=versions.env
. "$TREE/lib/versions.env"
RELEASE_VERSION=$(cat "$TREE/VERSION")

PREFIX=/opt/cloudphone
SDK=$PREFIX/android-sdk
STATE=/var/lib/cloudphone
AVD_HOME=$STATE/avd
CONF_DIR=/etc/cloudphone
CONF=$CONF_DIR/cloudphone.conf
SERVICE_USER=cloudphone

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"
}

# Reads the installed configuration, or the packaged defaults before the
# first installation.
load_conf() {
  local src=$CONF
  [ -f "$src" ] || src=$TREE/03-android-emulator/files/cloudphone.conf
  # shellcheck source=../03-android-emulator/files/cloudphone.conf
  . "$src"
  [[ $AVD_NAME =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid AVD_NAME: $AVD_NAME"
  ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5037}
}

as_service_user() {
  runuser -u "$SERVICE_USER" -- env HOME="$STATE" \
    ANDROID_ADB_SERVER_PORT="$ANDROID_ADB_SERVER_PORT" "$@"
}

adb_cmd() {
  as_service_user "$SDK/platform-tools/adb" -s "emulator-$EMULATOR_PORT" "$@"
}

# Accepts both "key=value" and the emulator's "key = value".
set_ini() {
  local file=$1 key=$2 value=$3
  local pattern="^${key//./\\.} *="
  if grep -Eq "$pattern" "$file"; then
    sed -Ei "s|$pattern.*|$key=$value|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

has_candidate() {
  local policy
  policy=$(apt-cache policy "$1" 2>/dev/null)
  [[ $policy == *"Candidate: "[0-9]* ]]
}

# Fails when one of the given TCP ports is already listening. Another program
# on one of our ports would make the page drive the wrong phone.
check_ports_free() {
  local listening port busy=()
  listening=$(ss -Hltn | awk '{ sub(/.*:/, "", $4); print $4 }')
  for port in "$@"; do
    if grep -qx "$port" <<<"$listening"; then
      busy+=("$port")
    fi
  done
  [ ${#busy[@]} -eq 0 ] ||
    die "TCP port(s) ${busy[*]} already in use by another program: choose free ports in $CONF (WEB_PORT, EMULATOR_PORT, GRPC_PORT, ANDROID_ADB_SERVER_PORT)"
}

# verify.sh helpers: each check prints one line and records failures, so a
# single run reports every unmet invariant.
failures=0
check() {
  local label=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'ok    %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    failures=$((failures + 1))
  fi
}

finish() {
  if [ "$failures" -eq 0 ]; then
    printf 'PASS: %s\n' "$1"
  else
    printf '%d check(s) failed\n' "$failures" >&2
    exit 1
  fi
}
