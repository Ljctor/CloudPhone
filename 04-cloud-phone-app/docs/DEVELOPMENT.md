# Developing the Cloud Phone app

`src/overlay/` holds only our files; their paths map onto Google's
`android-emulator-container-scripts` at the commit pinned in
`lib/versions.env`. Generated protobuf code, dependencies and bundles are
built, never committed.

| File | Role |
|---|---|
| `js/example/src/App.tsx` | the page: layout, toolbar, touch, panels, status banners, reconnect |
| `js/example/src/i18n.ts` | French (source text) and English; `tr()` falls back to French |
| `js/example/src/plugins.ts` | loads the installed plugins' `page.js` and their API |
| `js/src/components/emulator/net/ws_jsep_protocol_driver.ts` | signaling, viewer id, input on the emulator's data channels; waits for the emulator's SDP offer (Firefox) |
| `js/src/components/emulator/views/webrtc_view.tsx` | `connected` only after a real decoded frame |
| `gateway/src/videobridge_gateway/gateway_server.py` | serves the page, WebSocket JSEP bridge, HTTP API |
| `gateway/src/videobridge_gateway/plugins.py` | loads the installed plugins' `gateway.py`, serves their scripts |
| `js/test/*.test.js` | jest unit tests (run by `packaging/build-release.sh`) |

## Build

