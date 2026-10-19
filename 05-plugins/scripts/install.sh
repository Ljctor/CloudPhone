#!/usr/bin/env bash
# Installs plugins of the Cloud Phone app (part 04): optional features, one
# directory each under 05-plugins/ (for now: slayer-legend). They show in
# the page's options panel under "Plugins". Re-running it upgrades in place.
#
# Each plugin's files (plugin.json, page.js, gateway.py, features/, ...;
# not its README nor its tests) are copied to /opt/cloudphone/plugins/<id>,
# then the gateway restarts to load them (Android keeps running, the page
# reconnects by itself).
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
PART=$TREE/05-plugins
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"

usage() {
  cat <<USAGE
Usage: sudo 05-plugins/scripts/install.sh [--uninstall] [PLUGIN...]

Installs (or with --uninstall removes) the given plugins of the Cloud Phone
app; without a name, every plugin in 05-plugins/. Part 04 must be installed
first. Available: $(available | tr '\n' ' ')
USAGE
}

available() {
  local dir
  for dir in "$PART"/*/; do
    [ -f "$dir/plugin.json" ] && basename "$dir"
  done
}

action=install
plugins=()
while [ $# -gt 0 ]; do
  case $1 in
    --uninstall) action=uninstall ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; die "unknown option: $1" ;;
    *) plugins+=("$1") ;;
  esac
  shift
done
[ ${#plugins[@]} -gt 0 ] || mapfile -t plugins < <(available)
require_root
[ -f /etc/systemd/system/cloudphone-gateway.service ] ||
  die "cloudphone-gateway.service is missing: install part 04 (04-cloud-phone-app) first"

for plugin in "${plugins[@]}"; do
  [[ $plugin =~ ^[a-z0-9][a-z0-9-]{0,31}$ ]] || die "invalid plugin name: $plugin"
  dest=$PREFIX/plugins/$plugin
  if [ "$action" = uninstall ]; then
    log "Removing the $plugin plugin"
    rm -rf "$dest"
    continue
  fi
  [ -f "$PART/$plugin/plugin.json" ] || die "no plugin $plugin in $PART"
  log "Installing the $plugin plugin"
  install -d -m 755 "$PREFIX/plugins"
  # A new copy beside the old one, then swapped: the gateway never sees a
  # half-copied plugin.
  rm -rf "$dest.new"
  install -d -m 755 "$dest.new"
  find "$PART/$plugin" -maxdepth 1 -type f ! -name '*.md' ! -name 'test_*' -exec install -m 644 -t "$dest.new" {} +
  # Its subdirectories one level down (e.g. features/), without caches.
  for sub in "$PART/$plugin"/*/; do
    [ -d "$sub" ] || continue
    name=$(basename "$sub")
    [ "$name" != __pycache__ ] || continue
    install -d -m 755 "$dest.new/$name"
    find "$sub" -maxdepth 1 -type f ! -name '*.md' ! -name 'test_*' ! -name '*.pyc' \
      -exec install -m 644 -t "$dest.new/$name" {} +
  done
  rm -rf "$dest.old"
  [ ! -e "$dest" ] || mv -T "$dest" "$dest.old"
  mv -T "$dest.new" "$dest"
  rm -rf "$dest.old"
done

if systemctl is-active --quiet cloudphone-gateway.service; then
  log "Restarting the gateway to load plugins (Android keeps running)"
  systemctl restart cloudphone-gateway.service
fi
log "Done; reload the web page"
