# End-to-end tests

Black-box tests of Cloud Phone, written in Rust. They know only what a
user's browser reaches: the page, its HTTP and WebSocket API, and the page
as Firefox renders it. They never import the application's code. In the
browser they find things the way a user does: ARIA labels and roles,
visible text (French by default), labels of form fields.

By default every test starts its own instance on this machine: the
repository's gateway and page, unchanged, in front of a **fake emulator**
(`tests/fake-emulator`). Everything listens on 127.0.0.1 on free ports.
There is no phone, no game and no server involved, so the whole suite runs
on a workstation with only the repository. Tests against a deployed
instance are a separate, opt-in category (see "Smoke and contract tests").

```sh
cd tests/e2e
cargo test                         # everything, on the fake
cargo test --test api --test state # some files only
CLOUDPHONE_E2E_KEEP=1 cargo test --test display -- some_test   # keep the fake's files (logs) in $TMPDIR
```

## Prerequisites

- Rust (stable), Python 3.10 or later with `venv`, Node.js and npm,
  `cpio` and `flock` (used by `prepare.sh`).
- Firefox ESR and geckodriver for the `ui_*` tests (see "Browser").
- The first run needs `build/upstream` (the upstream page and the gRPC
  stubs): it calls `packaging/build-release.sh --skip-tests` if it is
  missing. Set `CLOUDPHONE_E2E_NO_BUILD=1` to fail instead, for instance
  while a release build runs: two builds at once wipe each other's build
  directory.

`tests/fake-emulator/prepare.sh` runs once per test binary and keeps
everything under `build/e2e/` (ignored by git):

| Path | What |
|---|---|
| `build/e2e/base/` | the upstream page sources with their `node_modules` and the gRPC stubs, taken once from `build/upstream` (hard links): later runs never read `build/upstream`, so a release build does not disturb them. Delete it to take them again |
| `build/e2e/web/` | the page, built from the overlay in a private copy (`build/e2e/js/`) whenever an overlay page file changed |
| `build/e2e/gateway/videobridge_gateway/` | the gateway's sources (symlinks to the overlay, so edits apply at the next test) and the gRPC stubs |
| `build/e2e/venv-gateway/` | the gateway's dependencies, from `04-cloud-phone-app/constraints.txt` |
| `build/e2e/venv-fake/` | the fake's dependencies, from `tests/fake-emulator/requirements.txt` (aiortc, grpcio, numpy...) |

The venvs are recreated when their pins change. Python packages come from
the public PyPI.

## The fake emulator

`tests/fake-emulator/fake_emulator.py` plays everything around the gateway,
in a fresh directory per test:

- the emulator's gRPC services (EmulatorController and Rtc) with the bearer
  token of its discovery file;
- the WebRTC stream (aiortc): a synthetic Android screen at the configured
  size with a frame counter, the last touch (a white disc while pressed, a
  ring after) and the last key; the data channels `mouse`, `keyboard`,
  `touch`, `adb`, whose raw protobuf messages are decoded and recorded;
- the files the gateway reads: discovery file `running/pid_N.ini`, AVD
  `config.ini`, request and status files of the display and settings
  services, answered the way part 03's root scripts do (including the
  emulator restart and the new discovery file that make the gateway exit
  and be restarted, as systemd does);
