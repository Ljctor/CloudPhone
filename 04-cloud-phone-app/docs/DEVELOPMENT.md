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

- Gray screen, spinner, orange dot: negotiating. Green dot: video playing.
  Green dot on black: Android itself shows black (screen off: press power).
- `↻` sends `bye`, closes the WebSocket and peer connection, waits 1 s for
  the emulator to drop the participant, then opens one new session; repeated
  clicks are ignored while it runs. Returning from background or from the
  back-forward cache does the same.
- `srv` falls to ~0 on a still Android screen: the emulator sends frames only
  on change.

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
