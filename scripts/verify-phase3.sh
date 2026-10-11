#!/bin/sh
set -eu

target=${1:-}
if [ -z "$target" ] || [ "${target%%@*}" != setup-agent ]; then
  echo "usage: $0 setup-agent@SERVER_ADDRESS" >&2
  exit 2
fi

ssh -o BatchMode=yes -o ConnectTimeout=10 "$target" \
  'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
test "$(uname -m)" = x86_64
test -c /dev/kvm
test -x /opt/android-sdk/emulator/emulator
/opt/android-sdk/emulator/emulator -version 2>&1 |
  grep -q 'Android emulator version 36\.6\.11\.0 (build_id 15507667)'
test -x /opt/android-sdk/platform-tools/adb
test -d /opt/android-sdk/system-images/android-36/google_apis_playstore/x86_64
test -f /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'abi.type=x86_64' /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'hw.lcd.density=240' /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'hw.keyboard=yes' /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'hw.keyboard.lid=yes' /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'hw.lcd.width=540' /opt/android-avd/slayer-google-test.avd/config.ini
grep -qx 'hw.lcd.height=1170' /opt/android-avd/slayer-google-test.avd/config.ini
test "$(stat -c %U:%G /opt/android-avd/slayer-google-test.avd)" = master:master

for unit in android-emulator android-emulator-gateway android-emulator-web wg-quick@wg0 nftables; do
  systemctl is-enabled --quiet "$unit"
  systemctl is-active --quiet "$unit"
done
! systemctl cat android-emulator.service | grep -q -- '-skip-adb-auth'
test "$(stat -c %a /home/master/.android/adbkey)" = 600

adb=/opt/android-sdk/platform-tools/adb
sudo -u master "$adb" -s emulator-5558 wait-for-device
test "$(sudo -u master "$adb" -s emulator-5558 shell getprop sys.boot_completed | tr -d '\r')" = 1
test "$(sudo -u master "$adb" -s emulator-5558 shell getprop ro.adb.secure | tr -d '\r')" = 1
test "$(sudo -u master "$adb" -s emulator-5558 shell getprop ro.build.version.release | tr -d '\r')" = 16
test "$(sudo -u master "$adb" -s emulator-5558 shell wm density | tr -d '\r')" = 'Physical density: 240'
test "$(sudo -u master "$adb" -s emulator-5558 shell settings get secure show_ime_with_hard_keyboard | tr -d '\r')" = 1
test "$(sudo -u master "$adb" -s emulator-5558 shell getprop persist.sys.timezone | tr -d '\r')" = Europe/Paris
test "$(sudo -u master "$adb" -s emulator-5558 shell settings get global auto_time | tr -d '\r')" = 1
test "$(sudo -u master "$adb" -s emulator-5558 shell settings get global auto_time_zone | tr -d '\r')" = 0
test "$(sudo -u master "$adb" -s emulator-5558 shell settings get system screen_off_timeout | tr -d '\r')" = 2147483647
sudo -u master "$adb" -s emulator-5558 shell dumpsys deviceidle whitelist |
  grep -q 'com\.gear2\.growslayer'
bucket=$(sudo -u master "$adb" -s emulator-5558 shell am get-standby-bucket com.gear2.growslayer | tr -d '\r')
test "$bucket" -le 10
sudo -u master "$adb" -s emulator-5558 shell pm path com.gear2.growslayer |
  grep -q '^package:'
sudo -u master "$adb" -s emulator-5558 shell pidof com.gear2.growslayer >/dev/null
sudo -u master "$adb" -s emulator-5558 shell dumpsys activity activities |
  grep -m1 'topResumedActivity=.*com\.gear2\.growslayer'
if systemctl cat slayer-watchdog.service >/dev/null 2>&1; then exit 1; fi

ip -4 address show dev wg0 | grep -q '10\.20\.0\.1/24'
wg show wg0 listen-port | grep -qx 51820
wg show wg0 allowed-ips | grep -q '10\.20\.0\.2/32'
nft list chain inet server_filter input | grep -q 'policy drop'
nft list chain inet server_filter input | grep -Eq 'tcp dport 52242 .* accept'
nft list chain inet server_filter input | grep -Eq 'udp dport 51820 .* accept'
nft list chain inet server_filter input | grep -Eq 'iifname "wg0" tcp dport \{ 8000, 8001 \} .* accept'
nft list chain inet server_filter input | grep -Eq 'iifname "wg0" udp dport 32768-60999 .* accept'

curl -fsS --max-time 5 http://127.0.0.1:8000/ >/dev/null
curl -fsS --max-time 5 http://127.0.0.1:8001/api/v1/emulator/status >/dev/null
grep -q 'reconnectStream' /opt/android-emulator-web/js/example/src/App.tsx
grep -q 'webControls' /opt/android-emulator-web/js/example/src/App.tsx
grep -q 'authoritative SDP offer' \
  /opt/android-emulator-web/js/src/components/emulator/net/ws_jsep_protocol_driver.ts
ss -lnt | awk '$4 ~ /:(5558|8554)$/ && $4 !~ /127\.0\.0\.1|\[::1\]/ { bad = 1 } END { exit bad }'
! docker ps -a --format '{{.Names}}' 2>/dev/null | grep -Eq '^(slayer-phone|slayer-web)$'
test ! -e /opt/redroid-slayer
test ! -e /etc/modules-load.d/redroid.conf
REMOTE

host=${target#*@}
for port in 8000 8001 8554 5558; do
  if curl -fsS --max-time 3 "http://$host:$port/" >/dev/null 2>&1; then
    echo "FAIL: port $port is reachable outside WireGuard" >&2
    exit 1
  fi
done

echo "PASS: official Android cloud-phone infrastructure is converged"
