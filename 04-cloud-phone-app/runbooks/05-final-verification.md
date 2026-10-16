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
for port in 8000; do
  ! curl -fsS --max-time 3 "http://$host:$port/" >/dev/null 2>&1
done
```

Use the instance's `WEB_PORT` in the last loop. Passes when
every command succeeds: the page answers on the VPN and not on the public
address. Runbook 03 and the human part of 04 complete the acceptance.
