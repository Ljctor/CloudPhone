#!/usr/bin/env bash
# Install only the passive evidence review service; never restart the gateway.
set -euo pipefail

source_dir=$(cd "$(dirname "$0")" && pwd)
listen_address=
port=7890
frontend_origins=()
data_dir=/var/lib/cloudphone/plugins/slayer-legend
feedback_file=/var/lib/cloudphone-review/feedback.json
ledger_file=/var/lib/cloudphone-review/trace-review.json
python_path=${CLOUDPHONE_REVIEW_PYTHON:-/opt/cloudphone/current/venv/bin/python3}
destination=/opt/cloudphone/review-navigation
plugin_source=$(cd "$source_dir/.." && pwd)

while [ "$#" -gt 0 ]; do
  case $1 in
    --host) listen_address=${2:?Missing host}; shift 2 ;;
    --port) port=${2:?Missing port}; shift 2 ;;
    --frontend-origin) frontend_origins+=("${2:?Missing frontend origin}"); shift 2 ;;
    --data-dir) data_dir=${2:?Missing data directory}; shift 2 ;;
    --feedback-file) feedback_file=${2:?Missing feedback file}; shift 2 ;;
    --ledger) ledger_file=${2:?Missing ledger file}; shift 2 ;;
    *) printf 'Usage: sudo %s --host PRIVATE_IP [--port 7890] [--data-dir PATH] [--feedback-file PATH] [--ledger PATH]\n' "$0" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo 'Run as root' >&2; exit 1; }
[ -n "$listen_address" ] || { echo 'An explicit private --host is required' >&2; exit 2; }
python3 - "$listen_address" "$port" <<'PY'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
assert address.is_private and not address.is_unspecified and not address.is_multicast, 'private explicit bind address required'
assert 1024 <= int(sys.argv[2]) <= 65535, 'unprivileged port required'
PY
for path in "$data_dir" "$feedback_file" "$ledger_file" "$python_path"; do
  [[ $path =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo 'Paths must be absolute and contain only safe path characters' >&2; exit 2; }
done
[[ $port =~ ^[0-9]+$ ]] || exit 2
frontend_argument=
for frontend_origin in "${frontend_origins[@]}"; do
  python3 - "$frontend_origin" <<'PY'
import re, sys, urllib.parse
url = urllib.parse.urlsplit(sys.argv[1])
assert url.scheme in ('http', 'https') and url.hostname and not (url.username or url.password or url.path or url.query or url.fragment)
assert re.fullmatch(r'[A-Za-z0-9._:-]+', url.hostname)
assert re.fullmatch(r'https?://[A-Za-z0-9._:\[\]-]+', sys.argv[1])
PY
  frontend_argument+=" --frontend-origin $frontend_origin"
done
[ -d "$data_dir" ] || { echo 'Recorded evidence directory is missing' >&2; exit 1; }
[ -x "$python_path" ] || { echo 'Gateway Python environment is missing' >&2; exit 1; }
"$python_path" -c 'import aiohttp'
for name in review_server.py index.html style.css app.js model.js; do
  [ -f "$source_dir/$name" ] || { printf 'Missing application file: %s\n' "$name" >&2; exit 1; }
done
[ -f "$source_dir/../evidence_review.py" ] || { echo 'Passive evidence reviewer is missing' >&2; exit 1; }
for name in zone_feedback.py oral_feedback.py page_zone_style.js page_oral_feedback.js; do
  [ -f "$plugin_source/$name" ] || { printf 'Missing shared module: %s\n' "$name" >&2; exit 1; }
done
feedback_directory=$(dirname "$feedback_file")
[[ $feedback_file != "$data_dir"/* && $ledger_file == "$feedback_directory"/* ]] || {
  echo 'Feedback and review ledger must share a separate writable directory outside raw evidence' >&2; exit 2;
}
# Explicit install and subsequent plugin upgrades share the exact same copy set.
# shellcheck source=refresh-installed.sh
. "$source_dir/refresh-installed.sh"
sync_review_files "$source_dir" "$destination" false
install -d -o cloudphone -g cloudphone -m 700 "$feedback_directory"
unit_file=$(mktemp)
trap 'rm -f "$unit_file"' EXIT
cat >"$unit_file" <<UNIT
[Unit]
Description=Cloud Phone recorded navigation review (passive)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=cloudphone
Group=cloudphone
WorkingDirectory=$destination
ExecStart=$python_path $destination/review_server.py --host $listen_address --port $port --data-dir $data_dir --feedback-file $feedback_file --ledger $ledger_file --plugin-dir $destination/readers --process-reviews$frontend_argument
Restart=on-failure
RestartSec=3
CPUQuota=30%
CPUWeight=10
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadOnlyPaths=$data_dir
ReadWritePaths=$feedback_directory

[Install]
WantedBy=multi-user.target
UNIT
install -m 644 "$unit_file" /etc/systemd/system/cloudphone-review.service
systemctl daemon-reload
systemctl enable cloudphone-review.service
systemctl restart cloudphone-review.service
systemctl is-active --quiet cloudphone-review.service
printf 'Passive review service installed on explicit private address, port %s. Gateway unchanged.\n' "$port"