- `adb` and `systemctl` on the gateway's `PATH` (`tests/fake-emulator/bin`);
- the host figures (`/proc/loadavg`, `/proc/meminfo`, the unit's cgroup):
  `gateway_shim.py` starts the gateway with `open()` redirected for those
  paths only. The gateway itself is not modified;
- plugins: `--plugins_dir` is an empty directory unless a test installs
  some (`"plugins": ["tests/fake-emulator/plugins/e2e-probe"]`). The test
  plugins under `tests/fake-emulator/plugins` exercise the plugin host;
  game plugins are not tested against the fake, except Slayer Legend's
  state kept across gateway restarts (routes that need no game screen).
  `--plugin_data` is a directory of the fake's, kept across gateway
  restarts;

Its control API (127.0.0.1, random port), wrapped by `src/fake.rs`:

| Call | What |
|---|---|
| `GET /record` | everything received: touches (with the channel or `grpc`), keys (`keyboard` channel, `adb`, `grpc`), data channel messages, gRPC calls, JSEP messages each way, display/settings requests and status lines, WebRTC sessions, gateway starts and exits, adb calls |
| `GET /state` | the fake's state: display, settings, unit, booted, gRPC up/down, sessions, gateway |
| `POST /control` | `options` (`data_channels`, `offer`, `touch_fails`, `adb_fails`, `hold_requests`, `status_lcd`, timings), `fail_next`, `load`, `unit`, `booted`, `grpc`, and one `action`: `drop_streams` (`bye`), `crash`, `restart`, `replace_discovery`, `stop_gateway`, `start_gateway`, `restart_gateway`, `pause_gateway` (`seconds`: stalled, then resumed), `reset_record` |

Initial state: `CloudPhone::start_with(json!({...}))`, keys as in
`DEFAULTS` in `fake_emulator.py` (480×1040 at density 213, lavapipe,
4 cores, 4 GiB, Android booted).

What the fake does that nothing in the repository confirms is marked
`UNVERIFIED` in its source: the contract tests print the real values. The
guesses they cover were checked against a live emulator (2026-10); the
marks left are the ones they do not print.
`vmConfig.numberOfCpuCores` is 16 on the live instance with 4 cores
configured on an 8-thread host (rule unknown), while the fake reports the
configured count.

## Files

| File | What it checks |
|---|---|
| `tests/page.rs` | the page carries a fresh token, is not cached; its assets are |
| `tests/guard.rs` | POSTs need the page's token; other sites are refused; no CORS |
| `tests/state.rs` | server state, unit states, load, metrics (host, emulator, Android via adb) |
| `tests/settings.rs` | renderer, cores, memory: reported, invalid choices refused, a change applied, merged with an optional size, 409 while pending |
| `tests/display.rs` | screen size: reported, invalid sizes refused (strings → 400), a change pending then done, 409, 429 |
| `tests/stream.rs` | signalling: start, offer, candidates, answer and candidates reaching the emulator |
| `tests/api.rs` | ping, caching, 404/405, viewers, disconnect-others, origin checks on the socket, consistency between endpoints |
| `tests/input.rs` | touches and keys over HTTP reach Android at the right place |
| `tests/lifecycle.rs` | crash, restart, discovery file replaced, gateway restarts |
| `tests/plugins.rs` | plugin host: list, served scripts, routes, token checks, screenshot (shared, counted in the state details), analysis off the event loop and adb for plugins, a plugin's state kept across gateway restarts, a plugin for another plugin API refused, broken plugins skipped |
| `tests/contract.rs` | what the emulator says (status, JSEP shapes, data channels, codecs): on the fake by default, on a deployed instance with `--features smoke` |
| `tests/ui_page.rs` | Firefox: video plays and fits, toolbar labels, landmarks, LED, metrics block, ↻ replaces only the video session, English browser |
| `tests/ui_banners.rs` | every status the page shows, covering or closable, with the LED colour; priority; closing; English |
| `tests/ui_input.rs` | a click lands on the Android pixel under it (several sizes and windows); drags; toolbar keys; HTTP fallbacks; the touch seen in the video |
| `tests/ui_changes.rs` | Apply from the page: one merged request, pending/applying/failed shown, the page reloads at a new size |
| `tests/ui_panels.rs` | Information panel (Client and Serveur tabs) and Options panel |
| `tests/ui_forms.rs` | Android settings and screen size fields, presets, Apply enabled only while they differ |
| `tests/ui_settings.rs` | client options and language in `localStorage`, plugin options included |
| `tests/ui_fullscreen.rs` | fullscreen, fold button, 3 s autofold, handle, docking |
| `tests/ui_plugins.rs` | plugins in the page: options of each kind, layer drawing, stored options, failures (also a plugin the gateway refused), translations |
| `tests/smoke.rs` | deployed instance only (`--features smoke`) |

## Browser

The `ui_*` tests drive Firefox through geckodriver (WebDriver), one fresh
profile per test, one browser at a time per test file.

| Variable | Meaning |
|---|---|
| `CLOUDPHONE_GECKODRIVER` | geckodriver binary (default: `geckodriver` in `PATH`) |
| `CLOUDPHONE_FIREFOX` | Firefox binary (default: the one geckodriver finds) |
| `CLOUDPHONE_FIREFOX_LIBS` | extra library directories for Firefox, `:`-separated (after Firefox's own directory) |
| `CLOUDPHONE_HEADED=1` | show the window instead of headless |

Setup without root, in your home directory: Mozilla's Firefox ESR and
geckodriver release tarballs, each in its own directory, checked against
Mozilla's signatures.

```sh
B=$HOME/.local/share/e2e-browsers
FF=153.5.0esr GD=0.37.1     # current versions
mkdir -p $B/firefox-$FF $B/geckodriver-$GD
cd $B/firefox-$FF
curl -fLO https://archive.mozilla.org/pub/firefox/releases/$FF/linux-x86_64/en-US/firefox-$FF.tar.xz
curl -fLO https://archive.mozilla.org/pub/firefox/releases/$FF/SHA256SUMS
curl -fLO https://archive.mozilla.org/pub/firefox/releases/$FF/SHA256SUMS.asc
curl -fLO https://archive.mozilla.org/pub/firefox/releases/$FF/KEY
gpg --import KEY && gpg --verify SHA256SUMS.asc SHA256SUMS   # "Mozilla Software Releases", primary key 14F2 6682 D091 6CDD 81E3 7B6D 61B7 B526 D98F 0353
grep " linux-x86_64/en-US/firefox-$FF.tar.xz\$" SHA256SUMS | awk '{print $1"  firefox-'$FF'.tar.xz"}' | sha256sum -c
tar xJf firefox-$FF.tar.xz
cd $B/geckodriver-$GD
curl -fLO https://github.com/mozilla/geckodriver/releases/download/v$GD/geckodriver-v$GD-linux64.tar.gz
curl -fLO https://github.com/mozilla/geckodriver/releases/download/v$GD/geckodriver-v$GD-linux64.tar.gz.asc
gpg --verify geckodriver-v$GD-linux64.tar.gz.asc geckodriver-v$GD-linux64.tar.gz
tar xzf geckodriver-v$GD-linux64.tar.gz

export CLOUDPHONE_FIREFOX=$B/firefox-$FF/firefox/firefox
export CLOUDPHONE_GECKODRIVER=$B/geckodriver-$GD/geckodriver
```

On a machine without Firefox's GTK libraries (a bare WSL, for instance)
and without root, unpack the missing Debian/Ubuntu packages (`apt-get
download libgtk-3-0 ...` then `dpkg -x`) into a directory and point
`CLOUDPHONE_FIREFOX_LIBS` at its `usr/lib/x86_64-linux-gnu`.

The fake's WebRTC stream reaches Firefox on 127.0.0.1: the tests set
`media.peerconnection.ice.obfuscate_host_addresses=false` in the profile.

## Smoke and contract tests

Against a deployed instance, from a WireGuard peer (the video is WebRTC
over UDP: an SSH tunnel carries the page and the API, not the video):

```sh
CLOUDPHONE_URL=http://<server>:8000/ cargo test --features smoke --test smoke --test contract -- --test-threads=1 --nocapture
```

`CLOUDPHONE_URL` is read by these tests only. The smoke tests act on the
phone (one volume step up then down, the notification shade opened then
closed with Back); run them when nobody uses it. The contract tests open
one short extra viewer and print (`CONTRACT ...` lines) what the real
emulator sends: compare with the fake's `UNVERIFIED` guesses.
