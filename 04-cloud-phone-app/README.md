# 04 — Cloud Phone app

Streams the emulator's screen to a browser over WebRTC and forwards touch and
keys. Agents: read `AGENTS.md`.

| Service | Listens on |
|---|---|
| `cloudphone-gateway` (page and API, one origin) | `LISTEN_ADDRESS:WEB_PORT` (TCP, 8000 by default), WebRTC media UDP 32768-60999 |

| Path | Content |
|---|---|
| `src/overlay/` | our files, laid over Google's `android-emulator-container-scripts` at the pinned commit |
| `scripts/install.sh` | install or upgrade the app (Android keeps running) |
| `scripts/verify.sh` | read-only acceptance test (token, origin check, no CORS, listen address, firewall) |
| `scripts/firewall.sh` | `--check` / `--apply` the VPN-only rules |
| `scripts/commission.sh` | `--check` / `--apply` passive settings for a Google Play app |
| `files/` | launchers and systemd units |
| `constraints.txt` | pinned gateway dependencies |
| `tests/` | Playwright browser test |
| `docs/DEVELOPMENT.md` | gateway API, page behaviour, build, test, iterate |

From a checkout, `packaging/deploy.sh SERVER 04` stages the built release
and runs `scripts/install.sh --listen 10.20.0.1`.

## The page

- Toolbar: power, volume down/up, the **ping** block, recents, home, back,
  the **fps** block (frames per second displayed), `↻`, fullscreen, and in
  fullscreen the fold button.
- The ping block opens **Server settings**: server and Android state,
  network, video stream, **Disconnect** for the other devices (shown when
  more than one is connected), and **Android settings**: renderer, cores,
  memory, device shape and resolution, applied together with one **Apply**
  (it reboots Android once; one change per 2 minutes).
- The fps block opens **Client settings**: this device's display, how
  touches reach Android, language (French/English), touch marker, emerald
  mask (Slayer Legend), fold 3 s after entering fullscreen. Settings stay in
  this browser (`localStorage`, key `cloudphone.settings`).
- Fold button (fullscreen only): tap folds the bar away and shows a small
  handle (drag to move, tap to unfold); long press docks the bar beside the
  screen.
- Touch and keys go over the emulator's own WebRTC data channels, with HTTP
  through the gateway as fallback.
- When something is wrong the screen or a closable banner says what (VPN,
  Android crashed or starting, video blocked, another device took over,
  heavy load); the LED on `↻` is green, orange (being fixed) or red (needs
  action).
- `↻` replaces the video session only; it never restarts Android or the
  foreground app.
