# Tutorial: Cloud Phone from scratch

A complete installation, from a fresh Debian server to an Android phone with
Google Play running in your own phone's browser. It follows parts 01 to 04 of
this repository in order; part 05, an optional game plugin, is a short extra
step at the end. You need to be comfortable with a terminal; nothing else is
assumed.

```text
 your phone ──WireGuard (UDP 51820)──▶ server 10.20.0.1
   browser ──http://10.20.0.1:8000/──▶ cloudphone-gateway (page + API, one port)
           ◀──WebRTC video (UDP 32768-60999)── Android Emulator (cloudphone-emulator)
```

The page has no login: whoever reaches it controls the phone and its Google
account. Everything below is arranged so that the page can only be reached
through the VPN.

## What you end up with

| | |
|---|---|
| `cloudphone-emulator` | Google's official Android Emulator running Android 16 with Google Play, headless, started at boot |
| `cloudphone-gateway` | serves the web page and streams the screen over WebRTC; forwards touches and keys |
| `cloudphone-settings.path` | applies the Android settings you change from the page (renderer, cores, memory, screen size) with one restart |
| `cloudphone-display.path` | the same for a screen size change alone, sent by API clients rather than the page |
| `wg-quick@wg0` | the WireGuard tunnel; the server is `10.20.0.1`, your phone `10.20.0.2` |
| `/var/lib/cloudphone/avd/` | **the phone's data**: Google account, apps, app data. Upgrades never touch it |
| `/etc/cloudphone/cloudphone.conf` | the configuration: listen address, port, renderer, cores, RAM, screen size. The page's Apply rewrites it, after saving a `.bak-<date>` copy |
| `/opt/cloudphone/` | Android SDK and emulator, the current and previous app release (`releases/`), the plugins (`plugins/`) |
| `http://10.20.0.1:8000/` | the page, from any device on the VPN |

Total time: 2 to 3 hours, most of it waiting for downloads and Android's first
boot. Part 01 is the only part that needs about an hour of your attention.

## Before you start

| | What you need |
|---|---|
| **Server** | x86-64 with KVM (`ls -l /dev/kvm` shows the device), a fresh Debian 12 or 13 reached by SSH key as the provider's `debian` account, 4 CPU cores, 6 GiB RAM, 15 GiB free disk, a public address. No GPU: Android is drawn on the CPU |
| **Workstation** | Linux x86-64 with `git`, `curl`, `make`, `tar`, `gzip`, `sha256sum`, `ssh` and `scp`, Node.js 18 or newer with `npm`, Python 3.10 or newer with its `venv` module (package `python3-venv` on Debian and Ubuntu) |
| **Phone** | the WireGuard app, a browser, a Google account |

Your SSH key must be loaded in `ssh-agent` (`ssh-add -l` lists it) or have no
passphrase: the scripts and runbooks connect with `BatchMode=yes`, which
cannot ask for one.

In the commands below, `SERVER_ADDRESS` is the server's public IP or DNS
name, and later `SERVER` is an ssh alias for it. Run the workstation commands
from the root of a clone of this repository.

## 1. Build the release (workstation, 5–10 minutes)

```sh
packaging/build-release.sh
```

Why a build: Google's emulator and Android image cannot be redistributed, so
the release tarball holds everything else (the page, the gateway, the scripts)
and the server downloads Google's files itself in part 03.

You should see `==> Fetching upstream android-emulator-container-scripts`,
`==> Building the web control page`, `==> Building the streaming gateway`,
then `==> Writing dist/cloudphone-<version>-linux-x86_64.tar.gz`, its size
and its checksum. Downloads are cached in `build/cache`, so later builds are
faster.

## 2. Harden the server (part 01, about 1 hour)

[`01-server-system-setup/`](../01-server-system-setup/) turns the fresh server
into a hardened baseline: dedicated accounts, SSH on port 52242, a firewall
that drops everything else, Fail2ban, command auditing. Parts 02 to 04 rely
on the accounts and the firewall it creates.

### Who is who

