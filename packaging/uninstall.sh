#!/usr/bin/env bash
# Removes Cloud Phone. By default the Android data (the AVD: Google account,
# apps and their data) and the configuration are kept, so that reinstalling
# brings the same phone back.
set -euo pipefail

PREFIX=/opt/cloudphone
STATE=/var/lib/cloudphone
CONF_DIR=/etc/cloudphone
SERVICE_USER=cloudphone
# cloudphone-web: separate page server of earlier releases.
UNITS=(cloudphone-web cloudphone-gateway cloudphone-emulator)

purge=no
assume_yes=no

usage() {
  cat <<EOF
Usage: sudo ./uninstall.sh [--purge [--yes]]

Without options, removes the services, the application and the Android SDK,
and keeps $STATE (Android data) and $CONF_DIR (configuration).

  --purge   Also delete the Android data, the configuration and the
            $SERVICE_USER account. This erases the phone permanently.
  --yes     Do not ask for confirmation with --purge.
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case $1 in
    --purge) purge=yes ;;
    --yes) assume_yes=yes ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || die "run as root: sudo $0"

if [ "$purge" = yes ] && [ "$assume_yes" = no ]; then
  [ -t 0 ] || die "--purge needs --yes when not run interactively"
  printf 'This permanently erases the phone in %s. Type "erase" to continue: ' "$STATE"
  read -r answer
  [ "$answer" = erase ] || die "aborted"
fi

systemctl disable --now cloudphone-display.path 2>/dev/null || true
rm -f /etc/systemd/system/cloudphone-display.path /etc/systemd/system/cloudphone-display.service
for unit in "${UNITS[@]}"; do
  systemctl disable --now "$unit.service" 2>/dev/null || true
  rm -f "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload

rm -rf "$PREFIX"

if [ "$purge" = yes ]; then
  rm -rf "$STATE" "$CONF_DIR"
  if id "$SERVICE_USER" >/dev/null 2>&1; then
    userdel "$SERVICE_USER"
  fi
  echo "Cloud Phone and all its data were removed."
else
  echo "Cloud Phone was removed. Kept: $STATE (Android data) and $CONF_DIR."
  echo "Run again with --purge to erase them."
fi
