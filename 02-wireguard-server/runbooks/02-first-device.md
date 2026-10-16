# 02 — First device

Human + agent step. The device's private key is generated on the device and
never leaves it; only its public key reaches the agent.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT wg show wg0 peers" | grep -q .
```

## Apply

1. Human: in the WireGuard app, **+ → Create from scratch**, generate the key
   pair, address `10.20.0.2/32`; send the **public** key to the agent.
2. Agent, with `PUBLIC_KEY` set to it:

   ```sh
   ssh "$TARGET" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/add-peer.sh phone '$PUBLIC_KEY' 10.20.0.2"
   ```

3. Human: copy the printed `[Peer]` values into the app (Endpoint = the
   server's public name or address), then switch the tunnel on.

More devices: same script, next free address. Revoke with `revoke-peer.sh
PUBLIC_KEY`.
