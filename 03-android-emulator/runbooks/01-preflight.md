# 01 — Host preflight

Read-only. No Apply: a failure means the host cannot run the emulator.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT sh -eu" <<'REMOTE'
test "$(uname -m)" = x86_64
test -c /dev/kvm
test -d /run/systemd/system
command -v apt-get >/dev/null
test "$(nproc)" -ge 4
test "$(awk '/MemTotal:/ { print int($2 / 1024) }' /proc/meminfo)" -ge 6144
test -d /opt/cloudphone/android-sdk/emulator ||
  test "$(df -Pk /opt | awk 'NR == 2 { print $4 }')" -ge 15728640
REMOTE
```

To run next to another emulator or adb server, write
`/etc/cloudphone/cloudphone.conf` with free ports **before** runbook 02 (see
README, "Running next to another emulator or adb server").
