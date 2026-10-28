# Agent instructions

This repository installs a cloud Android phone in four parts, in this order,
plus an optional fifth:

| Part | Read first |
|---|---|
| `01-server-system-setup/` | its `AGENTS.md` |
| `02-wireguard-server/` | its `AGENTS.md` |
| `03-android-emulator/` | its `AGENTS.md` |
| `04-cloud-phone-app/` | its `AGENTS.md` |
| `05-plugins/` (optional) | its `AGENTS.md` |

Each part's `AGENTS.md` is the installation procedure; development and
reference docs are linked from there. Execution model and safety rules:
`docs/METHOD.md`.

## Changing this repository

- Never commit passwords, private keys, tokens, signed URLs, host addresses,
  personal names or e-mail addresses, transcripts, or claims about a server's
  current state.
- Checks stay read-only and deterministic; Apply stays idempotent. A behaviour
  change updates the part's `scripts/verify.sh` in the same commit.
- One source of truth: runbooks call the part's scripts instead of copying
  their commands; the release tarball has the repository's layout.
- After a production deployment, the deploying agent sends an ntfy message
  explicitly identified as **Agent Codex — déploiement**, not as Cloud Phone
  or the plugin. Include the version, shipped changes and actual verification
  outcome; distinguish deployed code from unverified gameplay. Report failure
  truthfully. Use the existing notification configuration without exposing its
  private topic or changing subscription settings.
- Before committing:

```sh
git diff --check
shellcheck -x -P SCRIPTDIR */scripts/*.sh packaging/*.sh lib/common.sh */files/libexec/*
packaging/build-release.sh          # when parts 03–05 or packaging changed
```
