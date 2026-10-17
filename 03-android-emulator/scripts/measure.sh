#!/usr/bin/env bash
# Read-only performance sample of the running instance, run as root on the
# server while the app to measure is on screen and animating:
#   sudo 03-android-emulator/scripts/measure.sh [SECONDS]   (default 60)
# Prints one table: what was measured (screen, renderer, cores, memory,
# governor) and what it gave (the app's frame rate inside Android, the
# emulator's CPU, the host's free CPU, Android's swap).
#
# Change one setting between two runs, keep the same scene, and run nothing
# else on the host meanwhile: the table is only comparable that way.
# adb goes through the service user's adb server; if none is running the
# script stops rather than start one under another account.
set -uo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"
require_root
[ -f "$CONF" ] || die "$CONF is missing: part 03 is not installed"
load_conf

seconds=${1:-60}
[[ $seconds =~ ^[0-9]+$ ]] && [ "$seconds" -ge 10 ] || die "SECONDS must be a whole number, at least 10"

pgrep -u "$SERVICE_USER" -f "tcp:$ANDROID_ADB_SERVER_PORT" >/dev/null ||
  die "no adb server of $SERVICE_USER on port $ANDROID_ADB_SERVER_PORT: is the instance running?"
[ "$(adb_cmd shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] ||
  die "Android has not finished booting"

cgroup=/sys/fs/cgroup/system.slice/cloudphone-emulator.service
cpu_usec() { awk '$1 == "usage_usec" { print $2 }' "$cgroup/cpu.stat"; }
host_jiffies() { awk 'NR == 1 { idle = $5 + $6; total = 0; for (i = 2; i <= NF; i++) total += $i; print idle, total }' /proc/stat; }
swap_used_mb() {
  adb_cmd shell cat /proc/meminfo | tr -d '\r' |
    awk '/^SwapTotal:/ { t = $2 } /^SwapFree:/ { f = $2 } END { printf "%d", (t - f) / 1024 }'
}

size=$(adb_cmd shell wm size | tr -d '\r' | awk -F': ' '/Override size/ { o = $2 } /Physical size/ { p = $2 } END { print (o ? o " (override of " p ")" : p) }')
app=$(adb_cmd shell dumpsys window | tr -d '\r' | sed -n 's/.*mCurrentFocus=Window{[^ ]* [^ ]* \([^/}]*\).*/\1/p' | head -n 1)
governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)
swap_before=$(swap_used_mb)

adb_cmd shell dumpsys SurfaceFlinger --timestats -clear -enable >/dev/null
read -r idle0 total0 < <(host_jiffies)
usec0=$(cpu_usec)
start=$(date +%s.%N)
sleep "$seconds"
usec1=$(cpu_usec)
read -r idle1 total1 < <(host_jiffies)
end=$(date +%s.%N)
stats=$(adb_cmd shell dumpsys SurfaceFlinger --timestats -dump -maxlayers 1 | tr -d '\r')
adb_cmd shell dumpsys SurfaceFlinger --timestats -disable >/dev/null
swap_after=$(swap_used_mb)
top_thread=$(adb_cmd shell top -H -b -d 3 -n 2 -m 1 | tr -d '\r' | tail -n 1 | awk '{ print $(NF-1) " " $9 "%" }')

fps=$(printf '%s\n' "$stats" | awk -F' = ' '/^layerName/ { l = 1 } l && /^averageFPS/ { print $2; exit }')
layer=$(printf '%s\n' "$stats" | awk -F' = ' '/^layerName/ { print $2; exit }')
elapsed=$(awk -v a="$start" -v b="$end" 'BEGIN { print b - a }')
emulator_cores=$(awk -v a="$usec0" -v b="$usec1" -v s="$elapsed" 'BEGIN { printf "%.1f", (b - a) / 1e6 / s }')
host_free=$(awk -v i0="$idle0" -v i1="$idle1" -v t0="$total0" -v t1="$total1" 'BEGIN { printf "%d", 100 * (i1 - i0) / (t1 - t0) }')

printf '%-22s %s\n' \
  "date" "$(date '+%F %T')" \
  "duration" "${seconds} s" \
  "app in focus" "${app:-unknown}" \
  "measured layer" "${layer:-none}" \
  "screen" "$size" \
  "renderer" "${EMULATOR_GPU:-unknown}" \
  "emulator cores" "${EMULATOR_CORES:-unknown}" \
  "emulator memory" "${EMULATOR_MEMORY_MB:-unknown} MiB" \
  "host governor" "$governor" \
  "app frames/s" "${fps:-none (nothing drew)}" \
  "emulator CPU" "$emulator_cores cores" \
  "host CPU free" "$host_free %" \
  "Android swap used" "${swap_before} -> ${swap_after} MiB" \
  "busiest guest thread" "${top_thread:-unknown}"
