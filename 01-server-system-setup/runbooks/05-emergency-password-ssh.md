# 05 — Emergency-only SSH password access

Allow password authentication over SSH only for the `emergency` account. All
other accounts, including `debian`, `admin-human`, and `setup-agent`, must use a permitted
non-password method such as public-key authentication. Keyboard-interactive
authentication is disabled for every account. Functional accounts
`system-setup` and `master` are denied direct SSH login entirely.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(stat -c %a /etc/ssh/sshd_config.d/99-emergency-password-only.conf)" = 644
test "$(stat -c %U:%G /etc/ssh/sshd_config.d/99-emergency-password-only.conf)" = root:root

for user in debian admin-human setup-agent system-setup root; do
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
REMOTE
```

## Apply

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
install -d -m 755 /etc/ssh/sshd_config.d
install -m 644 /dev/stdin /etc/ssh/sshd_config.d/99-emergency-password-only.conf <<'CONFIG'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
DenyUsers system-setup master
Match User emergency
    PasswordAuthentication yes
CONFIG
sshd -t
systemctl reload ssh
REMOTE
```

The `emergency` password must be entered only at the SSH password prompt. This
runbook neither displays nor changes any password.
