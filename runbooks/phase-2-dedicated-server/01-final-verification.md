# 01 — Final verification

Run the repository's complete, read-only acceptance test from the repository
root:

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
./scripts/verify-all.sh "$TARGET"
```

The step is complete only when the script prints `PASS: server is converged` and
exits `0`. There is no separate Apply command. If it fails, return to the first
numbered runbook whose check fails, apply it, verify it, and run the final test
again.
