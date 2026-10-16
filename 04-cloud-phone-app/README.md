# 04 — Cloud Phone app

Streams the emulator's screen to a browser over WebRTC and forwards touch and
keys. Agents: read `AGENTS.md`.

| Service | Listens on |
|---|---|
| `cloudphone-web` (page) | `LISTEN_ADDRESS:WEB_PORT` |
| `cloudphone-gateway` | `LISTEN_ADDRESS:WEB_PORT+1`, WebRTC media UDP 32768-60999 |

| Path | Content |
|---|---|
| `src/overlay/` | our files, laid over Google's `android-emulator-container-scripts` at the pinned commit |
| `scripts/install.sh` | install or upgrade the app (Android keeps running) |
| `scripts/verify.sh` | read-only acceptance test |
| `scripts/firewall.sh` | `--check` / `--apply` the VPN-only rules |
| `scripts/commission.sh` | `--check` / `--apply` passive settings for a Google Play app |
| `files/` | launchers and systemd units |
| `constraints.txt` | pinned gateway dependencies |
| `tests/` | Playwright browser test |
| `docs/DEVELOPMENT.md` | build, test, iterate |

The toolbar shows `ping` (ms), `srv` (frames/s received from the server) and
`tél` (frames/s displayed). `↻` replaces the video session only; it never
restarts Android or the foreground app.
