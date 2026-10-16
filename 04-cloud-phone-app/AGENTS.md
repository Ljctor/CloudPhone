# Part 04 — agent instructions: Cloud Phone app

Default task: install the WebRTC streaming gateway and the mobile web page
(`cloudphone-gateway`, which also serves the page), reachable only through WireGuard,
then commission Google Play and the target app with the human.
Prerequisites: parts 02 and 03 converged.

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

- `install.sh` restarts only the gateway and the page; Android keeps running.
  Upgrade = stage a newer release, rerun runbook 02.
- The page has no login: `LISTEN_ADDRESS` must be the WireGuard address and
  the ports open only on `wg0` (runbooks 01, 05).
- Runbooks 03 and 04 need the human. Never handle Google credentials. Never
  install an APK or a third-party store. Never add anything that launches or
  restarts an app automatically.

Developing the app (source overlay, build, test instance loop):
`docs/DEVELOPMENT.md`.
