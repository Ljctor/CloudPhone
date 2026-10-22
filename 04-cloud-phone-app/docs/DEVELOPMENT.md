# Developing the Cloud Phone app

`src/overlay/` holds only our files; their paths map onto Google's
`android-emulator-container-scripts` at the commit pinned in
`lib/versions.env`. Generated protobuf code, dependencies and bundles are
built, never committed.

A page module marked (pure) has no React and no DOM: the rules, as plain
functions of their inputs. The hooks and components beside it wire them to
the browser and the gateway; `App.tsx` only assembles them.

| File | Role |
|---|---|
| `js/example/src/App.tsx` | the page's assembly: calls the hooks below, passes their state to the components, lays out the screen, the panels and the toolbar |
| `js/example/src/main.tsx` | mounts `App` |
| `js/example/src/layout.ts` | the screen's fitted size and the toolbar's place (side, below, overlay), Android's size from the emulator status, the running size's key, the toasts' top (pure) |
| `js/example/src/useLayout.ts` | the window's size, this device's pixel ratio and screen, the emulator status fetch, the screen refitted on resize and fullscreen, the reload after a screen size change |
| `js/example/src/usePanels.ts` | which panel is open (information, options) and the information tab; information opens on the client tab; the flags the panel-only polls follow (server tab, information, options) |
| `js/example/src/infoPanel.tsx` | the open panel's frame: its title, close button and, for information, the client and server tabs |
| `js/example/src/streamRules.ts` | when to reconnect the stream (Android usable again, the video cut or stuck 20 s), its delays, the log line for a new stream state (pure) |
| `js/example/src/useStream.ts` | the stream's state, remounting it to reconnect (button, Android back, page shown again), the manual reconnect's feedback, seconds spent connecting |
| `js/example/src/streamStats.ts` | the stream's figures (ping, fps, losses, jitter, buffer, path) from the WebRTC report and two samples (pure) |
| `js/example/src/useStreamStats.ts` | samples the stream once a second: ICE or HTTP ping, frames, the network details |
| `js/example/src/touchInput.ts` | the pointer to Android's pixels, the HTTP touches' queue, what plugins are told of a tap (pure) |
| `js/example/src/useInput.ts` | touches and keys to Android over the data channels or the gateway, the touch marker, failed touches |
| `js/example/src/diagnose.ts` | the status shown to the user from the server's state, the stream, the time spent connecting and failed touches; its log line; whether the banner shows (pure) |
| `js/example/src/banner.tsx` | that status as a cover over the screen or a closable banner, which banner was closed, each new status in the page's log |
| `js/example/src/serverState.ts` | the poll of `GET /api/v1/state` |
| `js/example/src/serverInfo.ts` | the Server tab's rows from the state, the metrics and the stream's figures (pure) |
| `js/example/src/serverPanel.tsx` | the Server tab: its rows, disconnecting the other viewers, the Android settings form, the server's log |
| `js/example/src/clientInfo.ts` | the Client tab's rows: network, display, input, this device's screen and window (pure) |
| `js/example/src/infoRows.tsx` | an information row and titled sections of rows |
| `js/example/src/emulatorSettings.ts` | the renderer, cores and memory offered, comparing two settings, whether a change is in progress (pure) |
| `js/example/src/screenSize.ts` | the screen shapes and resolutions offered, the size a choice gives, the choice closest to a size (pure) |
| `js/example/src/androidSettings.tsx` | the polls of `GET /api/v1/display` and `GET /api/v1/emulator-settings`, the form that changes them |
| `js/example/src/toolbarStatus.ts` | the round trip's colour, the connection LED's colour (pure) |
| `js/example/src/toolbar.tsx` | the toolbar (keys, figures, options, reconnect, fullscreen, fold and dock), the bar's folded state, the floating handle |
| `js/example/src/logRecords.ts` | which records a log keeps and shows, how a notify record changes the toasts (pure) |
| `js/example/src/logs.tsx` | the page's log and the server's (`GET /api/v1/logs`), the log list, the level filter, the toasts |
| `js/example/src/logSection.tsx` | a log in the information panel: folded at first, with its filter |
| `js/example/src/notify.tsx` | phone alerts (`GET`/`POST /api/v1/notify`), the options panel's section |
| `js/example/src/pageSettings.ts` | the per-viewer settings' key and defaults, reading them from the stored text, a change, the log sections' folded state (pure) |
| `js/example/src/viewerSettings.tsx` | the settings kept in this browser (`localStorage`), the page's language, the options panel's language, cursor and folding rows |
| `js/example/src/pluginSettings.ts` | a plugin option's stored value, its options cut into sections, folded sections (pure) |
| `js/example/src/pluginOptions.tsx` | each plugin's options in the options panel, the seven option kinds, the dialog an option opens |
| `js/example/src/plugins.ts` | loads the installed plugins' `page.js` and their API |
| `js/example/src/api.ts` | this page load's viewer id, POSTs with the page token |
| `js/example/src/i18n.ts` | French (source text) and English; `tr()` falls back to French; `english()` for log records, always in English (the server's are shown as they come) |
| `js/example/src/styles.ts` | the inline styles, the toolbar's width, the level colours, the page's CSS (pure) |
| `js/example/src/icons.tsx` | the toolbar's and panels' inline SVG icons |
| `js/src/components/emulator/net/ws_jsep_protocol_driver.ts` | signaling, viewer id, input on the emulator's data channels; waits for the emulator's SDP offer (Firefox) |
| `js/src/components/emulator/views/webrtc_view.tsx` | `connected` only after a real decoded frame |
| `gateway/src/videobridge_gateway/gateway_server.py` | the command line, the emulator's gRPC (status, keys, touch, GPS, screenshots), the health and metrics watches; wires the domains below into one HTTP server |
| `gateway/src/videobridge_gateway/core/session.py` | the page token, same-origin rule, the token's meta tag, JSEP's end of session (no I/O) |
| `gateway/src/videobridge_gateway/http/session.py` | serves the page with its token, the guard middleware (origin, token or one-time action token), the WebSocket JSEP bridge `GET /api/v1/emulator/ws-jsep` |
| `gateway/src/videobridge_gateway/core/actions.py` | the phone alerts' buttons' one-time action tokens: drawn per path, short-lived, spent once (no I/O) |
| `gateway/src/videobridge_gateway/adapters/videobridge.py` | the emulator's Video Bridge (gRPC Rtc): opens a stream, JSEP messages both ways |
| `gateway/src/videobridge_gateway/core/viewers.py` | viewers and their signalling sessions, who was disconnected by another viewer, which arrivals and departures are news (no I/O) |
| `gateway/src/videobridge_gateway/http/activity.py` | `POST /api/v1/input`, the user's last input (monotonic and Unix seconds) for the plugins |
| `gateway/src/videobridge_gateway/http/viewers.py` | `POST /api/v1/viewers/disconnect-others`, the viewer id of a request, sessions' arrivals and departures as log records |
| `gateway/src/videobridge_gateway/core/display.py` | screen size and density limits, the last request's state, one change of either kind (size, settings) every 2 minutes (no I/O) |
| `gateway/src/videobridge_gateway/http/display.py` | `GET`/`POST /api/v1/display`, the change limit as a 409 or 429 answer, refused changes as warning records |
| `gateway/src/videobridge_gateway/core/settings.py` | renderers, the cores and memory the host allows, the last settings request's state, the settings in the emulator's command line (no I/O) |
| `gateway/src/videobridge_gateway/http/settings.py` | `GET`/`POST /api/v1/emulator-settings`, sharing the screen size's change limit |
| `gateway/src/videobridge_gateway/core/metrics.py` | the server panel's figures from `/proc`, cgroup and adb texts: load, CPU, memory, Android's frame rate (no I/O) |
| `gateway/src/videobridge_gateway/core/events.py` | Android's and the server's events from logcat, `/proc/uptime` and `systemctl show` texts, and the record of each (no I/O) |
| `gateway/src/videobridge_gateway/http/events.py` | `GET /api/v1/events`, Android's new events as records and alerts every minute, the gateway's start record |
| `gateway/src/videobridge_gateway/core/alerts.py` | phone alerts: the saved state, the random topic, which events are new, their sentences (no I/O) |
| `gateway/src/videobridge_gateway/http/notify.py` | `GET`/`POST /api/v1/notify`, `POST /api/v1/notify/test`, `send()` for the events and the plugins |
| `gateway/src/videobridge_gateway/adapters/host_files.py` | every host file the gateway reads or writes: the request and status files the root-path units share with it, their times, the alerts' state (mode 600), `/proc`, `/sys`, the emulator's cgroup and command line |
| `gateway/src/videobridge_gateway/adapters/adb.py` | every adb command (keys, Android's metrics and events, the plugins'), its path and serial, and whether adb still reaches Android from its error text |
| `gateway/src/videobridge_gateway/adapters/ntfy.py` | the alert's HTTP post to ntfy.sh |
| `gateway/src/videobridge_gateway/adapters/systemd.py` | `systemctl show` of the emulator unit |
| `gateway/src/videobridge_gateway/plugins.py` | loads the installed plugins' `gateway.py`, serves their scripts |
| `gateway/src/videobridge_gateway/logs.py` | the gateway's log records: journald, the last 500 in memory for `GET /api/v1/logs` |

## Build

On Linux x86-64 with git, curl, make, Node.js 18+ and Python 3.10+:

```sh
packaging/build-release.sh          # page, gateway wheel, dist/*.tar.gz
```

The page and the gateway are tested black-box only, by the Rust
end-to-end tests in `tests/e2e` (a real browser, the real gateway, a
fake emulator); there are no JavaScript unit tests, and the release
build runs none. `tests/e2e/README.md` says which tests took over from
the jest suites the build used to run.

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
- A phone alert's button (an ntfy http action) cannot carry that token:
  the alerts go through the public ntfy.sh service. It carries instead a
  one-time action token in `X-CloudPhone-Action` (`core/actions.py`): drawn
  for one plugin path, at most 15 minutes, spent by the first POST to that
  path (403 after, or on another path), revoked by the plugin once the
  alert is out of date. The buttons post to `http://LISTEN_ADDRESS:WEB_PORT`
  (`10.20.0.1` when it listens on every address), which the phone reaches
  over WireGuard.
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
| `GET /api/v1/state?viewer=ID[&details=1]` | emulator unit state (`systemctl show`), Android booted, viewers, load, `display` and `settings` change status, `kicked` for this viewer; cached 2 s. `details=1` adds `metrics` (host, emulator, Android) and `plugins` (`{id: {screenshots}}`: the screenshots each plugin's gateway code took since the gateway started), and turns on adb sampling of Android for 30 s. The page polls every 3 s, every 2 s with details while the Server tab is open |
| `GET /api/v1/events` | what happened to Android and the server, newest first (`core/events.py`, `http/events.py`): app crashes, ANRs and apps Android stopped while noticeable (out-of-memory score ≤ 200, e.g. stopped for a Google Play Services update), low memory, from `logcat -b events,crash` (back to Android's last boot at most); Android's boot (`/proc/uptime`), the emulator unit's start, automatic restarts and last result (`systemctl show`), the gateway's start. Each event is `{time, kind, app, reason}`; cached 10 s. Kept for API clients: the page shows the server's log instead, where the gateway turns these events into records (below) |
| `GET /api/v1/logs?since=CURSOR` | the gateway's log records after `CURSOR`, oldest first: `{cursor, records}` (see "Logs" below). Without a cursor, or with one from an earlier gateway process, every record kept (the last 500). Same origin check as the other GETs; `no-store`. The page reads it every 4 s |
| `GET /api/v1/notify` | phone alerts through ntfy.sh (`core/alerts.py`, `http/notify.py`): `{available, enabled, topic, url}`; `available` is false without `--notify_file` |
| `POST /api/v1/notify` | `{enabled[, newTopic]}`: turns them on or off; the first time (or with `newTopic`) the gateway draws a random topic `cloudphone-<24 hex>`, kept with the setting in `/var/lib/cloudphone/notify.json` (mode 600). While on, the gateway alerts every minute on Android's new events (crash, ANR, app stopped while noticeable, Android or emulator restart) and plugins send theirs with `context.notify`. Messages go through the public ntfy.sh service: anyone who knows the topic can read them, so they carry nothing private |
| `POST /api/v1/notify/test` | one test alert; 502 when ntfy.sh did not take it |
| `GET /api/v1/emulator-settings` | renderer, cores and memory from the running emulator's command line, the configured screen (`display`), limits (`renderers`, `maxCores`, `maxMemoryMb`), state of the last request |
| `POST /api/v1/emulator-settings` `{renderer, cores, memoryMb[, width, height, density]}` | what the page's Apply sends: change all of them with one restart of Android |
| `GET /api/v1/display` | running and configured screen size, last change request, limits |
| `POST /api/v1/display` `{width, height, density}` | screen size only (reboots Android); kept for API clients, the page no longer calls it |
| `POST /api/v1/viewers/disconnect-others` `{viewer}` | close the other viewers' sessions |
| `GET /api/v1/plugins` | installed plugins (id, title, version, page script); one the gateway refused has `error` and no page script |
| `GET /api/v1/emulator/status` | emulator status and screen size |
| `POST /api/v1/emulator/touch`, `/key` | input fallback (gRPC touch, adb key) |
| `POST /api/v1/input` | the page sent a touch, swipe or key over the data channels (at once after a silence, then at most every 5 s; `http/activity.py`): the plugins' `last_input()`. No log record |
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
otherwise), counted from the request and status files' times, so it holds
across the gateway restart a change causes; 409 while either kind is pending
or applying. A page whose POST is refused for its token (the gateway
restarted) reads the new token from `/` and tries once more.

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
- Information, tab Client (default): network, display, input path, and the
  page's log (Journaux du client). Tab Server: state, machine, Android and
  video stream, the **Disconnect** button for other devices when more than
  one viewer is connected, Android settings (renderer, cores, memory, shape
  and resolution, one Apply), and the server's log (Journaux du serveur).
  Both logs fold, share one level filter (all, warnings and errors, errors)
  and colour each record by level.
- Options: language (French/English, default from the browser), cursor (the
  touch marker, setting `touchMarker`), fold 3 s after entering fullscreen,
  and Plugins: each installed plugin's options.
- Fold button: tap folds the bar away (the screen takes the whole window, a
  floating handle unfolds it and can be dragged); long press docks the bar
  so it keeps its own space; a tap then makes it float again.
- Settings are per browser, in `localStorage` key `cloudphone.settings`.

## Logs

One stream of records, two outputs. A record is

```json
{"time": 1792360000.12, "level": "error", "source": "emulator",
 "text": "Android crashed (exit-code): automatic restart. If it is not back within two minutes, restart it on the server.",
 "notify": true, "params": {"result": "exit-code"}}
```

- `level`: `normal`, `warning` or `error`; nothing below normal is kept or
  shown (the gateway's `logging.debug` lines, such as each JSEP message,
  go nowhere). Python's INFO is normal, WARNING warning, ERROR and above
  error.
- `source`: `gateway`, `emulator` (the unit, Android's boot and its apps),
  `adb`, a plugin's id (its `context.log`, `plugins.py`), or `page` for the
  page's own records.
- `notify` (only when true): the page also shows the record as a toast.
- `params` (records with parameters): the values `text` was filled with,
  as data (a viewer's id tells the page that connected it is itself).
- `text` is in English, whatever the page's language, and the page shows
  it as it is (no translation): the gateway's and the plugins' records,
  and the phone alerts, which are the same records with `notify`. The
  statuses a page shows elsewhere (a plugin's state, an error in an
  answer) are French templates the page translates instead.
- Every error says what to do next, in one sentence after the event (the
  wording of `diagnose()`'s banners where there is one).
- The same text from the same source within 30 s is dropped.

What becomes a record (`logs.py`, `watch_health()` every 3 s and
`watch()` every minute in `http/events.py`):

| Event | Level | Notify |
|---|---|---|
| gateway start | normal | yes |
| gateway restarting to follow a new emulator process | warning | yes |
| emulator unit in auto-restart (crash), `failed`, stopped without a request | error | yes |
| emulator restarted between two looks, or just before the gateway started (abnormal result) | error | yes |
| Android booted again; Android restarted after a requested change | normal | yes |
| Android restarted without a request (`/proc/uptime`) | error | yes |
| Android still booting after 3 minutes | warning | |
| gRPC silent for 12 s while the unit runs | error | yes |
| adb offline (`not found`, `offline`... in an adb call's error), and back | error / normal | yes / |
| app crash / ANR / app stopped by Android / low memory (logcat) | error / warning | |
| screen size or settings change requested, applied | normal | yes |
| change refused (400, 403, 409, 429) | warning | |
| change failed (status `failed`) | error | yes |
| another viewer connected, disconnected (5 s later, if its page did not come back) | normal | yes |
| a viewer disconnected the others | warning | yes |

adb is never called just to check it: its state comes from the calls the
gateway makes anyway (keys, metrics, events, plugins).

**journald.** The gateway writes each record to the journal's socket with
the native protocol: `PRIORITY` 6, 4 or 3, `SYSLOG_IDENTIFIER=cloudphone-gateway`,
`CLOUDPHONE_SOURCE`, `CLOUDPHONE_LEVEL`, `CLOUDPHONE_NOTIFY=1` and the code
location. It does so only when systemd connected its stderr to the journal
(`JOURNAL_STREAM`); if the socket fails, lines go to stderr prefixed with
`<N>`, which journald reads as the priority (`SyslogLevelPrefix=yes` in the
unit, which also sets `SyslogIdentifier`). Outside systemd (tests), plain
lines on stderr. Warnings and errors only:

```sh
journalctl -t cloudphone-gateway -p warning      # add -f to follow, -o verbose for the fields
journalctl -t cloudphone-gateway CLOUDPHONE_SOURCE=adb
```

**The page.** Its own records (source `page`): stream state changes, each
new message of `diagnose()` (error, warning for "being fixed", normal for
"works but worse"), touches falling back to the server path (HTTP, a
warning with notify) and back, and every `console.warn`/`console.error`
and uncaught error. Its warnings and errors also reach the browser's
console at the same level. It reads `GET /api/v1/logs` every 4 s, with
or without the panel open, and keeps the last 200 records of each side.
Colours at display time only: normal in the theme's foreground (white),
warning orange (`#ff9f0a`), error red (`#ff453a`).

Toasts: notify records from either side that arrive after the page's
first read of the log, stacked at the top of the screen (under a banner
when one shows, never over the toolbar), above the panels. Each has a
close cross; normal ones go after 6 s, warnings after 12 s, errors stay.
The same level, source and text again adds `×2` to the open toast instead
of a new one; at most 4 are shown. A viewer's own connection is not a
toast on its own page (`params.viewer`). While the tab is hidden, a system
notification too, only if the browser already allows notifications for
the page: the page never asks for the permission.

To see a warning and an error in the panel: open Information → Serveur and
unfold Journaux du serveur. A screen size the gateway refuses is a
warning, e.g. from a shell on the VPN (`PAGE` is the page's address):

```sh
TOKEN=$(curl -s "$PAGE" | sed -n 's/.*cloudphone-token" content="\([^"]*\)".*/\1/p')
curl -s -H "X-CloudPhone-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"width": 361, "height": 780, "density": 160}' "$PAGE/api/v1/display"   # 400: a warning record
```

An error comes with any of the failures above, e.g. on a test instance
`systemctl stop cloudphone-emulator` (Android stopped without a request:
an error record and a red toast; start it again afterwards). The level
filter set to Erreurs keeps only those.

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
`/opt/cloudphone/plugins/<id>/` holds `plugin.json` (id, title, version, `api`), an
optional `page.js` (ES module, may import the other `*.js` beside it) and an
optional `gateway.py` (`setup(context)`). The gateway (`--plugins_dir`)
loads them at start, logs and skips one that fails (still listed, with
`error`, when its manifest was read; the options panel shows the error),
refuses one whose `api` major differs from `API_VERSION` in `plugins.py`
(no `api`: 1), serves its scripts at
`/plugins/<id>/` and lists them at `GET /api/v1/plugins`; a plugin's own
routes live under `/api/v1/plugins/<id>/`, behind the usual origin and token
checks. The `id` must equal the directory name and match
`^[a-z0-9][a-z0-9-]{0,31}$`; only top-level `*.js` files matching
`^[a-z0-9][a-z0-9_-]{0,63}\.js$` are served. The page imports each
`page.js`, gives it the API described at the
top of `plugins.ts` (video element, a drawing layer over the screen, stored
options, gateway calls) and renders its options (toggle, number, choice, action,
buttons, dialog, status, grid, log: the server's records it keeps, and
foldable sub-sections) in Options → Plugins, one foldable section per
plugin, with the plugin's and its sections' optional icons.
`context` offers `add_get`/`add_post`, `screenshot(max_age=0)` (one
screenshot shared by every plugin: a capture younger than `max_age`
seconds, or one under way, is given instead of a new one; a plugin's own
`adb shell input` makes earlier ones stale), `analyse(fn, *args)` (runs
`fn` in a worker thread: pixel loops there leave the gateway answering),
`adb(...)`, `json()`,
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
