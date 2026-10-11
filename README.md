# Server system setup

This repository is an ordered, resumable runbook for configuring a fresh server.
It is written for an automation agent, but every command can also be run by a
human operator.

## Prerequisites

The operator or agent already has:

1. read access to this repository;
2. SSH key access to a fresh target as `debian`, or to a resumed target as
   `setup-agent`;
3. non-interactive access to the documented privilege path for that account.

Obtaining those three kinds of access is deliberately outside this runbook.
The target is a Debian-family system with `apt-get`, `systemd`, and OpenSSH.

Set the target once in the shell from which the runbooks are executed:

```sh
export TARGET=debian@SERVER_ADDRESS
# On a resumed or converged server:
export TARGET=setup-agent@SERVER_ADDRESS
```

Do not put private keys, passwords, access tokens, or host secrets in this
repository.

Agents maintaining this repository must also read [`AGENTS.md`](AGENTS.md) and
the execution model in [`docs/METHOD.md`](docs/METHOD.md).

## Execution protocol

Run phase 1 in lexical order. For an OVH dedicated server, then run phase 2 in
lexical order. Run phase 3 only when this server is intended to host the cloud
phone workload. Never skip ahead within a selected phase.

For every numbered runbook:

1. Run its **Check** exactly as written.
2. If the check exits `0`, record that the step was already converged and move
   to the next runbook.
3. If it exits nonzero, run **Apply**.
4. Run **Check** again.
5. Continue only if the second check exits `0`. Otherwise stop, report the
   command and its output, and fix that step before proceeding.

Checks are read-only and signal success through their exit status. Apply
commands are idempotent except for the explicitly interactive password step.
An interrupted setup can therefore restart at runbook 00 and converge again.

Phase 1 starts through the provider bootstrap account `debian`, hands off to
`setup-agent` at runbook 03, and removes `debian` at the final Phase-1
runbook. A resumed execution may start at runbook 00 with `setup-agent`; the
checks determine that the earlier state is already converged. Phases 2 and 3
use:

```sh
export TARGET=setup-agent@SERVER_ADDRESS
```

## Phase 1 — Any server

1. [`runbooks/phase-1-any-server/00-preflight.md`](runbooks/phase-1-any-server/00-preflight.md) — prove connectivity,
   operating-system compatibility, and sudo access.
2. [`runbooks/phase-1-any-server/01-connection-accounts.md`](runbooks/phase-1-any-server/01-connection-accounts.md)
   — create the connection accounts `emergency`, `admin-human`, and
   `setup-agent`, plus `system-setup` for phases 1–2 and a pre-created `master`
   account for phase 3.
3. [`runbooks/phase-1-any-server/02-connection-ssh.md`](runbooks/phase-1-any-server/02-connection-ssh.md)
   — authorize `admin-human` and `setup-agent` with the bootstrap SSH keys.
4. [`runbooks/phase-1-any-server/03-handoff-to-setup-agent.md`](runbooks/phase-1-any-server/03-handoff-to-setup-agent.md)
   — switch immediately to `setup-agent`, then enter `system-setup` for work.
5. [`runbooks/phase-1-any-server/04-command-auditing.md`](runbooks/phase-1-any-server/04-command-auditing.md)
   — preserve the original SSH login identity across functional-user and sudo transitions.
6. [`runbooks/phase-1-any-server/05-emergency-password-ssh.md`](runbooks/phase-1-any-server/05-emergency-password-ssh.md)
   — permit SSH password authentication only for `emergency`.
7. [`runbooks/phase-1-any-server/06-network-hardening.md`](runbooks/phase-1-any-server/06-network-hardening.md)
   — move SSH to port 52242, enable an inbound firewall, and protect SSH with Fail2ban.
8. [`runbooks/phase-1-any-server/07-tools.md`](runbooks/phase-1-any-server/07-tools.md) — configure CET/CEST and install Git and GitHub CLI.
9. [`runbooks/phase-1-any-server/08-passwords.md`](runbooks/phase-1-any-server/08-passwords.md) — preserve or set the
   sole password credential, owned by `emergency`.
10. [`runbooks/phase-1-any-server/09-password-change-verification.md`](runbooks/phase-1-any-server/09-password-change-verification.md)
   — verify that only `emergency` has a usable password hash.
11. [`runbooks/phase-1-any-server/10-retire-bootstrap-account.md`](runbooks/phase-1-any-server/10-retire-bootstrap-account.md)
   — remove `debian` only after proving access through the new connection users.
## Phase 2 — OVH dedicated server

1. [`runbooks/phase-2-dedicated-server/00-ovh-backup-agent.md`](runbooks/phase-2-dedicated-server/00-ovh-backup-agent.md)
   — install and verify the OVH Backup Agent.
2. [`runbooks/phase-2-dedicated-server/01-final-verification.md`](runbooks/phase-2-dedicated-server/01-final-verification.md) — run
   the complete read-only acceptance test.

## Phase 3 — Cloud Android phone

Phase 3 uses `setup-agent`, delegates to `master`, and installs the
application-specific workload:

1. [`runbooks/phase-3-cloud-phone/00-preflight.md`](runbooks/phase-3-cloud-phone/00-preflight.md)
   — verify x86-64, KVM, RAM, CPU, and storage prerequisites.
2. [`runbooks/phase-3-cloud-phone/01-official-android-emulator.md`](runbooks/phase-3-cloud-phone/01-official-android-emulator.md)
   — install the official Android SDK, the pinned stable Emulator, and a persistent Android 16 Google Play AVD.
3. [`runbooks/phase-3-cloud-phone/02-secure-emulator-service.md`](runbooks/phase-3-cloud-phone/02-secure-emulator-service.md)
   — run the official Android 16 Emulator with software rendering, authenticated gRPC, and loopback-only ADB.
4. [`runbooks/phase-3-cloud-phone/03-wireguard.md`](runbooks/phase-3-cloud-phone/03-wireguard.md)
   — expose the private cloud-phone network through WireGuard.
5. [`runbooks/phase-3-cloud-phone/04-web-control.md`](runbooks/phase-3-cloud-phone/04-web-control.md)
   — provide the patched WebRTC stream and touch controls only through WireGuard.
6. [`runbooks/phase-3-cloud-phone/05-application-acceptance.md`](runbooks/phase-3-cloud-phone/05-application-acceptance.md)
   — validate Google Play, Slayer Legend, CET/CEST, and passive anti-idle settings without automatic game recovery.
7. [`runbooks/phase-3-cloud-phone/06-final-verification.md`](runbooks/phase-3-cloud-phone/06-final-verification.md)
   — run the complete cloud-phone acceptance test.

The Phase-2 checker can also be called directly as:

```sh
./scripts/verify-all.sh "$TARGET"
```

That command diagnoses the current state; it does not replace ordered
execution of the runbooks on a fresh server.

For the optional cloud-phone workload, run its dedicated checker after Phase 3:

```sh
./scripts/verify-phase3.sh "$TARGET"
```
