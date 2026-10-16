# Part 02 — agent instructions: WireGuard server

Default task: a WireGuard interface `wg0` (`10.20.0.1/24`, UDP 51820) with
at least one authorized device, its port open in the host firewall.
Prerequisites: part 01 (or any host with an nftables input chain with policy
drop, a root path and outbound internet).

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

- Private keys: a device's key is generated on the device; only its public key
  is handled. Never print `server.key`, `wg0.conf` or a device config holding a
  private key.
- `install.sh` never rewrites an existing `wg0.conf`; peers change only through
  `add-peer.sh` / `revoke-peer.sh` (both back up the file first).
- Firewall changes go through `scripts/nft-allow.sh` only.
- Runbook 02 needs the human (device side).

Done when runbook 03 passes. Next: part 03. Manual setup, ufw and
troubleshooting: `README.md`.
