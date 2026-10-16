#!/usr/bin/env bash
# Cloud Phone installer: official Android Emulator + WebRTC streaming gateway
# + mobile web control page, run as systemd services.
#
# Re-running it upgrades in place. The Android disk (the AVD) is never
# recreated or deleted.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=versions.env
. "$HERE/versions.env"
RELEASE_VERSION=$(cat "$HERE/VERSION")

PREFIX=/opt/cloudphone
SDK=$PREFIX/android-sdk
STATE=/var/lib/cloudphone
AVD_HOME=$STATE/avd
CONF_DIR=/etc/cloudphone
CONF=$CONF_DIR/cloudphone.conf
SERVICE_USER=cloudphone
UNITS=(cloudphone-emulator cloudphone-gateway cloudphone-web)
# Shared libraries the emulator's binaries link against without bundling them,
# found with readelf over the pinned build. Debian 13 and Ubuntu 24.04 renamed
# some of them with a t64 suffix; resolve_package handles that.
EMULATOR_LIBS=(libgl1 libpulse0 libx11-6 libxcb1 libxcomposite1 libxcursor1
  libxdamage1 libxext6 libxfixes3 libxi6 libxkbcommon0 libxrandr2 libxrender1
  libxtst6 libnss3 libxkbfile1 libdrm2 libpng16-16 libgbm1 libice6 libsm6
  libbsd0 libexpat1 libdbus-1-3)

accept_license=no
emulator_zip=
cmdline_tools_zip=
listen=
start=yes
wait_boot=yes
emulator_changed=no

usage() {
  cat <<EOF
Usage: sudo ./install.sh [options]

Installs or upgrades Cloud Phone $RELEASE_VERSION.

Options:
  --accept-android-sdk-license  Accept the Android SDK licences without
                                prompting (you must have read them).
  --listen ADDRESS              Address for the web UI and gateway, e.g. the
                                WireGuard address 10.20.0.1. Default 0.0.0.0.
  --emulator-zip FILE           Use a local copy of the pinned emulator archive.
  --cmdline-tools-zip FILE      Use a local copy of the pinned command-line tools.
  --no-start                    Install and enable, but do not start services.
  --no-wait                     Do not wait for Android to finish booting.
  -h, --help                    Show this help.
EOF
}

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case $1 in
    --accept-android-sdk-license) accept_license=yes ;;
    --listen) listen=${2:?--listen needs an address}; shift ;;
    --emulator-zip) emulator_zip=$(realpath "${2:?--emulator-zip needs a file}"); shift ;;
    --cmdline-tools-zip) cmdline_tools_zip=$(realpath "${2:?--cmdline-tools-zip needs a file}"); shift ;;
    --no-start) start=no; wait_boot=no ;;
    --no-wait) wait_boot=no ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

