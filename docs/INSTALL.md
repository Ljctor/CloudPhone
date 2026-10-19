# Installing Cloud Phone by hand

Parts 03 and 04 in one command, on any Debian or Ubuntu host with KVM. Agents
and hardened servers follow the parts' `AGENTS.md` instead; the scripts are
the same. New to this? [`TUTORIAL.md`](TUTORIAL.md) walks through the whole
installation, parts 01 to 04, step by step.

Cloud Phone turns a Linux server into an Android phone you use from a browser.
It installs two systemd services, plus two root path units that apply changes
requested from the page: `cloudphone-settings.path` (renderer, cores, memory
and screen size sent by the page's Apply, one restart) and
`cloudphone-display.path` (screen size only, `POST /api/v1/display`, kept for
API clients):

| Service | What it does | Listens on |
|---|---|---|
| `cloudphone-emulator` | Google's official Android Emulator running Android 16 with Google Play, headless | `127.0.0.1:5558` (adb), `127.0.0.1:8554` (gRPC) |
| `cloudphone-gateway` | Serves the mobile control page and its API on one port, streams the screen over WebRTC and forwards touch and keys | `LISTEN_ADDRESS:8000` (`WEB_PORT`), WebRTC media on UDP 32768-60999 |

```text
 phone browser ──WireGuard──▶ :8000 page + gateway ──gRPC (loopback)──▶ Android Emulator
              ◀──WebRTC video (UDP)──────────────────────────────┘
```

> **The page has no login.** Anyone who can reach port 8000 controls the
> phone and its Google account. Reach it only through a VPN: set up
> [part 02](../02-wireguard-server/README.md) first. (The gateway refuses
> requests from other origins and POSTs without the page's per-start token,
> so another web site open in the same browser cannot drive the phone.)

## Requirements

- An **x86-64** host with **KVM**: a dedicated server, or a VM with nested
  virtualization enabled. Check with `ls -l /dev/kvm`.
- **Debian 12/13** or **Ubuntu 22.04/24.04**, with systemd and root access.
- **4 CPU cores** and **6 GiB of RAM** or more (Android itself gets 4 GiB).
- **15 GiB of free disk**: about 6 GiB for the Android SDK under `/opt`, the
  rest for Android's own data under `/var/lib`.
- **Internet access during installation**.

### Why the emulator is downloaded during installation

Google's Android Emulator and the Google Play system image are covered by the
Android SDK License Agreement, which does not allow redistributing them. The
release therefore contains everything else (the streaming gateway, the web
page, the services and the installer) and the installer fetches Google's files
directly from Google:

- the Android Emulator is **pinned to 36.6.11 (build 15507667)** and verified
  against a SHA-256 checksum, because 37.1.11 crashed while Google Play and
  WebRTC streaming were active;
- the command-line tools are pinned and verified the same way;
- the system image `android-36;google_apis_playstore;x86_64` and
  `platform-tools` are installed by Google's `sdkmanager`.

You are asked to read and accept Google's licences during the installation.

## 1. Get the release

Download `cloudphone-<version>-linux-x86_64.tar.gz` and its `.sha256` file
from the repository's releases page onto the server, then verify and unpack:

```sh
sha256sum -c cloudphone-0.1.0-linux-x86_64.tar.gz.sha256
tar xzf cloudphone-0.1.0-linux-x86_64.tar.gz
cd cloudphone-0.1.0-linux-x86_64
sha256sum -c --quiet SHA256SUMS
```

To build the tarball yourself instead, see [Building from source](#building-from-source).

## 2. Install

If you are going to set up WireGuard, do it first and pass the server's
WireGuard address, so the page is never reachable from the internet:

```sh
sudo ./install.sh --listen 10.20.0.1
```

Otherwise install with the default (`0.0.0.0`, every interface) and make sure
a firewall blocks port 8000 and UDP 32768-60999 from the internet:

```sh
sudo ./install.sh
```

The installer:

1. checks the host (x86-64, KVM, CPU, RAM, disk);
2. installs the system packages (Java for `sdkmanager`, the emulator's
   libraries, Python);
3. creates the unprivileged `cloudphone` account, member of `kvm`;
4. installs the Android SDK, the pinned emulator and the system image,
   showing you Google's licences;
5. creates the Android device (AVD) `cloudphone` with a 480×1040 screen (480p);
6. installs `cloudphone-emulator` and the two path units, starts Android and
   waits until it has booted;
7. installs the gateway and the web page, starts `cloudphone-gateway` and
   waits until the page answers.

Downloading the SDK takes a few minutes; Android's first boot takes up to 10
minutes with software rendering. Re-running `install.sh` is safe.

For an unattended installation, after reading the licences once:

```sh
sudo ./install.sh --accept-android-sdk-license --listen 10.20.0.1
```

Other options: `--no-start`, `--no-wait`, and `--emulator-zip FILE` /
`--cmdline-tools-zip FILE` to use archives you already downloaded (they are
still checksum-verified). `./install.sh --help` lists them.

## 3. First use

Open `http://<address>:8000/` in the phone's browser (with WireGuard active,
`http://10.20.0.1:8000/`). Android starts on its home screen; sign in to Google
Play as on a new phone.

- Spinner with "Connecting to the stream…" and an orange LED on `↻`: the
  video stream is still connecting.
- Green LED: video is playing. A black screen with a green LED means Android
  itself displays black (for example, the screen is off: press the power key).
- When something is wrong, the screen or a closable banner says what (see
  [Troubleshooting](#troubleshooting)); the LED turns red when it needs
  action.
- `↻` reconnects the video stream only. It never restarts Android or the app in
  the foreground.
- The ping/fps block opens **Information**, with two tabs. **Client**:
  network, display, touches. **Server**: Status, Machine, Android, Stream
  sent, then **Android settings** (**Renderer**, **Cores**, **Memory**,
  **Device**, **Resolution**: 360p, 480p (default), 720p, 1080p) and one
  **Apply**, which restarts Android with all of them (at most once every 2
  minutes); **Disconnect** appears only when another device is connected.
  The cog opens **Options**: **Language**, **Show the cursor**, **Fold the
  bar 3 s after entering fullscreen**, **Phone alerts**, **Plugins**.
- Both Information tabs end with a log, and events also show as toasts: see
  [Logs, toasts and phone alerts](#logs-toasts-and-phone-alerts).

## Configuration

Settings live in `/etc/cloudphone/cloudphone.conf`; upgrades keep your edits.
The page's Apply (Information → Server → Android settings) rewrites
`EMULATOR_GPU`, `EMULATOR_CORES`, `EMULATOR_MEMORY_MB` and `SCREEN_*` there
too, after saving a copy as `cloudphone.conf.bak-<date>`.

| Setting | Default | Meaning |
|---|---|---|
| `LISTEN_ADDRESS` | `0.0.0.0` | Address of the web page and the gateway |
| `WEB_PORT` | `8000` | Port of the web page and its API (one port, one origin) |
| `AVD_NAME` | `cloudphone` | Android device to run |
| `EMULATOR_MEMORY_MB` | `4096` | RAM given to Android |
| `EMULATOR_CORES` | `4` | CPU cores given to Android |
| `EMULATOR_GPU` | `swiftshader` | Renderer, all without a GPU: `lavapipe` (recommended by the page: right colours, the fastest), `swiftshader` (packaged default), `swangle`, `software` (the emulator's default software renderer); the older `swiftshader_indirect` and `swangle_indirect` are still accepted |
| `EMULATOR_PORT` / `GRPC_PORT` | `5558` / `8554` | Loopback ports of the emulator (it also uses `EMULATOR_PORT` + 1) |
| `ANDROID_ADB_SERVER_PORT` | `5037` | adb server of this instance |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` / `SCREEN_DENSITY` | `480` / `1040` / `213` | Screen of a newly created device |

Apply a change with `sudo systemctl restart cloudphone-emulator` (this reboots
Android; the gateway follows by itself) or, for `LISTEN_ADDRESS` and
`WEB_PORT` only, `sudo systemctl restart cloudphone-gateway`. After changing
`WEB_PORT`, rerun `04-cloud-phone-app/scripts/firewall.sh --apply` so the new
port is allowed on `wg0`.

### Running next to another Android emulator

The installer refuses to start when one of its ports is used by another
program. To run Cloud Phone on a host that already runs an emulator or an adb
server, write the configuration before installing, with free ports:

```sh
sudo install -d /etc/cloudphone
sudo tee /etc/cloudphone/cloudphone.conf >/dev/null <<'CONF'
LISTEN_ADDRESS=10.20.0.1
WEB_PORT=8100
AVD_NAME=cloudphone
EMULATOR_MEMORY_MB=4096
EMULATOR_CORES=2
EMULATOR_GPU=swiftshader
EMULATOR_PORT=5560
GRPC_PORT=8556
ANDROID_ADB_SERVER_PORT=5038
SCREEN_WIDTH=480
SCREEN_HEIGHT=1040
SCREEN_DENSITY=213
CONF
sudo ./install.sh
```

The page is then on port 8100. With software
rendering, each emulator keeps several CPU cores busy; to give another
workload priority, lower this instance's CPU share:

```sh
sudo systemctl edit cloudphone-emulator   # add: [Service] CPUWeight=20
```

## Plugins (optional)

Plugins add features to the page without touching parts 03 and 04. Each one
is a directory `/opt/cloudphone/plugins/<id>/` (`plugin.json`, optional
`page.js` and `gateway.py`), loaded when the gateway starts and listed by
`GET /api/v1/plugins`. Their options appear under cog → Options → Plugins;
without any, that section says "No plugin installed."

Part 05 installs the Slayer Legend plugin, from the unpacked release:

```sh
sudo 05-plugins/scripts/install.sh              # then reload the page
sudo 05-plugins/scripts/install.sh --uninstall
```

For now part 05 has one plugin, `slayer-legend`. `--uninstall` with a name
removes only that plugin (without a name, every plugin); its own data in
`/var/lib/cloudphone/plugins/<id>/` is kept until `uninstall.sh --purge`.
Either way the gateway restarts; Android keeps running. Details:
[`05-plugins/README.md`](../05-plugins/README.md),
[`05-plugins/slayer-legend/README.md`](../05-plugins/slayer-legend/README.md).

## Logs, toasts and phone alerts

**Logs.** Information → Client ends with **Journaux du client** (Client
logs, the page's own records: stream, touches, errors) and Information →
Server with **Journaux du serveur** (Server logs, the gateway's records:
Android, the emulator, adb, setting changes, other viewers). Each folds.
Records are white (normal), orange (warning) or red (error); errors say
what to do next. One **Niveau** (Level) filter serves both: all, warnings
and errors, or errors only. The gateway keeps its last 500 records in
memory; the page keeps the last 200 of each side.

**Toasts.** Events worth your attention also show as toasts at the top of
the screen: the gateway starting or following a new emulator, Android
crashing, stopping or restarting, adb going offline, a settings change
requested, applied or failed, another device connecting or disconnecting
the others, touches falling back to HTTP. Normal toasts go after 6 s,
warnings after 12 s; errors stay until you close them. The full list:
[DEVELOPMENT.md](../04-cloud-phone-app/docs/DEVELOPMENT.md#logs).

The same records reach journald under the identifier `cloudphone-gateway`:

```sh
journalctl -t cloudphone-gateway -p warning      # warnings and errors only; add -f to follow
```

**Phone alerts.** With the page closed, the gateway can still alert your
phone through [ntfy](https://ntfy.sh/): when an app crashes or stops
responding, when Android or the emulator restarts, and when a plugin sends
one. Turn them on in cog → Options → **Alertes sur le téléphone** (Phone
alerts): the page then shows an address `ntfy.sh/cloudphone-…`; subscribe
the ntfy app on your phone to it, and **Envoyer** (Send) a test alert.

- The topic name is long and random, and anyone who knows it can read the
  alerts: treat it like a password. It is shown only on the page.
- The setting and the name are kept on the server
  (`/var/lib/cloudphone/notify.json`, root and `cloudphone` only), across
  restarts and upgrades; turning alerts off and on keeps the same name.
- Messages say nothing private (an app's name, the kind of event) and go
  through the public ntfy.sh service.

## Day-to-day operations

```sh
systemctl status cloudphone-emulator cloudphone-gateway
journalctl -u cloudphone-gateway -f                 # follow the streaming logs
journalctl -t cloudphone-gateway -p warning         # the gateway's warnings and errors
sudo systemctl restart cloudphone-gateway   # fix streaming; Android keeps running
sudo systemctl restart cloudphone-emulator          # reboot Android
```

After an upgrade or a gateway restart, reload the page: the page itself is
never cached, and each gateway start issues a new page token, so the buttons
of a tab opened before answer 403 until it is reloaded.

### Upgrade

Unpack the new release and run its `install.sh` the same way. Android's data
is kept. Android itself is restarted only when the release pins a different
emulator version; otherwise only the gateway and the web page restart.

### Roll back

The previous release stays in `/opt/cloudphone/releases/`:

```sh
ls -t /opt/cloudphone/releases/
sudo ln -sfn /opt/cloudphone/releases/<previous> /opt/cloudphone/current
sudo systemctl restart cloudphone-gateway
```

### Back up the phone

Everything Android stores (Google account, apps, app data) is in
`/var/lib/cloudphone/avd/`. Back it up with Android stopped:

```sh
sudo systemctl stop cloudphone-emulator
sudo tar czf cloudphone-avd-$(date +%F).tar.gz -C /var/lib/cloudphone avd
sudo systemctl start cloudphone-emulator cloudphone-gateway
```

### Uninstall

```sh
sudo ./uninstall.sh            # keeps Android's data and the configuration
sudo ./uninstall.sh --purge    # erases the phone permanently
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `install.sh` stops at `/dev/kvm is missing` | Enable VT-x/AMD-V in the BIOS, or nested virtualization for a VM. Software emulation is far too slow to use. |
| Spinner forever, gateway logs show ICE failures | WebRTC media cannot reach the phone: allow UDP 32768-60999 on the WireGuard interface (see [part 02](../02-wireguard-server/README.md)). |
| The page loads but the screen stays gray after Android was restarted | `sudo systemctl restart cloudphone-gateway` |
| `cloudphone-emulator` keeps restarting | `journalctl -u cloudphone-emulator -n 100`; check free RAM against `EMULATOR_MEMORY_MB`. |
| The page does not load at all | Check `LISTEN_ADDRESS`: with a WireGuard address, the tunnel must be up on the server (`wg show`). The services retry until it is. |
| "Server unreachable" | The page no longer reaches the gateway: switch the phone's WireGuard tunnel on; on the server, `systemctl status cloudphone-gateway`. Right after an Apply in Android settings it can show for a moment while the gateway follows the new Android: wait, it reconnects. |
| "Android stopped on an error" / "Android is stopped" | `sudo systemctl start cloudphone-emulator`; read `journalctl -u cloudphone-emulator -n 100` first. |
| "Android crashed", "Android is starting…", "Changing resolution", "Changing Android settings" | Wait: systemd restarts Android, or an Apply (screen size, renderer, cores, memory) is rebooting it (1–2 minutes). The page reconnects by itself. |
| "The video does not connect" | UDP 32768-60999 does not reach the phone (firewall on `wg0`, or a network blocking UDP). Tap `↻` to retry. |
| "Another device took over" | Someone pressed Disconnect (Information → Server) on another device. Tap `↻` to take the phone back. |
| "Touches do not reach Android" | `sudo systemctl restart cloudphone-gateway`, then reload the page. |
| "Another device is watching this phone" | Information only: the image may be slower. Information → Server → Disconnect closes the other devices. |
| "Server under heavy load" | Information only. A lower Resolution or the Lavapipe renderer (Information → Server → Android settings) costs less CPU. |
| Buttons do nothing (POSTs answer 403) | The tab predates a gateway restart: reload the page. |

## Files

| Path | Content | Removed by `uninstall.sh` |
|---|---|---|
| `/opt/cloudphone/current` | Active app release: web page, gateway | yes |
| `/opt/cloudphone/releases` | Current and previous app release; `current` points into it | yes |
| `/opt/cloudphone/plugins` | Installed plugins, one directory each (part 05) | yes |
| `/opt/cloudphone/libexec` | Emulator launcher and the root helpers of the path units | yes |
| `/opt/cloudphone/tools` | `set-resolution.sh` and what it sources, for the path units | yes |
| `/opt/cloudphone/android-sdk` | Android SDK, pinned emulator, system image | yes |
| `/var/lib/cloudphone/avd` | **Android's data** | only with `--purge` |
| `/var/lib/cloudphone/.android` | adb key of the service account | only with `--purge` |
| `/var/lib/cloudphone/plugins` | Plugins' own data, one directory each (part 05) | only with `--purge` |
| `/etc/cloudphone` | Configuration and gRPC access policy | only with `--purge` |
| `/etc/systemd/system/cloudphone-*.service`, `cloudphone-*.path` | Services and the two path units | yes |

## Building from source

On a Linux x86-64 machine with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh
```

The script fetches Google's `android-emulator-container-scripts` at the commit
pinned in `lib/versions.env`, applies `04-cloud-phone-app/src/overlay`,
builds the web page and the gateway wheel, checks
that every Python dependency has a wheel for Python 3.10 to 3.13, and writes
`dist/cloudphone-<version>-linux-x86_64.tar.gz` with its checksum. Downloads
are cached in `build/cache`. The tarball is reproducible for a given commit.

### Black-box tests

`tests/e2e` holds black-box tests (Rust) that run on a workstation, with
no server and no phone: each test starts the repository's gateway and page
in front of a fake emulator on 127.0.0.1, and the `ui_*` tests drive
Firefox. Prerequisites (Rust, Python 3.10+ with `venv`, Node.js and npm,
`cpio`, `flock`, Firefox ESR and geckodriver for the browser tests) and
setup: [`tests/e2e/README.md`](../tests/e2e/README.md).

```sh
cd tests/e2e
cargo test
```

Run one suite at a time on a machine: two `cargo test` runs at once, from
two checkouts for instance, slow each other down until the browser tests
time out.
