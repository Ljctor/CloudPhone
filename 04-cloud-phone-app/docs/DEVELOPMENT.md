# Developing the Cloud Phone app

`src/overlay/` holds only our files; their paths map onto Google's
`android-emulator-container-scripts` at the commit pinned in
`lib/versions.env`. Generated protobuf code, dependencies and bundles are
built, never committed.

| File | Role |
|---|---|
| `js/example/src/App.tsx` | the page: layout, toolbar, touch, panels, status banners, reconnect |
| `js/example/src/i18n.ts` | French (source text) and English; `tr()` falls back to French |
| `js/example/src/emeraldMask.ts` | emerald counter detection (Slayer Legend option) |
| `js/src/components/emulator/net/ws_jsep_protocol_driver.ts` | signaling, viewer id, input on the emulator's data channels; waits for the emulator's SDP offer (Firefox) |
| `js/src/components/emulator/views/webrtc_view.tsx` | `connected` only after a real decoded frame |
| `gateway/src/videobridge_gateway/gateway_server.py` | serves the page, WebSocket JSEP bridge, HTTP API |
| `gateway/src/videobridge_gateway/emerald_mask.py` | Python twin of `emeraldMask.ts`, used by `/api/v1/emerald-mask` |
| `js/test/*.test.js` | jest unit tests (run by `packaging/build-release.sh`) |

## Build

On Linux x86-64 with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh          # jest tests, page, gateway wheel, dist/*.tar.gz
```

`--skip-tests` skips the jest tests; do not use it for a release.

## Iterate on a test instance

Use a second instance (other ports, see `03-android-emulator/README.md`),
never the production phone. Build, then stage and install part 04 in one
command (`SERVER` is an ssh destination; `AS_ROOT` and `LISTEN` as in
`packaging/deploy.sh`):

```sh
packaging/build-release.sh
packaging/deploy.sh SERVER 04       # stage-release.sh, then 04 install.sh --listen 10.20.0.1
packaging/deploy.sh SERVER 03 04    # also part 03 (an upgrade: the SDK licences are already accepted)
ssh SERVER "$AS_ROOT /var/tmp/cloudphone-release/cloudphone-VERSION-linux-x86_64/04-cloud-phone-app/scripts/verify.sh"
```

`deploy.sh` runs `install.sh` over non-interactive ssh, so a first install
of part 03 (licence prompt) still goes through its runbook 02.

Android keeps running. Reload the page (the index is never cached).

## Gateway: one port, one origin

`cloudphone-gateway` serves the page and the API on `LISTEN_ADDRESS:WEB_PORT`
(8000 by default; 8100 in the second-instance example). There is no CORS.

- Each start draws a random token and writes it into `index.html` as
  `<meta name="cloudphone-token">`. Every POST must carry it in the
  `X-CloudPhone-Token` header, else 403 ("reload the page").
- A request whose `Origin` is not this server is refused with 403 (GET,
  POST and the WebSocket alike). Requests without `Origin` pass.
- `Cache-Control`: `/` and `/index.html` `no-cache`; `/assets/*` (hashed
  names) `public, max-age=31536000, immutable`; API answers `no-store`.

| Route | Purpose |
|---|---|
| `GET /`, `/index.html`, `/assets/*` | the page |
| `GET /api/v1/ping` | 204 at once, for the round-trip time |
| `GET /api/v1/state?viewer=ID` | emulator unit state (`systemctl show`), Android booted, viewers, load, display change status, `kicked` for this viewer; cached 2 s |
| `GET /api/v1/display` | running and configured screen size, last change request, limits |
| `POST /api/v1/display` `{width, height, density}` | change Android's screen size (reboots Android) |
| `POST /api/v1/viewers/disconnect-others` `{viewer}` | close the other viewers' sessions |
| `GET /api/v1/emerald-mask` | emerald mask from an emulator screenshot |
| `GET /api/v1/emulator/status` | emulator status and screen size |
| `POST /api/v1/emulator/touch`, `/key` | input fallback (gRPC touch, adb key) |
| `POST /api/v1/emulator/gps`, `GET /api/v1/emulator/logcat` | upstream helpers |
| `GET /api/v1/emulator/ws-jsep?viewer=ID` | WebSocket signaling |

Screen size changes: the gateway (service user) writes `WIDTH HEIGHT
DENSITY` to `/var/lib/cloudphone/display-request`; the root path unit
`cloudphone-display.path` of part 03 starts `cloudphone-display.service`,
which checks the request and runs `set-resolution.sh`, reporting in
`/run/cloudphone-display/status`. Width and height even, within
240–1440 × 320–3200, density 80–640; one change per 2 minutes (429
otherwise), 409 while one is in progress.

Other viewers: `disconnect-others` closes every other signaling session with
WebSocket code 4001 and refuses those viewer ids for 10 minutes. The driver
does not reconnect after 4001; the page says another device took over and
`↻` reloads it (a new viewer id).

The gateway exits when the emulator restarts (new discovery file, new gRPC
token); systemd starts it again on the new emulator.

## The page

- Toolbar: power, volume, a server block (ping) opening **Server settings**,
  recents/home/back, a client block (displayed fps) opening **Client
  settings**, `↻`, fullscreen, and in fullscreen only the fold button.
- Server settings: state, network, Android and video stream, the
  **Disconnect** button for other devices when more than one viewer is
  connected, and Android's screen size (shape and resolution presets).
- Client settings: display, input path, language (French/English, default
  from the browser), touch marker, emerald mask, fold 3 s after entering
  fullscreen.
- Fold button: tap folds the bar away (the screen takes the whole window, a
  floating handle unfolds it and can be dragged); long press docks the bar
  so it keeps its own space; a tap then makes it float again.
- Settings are per browser, in `localStorage` key `cloudphone.settings`.

## Stream behaviour

- `diagnose()` picks the one message to show, from `GET /api/v1/state`
  (polled every 3 s) and the stream state: server unreachable (check
  WireGuard), another device took over, screen size change, Android
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
client settings panel shows which path the last touch took.

## Emerald mask (Slayer Legend)

Option in Client settings. It hides the decimals of the emerald counter
("282,230" shows as "282") by painting a rectangle in the bar's colour over
the video, on this screen only; nothing is sent to Android.
`emeraldMask.ts` finds the comma in a small area of the frame, 4 times a
second.

The page copies the video's pixels with the first method that gives a
non-blank image: 2D canvas (crop, then full frame), `createImageBitmap`,
WebGL `readPixels`, `VideoFrame`. On Firefox for Android with hardware
decoding the 2D canvas, `createImageBitmap` and `VideoFrame` give a blank
image or an error (WebGL was added afterwards and not checked there on its
own). When every method fails, the page asks
`GET /api/v1/emerald-mask` twice a second. The gateway takes an emulator
screenshot over gRPC and runs `emerald_mask.py` (one screenshot at a time,
shared for 0.4 s). Keep `emeraldMask.ts` and `emerald_mask.py` in step; the
jest fixtures in `js/test/emerald_mask.test.js` are the reference.
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