[ -z "$listen" ] || [[ $listen =~ ^[0-9A-Fa-f:.]+$ ]] || die "--listen expects an IP address"
[ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"

as_service_user() {
  runuser -u "$SERVICE_USER" -- env HOME="$STATE" \
    ANDROID_ADB_SERVER_PORT="$ANDROID_ADB_SERVER_PORT" "$@"
}

adb_cmd() {
  as_service_user "$SDK/platform-tools/adb" -s "emulator-$EMULATOR_PORT" "$@"
}

# fetch URL SHA256 DEST [LOCAL_COPY]
fetch() {
  local url=$1 sha=$2 dest=$3 local_copy=${4:-}
  if [ -n "$local_copy" ]; then
    cp -- "$local_copy" "$dest"
  else
    curl -fL --retry 3 --progress-bar -o "$dest" "$url"
  fi
  printf '%s  %s\n' "$sha" "$dest" | sha256sum -c --quiet - ||
    die "checksum mismatch for ${url##*/}: refusing to install it"
}

set_ini() {
  local file=$1 key=$2 value=$3
  if grep -q "^$key=" "$file"; then
    sed -i "s|^$key=.*|$key=$value|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >>"$file"
  fi
}

load_conf() {
  local src=$CONF
  [ -f "$src" ] || src=$HERE/etc/cloudphone.conf
  # shellcheck source=files/cloudphone.conf
  . "$src"
  [[ $AVD_NAME =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid AVD_NAME: $AVD_NAME"
  ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5037}
  GATEWAY_PORT=$((WEB_PORT + 1))
}

preflight() {
  log "Checking the host"
  [ "$(uname -m)" = x86_64 ] || die "an x86-64 host is required"
  [ -d /run/systemd/system ] || die "systemd is required"
  command -v apt-get >/dev/null || die "a Debian or Ubuntu host (apt-get) is required"
  [ -c /dev/kvm ] || die "/dev/kvm is missing: enable hardware virtualization (VT-x/AMD-V), or nested virtualization on a VM"
  getent group kvm >/dev/null || die "the kvm group does not exist"

  local cores mem_mb
  cores=$(nproc)
  [ "$cores" -ge "$EMULATOR_CORES" ] ||
    die "EMULATOR_CORES=$EMULATOR_CORES but the host has $cores CPU cores"
  mem_mb=$(awk '/MemTotal:/ { print int($2 / 1024) }' /proc/meminfo)
  [ "$mem_mb" -ge "$EMULATOR_MEMORY_MB" ] ||
    die "EMULATOR_MEMORY_MB=$EMULATOR_MEMORY_MB but the host has $mem_mb MiB of RAM"
  [ "$mem_mb" -ge $((EMULATOR_MEMORY_MB + 2048)) ] ||
    warn "only $mem_mb MiB of RAM: keep at least 2 GiB free beyond the emulator's $EMULATOR_MEMORY_MB MiB"

  mkdir -p /opt /var/lib
  local opt_kb var_kb
  opt_kb=$(df -Pk /opt | awk 'NR == 2 { print $4 }')
  var_kb=$(df -Pk /var/lib | awk 'NR == 2 { print $4 }')
  if [ "$(stat -c %d /opt)" = "$(stat -c %d /var/lib)" ]; then
    [ "$opt_kb" -ge $((15 * 1024 * 1024)) ] || [ -d "$SDK/emulator" ] ||
      die "at least 15 GiB of free disk space is required"
  else
    [ "$opt_kb" -ge $((8 * 1024 * 1024)) ] || [ -d "$SDK/emulator" ] ||
      die "at least 8 GiB must be free under /opt"
    [ "$var_kb" -ge $((8 * 1024 * 1024)) ] || [ -d "$AVD_HOME" ] ||
      die "at least 8 GiB must be free under /var/lib"
  fi
}

has_candidate() {
  local policy
  policy=$(apt-cache policy "$1" 2>/dev/null)
  [[ $policy == *"Candidate: "[0-9]* ]]
}

# Prints the installable name of a library package: NAME, or NAMEt64 on
# releases that renamed it.
resolve_package() {
  if has_candidate "$1"; then
    printf '%s\n' "$1"
  elif has_candidate "${1}t64"; then
    printf '%s\n' "${1}t64"
  else
    die "package $1 is not available on this system"
  fi
}

install_packages() {
  log "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  local java_pkg='' candidate
  for candidate in openjdk-21-jre-headless openjdk-17-jre-headless; do
    if has_candidate "$candidate"; then
      java_pkg=$candidate
      break
    fi
  done
  [ -n "$java_pkg" ] || die "no OpenJDK 17 or 21 package is available (needed by sdkmanager)"
  local libs=() lib resolved
  for lib in "${EMULATOR_LIBS[@]}"; do
    resolved=$(resolve_package "$lib") || exit 1
    libs+=("$resolved")
  done
  apt-get install -y --no-install-recommends \
    ca-certificates curl unzip python3 python3-venv "$java_pkg" "${libs[@]}"

  local java_major=${java_pkg#openjdk-}
  java_major=${java_major%%-*}
  JAVA_HOME=/usr/lib/jvm/java-$java_major-openjdk-$(dpkg --print-architecture)
  [ -x "$JAVA_HOME/bin/java" ] || die "Java not found in $JAVA_HOME"
  export JAVA_HOME

  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' ||
    die "Python 3.10 or newer is required"
}

ensure_user() {
  log "Preparing the $SERVICE_USER service account"
  if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$STATE" --no-create-home \
      --shell /usr/sbin/nologin "$SERVICE_USER"
  fi
  usermod -aG kvm "$SERVICE_USER"
  install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE"
  install -d -m 700 -o "$SERVICE_USER" -g "$SERVICE_USER" "$AVD_HOME" "$STATE/.android"
  install -d -m 755 "$PREFIX" "$PREFIX/releases" "$CONF_DIR"
}

accept_licenses() {
  local sdkmanager=$1
  if [ "$accept_license" = yes ]; then
    set +o pipefail
    yes | HOME=$WORK "$sdkmanager" --sdk_root="$SDK" --licenses >/dev/null
    local status=${PIPESTATUS[1]}
    set -o pipefail
    [ "$status" -eq 0 ] || die "sdkmanager could not record the licence acceptance"
  elif [ -t 0 ]; then
    log "Review and accept the Android SDK licences"
    HOME=$WORK "$sdkmanager" --sdk_root="$SDK" --licenses
  else
    die "the Android SDK licences must be accepted: run interactively, or pass --accept-android-sdk-license after reading them"
  fi
}

emulator_is_pinned() {
  [ -x "$SDK/emulator/emulator" ] || return 1
  local version
  version=$(HOME=$WORK "$SDK/emulator/emulator" -version 2>/dev/null || true)
  [[ $version == *"Android emulator version $EMULATOR_VERSION.0 (build_id $EMULATOR_BUILD)"* ]]
}

install_sdk() {
  local sdkmanager=$SDK/cmdline-tools/latest/bin/sdkmanager
  install -d -m 755 "$SDK" "$SDK/cmdline-tools"
  if [ ! -x "$sdkmanager" ]; then
    log "Installing the Android command-line tools"
    fetch "$CMDLINE_TOOLS_URL" "$CMDLINE_TOOLS_SHA256" "$WORK/cmdline-tools.zip" "$cmdline_tools_zip"
    unzip -q "$WORK/cmdline-tools.zip" -d "$WORK"
    rm -rf "$SDK/cmdline-tools/latest"
    mv "$WORK/cmdline-tools" "$SDK/cmdline-tools/latest"
  fi

  local packages=()
  [ -x "$SDK/platform-tools/adb" ] || packages+=(platform-tools)
  [ -f "$SDK/emulator/package.xml" ] || packages+=(emulator)
  [ -d "$SDK/${SYSTEM_IMAGE//;//}" ] || packages+=("$SYSTEM_IMAGE")
  if [ ${#packages[@]} -gt 0 ]; then
    accept_licenses "$sdkmanager"
    log "Downloading ${packages[*]} (the system image is several GB)"
    HOME=$WORK "$sdkmanager" --sdk_root="$SDK" "${packages[@]}"
  fi

  if emulator_is_pinned; then
    return
  fi
  log "Installing the pinned Android Emulator $EMULATOR_VERSION (build $EMULATOR_BUILD)"
  fetch "$EMULATOR_URL" "$EMULATOR_SHA256" "$WORK/emulator.zip" "$emulator_zip"
  unzip -q "$WORK/emulator.zip" -d "$WORK/emu"
  # Keep the package.xml written by sdkmanager so the SDK stays consistent,
  # with its revision set to the pinned version.
  python3 - "$SDK/emulator/package.xml" "$WORK/emu/emulator/package.xml" "$EMULATOR_VERSION" <<'EOF'
import re, sys
src, dst, version = sys.argv[1:4]
major, minor, micro = version.split(".")
xml = open(src).read()
xml, count = re.subn(
    r"<revision>.*?</revision>",
    f"<revision><major>{major}</major><minor>{minor}</minor><micro>{micro}</micro></revision>",
    xml, count=1, flags=re.S)
if count != 1:
    sys.exit("package.xml: no <revision> element found")
open(dst, "w").write(xml)
EOF
  rm -rf "$SDK/emulator.previous"
  mv "$SDK/emulator" "$SDK/emulator.previous"
  mv "$WORK/emu/emulator" "$SDK/emulator"
  rm -rf "$SDK/emulator.previous"
  emulator_is_pinned || die "the pinned emulator does not report version $EMULATOR_VERSION"
  emulator_changed=yes
}

install_config() {
  log "Installing configuration"
  if [ ! -f "$CONF" ]; then
    install -m 644 "$HERE/etc/cloudphone.conf" "$CONF"
  fi
  if [ -n "$listen" ]; then
    set_ini "$CONF" LISTEN_ADDRESS "$listen"
  fi
  if [ ! -f "$CONF_DIR/emulator_access.json" ]; then
    install -m 644 "$HERE/etc/emulator_access.json" "$CONF_DIR/emulator_access.json"
  elif ! cmp -s "$HERE/etc/emulator_access.json" "$CONF_DIR/emulator_access.json"; then
    install -m 644 "$HERE/etc/emulator_access.json" "$CONF_DIR/emulator_access.json.dist"
    warn "kept your $CONF_DIR/emulator_access.json; the packaged version is in emulator_access.json.dist"
  fi
  load_conf
}

create_avd() {
  local avd_dir=$AVD_HOME/$AVD_NAME.avd
  if [ -f "$avd_dir/config.ini" ]; then
    log "Keeping the existing Android device $AVD_NAME"
    return
  fi
  log "Creating the Android device $AVD_NAME"
  printf 'no\n' | HOME=$WORK ANDROID_SDK_ROOT=$SDK ANDROID_AVD_HOME=$AVD_HOME \
    "$SDK/cmdline-tools/latest/bin/avdmanager" create avd \
    --name "$AVD_NAME" --package "$SYSTEM_IMAGE"
  local config=$avd_dir/config.ini
  set_ini "$config" hw.lcd.width "$SCREEN_WIDTH"
  set_ini "$config" hw.lcd.height "$SCREEN_HEIGHT"
  set_ini "$config" hw.lcd.density "$SCREEN_DENSITY"
  set_ini "$config" hw.keyboard yes
  set_ini "$config" hw.keyboard.lid yes
  chown -R "$SERVICE_USER:$SERVICE_USER" "$AVD_HOME"
}

ensure_adb_key() {
  # The emulator authorizes the public key of the user running it, and the
  # gateway sends hardware keys through adb as that same user.
  if [ ! -f "$STATE/.android/adbkey" ]; then
    as_service_user "$SDK/platform-tools/adb" keygen "$STATE/.android/adbkey" >/dev/null
  fi
  chmod 600 "$STATE/.android/adbkey"
}

install_release() {
  log "Installing Cloud Phone $RELEASE_VERSION"
  local release
  release=$PREFIX/releases/$RELEASE_VERSION-$(date +%Y%m%d%H%M%S)
  install -d -m 755 "$release"
  cp -R "$HERE/share/web" "$release/web"
  cp -R "$HERE/libexec" "$release/libexec"
  chmod -R u=rwX,go=rX "$release"
  chmod 755 "$release"/libexec/*
  python3 -m venv "$release/venv"
  "$release/venv/bin/pip" install --quiet --disable-pip-version-check \
    -c "$HERE/share/constraints.txt" "$HERE"/share/wheels/*.whl
  install -m 644 "$HERE/VERSION" "$HERE/versions.env" "$release/"

  ln -sfn "$release" "$PREFIX/current.new"
  mv -T "$PREFIX/current.new" "$PREFIX/current"

  # Keep the active release and the one before it, for a manual rollback.
  local old
  while IFS= read -r old; do
    rm -rf "$old"
  done < <(find "$PREFIX/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
    sort -rn | tail -n +3 | cut -d' ' -f2-)
}

install_units() {
  log "Installing systemd services"
  local unit
  for unit in "${UNITS[@]}"; do
    install -m 644 "$HERE/systemd/$unit.service" "/etc/systemd/system/$unit.service"
  done
  systemctl daemon-reload
  systemctl enable "${UNITS[@]/%/.service}" >/dev/null
}

# Another program on one of our ports would make the page drive the wrong
# phone, so refuse to start rather than share them.
check_ports_free() {
  local unit
  for unit in "${UNITS[@]}"; do
    systemctl is-active --quiet "$unit.service" && return 0
  done
  local listening port busy=()
  listening=$(ss -Hltn | awk '{ sub(/.*:/, "", $4); print $4 }')
  for port in "$WEB_PORT" "$GATEWAY_PORT" "$EMULATOR_PORT" "$((EMULATOR_PORT + 1))" \
    "$GRPC_PORT" "$ANDROID_ADB_SERVER_PORT"; do
    if grep -qx "$port" <<<"$listening"; then
      busy+=("$port")
    fi
  done
  [ ${#busy[@]} -eq 0 ] ||
    die "TCP port(s) ${busy[*]} already in use by another program: choose free ports in $CONF (WEB_PORT, EMULATOR_PORT, GRPC_PORT, ANDROID_ADB_SERVER_PORT)"
}

start_services() {
  [ "$start" = yes ] || return 0
  check_ports_free
  if systemctl is-active --quiet cloudphone-emulator.service && [ "$emulator_changed" = no ]; then
    log "Restarting the streaming services (Android keeps running)"
    systemctl restart cloudphone-gateway.service cloudphone-web.service
  else
    log "Starting Cloud Phone"
    systemctl restart "${UNITS[@]/%/.service}"
  fi
}

wait_until_ready() {
  [ "$wait_boot" = yes ] || return 0
  log "Waiting for Android to boot (the first boot can take several minutes)"
  local deadline=$((SECONDS + 900))
  until [ "$(adb_cmd shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do
    [ $SECONDS -lt $deadline ] ||
      die "Android did not finish booting in 15 minutes: journalctl -u cloudphone-emulator"
    systemctl is-active --quiet cloudphone-emulator.service ||
      die "the emulator stopped: journalctl -u cloudphone-emulator"
    sleep 5
  done
  adb_cmd shell settings put secure show_ime_with_hard_keyboard 1

  local host=$LISTEN_ADDRESS
  [ "$host" != 0.0.0.0 ] || host=127.0.0.1
  deadline=$((SECONDS + 60))
  until curl -fsS "http://$host:$WEB_PORT/" >/dev/null 2>&1 &&
    curl -fsS "http://$host:$GATEWAY_PORT/api/v1/emulator/status" >/dev/null 2>&1; do
    [ $SECONDS -lt $deadline ] ||
      die "the web UI or the gateway is not answering: journalctl -u cloudphone-gateway -u cloudphone-web"
    sleep 2
  done
  as_service_user "$SDK/platform-tools/adb" kill-server >/dev/null 2>&1 || true
}

summary() {
  local host=$LISTEN_ADDRESS
  [ "$host" != 0.0.0.0 ] || host='<this-server-address>'
  cat <<EOF

Cloud Phone $RELEASE_VERSION is installed.

  Web control page : http://$host:$WEB_PORT/
  Configuration    : $CONF
  Android data     : $AVD_HOME  (back it up; never deleted by upgrades)
  Logs             : journalctl -u cloudphone-emulator -u cloudphone-gateway -u cloudphone-web

EOF
  if [ "$LISTEN_ADDRESS" = 0.0.0.0 ]; then
    cat <<EOF
SECURITY: the web UI and gateway listen on every interface and have no login.
Do not expose ports $WEB_PORT, $GATEWAY_PORT and UDP 32768-60999 to the internet.
Follow docs/WIREGUARD.md to reach the phone only through a VPN.

EOF
  fi
}

load_conf
preflight
install_packages
ensure_user
WORK=$(mktemp -d "$PREFIX/.install.XXXXXX")
trap 'rm -rf "$WORK"' EXIT
install_sdk
install_config
create_avd
ensure_adb_key
install_release
install_units
start_services
wait_until_ready
summary
