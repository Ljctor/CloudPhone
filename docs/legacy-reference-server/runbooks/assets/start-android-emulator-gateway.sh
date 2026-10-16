#!/bin/sh
set -eu

discovery=
while [ -z "$discovery" ]; do
  discovery=$(find /run/android-emulator/avd/running -maxdepth 1 -type f -name 'pid_*.ini' -print -quit 2>/dev/null || true)
  [ -n "$discovery" ] || sleep 1
done

exec /opt/android-emulator-web/gateway/venv/bin/videobridge-gateway \
  --port=8001 \
  --discovery_file="$discovery"
