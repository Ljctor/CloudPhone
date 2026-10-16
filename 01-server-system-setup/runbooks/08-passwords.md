# 08 — Emergency password

Preserve the operator-set password for `emergency`, the only account allowed to
authenticate to SSH with a password. If it is missing, set it through a
protected prompt. Never place it in shell arguments, environment variables,
files, logs, chat, or Git.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(passwd --status emergency | awk '{print $2}')" = P
REMOTE
```

`P` deterministically proves that `/etc/shadow` contains a usable password hash
for the account. The check cannot and must not recover or display the password.
Runbook 09 separately verifies the complete password-state policy.

## Apply

Open an interactive TTY only if `emergency` lacks a usable password hash:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
state=$(ssh "$TARGET" "sudo -n -u system-setup sudo passwd --status emergency | awk '{print \$2}'")
if test "$state" != P; then
  ssh -t "$TARGET" 'sudo -n -u system-setup sudo passwd emergency'
fi
```

Enter the secret only at the protected `passwd` prompt. An existing emergency
password is preserved. Then rerun **Check** and continue to runbook 09.