On Linux x86-64 with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh          # jest tests, page, gateway wheel, dist/*.tar.gz
```

`--skip-tests` skips the jest tests; do not use it for a release.

## Iterate on a test instance

Use a test instance on another host (the examples give it port 8100),
never the production phone. Build, then stage and install part 04 in one
command (`SERVER` is an ssh destination; `AS_ROOT` and `LISTEN` as in
`packaging/deploy.sh`):

```sh
packaging/build-release.sh
packaging/deploy.sh SERVER 04       # stage-release.sh, then 04 install.sh --listen 10.20.0.1
packaging/deploy.sh SERVER 03 04    # also part 03 (an upgrade: the SDK licences are already accepted)
ssh SERVER "$AS_ROOT /var/tmp/cloudphone-release/cloudphone-VERSION-linux-x86_64/04-cloud-phone-app/scripts/verify.sh"
```

`deploy.sh` allocates a terminal when it runs from one, so a first install
of part 03 can answer the licence prompt there; or pass
`ACCEPT_ANDROID_SDK_LICENSE=yes` after reading the licences. From a
non-interactive shell, use part 03's runbook 02 instead.

Android keeps running. Reload the page (the index is never cached).

## Gateway: one port, one origin

`cloudphone-gateway` serves the page and the API on `LISTEN_ADDRESS:WEB_PORT`
(8000 by default; 8100 for the test instance in the examples). There is no CORS.

- Each start draws a random token and writes it into `index.html` as
  `<meta name="cloudphone-token">`. Every POST must carry it in the
  `X-CloudPhone-Token` header, else 403 ("reload the page").
- A request whose `Origin` is not this server is refused with 403 (GET,
  POST and the WebSocket alike). Requests without `Origin` pass.
- `Cache-Control`: `/` and `/index.html` `no-cache`; `/assets/*` (hashed
  names) `public, max-age=31536000, immutable`; `/plugins/<id>/*.js`
  `no-cache`; every answer under `/api/` `no-store` unless the handler set
  its own (`cache_middleware`), including the upstream helpers
  `/api/v1/emulator/{status,gps,logcat,key,touch}`.

| Route | Purpose |
|---|---|
| `GET /`, `/index.html`, `/assets/*` | the page |
| `GET /api/v1/ping` | 204 at once, for the round-trip time |
| `GET /api/v1/state?viewer=ID[&details=1]` | emulator unit state (`systemctl show`), Android booted, viewers, load, `display` and `settings` change status, `kicked` for this viewer; cached 2 s. `details=1` adds `metrics` (host, emulator, Android) and turns on adb sampling of Android for 30 s. The page polls every 3 s, every 2 s with details while the Server tab is open |
| `GET /api/v1/events` | what happened to Android and the server, newest first (`events.py`): app crashes, ANRs and apps Android stopped while noticeable (out-of-memory score ≤ 200, e.g. stopped for a Google Play Services update), low memory, from `logcat -b events,crash` (back to Android's last boot at most); Android's boot (`/proc/uptime`), the emulator unit's start, automatic restarts and last result (`systemctl show`), the gateway's start. Each event is `{time, kind, app, reason}`; cached 10 s. The page reads it every 15 s while the Server tab is open (section Events) |
| `GET /api/v1/notify` | phone alerts through ntfy.sh (`notify.py`): `{available, enabled, topic, url}`; `available` is false without `--notify_file` |
| `POST /api/v1/notify` | `{enabled[, newTopic]}`: turns them on or off; the first time (or with `newTopic`) the gateway draws a random topic `cloudphone-<24 hex>`, kept with the setting in `/var/lib/cloudphone/notify.json` (mode 600). While on, the gateway alerts every minute on Android's new events (crash, ANR, app stopped while noticeable, Android or emulator restart) and plugins send theirs with `context.notify`. Messages go through the public ntfy.sh service: anyone who knows the topic can read them, so they carry nothing private |
| `POST /api/v1/notify/test` | one test alert; 502 when ntfy.sh did not take it |
| `GET /api/v1/emulator-settings` | renderer, cores and memory from the running emulator's command line, the configured screen (`display`), limits (`renderers`, `maxCores`, `maxMemoryMb`), state of the last request |
| `POST /api/v1/emulator-settings` `{renderer, cores, memoryMb[, width, height, density]}` | what the page's Apply sends: change all of them with one restart of Android |
| `GET /api/v1/display` | running and configured screen size, last change request, limits |
| `POST /api/v1/display` `{width, height, density}` | screen size only (reboots Android); kept for API clients, the page no longer calls it |
| `POST /api/v1/viewers/disconnect-others` `{viewer}` | close the other viewers' sessions |
| `GET /api/v1/plugins` | installed plugins (id, title, version, page script) |
| `GET /api/v1/emulator/status` | emulator status and screen size |
| `POST /api/v1/emulator/touch`, `/key` | input fallback (gRPC touch, adb key) |
| `POST /api/v1/emulator/gps`, `GET /api/v1/emulator/logcat` | upstream helpers |
| `GET /api/v1/emulator/ws-jsep?viewer=ID` | WebSocket signaling |

Changes that restart Android go through part 03's root path units: the
gateway (service user) writes a request file, the path unit starts a oneshot
service that checks it and reports in a status file, which the gateway reads
back (`display` and `settings` in `GET /api/v1/state`).
`POST /api/v1/emulator-settings` writes `RENDERER CORES MEMORY_MB[ WIDTH
HEIGHT DENSITY]` to `/var/lib/cloudphone/settings-request`;
`cloudphone-settings.path` runs `cloudphone-settings-apply`, which backs up
and rewrites `cloudphone.conf`, then restarts Android (through
`set-resolution.sh` when a size is given); status in
`/run/cloudphone-settings/status`. `POST /api/v1/display` writes `WIDTH
HEIGHT DENSITY` to `/var/lib/cloudphone/display-request`;
`cloudphone-display.path` runs `cloudphone-display-apply`, which runs
`set-resolution.sh`; status in `/run/cloudphone-display/status`. Numbers
must be JSON integers (`"360"` is refused with 400). Bounds: renderer in
`lavapipe`, `swiftshader`, `swangle`, `software` (a running emulator
started with the older `*_indirect` names is reported under the new ones); cores 1 to the host's
threads; memory a multiple of 512 from 2048 to the host's memory minus
2 GiB; width and height even, within 240–1440 × 320–3200, density 80–640,
all three or none. One change per 2 minutes for both routes together (429
otherwise); 409 while either kind is pending or applying.

Other viewers: `disconnect-others` closes every other signaling session with
WebSocket code 4001 and refuses those viewer ids for 10 minutes. The driver
does not reconnect after 4001; the page says another device took over and
`↻` reloads it (a new viewer id).

The gateway exits when the emulator restarts (new discovery file, new gRPC
token); systemd starts it again on the new emulator.

## The page

- Toolbar: power, volume, the ping/fps block (this device's ping above its
  displayed fps) opening **Information**, recents/home/back, the cog opening
  **Options**, `↻`, fullscreen, and in fullscreen only the fold button.
- Information, tab Client (default): network, display, input path. Tab
  Server: state, machine, Android and video stream, the **Disconnect** button
  for other devices when more than one viewer is connected, and Android
  settings (renderer, cores, memory, shape and resolution, one Apply).
- Options: language (French/English, default from the browser), cursor (the
  touch marker, setting `touchMarker`), fold 3 s after entering fullscreen,
  and Plugins: each installed plugin's options.
- Fold button: tap folds the bar away (the screen takes the whole window, a
  floating handle unfolds it and can be dragged); long press docks the bar
  so it keeps its own space; a tap then makes it float again.
- Settings are per browser, in `localStorage` key `cloudphone.settings`.

## Stream behaviour

- `diagnose()` picks the one message to show, from `GET /api/v1/state`
  (polled every 3 s, every 2 s while the Server tab is open) and the stream
  state: server unreachable (check WireGuard), another device took over,
  screen size or Android settings change (pending or applying), Android
  crashed/stopped/starting, server reconnecting to Android, video
  interrupted, video not connecting after 15 s (UDP). These cover the
  screen. Touches failing, other viewers watching and heavy load show as a
  banner with a close cross; a closed banner comes back only after its
  message changed.
- The LED in the corner of `↻` is green when all is well, orange while
  something is being fixed, red when it needs action.
- `↻` sends `bye`, closes the WebSocket and peer connection, waits 1 s for
  the emulator to drop the participant, then opens one new session; repeated
  clicks are ignored while it runs. Returning from background or from the
  back-forward cache does the same, and so does Android coming back after a
  crash or a restart.
- Frame rates fall to ~0 on a still Android screen: the emulator sends
  frames only on change.

Measured on emulator 36.6.11 (VP8 negotiated; the emulator offers VP8 and
VP9, no H264): with `b=AS` / `b=TIAS` in the browser's answer the emulator
honours the bitrate cap but keeps the stream at 360×780 and lowers the frame
rate; `a=imageattr` in the answer made the stream fail to start. A bitrate
cap therefore does not trade resolution for fluidity.

## Touch and keys

Emulator 36.6.11 opens four data channels towards the browser: `mouse`,
`keyboard`, `touch` and `adb`, and reads the raw `TouchEvent` /
`KeyboardEvent` bytes on them. It never reads the `input` channel that the
upstream driver creates (an `InputEvent` wrapper, for newer emulators): input
sent there arrives and is silently dropped. The driver therefore writes to
the channel named after the event and uses `input` only when that channel is
missing. Checked on 2026-10-16 with a swipe that opened the notification
shade and a volume key, with no HTTP request. While no channel is open,
touches go to `POST /api/v1/emulator/touch` (moves coalesced, one request in
flight) and keys to `POST /api/v1/emulator/key` (adb on the gateway). The
Information → Client tab shows which path the last touch took.

## Plugins

Game-specific features are plugins, never part of the page or the gateway.
`/opt/cloudphone/plugins/<id>/` holds `plugin.json` (id, title, version), an
optional `page.js` (ES module, may import the other `*.js` beside it) and an
optional `gateway.py` (`setup(context)`). The gateway (`--plugins_dir`)
loads them at start, logs and skips one that fails, serves its scripts at
`/plugins/<id>/` and lists them at `GET /api/v1/plugins`; a plugin's own
routes live under `/api/v1/plugins/<id>/`, behind the usual origin and token
checks. The `id` must equal the directory name and match
`^[a-z0-9][a-z0-9-]{0,31}$`; only top-level `*.js` files matching
`^[a-z0-9][a-z0-9_-]{0,63}\.js$` are served. The page imports each
`page.js`, gives it the API described at the
top of `plugins.ts` (video element, a drawing layer over the screen, stored
options, gateway calls) and renders its options (toggle, number, choice, action,
buttons, status) in Options → Plugins, one foldable section per plugin.
`context` offers `add_get`/`add_post`, `screenshot()`, `adb(...)`, `json()`,
`notify(text)`, which sends a phone alert when the user turned them on
(below), and `data_dir`: a directory the plugin may write to,
`/var/lib/cloudphone/plugins/<id>/` (`--plugin_data`, created by the gateway
as the `cloudphone` user, mode 700, kept by upgrades, removed by
`uninstall.sh --purge`), or `None` when the gateway has none. On the page,
`api.onTap(listener)` observes the user's touches on the Android screen once
the finger lifts (`{ x, y, kind: 'tap' | 'long' | 'swipe', end? }`, fractions
of the screen); touches reach Android exactly as without it.

## Emerald counter (part 05 plugin)

Option of the Slayer Legend plugin (`05-plugins/slayer-legend`). It
covers the emerald counter with the bar's colour and writes over it, at the
game's size for that many digits: the digits after the comma (leading zeros
dropped) copied from the video, or a number the user typed. Nothing is sent
to Android. `emerald_mask.js` finds the comma in a small area of the frame,
4 times a second.

The page copies the video's pixels with the first method that gives a
non-blank image: 2D canvas (crop, then full frame), `createImageBitmap`,
WebGL `readPixels`, `VideoFrame`. On Firefox for Android with hardware
decoding the 2D canvas, `createImageBitmap` and `VideoFrame` give a blank
image or an error (WebGL was added afterwards and not checked there on its
own). When every method fails, the plugin asks
`GET /api/v1/plugins/slayer-legend/emerald-mask` twice a second. The gateway takes an emulator
screenshot over gRPC and runs `emerald_mask.py` (one screenshot at a time,
shared for 0.4 s) and also returns the pixels of the digits after the comma.
Keep `emerald_mask.js` and `emerald_mask.py` in step.
The panel shows "detected" or why not (`flat`, `text`, `comma`, `digits`,
`colour`, and the capture methods tried).

## Testing from a workstation

The page is reachable only on the VPN. From a workstation with SSH access,
tunnel the page's port (here a test instance on 8100):

```sh
ssh -N -L 18100:10.20.0.1:8100 USER@SERVER
```

then open `http://127.0.0.1:18100/`, or drive it with Playwright (Firefox or
Chromium, headless). The tunnel carries TCP only: the page, the API and the
signaling. The WebRTC video is UDP and needs the workstation on WireGuard;
without it the page reports that the video does not connect, which still
tests the layout, panels, banners and API.

## Browser acceptance test

From the server (Chromium must reach the WebRTC candidates directly):

```sh
docker run --rm --network host \
  -e CLOUDPHONE_URL=http://10.20.0.1:8000/ \
  -e npm_config_registry=https://registry.npmjs.org/ \
  -v "$PWD/04-cloud-phone-app/tests/android-web-smoke.spec.js:/input/android-web-smoke.spec.js:ro" \
  mcr.microsoft.com/playwright:v1.62.1-noble \
  sh -c 'mkdir /work && cp /input/android-web-smoke.spec.js /work/ && \
    cd /work && npm init -y >/dev/null && \
    npm install --no-save @playwright/test@1.62.1 >/dev/null && \
    npx playwright test android-web-smoke.spec.js --reporter=line --workers=1'
```

It opens `CLOUDPHONE_URL` (default `http://127.0.0.1:8000/`; set it to the
gateway's `LISTEN_ADDRESS` and `WEB_PORT`) and checks decoded video, spinner/status transitions, clean
refresh, a rapid double refresh and console errors.
