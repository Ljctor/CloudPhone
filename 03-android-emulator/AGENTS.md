# Part 03 — agent instructions: Android Emulator

Default task: Google's Android Emulator 36.6.11 (pinned, SHA-256 verified)
with an Android 16 Google Play device, running headless as
`cloudphone-emulator.service` under the `cloudphone` account.
Prerequisites: part 01, an x86-64 host with KVM, 4 cores, 6 GiB RAM, 15 GiB
disk.

Variables, set once in the operator shell:

```sh
export TARGET=setup-agent@SERVER_ADDRESS
export RELEASE=/var/tmp/cloudphone-release/cloudphone-VERSION-linux-x86_64   # printed by stage-release.sh
export AS_ROOT='sudo -n -u master sudo -n'   # privilege path set up by part 01; plain 'sudo -n' elsewhere
```

For each runbook in `runbooks/`, in lexical order: run **Check**; if it
fails, run **Apply** once, then the same **Check** again; stop and report at
the first Check that still fails. Never infer state from chat, notes or Git
history: the server is the only source of truth (`../docs/METHOD.md`).

Rules:

- The Android SDK licences are accepted by the human: either they run the
  Apply in a terminal, or they state they accept and you pass
  `--accept-android-sdk-license`.
- Never delete or recreate `/var/lib/cloudphone/avd`: it holds the Google
  account, apps and their data. Re-running `install.sh` keeps it and does not
  restart a running Android unless the pinned emulator version changed.
- Another emulator or adb server on the host: write
  `/etc/cloudphone/cloudphone.conf` with free ports before installing
  (`README.md`). Do not run adb on a port the installer is about to check.
- Do not restart the emulator to fix a display problem; restart
  `cloudphone-gateway` instead (part 04).

Done when runbook 03 passes. Next: part 04. Settings and operations:
`README.md`.
