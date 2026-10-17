# Tutorial: Cloud Phone from scratch

This walks you through a complete installation, from a fresh server to an
Android phone with Google Play in your phone's browser. It follows the four
parts in order and points to their docs for detail. Agents follow the parts'
`AGENTS.md` instead; the scripts are the same.

```text
 your phone ──WireGuard (UDP 51820)──▶ server 10.20.0.1
   browser ──http://10.20.0.1:8000/──▶ cloudphone-gateway (page + API, one port)
           ◀──WebRTC video (UDP 32768-60999)── Android Emulator (cloudphone-emulator)
```

The page has no login: whoever reaches it controls the phone and its Google
account. That is why it listens only on the WireGuard address.

## What you need

- **A server**: x86-64 with KVM (`ls -l /dev/kvm`), Debian 12/13 or Ubuntu
  22.04/24.04, 4 CPU cores, 6 GiB RAM, 15 GiB free disk, a public address,
  and SSH access with a key. No GPU is needed (Android is drawn on the CPU).
- **A workstation** (Linux x86-64) with git, curl, make, ssh, Node.js 18+ and
  Python 3.10+, to build the release and drive the server.
- **A phone** (or any device) with the WireGuard app, and a Google account.

In the commands below, `SERVER` is how you reach the server with ssh: a host
alias or `USER@SERVER_ADDRESS`. A host alias in `~/.ssh/config` saves typing:

```text
Host cloudphone
  HostName SERVER_ADDRESS
  Port 52242            # after part 01; 22 before
  User setup-agent      # after part 01
```

## 1. Build the release

On the workstation, from a clone of this repository:

```sh
packaging/build-release.sh
```

It downloads Google's streaming sources at a pinned commit, runs the jest
unit tests, builds the web page and the gateway, and writes
`dist/cloudphone-<version>-linux-x86_64.tar.gz` with its checksum. The first
run takes a few minutes; downloads are cached in `build/cache`.

## 2. Harden the server (part 01)

