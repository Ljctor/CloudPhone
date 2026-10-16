# 02 — Secure persistent emulator service

Install `assets/android-emulator.service` as
`/etc/systemd/system/android-emulator.service` and
`assets/emulator_access.json` as `/etc/android-emulator/emulator_access.json`.
Enable the service after protecting the ADB key with mode 600.

The service deliberately omits `-skip-adb-auth`. ADB and authenticated gRPC are
bound to loopback; the AVD is persistent and runs as `master`, never as root.

## Apply

From the repository root, stage the public service assets, then install them
through the Phase-3 privilege path:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
assets=docs/legacy-reference-server/runbooks/assets
scp "$assets/android-emulator.service" "$TARGET:/tmp/"
scp "$assets/emulator_access.json" "$TARGET:/tmp/"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
install -d -m 755 /etc/android-emulator
install -m 644 /tmp/emulator_access.json \
  /etc/android-emulator/emulator_access.json
install -m 644 /tmp/android-emulator.service \
  /etc/systemd/system/android-emulator.service
sudo -u master env HOME=/home/master \
  /opt/android-sdk/platform-tools/adb start-server
chmod 600 /home/master/.android/adbkey
systemctl daemon-reload
systemctl enable --now android-emulator.service
REMOTE
```

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
systemctl is-enabled --quiet android-emulator.service
systemctl is-active --quiet android-emulator.service
test "$(stat -c %a /etc/android-emulator/emulator_access.json)" = 644
test "$(stat -c %U:%G /etc/android-emulator/emulator_access.json)" = root:root
test "$(stat -c %a /home/master/.android/adbkey)" = 600
! systemctl cat android-emulator.service | grep -q -- '-skip-adb-auth'
ss -lnt | grep -q '127.0.0.1:5558'
ss -lnt | grep -q '127.0.0.1:8554'
sudo -u master /opt/android-sdk/platform-tools/adb -s emulator-5558 wait-for-device
test "$(sudo -u master /opt/android-sdk/platform-tools/adb -s emulator-5558 \
  shell getprop sys.boot_completed | tr -d '\r')" = 1
test "$(sudo -u master /opt/android-sdk/platform-tools/adb -s emulator-5558 \
  shell getprop ro.adb.secure | tr -d '\r')" = 1
test "$(sudo -u master /opt/android-sdk/platform-tools/adb -s emulator-5558 \
  shell wm density | tr -d '\r')" = 'Physical density: 240'
test "$(sudo -u master /opt/android-sdk/platform-tools/adb -s emulator-5558 \
  shell settings get secure show_ime_with_hard_keyboard | tr -d '\r')" = 1
REMOTE
```

`Restart=on-failure` restarts the Android Emulator after a native emulator
failure. It does not launch or restart Slayer Legend; application recovery is
always a human decision.
