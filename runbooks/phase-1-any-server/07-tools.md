# 07 — System baseline and Git tooling

Install Git and GitHub CLI from the configured Debian package repositories.
Package installation is idempotent; no GitHub credentials are created here.
The agent's repository access remains a prerequisite, not a server secret.
Set the geographic timezone to `Europe/Paris`, which produces CET in winter and
CEST in summer while preserving automatic daylight-saving transitions.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sh -eu' <<'REMOTE'
test "$(dpkg-query -W -f='${Status}\n' git gh | grep -c '^install ok installed$')" -eq 2
command -v git >/dev/null
command -v gh >/dev/null
test "$(timedatectl show -p Timezone --value)" = Europe/Paris
timedatectl show -p NTPSynchronized --value | grep -qx yes
git --version
gh --version | head -n 1
REMOTE
```

## Apply

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git gh
timedatectl set-timezone Europe/Paris
REMOTE
```

No minimum version is pinned because Debian security updates legitimately change
package versions. Determinism here means `dpkg` reports both packages fully
installed from the server's configured APT sources and both programs execute.
