#!/usr/bin/env bash
# Passive Android settings for an app that must keep running, after a human
# installed it from Google Play:
#   sudo 04-cloud-phone-app/scripts/commission.sh --check PACKAGE   # read-only
#   sudo 04-cloud-phone-app/scripts/commission.sh --apply PACKAGE
# Screen never turns off, PACKAGE is exempt from idle restrictions, and the
# time zone is TIMEZONE (default Europe/Paris). Nothing here launches or
# restarts the app: that is always a human decision.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"

mode=${1:-}
package=${2:-}
timezone=${TIMEZONE:-Europe/Paris}
if ! [[ $mode == --check || $mode == --apply ]] || ! [[ $package =~ ^[A-Za-z0-9_.]+$ ]]; then
  die "usage: $0 --check|--apply PACKAGE"
fi
require_root
load_conf

shell() { adb_cmd shell "$@" | tr -d '\r'; }
adb_was_running=no
ss -Hltn | awk '{ print $4 }' | grep -q ":$ANDROID_ADB_SERVER_PORT\$" && adb_was_running=yes
cleanup() {
  [ "$adb_was_running" = yes ] || as_service_user "$SDK/platform-tools/adb" kill-server >/dev/null 2>&1 || true
}
trap cleanup EXIT

[ "$(shell getprop sys.boot_completed)" = 1 ] || die "Android is not running"
shell pm path "$package" | grep -q '^package:' ||
  die "$package is not installed: install it from Google Play in the web page first"

if [ "$mode" = --apply ]; then
  shell settings put system screen_off_timeout 2147483647
  shell dumpsys deviceidle whitelist "+$package" >/dev/null
  shell am set-inactive "$package" false
  shell am set-standby-bucket "$package" active
  shell settings put global auto_time 1
  shell settings put global auto_time_zone 0
  shell cmd alarm set-timezone "$timezone"
fi

screen_on() { [ "$(shell settings get system screen_off_timeout)" = 2147483647 ]; }
idle_exempt() { shell dumpsys deviceidle whitelist | grep -qF ",$package,"; }
active_bucket() { [ "$(shell am get-standby-bucket "$package")" -le 10 ]; }
timezone_set() {
  [ "$(shell getprop persist.sys.timezone)" = "$timezone" ] &&
    [ "$(shell settings get global auto_time)" = 1 ] &&
    [ "$(shell settings get global auto_time_zone)" = 0 ]
}
no_watchdog() { ! systemctl list-unit-files | grep -qi watchdog; }

check "screen never turns off" screen_on
check "$package is exempt from Doze" idle_exempt
check "$package is in the active standby bucket" active_bucket
check "time zone is $timezone, network time on" timezone_set
check "no service relaunches apps automatically" no_watchdog
finish "Android is commissioned for $package"
