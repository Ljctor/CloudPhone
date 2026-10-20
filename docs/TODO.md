# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code,
each with what is known. Owner: the agent maintaining the gateway and the
page; fix or explain each before the hexagonal refactor reaches its domain.

None at the moment.

# Planned work

In order of value. One worktree per track; never two black-box suites on
the machine at once (wrap `cargo test` in `flock` on one shared lock file).

1. fps uptime run (planned for 2026-10-20, with the emulator up about 24 h):
   steady state first; then relaunch the game only, wait the settle time,
   measure; then restart the emulator, relaunch, wait, measure. Same scene,
   same regime, three numbers: they say whether a scheduled game relaunch
   or a scheduled emulator restart (with no viewer connected) restores the
   frame rate. A relaunch costs about 5 minutes near 20 fps plus sign-in.
   Step 1 on 2026-10-20 03:07 found the game in Power Saving Mode (emulator
   up 23 h 08, game 22 h 25), so the battle reading waits for one guarded
   hold. Read-only reading of that scene instead, 180 s from 03:08, no
   baseline: 20.8 fps mean, p50 20.7, worst 10 s 19.9, UnityMain 98.6 %,
   host idle 33 %.
2. fps B7: the game's 30 fps cap through Game Mode (`cmd game set --mode 3
   --fps 30`), measured in both regimes (the first 5 minutes, where the
   paced steps become 30/15/10, and steady state); the worst-10 s column
   decides.
3. What the viewer sees: the browser's inbound-rtp stats (framesReceived,
   framesDecoded, framesDropped, framesPerSecond) beside SurfaceFlinger
   timestats in the same 60 s, on a battle and on a light screen. Needs the
   page open in the user's browser.
4. Hexagonal refactor: gateway domains (display next, with
   `adapters/host_files.py`), then the page, then the plugin.
