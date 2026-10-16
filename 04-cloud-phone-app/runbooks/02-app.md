# 02 — Gateway and web page

Installs the release under `/opt/cloudphone/releases/` and the services
`cloudphone-gateway` and `cloudphone-web`, bound to the WireGuard address.
Android keeps running.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"
```

## Apply

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/install.sh --listen 10.20.0.1"
```

The same command upgrades the app after staging a newer release.
