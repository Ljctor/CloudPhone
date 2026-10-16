# Developing the Cloud Phone app

`src/overlay/` holds only our files; their paths map onto Google's
`android-emulator-container-scripts` at the commit pinned in
`lib/versions.env`. Generated protobuf code, dependencies and bundles are
built, never committed.

| File | Role |
|---|---|
| `js/example/src/App.tsx` | the page: layout, toolbar, touch, stats, reconnect |
| `js/src/components/emulator/net/ws_jsep_protocol_driver.ts` | signaling; waits for the emulator's SDP offer (Firefox) |
| `js/src/components/emulator/views/webrtc_view.tsx` | `connected` only after a real decoded frame |
| `gateway/src/videobridge_gateway/gateway_server.py` | WebSocket JSEP bridge, touch/key API, `/api/v1/ping` |
| `js/test/*.test.js` | unit tests (run by the build) |

## Build

On Linux x86-64 with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh          # tests, page, gateway wheel, dist/*.tar.gz
```

## Iterate on a test instance

Use a second instance (other ports, see `03-android-emulator/README.md`),
never the production phone:

```sh
packaging/stage-release.sh "$TARGET"
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/install.sh --listen 10.20.0.1"
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"
```

Android keeps running. Close and reopen the browser tab to load the new page.

## Stream behaviour

- While the video is not playing, the screen shows a spinner with
  "Connexion au flux…", or the reason when the page knows it (from
  `GET /api/v1/state`): server unreachable, Android crashed/stopped/booting,
  screen size change, video not connecting (UDP). The LED in the corner of
  `↻` is green when all is well, orange while something is being fixed, red
  when it needs action. Information (other viewers, heavy load, touches
  failing) shows as a closable banner.
- `↻` sends `bye`, closes the WebSocket and peer connection, waits 1 s for
  the emulator to drop the participant, then opens one new session; repeated
  clicks are ignored while it runs. Returning from background or from the
  back-forward cache does the same, and so does Android coming back after a
  crash or a restart.
- Frame rates fall to ~0 on a still Android screen: the emulator sends
  frames only on change.

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
flight) and keys to `POST /api/v1/emulator/key` (adb on the gateway).

## Browser acceptance test

From the server (Chromium must reach the WebRTC candidates directly):

```sh
docker run --rm --network host \
  -e npm_config_registry=https://registry.npmjs.org/ \
  -v "$PWD/04-cloud-phone-app/tests/android-web-smoke.spec.js:/input/android-web-smoke.spec.js:ro" \
  mcr.microsoft.com/playwright:v1.62.1-noble \
  sh -c 'mkdir /work && cp /input/android-web-smoke.spec.js /work/ && \
    cd /work && npm init -y >/dev/null && \
    npm install --no-save @playwright/test@1.62.1 >/dev/null && \
    npx playwright test android-web-smoke.spec.js --reporter=line --workers=1'
```

It checks decoded 540×1170 video, spinner/status transitions, clean refresh,
a rapid double refresh and console errors.
