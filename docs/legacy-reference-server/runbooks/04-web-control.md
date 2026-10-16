# 04 — VPN-only official WebRTC control

Use Google's `android-emulator-container-scripts` WebRTC client and gateway,
pinned to commit `0654f694b46794fae4b178f1e1a17cb60c5d2d34`, under
`/opt/android-emulator-web`. The integration reuses the emulator discovery
token, uses emulator-initiated SDP negotiation, exposes authenticated touch/key
endpoints, and provides a responsive 540×1170 mobile page with a fixed vertical
toolbar. The client replaces its WebRTC session whenever the page returns from
the background or from the browser back-forward cache; this prevents a stale
video track from leaving a black screen on mobile Firefox. The `↻` toolbar
button also replaces the WebRTC session manually without restarting Android or
changing the foreground application.

## Apply

Stage the four repository-owned assets from the repository root:

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
assets=docs/legacy-reference-server/runbooks/assets
scp "$assets/android-emulator-web.patch" "$TARGET:/tmp/"
scp "$assets/android-emulator-gateway.service" "$TARGET:/tmp/"
scp "$assets/android-emulator-web.service" "$TARGET:/tmp/"
scp "$assets/start-android-emulator-gateway.sh" "$TARGET:/tmp/"
```

Install the build dependencies, converge the pinned upstream tree, apply the
patch exactly once, build it as `master`, and install the services:

```sh
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
  git nodejs npm protobuf-compiler python3-venv python3-pip make

if ! test -d /opt/android-emulator-web/.git; then
  install -d -m 755 -o master -g master /opt/android-emulator-web
  sudo -u master git clone \
    https://github.com/google/android-emulator-container-scripts.git \
    /opt/android-emulator-web
fi
sudo -u master git -C /opt/android-emulator-web checkout \
  0654f694b46794fae4b178f1e1a17cb60c5d2d34
if sudo -u master git -C /opt/android-emulator-web apply --check \
  /tmp/android-emulator-web.patch; then
  sudo -u master git -C /opt/android-emulator-web apply \
    /tmp/android-emulator-web.patch
elif ! sudo -u master git -C /opt/android-emulator-web apply --reverse --check \
  /tmp/android-emulator-web.patch; then
  echo 'The WebRTC source differs from both the upstream and patched states' >&2
  exit 1
fi

sudo -u master sh -eu <<'BUILD'
cd /opt/android-emulator-web/js
npm ci
make protoc
cd example
npm ci
npm run build
python3 -m venv /opt/android-emulator-web/gateway/venv
/opt/android-emulator-web/gateway/venv/bin/pip install \
  /opt/android-emulator-web/gateway
BUILD

install -m 644 /tmp/android-emulator-gateway.service \
  /etc/systemd/system/android-emulator-gateway.service
install -m 644 /tmp/android-emulator-web.service \
  /etc/systemd/system/android-emulator-web.service
install -d -m 755 /usr/local/libexec
install -m 755 /tmp/start-android-emulator-gateway.sh \
  /usr/local/libexec/start-android-emulator-gateway
systemctl daemon-reload
systemctl enable --now \
  android-emulator-gateway.service android-emulator-web.service
REMOTE
```

## Check

The firewall accepts TCP 8000/8001 and UDP 32768-60999 only on `wg0`. The public
interface must expose neither the web UI, gRPC, ADB nor WebRTC media ports.

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
ssh "$TARGET" 'sudo -n -u master sudo -n sh -eu' <<'REMOTE'
systemctl is-enabled --quiet android-emulator-gateway.service
systemctl is-enabled --quiet android-emulator-web.service
systemctl is-active --quiet android-emulator-gateway.service
systemctl is-active --quiet android-emulator-web.service
curl -fsS http://127.0.0.1:8000/ >/dev/null
curl -fsS http://127.0.0.1:8001/api/v1/emulator/status >/dev/null
nft list chain inet server_filter input |
  grep -Eq 'iifname "wg0" tcp dport \{ 8000, 8001 \} .* accept'
nft list chain inet server_filter input |
  grep -Eq 'iifname "wg0" udp dport 32768-60999 .* accept'
test -f /opt/android-emulator-web/js/example/src/App.tsx
grep -q 'reconnectStream' /opt/android-emulator-web/js/example/src/App.tsx
grep -q 'webControls' /opt/android-emulator-web/js/example/src/App.tsx
grep -q 'authoritative SDP offer' \
  /opt/android-emulator-web/js/src/components/emulator/net/ws_jsep_protocol_driver.ts
REMOTE
```

On the phone, activate WireGuard and open `http://10.20.0.1:8000`. After a web
deployment, close the existing tab before reopening it so the browser does not
keep the old JavaScript bundle. The `↻` button replaces only the WebRTC session;
it never changes the Android foreground application.
