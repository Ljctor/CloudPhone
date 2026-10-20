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
Every frame-rate figure measured so far, with its conditions. Only rows with
the same conditions compare; fps is the game layer's SurfaceFlinger frames.

| Date | Renderer | Screen | Guest cores / RAM | Regime | Emulator | fps | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-17 or earlier | SwiftShader | 360×780 | 2 / 4 GB | not recorded | – | ~20 | busiest vCPU 86 %, SwiftShader 1.8 cores, encoder 6 % of a core |
| 2026-10-18 (fps phase A) | lavapipe | 480×1040 | 4 / 8 GB | not recorded | uptime not recorded | ~16.5 | frame time p50 58 ms, p95 85 ms; emulator 4.5–5.4 host cores |
| 2026-10-19 | lavapipe | 480×1040 | 4 / 8 GB | first 5 minutes | freshly restarted | 19.6–19.8 | the series of launch options below |
| 2026-10-19 | lavapipe | 480×1040 | 4 / 8 GB | steady state | freshly restarted | 30.6 (worst 10 s 28.7) | p95 53 ms, p99 61 ms; main thread 94 % of one vCPU; emulator ~4.8 host cores |

The game's Power Saving Mode saves nothing on this host: on its near-black
screen (2026-10-20, emulator up 23 h, read-only, no baseline) the game layer
still ran at 20.8 fps with the main thread at 98.6 % and lavapipe at 3.1 host
cores, so the battle keeps being rendered underneath.

With SwiftShader the bottleneck was the guest CPU and software rendering, not
the video encoding or the network: a lower bitrate or a faster link did not
raise the frame rate; fewer pixels and more host CPU did.

### Lavapipe and a Unity game

Measured on one test host (4 cores, 8 threads, no GPU) with `-gpu lavapipe`
and Slayer Legend farming a stage. These are measurements on that host, not
a statement about any other server.

- The guest has 4 vCPUs, but Unity reports `Cores = 2` and `2 big (mask
  0x3)` on its own, from the emulator's fake cpufreq: the game runs one
  `Job.Worker` thread beside its main thread. The emulator's gRPC status
  reports `numberOfCpuCores: 16` for the same 4-vCPU guest: an emulator
  quirk, not the real count.
- The game is an arm64-v8a il2cpp build, run through ARM translation
  (`ro.dalvik.vm.native.bridge = libndk_translation.so`); no x86_64 build is
  served. Its main thread at about 94 % of one vCPU is the ceiling.
- Host rendering path: the guest's gfxstream GLES encoder → ANGLE on Vulkan
  → lavapipe (Mesa 25.2.4, bundled with the emulator, `llvmpipe` threads),
  about 2.5–3.2 host cores of rasterisation.

**Two regimes after each game launch.** For about the first 5 minutes after
TAP TO START the game runs paced at 60/3 = 20 fps (60/4 = 15 when the host is
loaded); at about 5:00 it switches to an unpaced mode capped near 30 fps. The
switch time did not move with host load, so it is most likely a timer in the
game. fps per minute, from the game layer's SurfaceFlinger frames:

| Minute after TAP TO START | 1–5 | 6–20 |
|---|---|---|
| Clean host (35 % idle) | 18.0–19.8 | 29.1–31.5 |
| Two extra busy loops (23 % idle) | 13.6–15.5 | 22.8–23.7 |

Method rule: a steady-state measurement starts at least 6 minutes after TAP
TO START (7 on a loaded host), and every table says which regime it
measured.

The present-to-present histogram in steady state is continuous (peak 26–33
ms, nothing clustered on 16.7 ms multiples), so the display's 60 Hz vsync
does not quantise frames and `hw.lcd.vsync` was not changed.

Launch and emulator options, each measured for 180 s **in the first-5-minute
regime** (so only relative to each other, against the ~20 fps ceiling of that
regime); one emulator restart separates the two groups:

| Change | fps | Verdict |
|---|---|---|
| none (before the restart) | 16.4 | baseline |
| Unity `-job-worker-count 2` / `3` / `4` | 16.8 / 17.1 / 17.3 | +2 to +5 %, within noise |
| Unity `-force-vulkan` | – | not available: the build has no Vulkan device |
| Unity `-force-gles20` | – | same as the default (treated as `-force-gles`) |
| none, `-job-worker-count 3` (after the restart) | 19.7 | baseline |
| `LP_NUM_THREADS=4` | 16.8 | −15 %: the rasteriser needs its threads |
| `-feature -GLPipeChecksum` | 19.8 | no effect |
| `GALLIVM_PERF=brilinear,rho_approx,no_quad_lod` | 19.7 | no effect |
| `LP_PERF=no_mip_linear` | – | not run: the filtering shortcuts above had no effect, so texture filtering is not the limit |
| `-feature -GLAsyncSwap` | 17.5 | worse: async swap helps |
| `-feature GLDirectMem` | 19.6 | no effect |
| `-feature VirtioGpuNativeSync` | – | the emulator crashes (SIGSEGV) when the game starts |

The one transferable lesson: anything that loads the host or stalls the
swap path costs frames. A freshly restarted emulator was also 12–15 % faster
than one up for a day; that is being measured separately.

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