| Account | Role |
|---|---|
| `debian` | the provider's account you start from; deleted at runbook 10 |
| `setup-agent` | key-only login you use from part 02 on; no root rights of its own, it may only become `system-setup` or `master` |
| `admin-human` | a second key-only login with the same rights, kept for a person |
| `emergency` | the only account allowed to log in with a password: your way back in if your key is lost |
| `system-setup` | no SSH login; password-less root for part 01's own work |
| `master` | no SSH login; password-less root for parts 02–04 (this is what `AS_ROOT` uses below) |
| `cloudphone` | created later by part 03: the unprivileged account that runs Android and the gateway |

### Before you start part 01

- Know how to open your provider's rescue or KVM console. Runbook 06 moves
  SSH to port 52242 and loads a firewall that drops everything else; a
  mistake there locks you out, and the console is the only way back.
- These steps cannot be undone from the runbooks: the drop-all firewall and
  the SSH port move (06), the time zone forced to `Europe/Paris` (07; edit the
  runbook first if you want another), the deletion of the provider's `debian`
  account and its home (10).
- Runbook 11 is for OVH dedicated servers only (it asks for a signed
  installer URL at a silent prompt); skip it anywhere else.
- Runbook 08 is the only step that asks for a password (for `emergency`); you
  type it at a `passwd` prompt, never in a command, a file or a chat.
- Runbook 06's Check runs `resolvectl` and its Apply restarts
  `systemd-resolved`, which some Debian images do not ship. Before you reach
  06, run `ssh "$TARGET" 'systemctl is-active systemd-resolved'`. If it does
  not print `active`, install it first with
  `ssh "$TARGET" 'sudo -n -u system-setup sudo -n apt-get install -y systemd-resolved'`,
  then confirm names still resolve: `ssh "$TARGET" 'getent hosts deb.debian.org'`
  (systemd-resolved takes over `/etc/resolv.conf`).
- Keep a second terminal connected to the server during runbook 06, and keep
  the rescue console at hand.

### Procedure

```sh
export TARGET=debian@SERVER_ADDRESS     # user@address, not an ssh alias
```

Why not an alias: runbook 00 reads the user part of `TARGET` to choose how it
reaches root, and refuses anything but `debian` or `setup-agent`. With a wrong
user part, several Check blocks end in `exit 2`, which closes your terminal
window when pasted.

Then, for each runbook from `00-preflight.md` to `12-final-verification.md`,
in order:

1. Open `01-server-system-setup/runbooks/NN-….md` and read it: one screen
   each, it says what the step changes.
2. Paste its **Check** block into the terminal, then type `echo $?`. `0`
   means the step is already done: go to the next runbook.
3. Otherwise paste the **Apply** block, then the Check block again, then
   `echo $?`. It must be `0` now. If it is not, stop: the output above names
   the failing command. Do not continue to a later runbook.

Why Check first: a runbook only changes what is missing, so you can stop at
any time and resume from 00 later; already done steps are simply skipped.

| At | What happens |
|---|---|
| 00 | No Apply: a failure means a prerequisite is missing (OS, SSH key, sudo) |
| 01–02 | Accounts and SSH keys. Runbook 02 ends with three `ssh … setup-agent@…` tests: all must print nothing and exit `0` |
| 03 | **Switch the target**: `export TARGET=setup-agent@SERVER_ADDRESS`, and keep it for everything that follows. The `debian` login is no longer used |
| 04–05 | Auditing; SSH passwords refused for everyone but `emergency` |
| 06 | **SSH moves to port 52242 and the firewall goes live.** Apply is three blocks: run them one at a time, and only run the third when the second (`ssh -p 52242 … 'true'`) succeeded. Then add the `Host SERVER_ADDRESS` entry below to `~/.ssh/config`, open a new terminal, check that `ssh "$TARGET" true` works, and rerun Check |
| 07 | Git, GitHub CLI, time zone |
| 08 | Apply opens `passwd emergency` in a terminal: type the password twice there. Choose a strong one; it is the password that works over SSH |
| 09 | Check only: confirms that `emergency` has a password and nobody else does |
| 10 | **Deletes `debian`** (irreversible). Check also logs in as `admin-human` to prove you still have two key-only logins |
| 11 | OVH dedicated servers only. Elsewhere, skip it; its Check fails there, which is expected |
| 12 | `./01-server-system-setup/scripts/verify.sh "$TARGET"` prints `PASS: server is converged`. You are done with part 01 |

