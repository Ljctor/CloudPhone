#!/usr/bin/env bash
# Installs the Cloud Phone app on top of part 03: the WebRTC streaming gateway
# (cloudphone-gateway), which also serves the mobile web control page on the
# same port.
#
# Run it from an unpacked release: the web page and the gateway wheel are
# built by packaging/build-release.sh into 04-cloud-phone-app/dist/.
# Re-running it upgrades in place; Android keeps running.
set -euo pipefail

TREE=$(cd "$(dirname "$0")/../.." && pwd)
PART=$TREE/04-cloud-phone-app
# shellcheck source=../../lib/common.sh
. "$TREE/lib/common.sh"
UNITS=(cloudphone-gateway)

listen=
start=yes
wait_ready=yes

usage() {
  cat <<EOF
Usage: sudo 04-cloud-phone-app/scripts/install.sh [options]

Installs or upgrades the Cloud Phone app $RELEASE_VERSION. Part 03 must be
installed first.

Options:
  --listen ADDRESS   Address for the web page and the gateway, e.g. the
                     WireGuard address 10.20.0.1. Written to $CONF.
  --no-start         Install and enable, but do not start the services.
  --no-wait          Do not wait for the page and the gateway to answer.
  -h, --help         Show this help.
EOF
}

while [ $# -gt 0 ]; do
  case $1 in
    --listen) listen=${2:?--listen needs an address}; shift ;;
    --no-start) start=no; wait_ready=no ;;
    --no-wait) wait_ready=no ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

[ -z "$listen" ] || [[ $listen =~ ^[0-9A-Fa-f:.]+$ ]] || die "--listen expects an IP address"
require_root

preflight() {
  log "Checking that part 03 is installed"
  [ -f "$CONF" ] || die "$CONF is missing: install part 03 (03-android-emulator) first"
  id "$SERVICE_USER" >/dev/null 2>&1 || die "the $SERVICE_USER account is missing: install part 03 first"
  [ -x "$SDK/platform-tools/adb" ] || die "adb is missing: install part 03 first"
  [ -f /etc/systemd/system/cloudphone-emulator.service ] ||
    die "cloudphone-emulator.service is missing: install part 03 first"
  if [ ! -f "$PART/dist/web/index.html" ] || ! compgen -G "$PART/dist/wheels/*.whl" >/dev/null; then
    die "no built app in $PART/dist: run this script from a release built by packaging/build-release.sh"
  fi
}

install_packages() {
  log "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl python3 python3-venv
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' ||
    die "Python 3.10 or newer is required"
}

configure() {
  if [ -n "$listen" ]; then
    set_ini "$CONF" LISTEN_ADDRESS "$listen"
  fi
  load_conf
}

install_release() {
  log "Installing Cloud Phone app $RELEASE_VERSION"
  install -d -m 755 "$PREFIX/releases"
  local release
  release=$PREFIX/releases/$RELEASE_VERSION-$(date +%Y%m%d%H%M%S)
  install -d -m 755 "$release"
  cp -R "$PART/dist/web" "$release/web"
  cp -R "$PART/files/libexec" "$release/libexec"
  chmod -R u=rwX,go=rX "$release"
  chmod 755 "$release"/libexec/*
  python3 -m venv "$release/venv"
  "$release/venv/bin/pip" install --quiet --disable-pip-version-check \
    -c "$PART/constraints.txt" "$PART"/dist/wheels/*.whl
  install -m 644 "$TREE/VERSION" "$TREE/lib/versions.env" "$release/"
  # The commit the release was built from, when stage-release.sh wrote it:
  # the gateway names it in its start record.
  [ ! -f "$TREE/COMMIT" ] || install -m 644 "$TREE/COMMIT" "$release/"

  ln -sfn "$release" "$PREFIX/current.new"
  mv -T "$PREFIX/current.new" "$PREFIX/current"

  # Keep the active release and the one before it, for a manual rollback.
  local old
  while IFS= read -r old; do
    rm -rf "$old"
  done < <(find "$PREFIX/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' |
    sort -rn | tail -n +3 | cut -d' ' -f2-)
}

install_units() {
  log "Installing systemd services"
  local unit
  # Earlier releases served the page from a separate cloudphone-web
  # service on WEB_PORT; the gateway now takes that port.
  if [ -f /etc/systemd/system/cloudphone-web.service ]; then
    systemctl disable --now cloudphone-web.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/cloudphone-web.service
  fi
  for unit in "${UNITS[@]}"; do
    install -m 644 "$PART/files/systemd/$unit.service" "/etc/systemd/system/$unit.service"
  done
  systemctl daemon-reload
  systemctl enable "${UNITS[@]/%/.service}" >/dev/null
}

start_services() {
  [ "$start" = yes ] || return 0
  local unit running=no
  for unit in "${UNITS[@]}"; do
    systemctl is-active --quiet "$unit.service" && running=yes
  done
  [ "$running" = yes ] || check_ports_free "$WEB_PORT"
  log "Restarting the streaming services (Android keeps running)"
  systemctl restart "${UNITS[@]/%/.service}"
}

wait_until_ready() {
  [ "$wait_ready" = yes ] || return 0
  local host=$LISTEN_ADDRESS deadline=$((SECONDS + 120))
  [ "$host" != 0.0.0.0 ] || host=127.0.0.1
  until curl -fsS "http://$host:$WEB_PORT/" >/dev/null 2>&1 &&
    curl -fsS "http://$host:$WEB_PORT/api/v1/emulator/status" >/dev/null 2>&1; do
    [ $SECONDS -lt $deadline ] ||
      die "the page and gateway are not answering: journalctl -u cloudphone-gateway"
    sleep 2
  done
}

summary() {
  local host=$LISTEN_ADDRESS
  [ "$host" != 0.0.0.0 ] || host='<this-server-address>'
  cat <<EOF

Cloud Phone $RELEASE_VERSION is installed.

  Web control page : http://$host:$WEB_PORT/
  Configuration    : $CONF
  Android data     : $AVD_HOME  (back it up; never deleted by upgrades)
  Logs             : journalctl -u cloudphone-emulator -u cloudphone-gateway

EOF
  if [ "$LISTEN_ADDRESS" = 0.0.0.0 ]; then
    cat <<EOF
SECURITY: the web page and the gateway listen on every interface and have no
login. Do not expose port $WEB_PORT and UDP 32768-60999 to the
internet: reach the phone through WireGuard (02-wireguard-server).

EOF
  fi
}

preflight
install_packages
configure
install_release
install_units
start_services
wait_until_ready
summary
