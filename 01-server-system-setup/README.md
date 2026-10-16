# 01 — Server system setup

Hardened baseline for any Debian-family server, applied from the operator's
machine over SSH. Agents: read `AGENTS.md`.

| Runbook | Result |
|---|---|
| 00 | connectivity, OS and sudo prerequisites |
| 01–03 | accounts `emergency`, `admin-human`, `setup-agent`, `system-setup`, `master`; SSH keys; handoff to `setup-agent` |
| 04 | `auditd` keeps the login identity across sudo |
| 05 | password SSH only for `emergency` |
| 06 | SSH on port 52242, nftables (policy drop), Fail2ban, no LLMNR |
| 07 | Europe/Paris time, Git, GitHub CLI |
| 08–09 | the only password belongs to `emergency` |
| 10 | provider account `debian` removed |
| 11 | OVH Backup Agent (OVH dedicated servers only) |
| 12 | `scripts/verify.sh` acceptance test |

Workload parts run as `setup-agent` and reach root through `master`.
