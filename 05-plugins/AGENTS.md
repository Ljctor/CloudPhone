# Part 05 — agent instructions: plugins

Default task: after part 04 converged, install the plugins with
`sudo 05-plugins/scripts/install.sh` (every plugin; or name them) or
`packaging/deploy.sh "$TARGET" 05`. Check:
`curl -fsS http://LISTEN_ADDRESS:WEB_PORT/api/v1/plugins` lists each one.

Rules:

- Everything specific to one game or app lives in its plugin directory
  here, never in parts 03–04.
- A plugin never launches or restarts an app by itself: only on a user's
  press, never from a timer or a script. The one exception, asked by the
  user: Slayer Legend's mpw18 watchdog relaunches the game (at most 3 times
  an hour, never during free play, a timed mode or the mine, a minute
  after a user input at the earliest, under the shared lease). No launch
  ever kills the app (`am start` without `-S`, no force-stop). On Android's
  "isn't responding" dialog the watchdog taps only "Wait", once, then
  alerts: never its "Close app", which kills the game.
- Slayer Legend's launch taps only "TAP TO START", Confirm on the save
  notice, "Close app" on Android's crash dialog (found by uiautomator, at
  most 2 times) and the "Press here to finish Power Saving Mode" button
  (held 4 s, at most 3 times), each only when the screen shows it; on any
  other screen it stops.
- Screenshots of a game go in the repository only when reviewed one by one
  (no Google account, no server address); never commit raw captures.
