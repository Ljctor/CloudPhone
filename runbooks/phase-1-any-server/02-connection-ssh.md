# 02 — SSH access for connection accounts

Authorize exactly the same public keys for `admin-human` and `setup-agent`.
During bootstrap they are copied from `debian`; after `debian` is retired the
two surviving files remain sufficient to prove convergence. No private key is
ever copied.

## Check

```sh
: "${TARGET:?Set TARGET to debian@SERVER_ADDRESS or setup-agent@SERVER_ADDRESS}"
case ${TARGET%%@*} in
  debian) root_shell='sudo -n sh -eu' ;;
  setup-agent) root_shell='sudo -n -u system-setup sudo -n sh -eu' ;;
  *) exit 2 ;;
esac
ssh "$TARGET" "$root_shell" <<'REMOTE'
for user in admin-human setup-agent; do
  test "$(stat -c %a "/home/$user")" = 700
  test "$(stat -c %a "/home/$user/.ssh")" = 700
  test "$(stat -c %a "/home/$user/.ssh/authorized_keys")" = 600
  test "$(stat -c %U:%G "/home/$user")" = "$user:$user"
  test "$(stat -c %U:%G "/home/$user/.ssh")" = "$user:$user"
  test "$(stat -c %U:%G "/home/$user/.ssh/authorized_keys")" = "$user:$user"
done
cmp -s /home/admin-human/.ssh/authorized_keys /home/setup-agent/.ssh/authorized_keys
sshd -T | grep -qx 'pubkeyauthentication yes'
sshd -T | grep -qx 'strictmodes yes'
REMOTE
```

## Apply

```sh
: "${TARGET:?Set TARGET to debian@SERVER_ADDRESS or setup-agent@SERVER_ADDRESS}"
case ${TARGET%%@*} in
  debian) root_shell='sudo -n sh -eu' ;;
  setup-agent) root_shell='sudo -n -u system-setup sudo -n sh -eu' ;;
  *) exit 2 ;;
esac
ssh "$TARGET" "$root_shell" <<'REMOTE'
source_keys=
for candidate in \
  /home/debian/.ssh/authorized_keys \
  /home/admin-human/.ssh/authorized_keys \
  /home/setup-agent/.ssh/authorized_keys; do
  if test -s "$candidate"; then
    source_keys=$candidate
    break
  fi
done
test -n "$source_keys"
key_copy=$(mktemp)
trap 'rm -f "$key_copy"' EXIT HUP INT TERM
install -m 600 "$source_keys" "$key_copy"
for user in admin-human setup-agent; do
  uid=$(id -u "$user")
  gid=$(id -g "$user")
  install -d -m 700 -o "$uid" -g "$gid" "/home/$user"
  install -d -m 700 -o "$uid" -g "$gid" "/home/$user/.ssh"
  install -m 600 -o "$uid" -g "$gid" \
    "$key_copy" \
    "/home/$user/.ssh/authorized_keys"
done
REMOTE
```

After the check passes, test the `setup-agent` end-to-end login from the same
machine and key used for the `debian` connection:

```sh
SETUP_AGENT_TARGET="setup-agent@${TARGET#*@}"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SETUP_AGENT_TARGET" \
  'test "$(id -un)" = setup-agent'
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SETUP_AGENT_TARGET" \
  'test "$(sudo -n -u system-setup id -un)" = system-setup && sudo -n -u system-setup sudo -n true'
ssh -o BatchMode=yes -o ConnectTimeout=10 "$SETUP_AGENT_TARGET" \
  'test "$(sudo -n -u master id -un)" = master && sudo -n -u master sudo -n true'
```

These end-to-end tests must exit `0` before continuing. `admin-human` is also
tested before the bootstrap account is removed. Both accounts are key-only.
