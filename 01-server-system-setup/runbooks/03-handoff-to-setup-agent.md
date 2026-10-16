# 03 — Handoff to `setup-agent`

Immediately after the connection accounts and their SSH keys are configured,
stop using the provider bootstrap login. All remaining runbooks, in this part
and in parts 02–04, run as `setup-agent`, which may enter the functional `system-setup`
or `master` but has no direct sudo access.

Set the target before running this check:

```sh
export TARGET=setup-agent@SERVER_ADDRESS
```

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
test "${TARGET%%@*}" = setup-agent
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" \
  'test "$(id -un)" = setup-agent'
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" \
  'test "$(sudo -n -u system-setup id -un)" = system-setup && sudo -n -u system-setup sudo -n true'
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TARGET" \
  'test "$(sudo -n -u master id -un)" = master && sudo -n -u master sudo -n true'
```

There is no Apply section. Failure means the connection-account or delegation
steps must be fixed before continuing. `debian` remains only until runbook 10
can safely delete it.
