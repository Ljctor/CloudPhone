# 10 — Retire the bootstrap account

`debian` is only the initial bootstrap account. Delete it after proving that
`admin-human` and the separately created `setup-agent` account can both log in
by SSH key. This step never renames `debian`.

Run both **Check** and **Apply** with `TARGET=setup-agent@SERVER_ADDRESS`. The
bootstrap account is never used to delete its own live session.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
test "${TARGET%%@*}" = setup-agent
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
if getent passwd debian >/dev/null; then exit 1; fi
for user in emergency admin-human setup-agent system-setup master; do
  entry=$(getent passwd "$user")
  IFS=: read -r name _ uid gid _ home shell <<EOF
$entry
EOF
  test "$name" = "$user"
  test "$home" = "/home/$user"
  test "$shell" = /bin/bash
  test -d "$home"
done
test -s /home/admin-human/.ssh/authorized_keys
test -s /home/setup-agent/.ssh/authorized_keys
test "$(stat -c %a /etc/sudoers.d/connection-delegation)" = 440
test "$(stat -c %U:%G /etc/sudoers.d/connection-delegation)" = root:root
visudo -cf /etc/sudoers.d/connection-delegation >/dev/null
REMOTE

ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" \
  'test "$(sudo -n -u system-setup id -un)" = system-setup'
ssh -o BatchMode=yes -o ConnectTimeout=10 "admin-human@${TARGET#*@}" \
  'test "$(id -un)" = admin-human'
```

## Apply

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
test "${TARGET%%@*}" = setup-agent
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" \
  'test "$(sudo -n -u system-setup id -un)" = system-setup'
ssh -o BatchMode=yes -o ConnectTimeout=10 "admin-human@${TARGET#*@}" \
  'test "$(id -un)" = admin-human'
ssh "$TARGET" 'sudo -n -u system-setup sudo -n sh -eu' <<'REMOTE'
getent passwd debian >/dev/null
debian_uid=$(id -u debian)
loginctl terminate-user debian || true
if pgrep -u "$debian_uid" >/dev/null; then
  echo 'Refusing to remove debian while processes still use its UID' >&2
  ps -o pid,ppid,user,cmd -u "$debian_uid" >&2
  exit 1
fi
userdel --remove debian
if getent group debian >/dev/null; then
  groupdel debian
fi
REMOTE
```

The deletion is performed through `setup-agent`, not the live `debian` session,
so the active bootstrap login cannot prevent its own removal.
