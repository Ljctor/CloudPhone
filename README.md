# CloudPhone

A private Android phone with Google Play, running on a Linux server and used
from a browser through WireGuard.

| Part | What it sets up | Entry points |
|---|---|---|
| [01 Server system setup](01-server-system-setup/) | hardened Debian baseline: accounts, SSH 52242, auditing, firewall, Fail2ban | runbooks over SSH, `scripts/verify.sh` |
| [02 WireGuard server](02-wireguard-server/) | VPN `10.20.0.0/24` on UDP 51820, device keys, firewall rules | `scripts/install.sh`, `add-peer.sh`, `nft-allow.sh` |
| [03 Android Emulator](03-android-emulator/) | pinned official emulator, Android 16 Google Play AVD, systemd service | `scripts/install.sh`, `scripts/verify.sh` |
| [04 Cloud Phone app](04-cloud-phone-app/) | WebRTC gateway and mobile web page, VPN-only; Google Play commissioning | `scripts/install.sh`, `src/`, `docs/DEVELOPMENT.md` |

**First time?** Follow [`docs/TUTORIAL.md`](docs/TUTORIAL.md): a step-by-step
installation from a fresh server to Android in your phone's browser.

Run the parts in order. Every part has:

- `AGENTS.md`: how an agent installs it (the default task);
- `README.md`: what it is, its files, how to operate it;
- `runbooks/`: ordered Check → Apply → Check steps calling `scripts/`.

Shared: `lib/` (pinned versions, shell helpers), `packaging/`
(`build-release.sh` builds `dist/cloudphone-<version>-linux-x86_64.tar.gz`
with parts 02–04, `stage-release.sh SERVER` stages it on a server,
`deploy.sh SERVER [03] [04]` stages it and runs those parts' install
scripts), `docs/TUTORIAL.md` (beginner walkthrough, parts 01–04),
`docs/INSTALL.md` (install parts 03+04 by hand on any Debian or Ubuntu host
with KVM; configuration and operations), `docs/METHOD.md` (execution model).

The release tarball has the repository's layout, so the scripts behave the
same from a checkout and from the unpacked release.