The `~/.ssh/config` entries to add at runbook 06. The first keeps the
runbooks' `ssh "$TARGET"` working on the new port; the second is the alias
used for parts 02–04:

```text
Host SERVER_ADDRESS
  Port 52242

Host cloudphone
  HostName SERVER_ADDRESS
  Port 52242
  User setup-agent
```

**Skipping part 01.** On a server you hardened yourself you need: an nftables
input chain with policy `drop` (parts 02 and 04 add their rules to it;
without one their firewall script refuses to run, see the
[02 README](../02-wireguard-server/README.md#4-firewall) for ufw), outbound
internet, and an account with password-less `sudo`. Use that account as
`SERVER` and set `AS_ROOT='sudo -n'` below.

## 3. Set these in every new terminal

From here on, every command runs on the workstation, from the repository
root, and reaches the server through these three variables. Set them again
in each new terminal:

```sh
SERVER=cloudphone                                   # the ssh alias, or setup-agent@SERVER_ADDRESS
export AS_ROOT='sudo -n -u master sudo -n'         # how setup-agent reaches root (part 01); 'sudo -n' without part 01
RELEASE=$(packaging/stage-release.sh "$SERVER")    # uploads the release and prints its directory on the server
echo "$RELEASE"
```

You should see `/var/tmp/cloudphone-release/cloudphone-<version>-linux-x86_64`.
`stage-release.sh` copies the tarball, verifies its checksum and unpacks it as
root (a few seconds; running it again just replaces the copy). Why on the
server: parts 02 to 04 run their scripts from that copy as root, so only root
may write it.

## 4. Set up WireGuard (part 02, 10 minutes)

Create the tunnel and open UDP 51820 in the server's firewall:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/install.sh"
```

You should see `WireGuard is running on wg0.` with the server's public key
and `Public UDP port   : 51820`. If your provider has its own network
firewall, allow UDP 51820 there too.

On the phone, in the WireGuard app: **+ → Create from scratch**, name it
`cloudphone`, tap the generate icon next to *Private key*, set *Addresses* to
`10.20.0.2/32`, and copy the **Public key**. The private key never leaves the
phone; only the public key goes to the server:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/add-peer.sh phone 'PHONE_PUBLIC_KEY' 10.20.0.2"
```

You should see `Backup: /etc/wireguard/wg0.conf.bak-…`, then `Peer phone
added. On the device, finish its tunnel with:` and a `[Peer]` block. In the
app, tap **Add peer** and copy it in:

| Field | Value |
|---|---|
| Public key | the server's key, as printed |
| Endpoint | the script prints the literal `SERVER_PUBLIC_ADDRESS:51820` because it does not know how the server is reached from outside: replace `SERVER_PUBLIC_ADDRESS` with the server's public IP or DNS name, keep `:51820` |
| Allowed IPs | `10.20.0.0/24`: only traffic for the VPN network goes through the tunnel; the rest of the phone's traffic keeps its normal route |
| Persistent keepalive | `25`: keeps the tunnel open through mobile networks, which drop idle connections |

Save, switch the tunnel on, then check:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/verify.sh"
ssh "$SERVER" "$AS_ROOT wg show wg0"
```

You should see `ok` lines ending with `PASS: WireGuard server is converged`,
and in `wg show` a `latest handshake:` a few seconds old for the phone. No
handshake: see [Troubleshooting](#troubleshooting).

## 5. Install Android (part 03, 10–30 minutes)

The server now downloads Google's emulator (pinned to 36.6.11 and
checksum-verified) and the Android 16 Google Play image, several GB. You must
accept Google's Android SDK licences yourself, so run the installer with a
terminal (`-t`) to read and answer them:

```sh
ssh -t "$SERVER" "$AS_ROOT $RELEASE/03-android-emulator/scripts/install.sh"
```

You should see, in order: `==> Checking the host`, `==> Installing system
packages`, `==> Preparing the cloudphone service account`, `==> Installing
the Android command-line tools`, then `==> Review and accept the Android SDK
licences`: Google's `sdkmanager` shows each licence and asks you to accept it
(answer `y`). Then `==> Downloading … (the system image is several GB)`,
`==> Installing the pinned Android Emulator 36.6.11 (build 15507667)`,
`==> Installing configuration`, `==> Creating the Android device cloudphone`,
`==> Installing the cloudphone-emulator service`, `==> Starting the Android
Emulator`, `==> Waiting for Android to boot (the first boot can take several
minutes)` and finally `==> Android is running`.

It takes 10 to 30 minutes depending on the download speed. Do not interrupt
it. If your connection drops, run
the same command again: it continues where it stopped and never recreates
the Android device. Without `-t` it stops at once with `ERROR: the Android
SDK licences must be accepted: run interactively, or pass
--accept-android-sdk-license after reading them`.

Equivalent shortcut from the checkout: `packaging/deploy.sh "$SERVER" 03`
stages the release and runs this installer; run it from a terminal so it
can show the licence prompt, or, once you have read the licences,
`ACCEPT_ANDROID_SDK_LICENSE=yes packaging/deploy.sh "$SERVER" 03`.

Then:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/03-android-emulator/scripts/verify.sh"
```

You should see `ok` lines ending with `PASS: Android Emulator is converged`.

Another Android emulator or adb server already on this host? Write
`/etc/cloudphone/cloudphone.conf` with free ports **before** installing
([03 README](../03-android-emulator/README.md#running-next-to-another-emulator-or-adb-server));
the page is then on port 8100 instead of 8000.

## 6. Install the page and the gateway (part 04, 5 minutes)

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --apply"
ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/install.sh --listen 10.20.0.1"
ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"
```

Why two safeguards: `firewall.sh` accepts TCP 8000 and UDP 32768-60999 on the
`wg0` interface only, and `--listen 10.20.0.1` makes the page listen on the
VPN address only, so it is not even reachable from the public interface if
the firewall ever changes.

You should see: from `firewall.sh`, `Persisted in
/etc/nftables.d/cloudphone-web-8000.nft` and `Active now: …` for each of the
two rules (or `Already allowed:` when rerun); from `install.sh`,
`==> Installing Cloud Phone app <version>`, `==> Restarting the streaming
services (Android keeps running)` and then:

```text
Cloud Phone <version> is installed.

  Web control page : http://10.20.0.1:8000/
  Configuration    : /etc/cloudphone/cloudphone.conf
  Android data     : /var/lib/cloudphone/avd  (back it up; never deleted by upgrades)
  Logs             : journalctl -u cloudphone-emulator -u cloudphone-gateway
```

and from `verify.sh`, `ok` lines ending with `PASS: Cloud Phone app is
converged` (it checks the page's token, that other web sites are refused,
that nothing listens outside `10.20.0.1`, and the two firewall rules).

One last check, from the workstation, which is outside the VPN:

```sh
curl -m 3 http://SERVER_ADDRESS:8000/
```

It must fail (`Connection timed out` or `Connection refused`). If it answers,
stop and fix the firewall before going on.

## 7. Open the phone

On the phone, with the WireGuard tunnel on, open **http://10.20.0.1:8000/**
in the browser. You should see a spinner with `Connecting to the stream…`
and an orange LED on `↻`, then Android's home screen within about 10 seconds
and a green LED. The page is in French when the browser is, English
otherwise: the cog → **Options** → *Language* changes it.

Sign in to Google Play as on a new phone: open the Play Store, enter your
account. Android's on-screen keyboard appears in text fields. Because this is
a new device, Google usually asks you to confirm on a phone that already has
your account: a notification like **Is it you?** / *Trying to sign in from
another device?* appears on that phone, possibly the very one you are
holding, so pull down the notification shade to find it, tap **Yes**, then
return to the Cloud Phone tab (the stream reconnects by itself). A passkey
works too. Then install your apps from Google Play.

The toolbar holds: power and volume, the **ping/fps** block (your ping above
the frames per second you see), recents / home / back, the **cog**, `↻`
(reconnect the video only; it never restarts Android or the app on screen)
and fullscreen. The ping/fps block opens **Information** with two tabs:
**Client** (network, display, touches) and **Server** (Status, Machine,
Android and Stream sent, then **Android settings**: **Renderer**, **Cores**,
**Memory**, **Device** and **Resolution** (360p, 480p (default), 720p,
1080p); one **Apply** restarts Android once with all of them, at most once
every 2 minutes; **Disconnect** shows only when another device is
connected). Each tab ends with a log: **Journaux du client** (Client logs)
and **Journaux du serveur** (Server logs). The cog opens **Options**:
**Language**, **Show the cursor**, **Fold the bar 3 s after entering
fullscreen**, **Alertes sur le téléphone** (Phone alerts, step 10) and
**Plugins** (the options of installed plugins). In fullscreen, a fold button hides the bar; a small
handle brings it back, and a long press docks the bar instead.

## 8. First checks

- The LED on `↻` is green and no message covers the screen.
- A swipe from the top opens Android's notification shade; home, back and
  the volume keys work.
- Information → Client → *Touches via* says `data channel` (touches go straight
  to the emulator; `HTTP` is the slower fallback through the gateway).
- Information → Server → *Android service* says `active (running)` and *Android
  booted* says `yes`.
- `↻` brings the image back without restarting the app on screen.
- Closing and reopening the tab reconnects.

## 9. Keep one app running around the clock (optional)

To run one app permanently (a game, a messaging app), install it from Google
Play in the page and launch it once. Then give Android the passive settings
that keep it alive: screen never off, exemption from Android's battery
saving, time zone and network time. You need the app's package name: the
`id=` part of its Google Play link
(`https://play.google.com/store/apps/details?id=com.example.app` →
`com.example.app`; share the app from the Play Store, or search it on
play.google.com from a desktop browser).

```sh
APP_PACKAGE=com.example.app
ssh "$SERVER" "$AS_ROOT env TIMEZONE=Europe/Paris $RELEASE/04-cloud-phone-app/scripts/commission.sh --apply $APP_PACKAGE"
```

You should see `ok` lines (`screen never turns off`, `… is exempt from
Doze`, `… is in the active standby bucket`, `time zone is Europe/Paris,
network time on`, `no service relaunches apps automatically`) and `PASS:
Android is commissioned for com.example.app`. If the app is not installed
yet: `ERROR: … is not installed: install it from Google Play in the web page
first`. `--check` instead of `--apply` re-tests without changing anything.

Nothing launches or relaunches the app for you, by design: after a reboot of
Android, you open it again from the page.

## 10. Turn on phone alerts (optional, 2 minutes)

The page shows what happens as toasts and in its logs, but only while it is
open. To hear about a crash or a restart with the page closed, the gateway
can send alerts to your phone through ntfy.sh, a public notification
service:

1. Install the **ntfy** app on the phone.
2. In the page: cog → Options → **Alertes sur le téléphone**, tick **Alertes
   par ntfy**. An address `ntfy.sh/cloudphone-…` appears under it; copy it
   with the button beside it.
3. In the ntfy app: **+** (subscribe to topic), paste the part after
   `ntfy.sh/`, subscribe.
4. Back in the page, **Alerte de test** → **Envoyer**: the phone shows a
   test alert within seconds.

The topic name works like a password: anyone who knows it can read the
alerts, so do not share it; the page is the only place that shows it. The
server keeps the setting across restarts and upgrades. Messages only name
an app and what happened. What triggers an alert, how long toasts stay and
how to read the logs:
[INSTALL.md](INSTALL.md#logs-toasts-and-phone-alerts).

## Install the Slayer Legend plugin (part 05, optional)

Only if you play Slayer Legend: part 05 holds the page's optional plugins,
and for now its only one, `slayer-legend`, adds a launch button and an
emerald counter option to the page. The game must already be installed from
Google Play and signed in once, in the page. From the workstation (every
plugin):

```sh
packaging/deploy.sh "$SERVER" 05
```

You should see `==> Installing the slayer-legend plugin`, `==> Restarting
the gateway to load plugins (Android keeps running)` and `==> Done; reload
the web page`. Reload the page: cog → **Options** → **Plugins** now shows
**Slayer Legend**. What its options do:
[05 README](../05-plugins/slayer-legend/README.md). To remove one plugin
(or every plugin, without a name):

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/05-plugins/scripts/install.sh --uninstall slayer-legend"
```

You should see `==> Removing the slayer-legend plugin` and the gateway
restarting; reload the page. The plugin's own data is kept until
`uninstall.sh --purge`. More: [05 README](../05-plugins/README.md).

## Adding a second device

Create its tunnel in its WireGuard app or client the same way, with the next
address (`10.20.0.3/32`), then:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/add-peer.sh laptop 'DEVICE_PUBLIC_KEY' 10.20.0.3"
```

Existing devices are not disturbed. Enter the printed `[Peer]` values as in
step 4 (`10.20.0.4` for the next one, and so on). Several devices can watch
the phone at once; Information → Server → **Disconnect** closes the others. To
remove a device:

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/revoke-peer.sh 'DEVICE_PUBLIC_KEY'"
```

## Updating

Pull the new version, rebuild, then stage and install in one command:

```sh
git pull
packaging/build-release.sh
packaging/deploy.sh "$SERVER" 04        # the page and the gateway; Android keeps running (about a minute)
packaging/deploy.sh "$SERVER" 03 04     # also the emulator part
packaging/deploy.sh "$SERVER" 04 05     # add 05 when the plugin is installed, to update it too
```

`deploy.sh` runs `stage-release.sh` and then each part's `install.sh`; it
uses `AS_ROOT` from your terminal and listens on `10.20.0.1` (`LISTEN`
overrides it). Reload the page afterwards: each gateway start issues a new
page token, and a tab opened before it answers 403 to every button until it
is reloaded.

When part 03 restarts Android: only when the new release pins a different
emulator version. The installer then prints `==> Restarting Android on the
new emulator version` and Android reboots, which takes 1 to 2 minutes; the
page shows it and reconnects by itself, and your data is kept. Otherwise it
prints `==> The emulator is already running; Android keeps running`.

If `verify.sh` fails after an update: its `FAIL` line names the check. Read
the logs, restart the gateway, verify again:

```sh
ssh "$SERVER" "$AS_ROOT journalctl -u cloudphone-gateway -n 100"
ssh "$SERVER" "$AS_ROOT systemctl restart cloudphone-gateway"
ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"
```

Still failing: roll back.

## Rolling back

The previous app release is kept next to the current one. Point `current`
back at it and restart the gateway; Android and its data are not involved:

```sh
ssh "$SERVER" "$AS_ROOT ls -t /opt/cloudphone/releases/"
ssh "$SERVER" "$AS_ROOT ln -sfn /opt/cloudphone/releases/PREVIOUS /opt/cloudphone/current"
ssh "$SERVER" "$AS_ROOT systemctl restart cloudphone-gateway"
```

## Backing up the phone

Everything Android stores (Google account, apps, app data) is in
`/var/lib/cloudphone/avd/`. Copy it with Android stopped, straight to the
workstation; it is several GB and takes a few minutes, during which the phone
is off:

```sh
ssh "$SERVER" "$AS_ROOT systemctl stop cloudphone-emulator"
ssh "$SERVER" "$AS_ROOT tar czf - -C /var/lib/cloudphone avd" > cloudphone-avd-$(date +%F).tar.gz
ssh "$SERVER" "$AS_ROOT systemctl start cloudphone-emulator cloudphone-gateway"
```

To restore, stop Android the same way, unpack the archive back into
`/var/lib/cloudphone/` as root, run `chown -R cloudphone:cloudphone
/var/lib/cloudphone/avd`, and start the services again.

## Uninstalling

```sh
ssh "$SERVER" "$AS_ROOT $RELEASE/uninstall.sh"              # keeps the phone's data and the configuration
ssh -t "$SERVER" "$AS_ROOT $RELEASE/uninstall.sh --purge"   # erases the phone permanently
```

The first prints `Cloud Phone was removed. Kept: /var/lib/cloudphone (Android
data) and /etc/cloudphone.`: reinstalling later brings the same phone back.
`--purge` asks you to type `erase`, then deletes the Android data, the
configuration and the `cloudphone` account for good; back up first. Neither
removes WireGuard or the firewall rules.

## Troubleshooting

The page tells you what is wrong. Messages that cover the screen block it;
the others are banners with a close cross. Recent events are in
Information → Server → **Journaux du serveur**, red for errors, each with
what to do next; the **Niveau** filter keeps only warnings and errors. The
same on the server:
`ssh "$SERVER" "$AS_ROOT journalctl -t cloudphone-gateway -p warning"`.
Server commands below go through the same variables as the installation.

| Message on the page | What to do |
|---|---|
| Server unreachable | Switch the phone's WireGuard tunnel on. Right after an Apply in Android settings, it can show for a few seconds while the server follows the new Android: wait. Still there: `ssh "$SERVER" "$AS_ROOT systemctl status cloudphone-gateway"`. |
| Another device took over | Someone pressed Disconnect on another device. Tap `↻` to take the phone back. |
| Changing resolution / Changing Android settings / Android is restarting… | An Apply (screen size, renderer, cores or memory) reboots Android: 1–2 minutes. |
| Android crashed / Restarting automatically… | systemd restarts it; the page reconnects by itself. |
| Android stopped on an error / Android is stopped | It will not come back alone: `ssh "$SERVER" "$AS_ROOT journalctl -u cloudphone-emulator -n 100"`, then `ssh "$SERVER" "$AS_ROOT systemctl start cloudphone-emulator"`. |
| Android is starting… / The server is reconnecting to Android… | Wait; the first boot takes up to 10 minutes. |
| Video interrupted | The page reconnects by itself. |
| The video does not connect | UDP 32768-60999 does not reach the phone: `ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --check"`; some networks block UDP. Tap `↻` to retry. |
| Touches do not reach Android | `ssh "$SERVER" "$AS_ROOT systemctl restart cloudphone-gateway"`, then reload the page. |
| Another device is watching this phone | Information: the image may be slower. Information → Server → Disconnect. |
| Server under heavy load | Information: a lower Resolution or the Lavapipe renderer (Information → Server → Android settings) costs less CPU. |

| Symptom | Fix |
|---|---|
| The page is in the wrong language | cog → Options → *Language*. The page follows the browser's language the first time. |
| Black screen, green LED | The video works; Android itself shows black, usually because its screen is off. Press the power key in the toolbar. |
| Works on Wi-Fi, not on mobile data | That network blocks UDP (WireGuard or the video). Keep *Persistent keepalive* 25; try another network. |
| No *latest handshake* in `wg show` | UDP 51820 blocked (server or provider firewall), or a wrong key or Endpoint in the app. |
| Handshake OK but the page does not load | `ssh "$SERVER" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"` names the failing check. |
| Buttons do nothing after an update | Reload the page: each gateway start issues a new page token. |
| `install.sh` stops at `/dev/kvm is missing` | Enable VT-x/AMD-V, or nested virtualization for a VM. |
| `install.sh` says a port is in use | Another program uses it: choose free ports in `/etc/cloudphone/cloudphone.conf`. |
| A part 01 Check prints `TARGET must use debian or setup-agent`, or closes your terminal | `TARGET` is an alias or has the wrong user: set it to `debian@SERVER_ADDRESS` or `setup-agent@SERVER_ADDRESS`. |
| A script fails with `Permission denied (publickey)` although `ssh` by hand works | The key is not in `ssh-agent`: run `ssh-add`. The scripts use `BatchMode`, which cannot ask for a passphrase. |

More: [`INSTALL.md`](INSTALL.md) (every setting, running next to another
emulator, logs and alerts, the black-box tests), [02 README](../02-wireguard-server/README.md#troubleshooting),
[03 README](../03-android-emulator/README.md#performance) (why the image is
around 20 fps without a GPU).

Agents: see the parts' `AGENTS.md`.
