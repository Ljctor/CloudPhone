# 09 — Password-state verification

Verify the complete password-state policy without recovering, displaying, or
comparing any secret. `emergency` alone has a usable password hash. The two
ordinary connection accounts are key-only, while functional accounts remain
locked.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
test "$(passwd --status emergency | awk '{print $2}')" = P
for user in admin-human setup-agent; do
  test "$(passwd --status "$user" | awk '{print $2}')" = NP
  test -z "$(getent shadow "$user" | cut -d: -f3)"
done
for user in system-setup master; do
  test "$(passwd --status "$user" | awk '{print $2}')" = L
done
REMOTE
```

There is no Apply section. A failure means returning to the account or emergency
password runbook that owns the incorrect state.
