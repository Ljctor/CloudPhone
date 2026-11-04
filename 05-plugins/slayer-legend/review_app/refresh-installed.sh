#!/usr/bin/env bash
# Refresh an already installed passive review service from this plugin release.
# No installation, enablement, address/origin changes, or gateway restart.
set -euo pipefail

stage_review_files() {
  local source_dir=$1 target=$2 plugin_source name
  plugin_source=$(cd "$source_dir/.." && pwd)
  install -d -m 755 "$target/readers/fixtures"
  for name in review_server.py index.html style.css app.js model.js; do
    install -m 644 "$source_dir/$name" "$target/$name"
  done
  for name in evidence_review.py zone_feedback.py oral_feedback.py page_zone_style.js page_oral_feedback.js; do
    install -m 644 "$plugin_source/$name" "$target/$name"
  done
  find "$plugin_source" -maxdepth 1 -type f \( -name '*.py' -o -name '*.json' \) ! -name 'test_*' \
    -exec install -m 644 -t "$target/readers" {} +
  find "$plugin_source/fixtures" -maxdepth 1 -type f -name '*.txt' \
    -exec install -m 644 -t "$target/readers/fixtures" {} +
  python3 - "$target" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
files = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
         for path in sorted(root.rglob('*')) if path.is_file()}
(root / 'source-manifest.json').write_text(json.dumps({'version': 1, 'files': files}, sort_keys=True) + '\n')
PY
}

sync_review_files() {
  local source_dir=$1 destination=$2 restart=${3:-true} active=false
  if systemctl is-active --quiet cloudphone-review.service; then active=true; fi
  # Prepare the whole app and all readers together before stopping anything.
  rm -rf "$destination.new"
  stage_review_files "$source_dir" "$destination.new"
  if "$active"; then systemctl stop cloudphone-review.service; fi
  rm -rf "$destination.old"
  [ ! -e "$destination" ] || mv -T "$destination" "$destination.old"
  mv -T "$destination.new" "$destination"
  if "$active" && "$restart"; then
    if ! systemctl start cloudphone-review.service; then
      # Restore only review code; evidence and feedback live elsewhere.
      rm -rf "$destination"
      [ ! -e "$destination.old" ] || mv -T "$destination.old" "$destination"
      systemctl start cloudphone-review.service || true
      return 1
    fi
  fi
  rm -rf "$destination.old"
}

refresh_installed_review() {
  local source_dir destination unit_file
  source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  destination=${CLOUDPHONE_REVIEW_DESTINATION:-/opt/cloudphone/review-navigation}
  unit_file=${CLOUDPHONE_REVIEW_UNIT_FILE:-/etc/systemd/system/cloudphone-review.service}
  [ -f "$unit_file" ] || return 0
  [ "$(id -u)" -eq 0 ] || { echo 'Run as root' >&2; return 1; }
  [[ $destination == /* && $destination != / && $destination != /opt && $destination != /opt/cloudphone ]] || return 2
  [ -d "$destination" ] || { echo 'Installed review directory is missing' >&2; return 1; }
  sync_review_files "$source_dir" "$destination"
  echo 'Installed passive review app and readers refreshed; existing service configuration preserved.'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  refresh_installed_review
fi
