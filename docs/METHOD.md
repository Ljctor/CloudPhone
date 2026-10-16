# Agent execution method

This repository describes a desired server state and a deterministic way to
discover whether each part of that state is already satisfied. It does not track
the current state of any server.

## No inherited task state

A future agent knows only:

- the prerequisites in `README.md`;
- the desired outcome encoded by the ordered runbooks of each part;
- the target address supplied at execution time.

The agent must not assume that a step is complete or incomplete based on a prior
conversation, an earlier execution, the apparent age of the server, or this
repository's history. Every execution of a part starts at its runbook 00.

## State discovery algorithm

For each part in `README.md` (01, 02, 03, 04), run its runbooks in lexical
order before moving to the next part:

1. Execute Check.
2. If Check succeeds, make no change and continue.
3. If Check fails and the runbook has no Apply section, stop because a
   prerequisite or manual intervention is required.
4. If Check fails and Apply exists, execute Apply once.
5. Execute the same Check again.
6. If the second Check fails, stop and report the exact failing command and
   output. Never continue to a later runbook.
7. If it succeeds, continue to the next runbook.

The server itself is the only source of truth about completed work. This makes
the process safe for fresh, partially configured, fully configured, or
interrupted installations.

## Check contract

Every Check must:

- be read-only;
- return exit status `0` only when the complete step is satisfied;
- return nonzero when any required invariant is absent;
- avoid depending on prose, timestamps, chat history, or local marker files;
- expose enough command output to diagnose a failure without exposing secrets.

## Apply contract

Every Apply must:

- change only the state owned by that runbook;
- be idempotent whenever the underlying operation permits it;
- preserve unrelated server state;
- stop on an unsafe identity or configuration conflict;
- never embed secrets in arguments, files, logs, chat, or Git.

Interactive password entry is the documented exception to full automation. Its
result is still deterministically testable through the password-hash state.

## Completion

A part is complete when its last runbook (final verification) succeeds for the
current target, and its human checks, if any, pass. A successful run says
nothing about any other server. No persistent checklist or conversation copy
is needed.
