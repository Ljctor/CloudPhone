# 03 — Android Emulator

Official Android Emulator with Google Play, headless, as a systemd service.
Agents: read `AGENTS.md`. All-in-one install with part 04:
[`../docs/INSTALL.md`](../docs/INSTALL.md).

| Path | Content |
|---|---|
| `scripts/install.sh` | SDK, pinned emulator, system image, AVD, service; waits for boot |
| `scripts/verify.sh` | read-only acceptance test (prints `PASS`) |
| `scripts/set-resolution.sh` | change Android's screen size (reboots Android); the web page can request it too |
| `files/libexec/cloudphone-display-apply` | root side of size changes requested from the page: checks the request, runs `set-resolution.sh` (started by `cloudphone-display.path`) |
| `files/cloudphone.conf` | default `/etc/cloudphone/cloudphone.conf` |
| `files/emulator_access.json` | gRPC allowlist (token-authenticated, loopback) |
| `files/libexec/cloudphone-emulator` | launcher, installed in `/opt/cloudphone/libexec` |
| `files/systemd/cloudphone-emulator.service` | the service |
| `files/systemd/cloudphone-display.path`, `.service` | root unit applying screen size requests from the page |
| `files/libexec/cloudphone-settings-apply` | root side of renderer, cores and memory changes requested from the page: checks the request against a fixed list and bounds, backs up `cloudphone.conf`, sets `EMULATOR_GPU`, `EMULATOR_CORES`, `EMULATOR_MEMORY_MB`, restarts Android (started by `cloudphone-settings.path`) |
| `files/systemd/cloudphone-settings.path`, `.service` | root unit applying emulator settings requests from the page |
| `../lib/versions.env` | pinned versions, URLs and checksums |

Emulator 37.1.11 crashed with Google Play and WebRTC active, hence the pin.
Google's files are downloaded on the server, never redistributed.

## Screen size

`sudo scripts/set-resolution.sh WIDTH HEIGHT DENSITY` (e.g. `360 780 160`)
changes Android's screen and reboots Android; data is kept and the page
follows the new size. Fewer pixels cost less CPU: without a GPU, Android is
drawn and encoded by the CPU. The page's Server settings panel requests the
same change through `cloudphone-display.path` (root), at most once every 2
minutes.

## Performance

The server has no GPU: `EMULATOR_GPU=swiftshader_indirect` renders on the
CPU with SwiftShader. Measured at 360×780 with a game running:

| What | Measured |
|---|---|
| Frames rendered inside Android (SurfaceFlinger timestats) | ~20 fps |
| Busiest guest vCPU | ~86 % of a core |
| SwiftShader worker threads | ~1.8 cores |
| Video encoder | ~6 % of a core |

The bottleneck is the guest CPU and software rendering, not the video
encoding or the network: a lower bitrate or a faster link does not raise the
frame rate; fewer pixels and more host CPU do.

Measure the frame rate inside Android, as root on the server, with the
instance's adb server port (`ANDROID_ADB_SERVER_PORT`, here 5038):

```sh
adb() { runuser -u cloudphone -- env HOME=/var/lib/cloudphone \
  /opt/cloudphone/android-sdk/platform-tools/adb -P 5038 "$@"; }
adb shell dumpsys SurfaceFlinger --timestats -clear -enable
sleep 30                                   # use the app meanwhile
adb shell dumpsys SurfaceFlinger --timestats -dump
adb shell dumpsys SurfaceFlinger --timestats -disable
```

Never run adb on that port while `install.sh` runs: the installer checks the
port is free before starting Android.

## Several instances on one host

Each instance needs free ports. Before installing the second one:

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
SCREEN_WIDTH=480
SCREEN_HEIGHT=1040
SCREEN_DENSITY=213
CONF
```

To give the other workload priority:
`sudo systemctl edit cloudphone-emulator` → `[Service]` `CPUWeight=20`.

Settings, upgrade, backup and uninstall: [`../docs/INSTALL.md`](../docs/INSTALL.md).
