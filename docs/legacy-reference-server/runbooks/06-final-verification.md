# 06 — Cloud-phone final verification

Run the read-only Phase 3 acceptance test from the repository root:

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
./docs/legacy-reference-server/verify.sh "$TARGET"
```

The step passes only when the script prints
`PASS: official Android cloud-phone infrastructure is converged`. The script
also checks that Slayer Legend is installed, running in the foreground, exempt
from idle restrictions, and not managed by a watchdog. Google account login,
visible rendering, touch responsiveness, and in-game account persistence remain
explicit human tests.
