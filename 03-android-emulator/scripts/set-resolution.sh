#!/usr/bin/env bash
# Changes Android's screen size, then reboots Android (data is kept):
#   sudo 03-android-emulator/scripts/set-resolution.sh WIDTH HEIGHT DENSITY
# e.g. 360 780 160 (light) or 540 1170 240 (default). Fewer pixels means
# less CPU for software rendering and video encoding.
#
# Updates the AVD's config.ini and SCREEN_* in cloudphone.conf (a backup of
# both is kept), restarts cloudphone-emulator and, if installed, the gateway,
# which reads the new size at start. The gateway (and the page it serves)
# stays up meanwhile, so the page can show that Android is restarting. The web page
# can request the same change: see files/libexec/cloudphone-display-apply.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"

[ $# -eq 3 ] || die "usage: $0 WIDTH HEIGHT DENSITY"
width=$1 height=$2 density=$3
for value in "$width" "$height" "$density"; do
  [[ $value =~ ^[1-9][0-9]{1,3}$ ]] || die "WIDTH, HEIGHT and DENSITY must be positive integers"
done
require_root
[ -f "$CONF" ] || die "$CONF is missing: install part 03 first"
load_conf
avd_config=$AVD_HOME/$AVD_NAME.avd/config.ini
[ -f "$avd_config" ] || die "$avd_config is missing"

# Stop first: the emulator may rewrite config.ini when it shuts down.
log "Stopping Android"
systemctl stop cloudphone-emulator.service

stamp=$(date +%Y%m%d%H%M%S)
cp -p "$avd_config" "$avd_config.bak-$stamp"
cp -p "$CONF" "$CONF.bak-$stamp"

set_ini "$avd_config" hw.lcd.width "$width"
set_ini "$avd_config" hw.lcd.height "$height"
set_ini "$avd_config" hw.lcd.density "$density"
set_ini "$CONF" SCREEN_WIDTH "$width"
set_ini "$CONF" SCREEN_HEIGHT "$height"
set_ini "$CONF" SCREEN_DENSITY "$density"
log "Android screen set to ${width}x${height} at density $density (backups: *.bak-$stamp)"

log "Starting Android"
systemctl start cloudphone-emulator.service
deadline=$((SECONDS + 600))
until [ "$(adb_cmd shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do
  [ $SECONDS -lt $deadline ] || die "Android did not boot in 10 minutes: journalctl -u cloudphone-emulator"
  sleep 5
done
as_service_user "$SDK/platform-tools/adb" kill-server >/dev/null 2>&1 || true
if systemctl is-enabled --quiet cloudphone-gateway.service 2>/dev/null; then
  systemctl restart cloudphone-gateway.service
fi
log "Done; reload the web page"
