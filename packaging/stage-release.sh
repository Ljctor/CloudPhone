#!/bin/sh
# Copies a release tarball to a server, verifies it and unpacks it as root
# under /var/tmp/cloudphone-release/, where the runbooks of parts 02-05 run it
# from (root runs these scripts, so only root may write them):
#   packaging/stage-release.sh setup-agent@SERVER_ADDRESS [TARBALL]
# AS_ROOT is the privilege path on the server (default: through master).
# Prints the unpacked directory.
set -eu

target=${1:?usage: $0 USER@SERVER [TARBALL]}
root=$(cd "$(dirname "$0")/.." && pwd)
tarball=${2:-$root/dist/cloudphone-$(cat "$root/VERSION")-linux-x86_64.tar.gz}
as_root=${AS_ROOT:-sudo -n -u master sudo -n}
[ -f "$tarball" ] || { echo "ERROR: $tarball is missing: run packaging/build-release.sh" >&2; exit 1; }
[ -f "$tarball.sha256" ] || { echo "ERROR: $tarball.sha256 is missing" >&2; exit 1; }
name=$(basename "$tarball" .tar.gz)
dir=/var/tmp/cloudphone-release
# The commit build-release.sh wrote beside the tarball, "-dirty" when built
# with uncommitted changes: unpacked as COMMIT, which the gateway names in
# its start record.
commit=$(head -1 "$tarball.commit" 2>/dev/null || true)
case $commit in
  *[!0-9a-f]* | '') commit=unknown ;;
esac
if [ "$commit" != unknown ] && grep -q "uncommitted changes" "$tarball.commit"; then
  commit=$commit-dirty
fi

upload=$(ssh -o BatchMode=yes "$target" 'mktemp -d /var/tmp/cloudphone-upload.XXXXXX')
scp -q -o BatchMode=yes "$tarball" "$tarball.sha256" "$target:$upload/"
ssh -o BatchMode=yes "$target" "$as_root sh -euc '
  cd $upload
  sha256sum -c --quiet $name.tar.gz.sha256
  install -d -m 755 -o root -g root $dir
  rm -rf $dir/$name
  tar --no-same-owner -xzf $name.tar.gz -C $dir
  chown -R root:root $dir/$name
  cd $dir/$name
  sha256sum -c --quiet SHA256SUMS
  echo $commit >COMMIT
  rm -rf $upload
'"
echo "$dir/$name"
