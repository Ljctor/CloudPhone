# Android Emulator Web

This directory contains the complete repository-owned source overlay for the
cloud-phone web application. It is applied on top of Google's
`android-emulator-container-scripts` repository pinned to commit:

```text
0654f694b46794fae4b178f1e1a17cb60c5d2d34
```

The paths below `overlay/` map directly onto the upstream checkout. The
overlay contains the gateway, WebRTC lifecycle, video-state detection and the
mobile interface customizations; generated protobuf files, dependencies and
production bundles are intentionally built from source and are not committed.

## Stream states

- Gray screen, spinner and orange indicator: the web application is still
  negotiating or buffering the video stream.
- Green indicator: the browser video element is actually playing.
- Green indicator with a black display: Android itself is rendering black.

The refresh button performs a clean WebRTC reset. It sends the protocol `bye`,
closes the old WebSocket and peer connection, waits for the emulator-side
participant to be destroyed, and then creates one new session. Concurrent
refresh requests are ignored.

## Build

Apply the overlay to the pinned upstream checkout, generate the JavaScript
protobuf module, then build the example application:

```sh
cd js
npm ci
make protoc
cd example
npm ci
npm run build
```

The Python gateway is installed from `gateway/`. Its `setup.py` generates gRPC
stubs from `emulator_controller.proto`, `rtc_service_v2.proto` and
`ice_config.proto`, read from `$BAZEL_ROOT/hardware/google/aemu/protos/services/`;
the pinned emulator ships these files in `emulator/lib/`.
`packaging/build-release.sh` automates the whole build and packages the result.
The application does not restart Android or Slayer Legend when a viewer
connects, disconnects or refreshes the stream.

## Browser acceptance test

Run the Playwright test on the server so Chromium can reach the emulator's
WebRTC media candidates directly:

```sh
docker run --rm --network host \
  -e npm_config_registry=https://registry.npmjs.org/ \
  -v "$PWD/tests/android-web-smoke.spec.js:/input/android-web-smoke.spec.js:ro" \
  mcr.microsoft.com/playwright:v1.62.1-noble \
  sh -c 'mkdir /work && cp /input/android-web-smoke.spec.js /work/ && \
    cd /work && npm init -y >/dev/null && \
    npm install --no-save @playwright/test@1.62.1 >/dev/null && \
    npx playwright test android-web-smoke.spec.js --reporter=line --workers=1'
```

The test checks real decoded 540×1170 video, spinner/status transitions, clean
refresh, serialization of a rapid double refresh, and browser console errors.
