# 01 — Connection accounts

Create the three connection accounts: `emergency`, `admin-human`, and
`setup-agent`, plus the functional accounts `system-setup` and `master`. Each
account gets a matching primary group, `/home/NAME`, Bash, and no supplementary groups.
A prior `admin` account is migrated to
`admin-human` while retaining its numeric identity, home contents, password
hash, and SSH authorization. `system-setup` is the sole functional account for
phases 1 and 2. `master` is pre-created for phase 3; other application-specific
accounts belong to phase 3.

The connection accounts have no direct sudo access. `setup-agent`,
`admin-human`, and `emergency` may enter `system-setup` or the phase-3 `master`
account. Both functional accounts have administrative sudo access.

## Check

```sh
: "${TARGET:?Set TARGET to debian@SERVER_ADDRESS or setup-agent@SERVER_ADDRESS}"
case ${TARGET%%@*} in
  debian) root_shell='sudo -n sh -eu' ;;
  setup-agent) root_shell='sudo -n -u system-setup sudo -n sh -eu' ;;
  *) exit 2 ;;
esac
ssh "$TARGET" "$root_shell" <<'REMOTE'
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
test "$(stat -c %a /etc/sudoers.d/connection-delegation)" = 440
test "$(stat -c %U:%G /etc/sudoers.d/connection-delegation)" = root:root
visudo -cf /etc/sudoers.d/connection-delegation >/dev/null
if test -e /etc/sudoers.d/setup-agent; then exit 1; fi
for user in system-setup master; do
  test "$(passwd --status "$user" | awk '{print $2}')" = L
  if test -s "/home/$user/.ssh/authorized_keys"; then exit 1; fi
done
for user in admin-human setup-agent; do
  test "$(passwd --status "$user" | awk '{print $2}')" = NP
  test -z "$(getent shadow "$user" | cut -d: -f3)"
done
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
if getent passwd admin >/dev/null; then
  if getent passwd admin-human >/dev/null; then
    echo 'Refusing to merge existing admin and admin-human accounts' >&2
    exit 1
  fi
  test "$(getent passwd admin | cut -d: -f6)" = /home/admin
  test "$(id -G admin | wc -w)" -eq 1
  if getent group admin-human >/dev/null; then
    echo 'Refusing to overwrite existing admin-human group' >&2
    exit 1
  fi
  groupmod -n admin-human admin
  usermod -l admin-human -d /home/admin-human -m admin
fi

for user in emergency admin-human setup-agent system-setup master; do
  if ! getent passwd "$user" >/dev/null; then
    useradd --create-home --shell /bin/bash --user-group "$user"
  fi
  uid=$(id -u "$user")
  gid=$(id -g "$user")
  home=$(getent passwd "$user" | cut -d: -f6)
  test "$home" = "/home/$user"
  install -d -m 700 -o "$uid" -g "$gid" "$home"
done
for user in admin-human setup-agent; do
  passwd --delete "$user"
  chage --lastday -1 "$user"
done
rm -f /etc/sudoers.d/setup-agent
install -m 440 /dev/stdin /etc/sudoers.d/connection-delegation <<'SUDOERS'
system-setup ALL=(ALL) NOPASSWD:ALL
master ALL=(ALL) NOPASSWD:ALL
setup-agent ALL=(system-setup) NOPASSWD:ALL
setup-agent ALL=(master) NOPASSWD:ALL
admin-human ALL=(system-setup) NOPASSWD:ALL
admin-human ALL=(master) NOPASSWD:ALL
emergency ALL=(system-setup) NOPASSWD:ALL
emergency ALL=(master) NOPASSWD:ALL
SUDOERS
visudo -cf /etc/sudoers.d/connection-delegation >/dev/null
for user in system-setup master; do
  passwd --lock "$user"
  key_file="/home/$user/.ssh/authorized_keys"
  if test -e "$key_file"; then
    test -f "$key_file"
    if test -L "$key_file"; then
      echo "Refusing to remove symlink: $key_file" >&2
      exit 1
    fi
    rm -- "$key_file"
  fi
done
REMOTE
```

The Apply command intentionally refuses to reshape an existing account whose
home differs from the specification. That is an identity conflict, not a safe
automatic repair.
