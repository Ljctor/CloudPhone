# Part 05 — agent instructions: plugins

Default task: after part 04 converged, install the plugins with
`sudo 05-plugins/scripts/install.sh` (every plugin; or name them) or
`packaging/deploy.sh "$TARGET" 05`. Check:
`curl -fsS http://LISTEN_ADDRESS:WEB_PORT/api/v1/plugins` lists each one.

Rules:

- Everything specific to one game or app lives in its plugin directory
  here, never in parts 03–04.
- A plugin never launches or restarts an app by itself: only on a user's
  press, never from a watchdog, a timer or a script.
- Slayer Legend's launch taps only "TAP TO START", Confirm on the save
  notice and the "Press here to finish Power Saving Mode" button (held 4 s,
  at most 3 times), each only when the screen shows it; on any other screen
  it stops.
- Screenshots of a game go in the repository only when reviewed one by one
  (no Google account, no server address); never commit raw captures.
