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
  user: Slayer Legend's mpw18 watchdog relaunches the game (backing off
  after each failure: 1, 2, 4, 8, 16, then 30 minutes between attempts;
  never during free play, a timed mode or the mine, a minute after a user
  input at the earliest, under the shared lease). No launch
  ever kills the app (`am start` without `-S`, no force-stop). On Android's
  "isn't responding" dialog the watchdog taps only "Wait", once, then
  alerts: never its "Close app", which kills the game.
- What Slayer Legend's plugin taps by itself: this list is exhaustive.
  Every move goes through the navigation guard (`navigation.json`) under
  the shared lease, on a fresh capture showing that screen; anything else
  stops the sequence with one alert. Nothing outside it is ever tapped.
  - Launch:
    - "TAP TO START": on the title screen, at most every 8 s.
    - Confirm on the save notice: only when the notice shows (never Exit).
    - "Close app" on Android's crash dialog: found by uiautomator, at most
      2 times per launch.
    - "Sign in with Google": on the sign-in screen, once per launch; never
      "Sign in with Apple".
    - The account of Google's chooser: found by uiautomator, only when
      exactly one is listed and the launch's own tap opened the chooser.
    - "Press here to finish Power Saving Mode": held 4 s, at most 3 times.
  - Watchdog:
    - "Wait" on Android's "isn't responding" dialog: once per dialog, never
      its "Close app".
    - The right edge's arrow that unfolds the controls, to read the preset
      badge and AUTO: only with no viewer connected, at most every 5
      minutes, only while the preset or auto switch is real.
  - Stage change and preset (mode changes and the watchdog's repairs,
    each only while its switch is real):
    - Closing a bottom panel with its own tab: only when that tab reads lit.
    - Opening Select Region (the stage map button on the battle screen).
    - Select Region's region arrows: only while its banner reads one region.
    - Select Region's arrows and list scrolls: at most 10 moves for the whole
      sequence, arrows and scrolls together (`MOST_MOVES`).
    - Move: only on the row whose name reads as the target stage.
    - The preset badge: with the arrow that unfolds it, in one adb call,
      only when the fresh capture reads the controls folded and the badge
      reads another preset.
    - The preset's button in Battle settings: only once Battle settings
      reads open, and another preset reads selected.
    - Battle settings' close button: after its preset reads selected.
    - The AUTO gear: not tapped until a real AUTO-off capture calibrates
      its reading (`AUTO_TAP_LEARNED`).
  - Closed mine (mode "mine"): its floor row, the Area, 3 feathers,
    scrolling its floor list, and unticking "Repeat entry" (at most 3
    tries, then one alert).
- Screenshots of a game go in the repository only when reviewed one by one
  (no Google account, no server address); never commit raw captures.
