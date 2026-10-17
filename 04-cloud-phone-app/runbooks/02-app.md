# 02 — Gateway and web page

Installs the release under `/opt/cloudphone/releases/` and the service
`cloudphone-gateway`, which serves the page and the API on one port
(`WEB_PORT`), bound to the WireGuard address. Android keeps running.

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

The same command upgrades the app after staging a newer release. From a
checkout, `packaging/deploy.sh "$TARGET" 04` does runbook 00's Apply and
this Apply in one step (it uses `AS_ROOT`, and `LISTEN` instead of
10.20.0.1).
