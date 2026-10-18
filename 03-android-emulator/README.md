# 03 — Android Emulator

Official Android Emulator with Google Play, headless, as a systemd service.
Agents: read `AGENTS.md`. All-in-one install with part 04:
[`../docs/INSTALL.md`](../docs/INSTALL.md).

| Path | Content |
|---|---|
| `scripts/install.sh` | SDK, pinned emulator, system image, AVD, service; waits for boot |
| `scripts/verify.sh` | read-only acceptance test (prints `PASS`) |
| `scripts/measure.sh` | read-only performance sample of the running instance (frame rate inside Android, emulator CPU, host CPU, swap) |
| `scripts/set-resolution.sh` | change Android's screen size (reboots Android); the web page can request it too |
| `files/libexec/cloudphone-display-apply` | root side of size-only changes sent by API clients (`POST /api/v1/display`): checks the request, runs `set-resolution.sh` (started by `cloudphone-display.path`) |
| `files/cloudphone.conf` | default `/etc/cloudphone/cloudphone.conf` |
| `files/emulator_access.json` | gRPC allowlist (token-authenticated, loopback) |
| `files/libexec/cloudphone-emulator` | launcher, installed in `/opt/cloudphone/libexec` |
| `files/systemd/cloudphone-emulator.service` | the service |
| `files/systemd/cloudphone-display.path`, `.service` | root unit applying size-only requests from API clients |
| `files/libexec/cloudphone-settings-apply` | root side of the page's Apply: checks the request (renderer from a fixed list, bounded cores, memory and size), backs up `cloudphone.conf`, sets `EMULATOR_GPU`, `EMULATOR_CORES`, `EMULATOR_MEMORY_MB`, then restarts Android, through `set-resolution.sh` when a screen size comes with it (started by `cloudphone-settings.path`) |
| `files/systemd/cloudphone-settings.path`, `.service` | root unit applying the page's Android settings requests |
| `../lib/versions.env` | pinned versions, URLs and checksums |

Emulator 37.1.11 crashed with Google Play and WebRTC active, hence the pin.
Google's files are downloaded on the server, never redistributed.

## Screen size

`sudo scripts/set-resolution.sh WIDTH HEIGHT DENSITY` (e.g. `360 780 160`)
changes Android's screen and reboots Android; data is kept and the page
follows the new size. Fewer pixels cost less CPU: without a GPU, Android is
drawn and encoded by the CPU. The page's Apply (Information → Server →
Android settings) sends the size together with the renderer, cores and
memory through `cloudphone-settings.path` (root): `cloudphone-settings-apply`
runs `set-resolution.sh` when a size comes with the request, one restart for
all of it. `cloudphone-display.path` and `cloudphone-display-apply` handle
size-only requests (`POST /api/v1/display`) from API clients. Either way, at
most one change every 2 minutes.

## Performance

Without a GPU (the default target), Android is rendered on the CPU.
`EMULATOR_GPU` picks the renderer: `swiftshader` (SwiftShader, the
packaged default), `lavapipe` (recommended by the page: right colours and
the fastest without a GPU), `swangle` or `software` (the emulator's default
software renderer); the page's Android settings switch between them. The
older names `swiftshader_indirect` and `swangle_indirect` are still accepted.
Measured with SwiftShader at 360×780 with a
game running:

| What | Measured |
|---|---|
| Frames rendered inside Android (SurfaceFlinger timestats) | ~20 fps |
| Busiest guest vCPU | ~86 % of a core |
| SwiftShader worker threads | ~1.8 cores |
| Video encoder | ~6 % of a core |

The bottleneck is the guest CPU and software rendering, not the video
encoding or the network: a lower bitrate or a faster link does not raise the
frame rate; fewer pixels and more host CPU do.

### Lavapipe and a Unity game

Measured on one test host (4 cores, 8 threads, no GPU) with `-gpu lavapipe`
and Slayer Legend running. These are measurements on that
host, not a statement about any other server.

- The guest has 4 vCPUs, but Unity reports `Cores = 2` and `2 big (mask
  0x3)` on its own, from the emulator's fake cpufreq: the game runs one
  `Job.Worker` thread beside its main thread.
- The game is an arm64-v8a il2cpp build, run through ARM translation
  (`ro.dalvik.vm.native.bridge = libndk_translation.so`); no x86_64 build is
  served. Its main thread at about 100 % of one vCPU is the known ceiling.
- Host rendering path: the guest's gfxstream GLES encoder → ANGLE on Vulkan
  → lavapipe (Mesa 25.2.4, bundled with the emulator, `llvmpipe` threads),
  about 2.9 host cores of rasterisation.

| What | Measured |
|---|---|
| Frame rate | ~16.5 fps |
| Frame time | p50 58 ms, p95 85 ms |
| Emulator process | ~4.5–5.4 host cores |

Being evaluated, with no recommendation yet: `LP_NUM_THREADS` (lavapipe's
thread count), thread affinity, and `-force-vulkan` for the game.

Measure on the server, as root, while the app to compare is on screen and
animating:

```sh
sudo scripts/measure.sh 60      # seconds; prints one table
```

It prints the screen, renderer, cores, memory and governor, then the app's
frame rate inside Android, the emulator's CPU, the host's free CPU and
Android's swap. Change one setting between two runs and keep the same scene.
It goes through the instance's own adb server (`ANDROID_ADB_SERVER_PORT`,
5037 by default) and never starts one. Never run adb on that port while
`install.sh` runs: the installer checks the port is free before starting
Android.

## Running next to another emulator or adb server

One host runs one Cloud Phone: one `cloudphone.conf`, one
`/var/lib/cloudphone`, fixed unit names. It can share the host with another
emulator or adb server if its ports are free. Before installing, write:

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
```

To give the other workload priority:
`sudo systemctl edit cloudphone-emulator` → `[Service]` `CPUWeight=20`.

Settings, upgrade, backup and uninstall: [`../docs/INSTALL.md`](../docs/INSTALL.md).
