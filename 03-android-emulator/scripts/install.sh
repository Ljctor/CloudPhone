#!/usr/bin/env bash
# Installs Google's official Android Emulator, pinned and checksum-verified,
# with an Android 16 Google Play device (AVD), and runs it headless as the
# cloudphone-emulator systemd service.
#
# Re-running it converges in place. The Android disk (the AVD) is never
# recreated or deleted, and a running emulator is restarted only when the
# pinned emulator version changes.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
PART=$TREE/03-android-emulator
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"

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
start=yes
wait_boot=yes
emulator_changed=no

usage() {
  cat <<EOF
Usage: sudo 03-android-emulator/scripts/install.sh [options]

Installs or upgrades the Android Emulator $EMULATOR_VERSION (build $EMULATOR_BUILD)
and the cloudphone-emulator service.

Options:
  --accept-android-sdk-license  Accept the Android SDK licences without
                                prompting (you must have read them).
  --emulator-zip FILE           Use a local copy of the pinned emulator archive.
  --cmdline-tools-zip FILE      Use a local copy of the pinned command-line tools.
  --no-start                    Install and enable, but do not start the service.
  --no-wait                     Do not wait for Android to finish booting.
  -h, --help                    Show this help.
EOF
}

while [ $# -gt 0 ]; do
  case $1 in
    --accept-android-sdk-license) accept_license=yes ;;
    --emulator-zip) emulator_zip=$(realpath "${2:?--emulator-zip needs a file}"); shift ;;
    --cmdline-tools-zip) cmdline_tools_zip=$(realpath "${2:?--cmdline-tools-zip needs a file}"); shift ;;
    --no-start) start=no; wait_boot=no ;;
    --no-wait) wait_boot=no ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

require_root

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
    ca-certificates curl unzip python3 "$java_pkg" "${libs[@]}"

  local java_major=${java_pkg#openjdk-}
  java_major=${java_major%%-*}
  JAVA_HOME=/usr/lib/jvm/java-$java_major-openjdk-$(dpkg --print-architecture)
  [ -x "$JAVA_HOME/bin/java" ] || die "Java not found in $JAVA_HOME"
  export JAVA_HOME
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
  install -d -m 755 "$PREFIX" "$PREFIX/libexec" "$CONF_DIR"
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
    install -m 644 "$PART/files/cloudphone.conf" "$CONF"
  fi
  local access=$PART/files/emulator_access.json
  if [ ! -f "$CONF_DIR/emulator_access.json" ]; then
    install -m 644 "$access" "$CONF_DIR/emulator_access.json"
  elif ! cmp -s "$access" "$CONF_DIR/emulator_access.json"; then
    install -m 644 "$access" "$CONF_DIR/emulator_access.json.dist"
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

install_unit() {
  log "Installing the cloudphone-emulator service"
  install -m 755 "$PART/files/libexec/cloudphone-emulator" "$PREFIX/libexec/cloudphone-emulator"
  install -m 644 "$PART/files/systemd/cloudphone-emulator.service" \
    /etc/systemd/system/cloudphone-emulator.service
  install -m 644 "$TREE/lib/versions.env" "$PREFIX/versions.env"
  # Screen size changes requested from the web page: the gateway writes a
  # request, this root service checks it and runs set-resolution.sh, which
  # is installed with what it sources under $PREFIX/tools.
  install -d -m 755 "$PREFIX/tools/lib" "$PREFIX/tools/03-android-emulator/scripts" \
    "$PREFIX/tools/03-android-emulator/files"
  install -m 644 "$TREE/VERSION" "$PREFIX/tools/VERSION"
  install -m 644 "$TREE/lib/common.sh" "$TREE/lib/versions.env" "$PREFIX/tools/lib/"
  install -m 644 "$PART/files/cloudphone.conf" "$PREFIX/tools/03-android-emulator/files/"
  install -m 755 "$PART/scripts/set-resolution.sh" "$PREFIX/tools/03-android-emulator/scripts/"
  install -m 755 "$PART/files/libexec/cloudphone-display-apply" "$PREFIX/libexec/"
  install -m 644 "$PART/files/systemd/cloudphone-display.path" \
    "$PART/files/systemd/cloudphone-display.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable cloudphone-emulator.service >/dev/null
  systemctl enable --now cloudphone-display.path >/dev/null
}

start_emulator() {
  [ "$start" = yes ] || return 0
  if systemctl is-active --quiet cloudphone-emulator.service; then
    if [ "$emulator_changed" = no ]; then
      log "The emulator is already running; Android keeps running"
      return
    fi
    log "Restarting Android on the new emulator version"
  else
    check_ports_free "$EMULATOR_PORT" "$((EMULATOR_PORT + 1))" "$GRPC_PORT" "$ANDROID_ADB_SERVER_PORT"
    log "Starting the Android Emulator"
  fi
  systemctl restart cloudphone-emulator.service
}

wait_until_booted() {
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
  as_service_user "$SDK/platform-tools/adb" kill-server >/dev/null 2>&1 || true
  log "Android is running"
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
install_unit
start_emulator
wait_until_booted
