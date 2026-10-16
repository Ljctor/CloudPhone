# 04 — Google Play and the target app

Human + agent step. Never put Google credentials in a command, file or chat.

1. Human, in the web page: sign in to Google Play (prefer the prompt or passkey
   on their own phone), disable unneeded sync, install the target app from
   Google Play only (no APK sideloading, no third-party store), launch it.
2. Agent: passive settings so it keeps running (screen always on, Doze and
   standby exemption, time zone). They never launch or restart the app.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```
```sh
: "${APP_PACKAGE:?Android package of the target app, e.g. com.gear2.growslayer}"
: "${TIMEZONE:=Europe/Paris}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT env TIMEZONE=$TIMEZONE $RELEASE/04-cloud-phone-app/scripts/commission.sh --check $APP_PACKAGE"
```

## Apply

```sh
ssh "$TARGET" "$AS_ROOT env TIMEZONE=$TIMEZONE $RELEASE/04-cloud-phone-app/scripts/commission.sh --apply $APP_PACKAGE"
```

Then the human confirms the app runs, its account login works, and it is still
there after `systemctl restart cloudphone-emulator` (Android reboot). Whether
to relaunch the app is always the human's decision: add no watchdog.
