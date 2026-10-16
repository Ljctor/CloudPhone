# 05 — Google Play and Slayer Legend acceptance

The human operator signs in through the official Google Play UI. Prefer the
Google prompt or passkey on the Samsung phone and disable unneeded Gmail,
Contacts, Drive and Photos synchronization. Never place Google credentials in a
runbook, shell history, vault entry intended for automation, or ADB command.

Install Slayer Legend only from Google Play. The expected package is
`com.gear2.growslayer`; APK sideloading and third-party stores are outside the
accepted configuration.

Keep the Android screen awake and exempt the game from idle restrictions. These
are passive protections: they never launch or restart the game.

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
adb=/opt/android-sdk/platform-tools/adb
$adb -s emulator-5558 shell pm path com.gear2.growslayer | grep -q '^package:'
$adb -s emulator-5558 shell dumpsys package com.gear2.growslayer |
  grep -E 'versionName=|primaryCpuAbi='
$adb -s emulator-5558 shell pidof com.gear2.growslayer >/dev/null
$adb -s emulator-5558 shell dumpsys activity activities |
  grep -m1 'topResumedActivity=.*com\.gear2\.growslayer'
test "$($adb -s emulator-5558 shell settings get system screen_off_timeout | tr -d '\r')" = 2147483647
$adb -s emulator-5558 shell dumpsys deviceidle whitelist |
  grep -q 'com\.gear2\.growslayer'
bucket=$($adb -s emulator-5558 shell am get-standby-bucket com.gear2.growslayer | tr -d '\r')
test "$bucket" -le 10
test "$($adb -s emulator-5558 shell getprop persist.sys.timezone | tr -d '\r')" = Europe/Paris
test "$($adb -s emulator-5558 shell settings get global auto_time | tr -d '\r')" = 1
test "$($adb -s emulator-5558 shell settings get global auto_time_zone | tr -d '\r')" = 0
if systemctl cat slayer-watchdog.service >/dev/null 2>&1; then exit 1; fi
REMOTE
```

## Apply

The human operator installs Slayer Legend from Google Play and launches it
manually. Configure only the passive Android protections and the CET/CEST
timezone automatically:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
adb=/opt/android-sdk/platform-tools/adb
$adb -s emulator-5558 shell settings put system screen_off_timeout 2147483647
$adb -s emulator-5558 shell dumpsys deviceidle whitelist +com.gear2.growslayer
$adb -s emulator-5558 shell am set-inactive com.gear2.growslayer false
$adb -s emulator-5558 shell am set-standby-bucket com.gear2.growslayer active
$adb -s emulator-5558 shell settings put global auto_time_zone 0
$adb -s emulator-5558 shell cmd alarm set-timezone Europe/Paris
REMOTE
```

If the process or foreground checks fail, the human operator decides whether
to launch the game. The runbook deliberately contains no watchdog and no
automatic application launch.

Acceptance additionally requires visible rendering, responsive touch, working
network/account login, and persistence after an emulator restart.
