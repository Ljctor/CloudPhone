# 00 — Official Android Emulator preflight

Phase 3 runs through the functional account `master`. The working target is an
x86-64 host with KVM; Slayer Legend's ARM libraries are handled by the native
translation shipped in Google's Play Store system image.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
test "$(uname -m)" = x86_64
test -c /dev/kvm
test -r /dev/kvm && test -w /dev/kvm
test "$(nproc)" -ge 4
test "$(awk '/MemTotal:/ { print int($2 / 1024) }' /proc/meminfo)" -ge 4096
test "$(df -Pk /opt | awk 'NR == 2 { print $4 }')" -ge 15728640
REMOTE
```

Do not install ReDroid, binder devices, an APK store, or a sideloaded copy of
Slayer Legend. They are not part of the accepted solution.
