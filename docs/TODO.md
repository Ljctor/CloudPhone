# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code,
each with what is known. Owner: the agent maintaining the gateway and the
page; fix or explain each before the hexagonal refactor reaches its domain.

None at the moment.

## Game incidents

- 2026-10-21, Slayer Legend: a guarded tap meant for the small arrow on
  the battle screen's right edge landed on the AUTO gear and turned AUTO
  off. Cause: the arrow unfolds the preset badge and the AUTO gear, which
  fold away again after about 2 s; a guarded tap (guard, then the ssh/adb
  round trip) arrived after the fold, on the gear. AUTO was turned back
  on the same night (gear spinning, skills on cooldown). Fix: unfold and
  next tap in one adb call, both guarded first, only when a fresh capture
  reads the controls folded. Since 2026-10-22 (the user's order) the AUTO
  button is never tapped at all (forbidden in navigation.json): a stage
  progress bar that stops moving is an error alert instead.

- 2026-10-21, Slayer Legend: the plugin equipped the soul weapon Vision in
  mpw18 by itself (the user saw the result) while the Equip tag reader had
  never read a real tag (its two fixture tests were skipped). No supervised
  run up to Equip was recorded; the run's records were not collected. Fix:
  Equip is planned only once fixtures/sw_tag_equip.txt and
  sw_tag_unequip.txt exist from real captures; until then the step raises
  an error alert and does not equip.

## First real runs of opened gates

Each gate on a reading (`05-plugins/AGENTS.md`) has its first real run
made with the user present, recorded here: date, readings, result.

- Slayer Legend engraving lock and swap (`PADLOCK_LEARNED`,
  `POPUP_LEARNED`, `PREVIEW_LEARNED`, opened 2026-10-22 on the captures
  eg2–eg10): to run with the user present (Vision, Atk to Gold-balanced),
  then recorded here. Until then the engraving switch (`POST /farming`
  `{engraving}`) stays "off" (its default: no lock, removal, placing or
  preview, an error alert "engraving not set up: first supervised run
  pending", the weapon not ready); it goes to "real" only with the user
  present, for that run.
- Slayer Legend Equip tap (`TAG_LEARNED`): closed until the Equip tag is
  captured.

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
