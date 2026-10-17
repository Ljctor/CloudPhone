#!/usr/bin/env bash
# Installs the Slayer Legend plugin into the Cloud Phone app (part 04):
# features for that game only, shown in the page's options panel under
# "Plugins". Re-running it upgrades in place.
#
# It copies files/plugin to /opt/cloudphone/plugins/slayer-legend and
# restarts the gateway, which loads plugins at start (Android keeps running,
# the page reconnects by itself). Remove it with --uninstall.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
PART=$TREE/05-slayer-legend
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"
PLUGIN=slayer-legend
DEST=$PREFIX/plugins/$PLUGIN

usage() {
  cat <<USAGE
Usage: sudo 05-slayer-legend/scripts/install.sh [--uninstall]

Installs (or with --uninstall removes) the Slayer Legend plugin of the
Cloud Phone app. Part 04 must be installed first.
USAGE
}

action=install
case ${1:-} in
  '') ;;
  --uninstall) action=uninstall ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; die "unknown option: $1" ;;
esac
require_root
[ -f /etc/systemd/system/cloudphone-gateway.service ] ||
  die "cloudphone-gateway.service is missing: install part 04 (04-cloud-phone-app) first"

if [ "$action" = uninstall ]; then
  log "Removing the $PLUGIN plugin"
  rm -rf "$DEST"
else
  log "Installing the $PLUGIN plugin"
  install -d -m 755 "$PREFIX/plugins"
  # A new copy beside the old one, then swapped: the gateway never sees a
  # half-copied plugin.
  rm -rf "$DEST.new"
  install -d -m 755 "$DEST.new"
  install -m 644 "$PART"/files/plugin/* "$DEST.new/"
  rm -rf "$DEST.old"
  [ ! -e "$DEST" ] || mv -T "$DEST" "$DEST.old"
  mv -T "$DEST.new" "$DEST"
  rm -rf "$DEST.old"
fi

if systemctl is-active --quiet cloudphone-gateway.service; then
  log "Restarting the gateway to load plugins (Android keeps running)"
  systemctl restart cloudphone-gateway.service
fi
log "Done; reload the web page"
