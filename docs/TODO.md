# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code,
each with what is known. Owner: the agent maintaining the gateway and the
page; fix or explain each before the hexagonal refactor reaches its domain.

- Harness port clashes, "address already in use": now and then a test's
  gateway, fake emulator or geckodriver fails to bind its port, three
  times in one day (the latest in `ui_page`, the gateway on the very port
  the fake's gRPC service had just been given). The gateway's port is
  picked ahead (`free_port()` in `tests/fake-emulator/fake_emulator.py`:
  bind port 0, close, pass the number on), and so is geckodriver's
  (`tests/e2e/src/browser.rs`); until the process binds it, the fake's own
  gRPC server (bound on port 0 meanwhile) or any other process can get the
  same port. A rerun passes. A test that fails this way can also leave
  its geckodriver and Firefox running, holding the suite lock, so the
  next `flock` waits until they are stopped. Fix: the fake, the gateway and geckodriver each bind port
  0 and pass the port they got on to the harness; in one commit, by
  whoever next works on the harness.

# Planned work

In order of value. One worktree per track; never two black-box suites on
the machine at once (wrap `cargo test` in `flock` on one shared lock file).

1. fps uptime run (planned for 2026-10-20, with the emulator up about 24 h):
   steady state first; then relaunch the game only, wait the settle time,
   measure; then restart the emulator, relaunch, wait, measure. Same scene,
   same regime, three numbers: they say whether a scheduled game relaunch
   or a scheduled emulator restart (with no viewer connected) restores the
   frame rate. A relaunch costs about 5 minutes near 20 fps plus sign-in.
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
