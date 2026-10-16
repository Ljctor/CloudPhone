# 01 — VPN-only firewall rules

Accept TCP `WEB_PORT`, `WEB_PORT + 1` and UDP 32768-60999 on `wg0` only.
Requires parts 02 and 03.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --check"
```

## Apply

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --apply"
```
