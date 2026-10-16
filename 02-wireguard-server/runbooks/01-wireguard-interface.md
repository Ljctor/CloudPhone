# 01 — WireGuard interface

`wg0` = `10.20.0.1/24` on UDP 51820, port opened in the host firewall. An
existing `wg0.conf` is kept as is.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/verify.sh --no-peer"
```

## Apply

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/02-wireguard-server/scripts/install.sh"
```

If the hosting provider has a network firewall, the human allows UDP 51820
there too.
