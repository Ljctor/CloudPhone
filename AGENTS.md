# Instructions for agents

Read these files before changing or running anything:

1. `README.md` for prerequisites, ordering, and the convergence protocol;
2. every file in `runbooks/phase-1-any-server/` in lexical order, then every
   file in `runbooks/phase-2-dedicated-server/`, then
   `runbooks/phase-3-cloud-phone/`, each in lexical order;
3. `docs/METHOD.md` for the state-discovery model and safety rules.

When configuring a server, do not infer completion from prior chat, notes, or an
operator's memory. For each runbook, execute its Check, Apply only when needed,
then execute the same Check again. Stop at the first failed post-Apply check.

Keep all checks read-only and deterministic. Keep Apply sections idempotent.
Never commit passwords, private keys, personal access tokens, host addresses,
raw conversation transcripts, or claims about a target server's current state.

Changes to runbook behavior must update the corresponding final assertions in
`scripts/verify-all.sh`. Before committing, run:

```sh
git diff --check
sh -n scripts/verify-all.sh
sh -n scripts/verify-phase3.sh
```
