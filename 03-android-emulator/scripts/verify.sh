#!/usr/bin/env bash
# Read-only acceptance test of part 03, run as root on the server:
#   sudo 03-android-emulator/scripts/verify.sh
# Exits 0 and prints PASS only when every invariant holds.
#
# Asking Android for its state needs an adb server on ANDROID_ADB_SERVER_PORT.
# If none is running, the script starts one and stops it before exiting.
set -uo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"
require_root
[ -f "$CONF" ] || die "$CONF is missing: part 03 is not installed"
load_conf

avd_config=$AVD_HOME/$AVD_NAME.avd/config.ini
emulator=$SDK/emulator/emulator
adb=$SDK/platform-tools/adb

pinned() {
  local home status
  home=$(mktemp -d)
  HOME=$home "$emulator" -version 2>/dev/null |
    grep -qF "Android emulator version $EMULATOR_VERSION.0 (build_id $EMULATOR_BUILD)"
  status=$?
  rm -rf "$home"
  return "$status"
}
in_kvm_group() { id -nG "$SERVICE_USER" | grep -qw kvm; }
# The emulator rewrites config.ini as "key = value" after the first boot.
ini() { grep -Eqx "${1//./\\.} *= *$2" "$avd_config"; }
loopback_only() {
  local port=$1 addresses
  addresses=$(ss -Hltn | awk -v p=":$port" 'substr($4, length($4) - length(p) + 1) == p { print $4 }')
  [ -n "$addresses" ] || return 1
  ! grep -Ev '^(127\.0\.0\.1|\[::1\]|\[::ffff:127\.0\.0\.1\]):' <<<"$addresses" | grep -q .
}
prop() { [ "$(adb_cmd shell "$1" 2>/dev/null | tr -d '\r')" = "$2" ]; }

check "host is x86-64 with /dev/kvm" test "$(uname -m)" = x86_64 -a -c /dev/kvm
check "account $SERVICE_USER is in group kvm" in_kvm_group
check "emulator is pinned to $EMULATOR_VERSION ($EMULATOR_BUILD)" pinned
check "adb is installed" test -x "$adb"
check "system image $SYSTEM_IMAGE is installed" test -d "$SDK/${SYSTEM_IMAGE//;//}"
check "AVD $AVD_NAME exists" test -f "$avd_config"
check "AVD uses the x86-64 Google Play image" ini abi.type x86_64
check "AVD screen is ${SCREEN_WIDTH}x${SCREEN_HEIGHT}" ini hw.lcd.width "$SCREEN_WIDTH"
check "AVD screen height" ini hw.lcd.height "$SCREEN_HEIGHT"
check "AVD density is $SCREEN_DENSITY" ini hw.lcd.density "$SCREEN_DENSITY"
check "AVD has a hardware keyboard" ini hw.keyboard yes
check "AVD belongs to $SERVICE_USER" test "$(stat -c %U:%G "$AVD_HOME/$AVD_NAME.avd")" = "$SERVICE_USER:$SERVICE_USER"
check "adb key is private" test "$(stat -c %a "$STATE/.android/adbkey")" = 600
check "gRPC access policy is root-owned" test "$(stat -c %U:%a "$CONF_DIR/emulator_access.json")" = root:644
check "cloudphone-emulator is enabled" systemctl is-enabled --quiet cloudphone-emulator.service
check "cloudphone-emulator is active" systemctl is-active --quiet cloudphone-emulator.service
check "screen size requests from the page are watched" systemctl is-active --quiet cloudphone-display.path
check "service does not skip adb authentication" bash -c '! systemctl cat cloudphone-emulator.service | grep -q -- -skip-adb-auth'
check "console port $EMULATOR_PORT is loopback-only" loopback_only "$EMULATOR_PORT"
check "gRPC port $GRPC_PORT is loopback-only" loopback_only "$GRPC_PORT"

adb_was_running=no
ss -Hltn | awk '{ print $4 }' | grep -q ":$ANDROID_ADB_SERVER_PORT\$" && adb_was_running=yes
check "Android finished booting" prop "getprop sys.boot_completed" 1
check "Android runs version 16" prop "getprop ro.build.version.release" 16
check "adb requires authorization" prop "getprop ro.adb.secure" 1
check "on-screen keyboard shows with the hardware keyboard" prop "settings get secure show_ime_with_hard_keyboard" 1
if [ "$adb_was_running" = no ]; then
  as_service_user "$adb" kill-server >/dev/null 2>&1 || true
fi

finish "Android Emulator is converged"
