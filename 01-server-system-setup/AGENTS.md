# Part 01 — agent instructions: server system setup

Default task: converge a fresh or partially configured Debian server to the
hardened baseline (connection accounts, SSH on 52242, auditing, firewall,
Fail2ban, tools, emergency password, bootstrap account removed).

Prerequisites: SSH key access as `debian` (fresh) or `setup-agent` (resumed).

```sh
export TARGET=debian@SERVER_ADDRESS        # fresh server
export TARGET=setup-agent@SERVER_ADDRESS   # from runbook 03 on, or resumed
```

For each runbook in `runbooks/`, in lexical order: run **Check**; if it
fails, run **Apply** once, then the same **Check** again; stop and report at
the first Check that still fails. Never infer state from chat, notes or Git
history: the server is the only source of truth (`../docs/METHOD.md`).

- Runbook 03 switches `TARGET` to `setup-agent`; keep it for the rest.
- Runbook 06 moves SSH: keep the current session open until a new connection
  on 52242 is proven.
- Runbooks 08–09 need the human (password typed interactively, never in a
  command, file, log or chat).
- Runbook 11 only on OVH dedicated servers; it needs a signed URL the human
  enters at a silent prompt.
- Done when runbook 12 prints `PASS: server is converged`.

Next: part 02. Maintaining this part: keep every Check read-only and mirror
behaviour changes in `scripts/verify.sh`.
