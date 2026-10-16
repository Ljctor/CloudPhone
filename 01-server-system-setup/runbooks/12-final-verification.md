# 12 — Final verification

Run the repository's complete, read-only acceptance test from the repository
root:

## Check

```sh
: "${TARGET:?Set TARGET to setup-agent@SERVER_ADDRESS}"
./01-server-system-setup/scripts/verify.sh "$TARGET"
# On an OVH dedicated server that ran runbook 11:
./01-server-system-setup/scripts/verify.sh "$TARGET" --ovh-backup
```

The step is complete only when the script prints `PASS: server is converged` and
exits `0`. There is no separate Apply command. If it fails, return to the first
numbered runbook whose check fails, apply it, verify it, and run the final test
again.
