# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code,
each with what is known. Owner: the agent maintaining the gateway and the
page; fix or explain each before the hexagonal refactor reaches its domain.

None at the moment.

# Planned work

In order of value. One worktree per track; never two black-box suites on
the machine at once (wrap `cargo test` in `flock` on one shared lock file).

1. Plugin hardening: one shared screenshot in the plugin context with a
   per-caller maximum age and a capture count in `/api/v1/state?details=1`;
   pixel analysis in a thread executor (`context.analyse`); plugin state
   (mode, timers, mine floor and area, highest stage) kept in the plugin's
   data directory across gateway restarts; manifest `"api": 1` checked by
   the loader; the trust model written down in part 05's README.
2. Contract run against the live instance (one extra viewer, no input; needs
   the user's go): fix the fake emulator where it differs and remove its
   UNVERIFIED marks.
3. Docs: logs panel and toasts, ntfy alerts, plugin install and removal, the
   black-box suite on a workstation; part 03's performance facts from fps
   phase A.
4. fps phase B readiness: scripts dry-run, part 03 deployed at the first
   emulator restart; launch-only runs first (-force-vulkan, -force-gles20,
   -job-worker-count 3).
5. Hexagonal refactor: gateway domains, then the page, then the plugin.
