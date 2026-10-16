#!/bin/sh
set -eu

# Read-only acceptance test of part 01, run from the operator's machine:
#   01-server-system-setup/scripts/verify.sh setup-agent@SERVER_ADDRESS [--ovh-backup]
# --ovh-backup also checks the OVH Backup Agent (runbook 11).
target=${1:-}
ovh_backup=no
case ${2:-} in
  --ovh-backup) ovh_backup=yes ;;
  '') ;;
  *) target= ;;
esac
if [ -z "$target" ]; then
  echo "usage: $0 setup-agent@SERVER_ADDRESS [--ovh-backup]" >&2
  exit 2
fi
if [ "${target%%@*}" != setup-agent ]; then
  echo "FAIL: target user must be setup-agent" >&2
  exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
  'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test -r /etc/os-release
. /etc/os-release
test "$ID" = debian || test "${ID_LIKE:-}" = debian
command -v apt-get >/dev/null
command -v systemctl >/dev/null
command -v sshd >/dev/null
test "$(timedatectl show -p Timezone --value)" = Europe/Paris
timedatectl show -p NTPSynchronized --value | grep -qx yes

if getent passwd debian >/dev/null; then exit 1; fi
entry=$(getent passwd setup-agent)
IFS=: read -r name _ uid gid _ home shell <<EOF
$entry
EOF
test "$name" = setup-agent
test "$uid" -ge 1000
test "$home" = /home/setup-agent
test "$shell" = /bin/bash
test -d "$home"
test "$(stat -c %u "$home")" = "$uid"
test "$(stat -c %g "$home")" = "$gid"
test "$(stat -c %a /etc/sudoers.d/connection-delegation)" = 440
test "$(stat -c %U:%G /etc/sudoers.d/connection-delegation)" = root:root
visudo -cf /etc/sudoers.d/connection-delegation >/dev/null
if test -e /etc/sudoers.d/setup-agent; then exit 1; fi

for user in emergency admin-human setup-agent system-setup master; do
  entry=$(getent passwd "$user")
  IFS=: read -r name _ uid gid _ home shell <<EOF
$entry
EOF
  test "$name" = "$user"
  test "$uid" -ge 1000
  test "$home" = "/home/$user"
  test "$shell" = /bin/bash
  test -d "$home"
  test "$(stat -c %u "$home")" = "$uid"
  test "$(stat -c %g "$home")" = "$gid"
  test "$(id -G "$user" | wc -w)" -eq 1
done

test "$(passwd --status emergency | awk '{print $2}')" = P

for user in system-setup master; do
  test "$(passwd --status "$user" | awk '{print $2}')" = L
  if test -s "/home/$user/.ssh/authorized_keys"; then exit 1; fi
done
for user in admin-human setup-agent; do
  test "$(passwd --status "$user" | awk '{print $2}')" = NP
  test -z "$(getent shadow "$user" | cut -d: -f3)"
done

test -s /home/setup-agent/.ssh/authorized_keys
for user in admin-human setup-agent; do
  test "$(stat -c %a "/home/$user")" = 700
  test "$(stat -c %a "/home/$user/.ssh")" = 700
  test "$(stat -c %a "/home/$user/.ssh/authorized_keys")" = 600
  test "$(stat -c %U:%G "/home/$user")" = "$user:$user"
  test "$(stat -c %U:%G "/home/$user/.ssh")" = "$user:$user"
  test "$(stat -c %U:%G "/home/$user/.ssh/authorized_keys")" = "$user:$user"
  cmp -s /home/setup-agent/.ssh/authorized_keys "/home/$user/.ssh/authorized_keys"
done
sshd -T | grep -qx 'pubkeyauthentication yes'
sshd -T | grep -qx 'strictmodes yes'
test "$(stat -c %a /etc/ssh/sshd_config.d/99-emergency-password-only.conf)" = 644
test "$(stat -c %U:%G /etc/ssh/sshd_config.d/99-emergency-password-only.conf)" = root:root
for user in debian admin-human setup-agent root; do
  sshd -T -C "user=$user,host=localhost,addr=127.0.0.1" |
    grep -qx 'passwordauthentication no'
done
sshd -T -C 'user=emergency,host=localhost,addr=127.0.0.1' |
  grep -qx 'passwordauthentication yes'
sshd -T | grep -qx 'kbdinteractiveauthentication no'
sshd -T | grep -qx 'permitemptypasswords no'
for user in system-setup master; do
  sshd -T -C "user=$user,host=localhost,addr=127.0.0.1" |
    awk -v wanted="$user" '$1 == "denyusers" {
      for (i = 2; i <= NF; i++) if ($i == wanted) found = 1
    } END { exit !found }'
done

command -v auditctl >/dev/null
command -v ausearch >/dev/null
test "$(dpkg-query -W -f='${Status}\n' auditd |
  grep -c '^install ok installed$')" -eq 1
systemctl is-enabled --quiet auditd
systemctl is-active --quiet auditd
auditctl -s | grep -qx 'enabled 1'
auditctl -l | grep -q 'auid>=1000'
auditctl -l | grep -q 'execve'
auditctl -l | grep -q 'user-commands'
grep -Eq '^[[:space:]]*session[[:space:]]+required[[:space:]]+pam_loginuid\.so' /etc/pam.d/sshd

command -v git >/dev/null
command -v gh >/dev/null
test "$(dpkg-query -W -f='${Status}\n' git gh | grep -c '^install ok installed$')" -eq 2
git --version >/dev/null
gh --version >/dev/null

test "$(dpkg-query -W -f='${Status}\n' nftables fail2ban |
  grep -c '^install ok installed$')" -eq 2
sshd -T | grep -qx 'port 52242'
nft list chain inet server_filter input | grep -q 'policy drop'
nft list chain inet server_filter input | grep -Eq 'tcp dport 52242 .* accept'
systemctl is-active --quiet nftables
systemctl is-active --quiet fail2ban
systemctl is-enabled --quiet nftables
systemctl is-enabled --quiet fail2ban
fail2ban-client status sshd | grep -q 'Status for the jail: sshd'
resolvectl status | grep -Eq 'Protocols:.*-LLMNR'
ss -lnt | awk '$4 ~ /:52242$/ { found = 1 } END { exit !found }'
if ss -lnt | awk '$4 ~ /:22$/ { found = 1 } END { exit !found }'; then exit 1; fi
REMOTE

if [ "$ovh_backup" = yes ]; then
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
    'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(dpkg-query -W -f='${Status}\n' veeamma veeam veeam-libs |
  grep -c '^install ok installed$')" -eq 3
veeam_status=$(veeamconsoleconfig -s)
printf '%s\n' "$veeam_status" |
  grep -Eq 'Connection state[[:space:]]*:[[:space:]]*Connected'
printf '%s\n' "$veeam_status" |
  grep -Eq 'Status[[:space:]]*:[[:space:]]*Running'
REMOTE
fi

test "$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" 'id -un')" = setup-agent
test "$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
  'sudo -n -u system-setup id -un')" = system-setup
test "$(ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
  'sudo -n -u master id -un')" = master
ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
  'sudo -n -u master sudo -n true'

admin_human_target="admin-human@${target#*@}"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$admin_human_target" \
  'test "$(id -un)" = admin-human'

echo "PASS: server is converged"
