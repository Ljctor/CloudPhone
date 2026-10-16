#!/usr/bin/env bash
# Installs the whole Cloud Phone on one host: part 03 (Android Emulator), then
# part 04 (the streaming gateway and the web page). Part 02 (WireGuard) is
# separate: run 02-wireguard-server/scripts/install.sh first to keep the phone
# private.
#
# Re-running it upgrades in place. The Android disk (the AVD) is never
# recreated or deleted.
set -euo pipefail

TREE=$(cd "$(dirname "$0")" && pwd)

emulator_args=()
app_args=()

usage() {
  cat <<EOF
Usage: sudo ./install.sh [options]

Options:
  --accept-android-sdk-license  Accept the Android SDK licences without
                                prompting (you must have read them).
  --listen ADDRESS              Address for the web page and gateway, e.g. the
                                WireGuard address 10.20.0.1. Default 0.0.0.0.
  --emulator-zip FILE           Use a local copy of the pinned emulator archive.
  --cmdline-tools-zip FILE      Use a local copy of the pinned command-line tools.
  --no-start                    Install and enable, but do not start services.
  --no-wait                     Do not wait for Android to finish booting.
  -h, --help                    Show this help.
EOF
}

while [ $# -gt 0 ]; do
  case $1 in
    --accept-android-sdk-license) emulator_args+=("$1") ;;
    --emulator-zip|--cmdline-tools-zip)
      emulator_args+=("$1" "$(realpath "${2:?$1 needs a file}")"); shift ;;
    --listen) app_args+=("$1" "${2:?--listen needs an address}"); shift ;;
    --no-start|--no-wait) emulator_args+=("$1"); app_args+=("$1") ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; printf 'ERROR: unknown option: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

"$TREE/03-android-emulator/scripts/install.sh" "${emulator_args[@]}"
"$TREE/04-cloud-phone-app/scripts/install.sh" "${app_args[@]}"
