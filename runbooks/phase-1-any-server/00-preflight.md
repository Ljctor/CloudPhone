# 00 — Preflight

This step proves that the documented transport and privilege assumptions are
true before the server is changed.

On a fresh server, use the provider account `debian`. On an interrupted or
already converged server where `debian` has been retired, use `setup-agent`.
This makes the runbook restartable from step 00 in both states.

## Check

```sh
: "${TARGET:?Set TARGET to debian@SERVER_ADDRESS or setup-agent@SERVER_ADDRESS}"
case ${TARGET%%@*} in
  debian)
    privilege_check='sudo -n true'
    ;;
  setup-agent)
    privilege_check='test "$(sudo -n -u system-setup id -un)" = system-setup && sudo -n -u system-setup sudo -n true'
    ;;
  *)
    echo 'TARGET must use debian or setup-agent' >&2
    exit 2
    ;;
esac
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" 'set -eu
  test -r /etc/os-release
  . /etc/os-release
  test "$ID" = debian || test "${ID_LIKE:-}" = debian
  command -v apt-get >/dev/null
  command -v systemctl >/dev/null
  command -v sshd >/dev/null
'
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" "$privilege_check"
```

Success means SSH required no password, the OS is supported, and the selected
connection account can reach administrative sudo through its documented path.
There is no Apply section: failure means a prerequisite is missing and setup
must stop.
