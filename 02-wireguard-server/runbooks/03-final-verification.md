# 03 — Final verification

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/verify.sh"
ssh "$TARGET" "$AS_ROOT wg show wg0 latest-handshakes" | awk '$2 > 0 { ok = 1 } END { exit !ok }'
```

Passes when the first command prints `PASS: WireGuard server is converged` and
at least one device has completed a handshake (its tunnel is on).
