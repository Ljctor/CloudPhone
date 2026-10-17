# 05 — Final verification

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/03-android-emulator/scripts/verify.sh"
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/verify.sh"
ssh "$TARGET" "$AS_ROOT $RELEASE/04-cloud-phone-app/scripts/firewall.sh --check"
host=${TARGET#*@}
! curl -fsS --max-time 3 "http://$host:${WEB_PORT:-8000}/" >/dev/null 2>&1
```

Set `WEB_PORT` to the instance's port (8000 by default; a test instance on
another host may use another one, 8100 in the examples). Page and API share
that one port. Passes when every command
succeeds: the page answers on the VPN and not on the public address. Runbook 03 and the human part of 04 complete the acceptance.
