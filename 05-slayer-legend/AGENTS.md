# Part 05 — agent instructions: Slayer Legend plugin

Default task: install the plugin with `sudo 05-slayer-legend/scripts/install.sh`
(or `packaging/deploy.sh "$TARGET" 05`) after part 04 converged. Check:
`curl -fsS http://LISTEN_ADDRESS:WEB_PORT/api/v1/plugins` lists
`slayer-legend`.

Rules:

- Everything specific to Slayer Legend lives here, never in parts 03–04.
- The launch only runs when the user presses it. Never call it from a
  watchdog, a timer or a script: nothing may launch or restart an app
  automatically. It taps only "TAP TO START" and Confirm on the save notice.
- Never commit screenshots of the game: they can show the user's Google
  account.