[`01-server-system-setup/`](../01-server-system-setup/) turns a fresh Debian
server into a hardened baseline: personal accounts, SSH on port 52242, an
nftables firewall that drops everything not allowed, Fail2ban, auditing. Its
runbooks are run from the workstation over SSH, one by one, in order: each
has a **Check**, and an **Apply** to run when the Check fails (see
[`METHOD.md`](METHOD.md) and the part's `AGENTS.md`).

- Keep an SSH session open while runbook 06 moves SSH and loads the firewall.
- Runbooks 08–09 ask you to type a password; never paste it anywhere else.
- When it is done, you log in as `setup-agent` on port 52242 and reach root
  through `master`:

  ```sh
  export AS_ROOT='sudo -n -u master sudo -n'
  ```

Part 01 assumes a fresh server reached as the provider's `debian` account.
If yours differs, read the runbooks before running them. If you skip part
01, you still need an nftables firewall with a drop policy (the scripts of
parts 02 and 04 add their rules to it; see the
[02 README](../02-wireguard-server/README.md#4-firewall)) and an account with
password-less sudo; then use `export AS_ROOT='sudo -n'`.

## 3. Copy the release to the server

```sh
packaging/stage-release.sh SERVER
```

It uploads the tarball, verifies its checksums and unpacks it as root. It
prints the directory to use next:

```sh
export RELEASE=/var/tmp/cloudphone-release/cloudphone-VERSION-linux-x86_64
```

## 4. Set up WireGuard (part 02)

On the server, create the tunnel and open UDP 51820 in the firewall:

```sh
ssh SERVER "$AS_ROOT $RELEASE/02-wireguard-server/scripts/install.sh"
```

If your hosting provider has its own network firewall, allow UDP 51820 there
too.

On the phone, in the WireGuard app: **+ → Create from scratch**, name
`cloudphone`, tap the generate icon next to *Private key*, set *Addresses* to
`10.20.0.2/32`. Copy the **public** key (the private key never leaves the
phone), then authorize it on the server:

```sh
ssh SERVER "$AS_ROOT $RELEASE/02-wireguard-server/scripts/add-peer.sh phone 'PHONE_PUBLIC_KEY' 10.20.0.2"
```

It prints the peer values to enter in the app: the server's public key,
*Endpoint* `SERVER_ADDRESS:51820`, *Allowed IPs* `10.20.0.0/24`,
*Persistent keepalive* 25. Save, switch the tunnel on, and check on the
server that the phone shows a *latest handshake*:

```sh
ssh SERVER "$AS_ROOT $RELEASE/02-wireguard-server/scripts/verify.sh"
ssh SERVER "$AS_ROOT wg show wg0"
```

More devices: same `add-peer.sh` with `10.20.0.3`, `10.20.0.4`… Manual
setup and ufw: [02 README](../02-wireguard-server/README.md).

## 5. Install Android (part 03)

Google's emulator and system image are downloaded on the server, and you must
accept Google's Android SDK licences. Run the installer in a terminal (`-t`)
so it can show them:

```sh
ssh -t SERVER "$AS_ROOT $RELEASE/03-android-emulator/scripts/install.sh"
```

It checks the host, installs the SDK, the pinned emulator and the Android 16
Google Play image, creates the device, starts `cloudphone-emulator` and waits
for Android to boot: 5–20 minutes. Do not interrupt it. Then:

```sh
ssh SERVER "$AS_ROOT $RELEASE/03-android-emulator/scripts/verify.sh"   # prints PASS
```

Another Android emulator or adb server on the same host? Write
`/etc/cloudphone/cloudphone.conf` with free ports **before** installing
([03 README](../03-android-emulator/README.md#several-instances-on-one-host));
the page is then on port 8100 instead of 8000.

## 6. Install the page and the gateway (part 04)

Open the page's ports on the WireGuard interface only, then install, bound to
the WireGuard address:

```sh
ssh SERVER "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --apply"
ssh SERVER "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/install.sh --listen 10.20.0.1"
ssh SERVER "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"   # prints PASS
```

`cloudphone-gateway` serves the page and its API on one port, `WEB_PORT`
(8000), and streams the video over UDP 32768-60999. `verify.sh` also checks
that the page carries its token, that requests from other sites are refused
and that nothing listens outside the WireGuard address.

## 7. Open the phone

On the phone, with the WireGuard tunnel on, open
**http://10.20.0.1:8000/** in the browser. Android appears within about 10
seconds. Sign in to Google Play as on a new phone (prefer the prompt or
passkey on your own phone), then install your apps from Google Play.

The bar holds: power and volume, the **ping** block, recents / home / back,
the **fps** block, `↻` (reconnect the video), fullscreen. The ping block
opens **Server settings**: server and Android state, Android's screen size,
**Disconnect** for other devices. The fps block opens **Client settings**:
language (French or English), touch marker, other options. In fullscreen, a
fold button hides the bar (a small handle brings it back); a long press on it
docks the bar instead.

Optional: to keep one app running around the clock, follow part 04's
[runbook 04](../04-cloud-phone-app/runbooks/04-commissioning.md) (screen
always on, battery exemptions).

## 8. First checks

- The LED in the corner of `↻` is green and no message covers the screen.
- A swipe from the top opens Android's notification shade; home, back and the
  volume keys work.
- Client settings → *Touches via* says `data channel` (touches go straight
  to the emulator; `HTTP` means the fallback through the gateway).
- Server settings → *Android service* is `active (running)`, *Android
  booted* is yes.
- `↻` brings the image back without restarting the app on screen.
- From outside the VPN, `http://SERVER_ADDRESS:8000/` does not answer.

## Updating

Pull the new version, rebuild, then stage and install in one command:

```sh
packaging/build-release.sh
packaging/deploy.sh SERVER 04       # the page and the gateway; Android keeps running
packaging/deploy.sh SERVER 03 04    # also part 03 (upgrades only: licences already accepted)
```

`deploy.sh` uses `AS_ROOT` (default: through `master`) and `LISTEN` (default
`10.20.0.1`). Reload the page afterwards.

## Troubleshooting

The page tells you what is wrong. Messages that cover the screen block it;
the others are banners with a close cross (a closed banner comes back only if
the problem changes).

| Message | What to do |
|---|---|
| Server unreachable | Switch the phone's WireGuard tunnel on. Still there: `systemctl status cloudphone-gateway` on the server. |
| Another device took over | Someone pressed Disconnect on another device. Tap `↻` to take the phone back. |
| Changing resolution / Android is restarting… | A screen size change reboots Android: 1–2 minutes. |
| Android crashed / Restarting automatically… | systemd restarts it; the page reconnects by itself. |
| Android stopped on an error / Android is stopped | It will not come back alone: `journalctl -u cloudphone-emulator -n 100`, then `sudo systemctl start cloudphone-emulator`. |
| Android is starting… / The server is reconnecting to Android… | Wait; the first boot takes up to 10 minutes. |
| Video interrupted | The page reconnects by itself. |
| The video does not connect | UDP 32768-60999 does not reach the phone: run `firewall.sh --check`; some networks block UDP. Tap `↻` to retry. |
| Touches do not reach Android | `sudo systemctl restart cloudphone-gateway`, then reload the page. |
| Another device is watching this phone | Information: the image may be slower. Server settings → Disconnect. |
| Server under heavy load | Information: a smaller screen size (Server settings) costs less CPU. |

Other problems:

| Symptom | Fix |
|---|---|
| `install.sh` stops at `/dev/kvm is missing` | Enable VT-x/AMD-V, or nested virtualization for a VM. |
| `install.sh` says a port is in use | Another program uses it: choose free ports in `/etc/cloudphone/cloudphone.conf`. |
| No *latest handshake* in `wg show` | UDP 51820 blocked (server or provider firewall), or a wrong key or endpoint in the app. |
| Handshake OK but the page does not load | `ssh SERVER "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"` names the failing check. |
| Buttons do nothing after an update | Reload the page: each gateway start issues a new page token. |

More: [`INSTALL.md`](INSTALL.md) (configuration, backup, roll back,
uninstall), [02 README](../02-wireguard-server/README.md#troubleshooting),
[03 README](../03-android-emulator/README.md#performance) (why the image is
around 20 fps without a GPU).
