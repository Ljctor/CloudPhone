# Installing Cloud Phone

Cloud Phone turns a Linux server into an Android phone you use from a browser.
It installs three systemd services:

| Service | What it does | Listens on |
|---|---|---|
| `cloudphone-emulator` | Google's official Android Emulator running Android 16 with Google Play, headless | `127.0.0.1:5558` (adb), `127.0.0.1:8554` (gRPC) |
| `cloudphone-gateway` | Streams the screen over WebRTC and forwards touch and keys | `LISTEN_ADDRESS:8001` (always `WEB_PORT` + 1), WebRTC media on UDP 32768-60999 |
| `cloudphone-web` | Mobile control page (540×1170 screen with a toolbar) | `LISTEN_ADDRESS:8000` |

```text
 phone browser ──WireGuard──▶ :8000 web page
                              :8001 gateway ──gRPC (loopback)──▶ Android Emulator
              ◀──WebRTC video (UDP)──────────────────────────────┘
```

> **The web page and the gateway have no login.** Anyone who can reach ports
> 8000 and 8001 controls the phone and its Google account. Reach them only
> through a VPN: follow [WIREGUARD.md](WIREGUARD.md) after installing.

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
a firewall blocks ports 8000, 8001 and UDP 32768-60999 from the internet:

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
5. creates the Android device (AVD) `cloudphone` with a 540×1170 screen;
6. installs the gateway and the web page, then starts the three services;
7. waits until Android has booted and the page answers.

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

- Gray screen with a spinner and an orange dot: the video stream is still
  connecting.
- Green dot: video is playing. A black screen with a green dot means Android
  itself displays black (for example, the screen is off: press the power key).
- `↻` reconnects the video stream only. It never restarts Android or the app in
  the foreground.

## Configuration

Settings live in `/etc/cloudphone/cloudphone.conf`; upgrades keep your edits.

| Setting | Default | Meaning |
|---|---|---|
| `LISTEN_ADDRESS` | `0.0.0.0` | Address of the web page and the gateway |
| `WEB_PORT` | `8000` | Port of the web page; the gateway uses `WEB_PORT` + 1 |
| `AVD_NAME` | `cloudphone` | Android device to run |
| `EMULATOR_MEMORY_MB` | `4096` | RAM given to Android |
| `EMULATOR_CORES` | `4` | CPU cores given to Android |
| `EMULATOR_GPU` | `swiftshader_indirect` | Software rendering, works without a GPU |
| `EMULATOR_PORT` / `GRPC_PORT` | `5558` / `8554` | Loopback ports of the emulator (it also uses `EMULATOR_PORT` + 1) |
| `ANDROID_ADB_SERVER_PORT` | `5037` | adb server of this instance |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` / `SCREEN_DENSITY` | `540` / `1170` / `240` | Screen of a newly created device |

Apply a change with `sudo systemctl restart cloudphone-emulator` (this reboots
Android) or, for `LISTEN_ADDRESS` and `WEB_PORT` only,
`sudo systemctl restart cloudphone-gateway cloudphone-web`.

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
EMULATOR_GPU=swiftshader_indirect
EMULATOR_PORT=5560
GRPC_PORT=8556
ANDROID_ADB_SERVER_PORT=5038
SCREEN_WIDTH=540
SCREEN_HEIGHT=1170
SCREEN_DENSITY=240
CONF
sudo ./install.sh
```

The page is then on port 8100 and the gateway on 8101. With software
rendering, each emulator keeps several CPU cores busy; to give another
workload priority, lower this instance's CPU share:

```sh
sudo systemctl edit cloudphone-emulator   # add: [Service] CPUWeight=20
```

## Day-to-day operations

```sh
systemctl status cloudphone-emulator cloudphone-gateway cloudphone-web
journalctl -u cloudphone-gateway -f                 # follow the streaming logs
sudo systemctl restart cloudphone-gateway cloudphone-web   # fix streaming; Android keeps running
sudo systemctl restart cloudphone-emulator          # reboot Android
```

After an upgrade of the web page, close the browser tab and open it again so
the browser does not keep the old version.

### Upgrade

Unpack the new release and run its `install.sh` the same way. Android's data
is kept. Android itself is restarted only when the release pins a different
emulator version; otherwise only the gateway and the web page restart.

### Roll back

The previous release stays in `/opt/cloudphone/releases/`:

```sh
ls -t /opt/cloudphone/releases/
sudo ln -sfn /opt/cloudphone/releases/<previous> /opt/cloudphone/current
sudo systemctl restart cloudphone-gateway cloudphone-web
```

### Back up the phone

Everything Android stores (Google account, apps, app data) is in
`/var/lib/cloudphone/avd/`. Back it up with Android stopped:

```sh
sudo systemctl stop cloudphone-emulator
sudo tar czf cloudphone-avd-$(date +%F).tar.gz -C /var/lib/cloudphone avd
sudo systemctl start cloudphone-emulator cloudphone-gateway cloudphone-web
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
| Spinner forever, gateway logs show ICE failures | WebRTC media cannot reach the phone: allow UDP 32768-60999 on the WireGuard interface (see [WIREGUARD.md](WIREGUARD.md)). |
| The page loads but the screen stays gray after Android was restarted | `sudo systemctl restart cloudphone-gateway` |
| `cloudphone-emulator` keeps restarting | `journalctl -u cloudphone-emulator -n 100`; check free RAM against `EMULATOR_MEMORY_MB`. |
| The page does not load at all | Check `LISTEN_ADDRESS`: with a WireGuard address, the tunnel must be up on the server (`wg show`). The services retry until it is. |

## Files

| Path | Content | Removed by `uninstall.sh` |
|---|---|---|
| `/opt/cloudphone/current` | Active release: web page, gateway, launchers | yes |
| `/opt/cloudphone/android-sdk` | Android SDK, pinned emulator, system image | yes |
| `/var/lib/cloudphone/avd` | **Android's data** | only with `--purge` |
| `/var/lib/cloudphone/.android` | adb key of the service account | only with `--purge` |
| `/etc/cloudphone` | Configuration and gRPC access policy | only with `--purge` |
| `/etc/systemd/system/cloudphone-*.service` | Services | yes |

## Building from source

On a Linux x86-64 machine with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh
```

The script fetches Google's `android-emulator-container-scripts` at the commit
pinned in `packaging/versions.env`, applies `apps/android-emulator-web/overlay`,
runs the JavaScript tests, builds the web page and the gateway wheel, checks
that every Python dependency has a wheel for Python 3.10 to 3.13, and writes
`dist/cloudphone-<version>-linux-x86_64.tar.gz` with its checksum. Downloads
are cached in `build/cache`. The tarball is reproducible for a given commit.
