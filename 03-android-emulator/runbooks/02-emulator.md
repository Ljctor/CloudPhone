# 02 — Pinned emulator, AVD and service

Installs the SDK, emulator 36.6.11 (SHA-256 verified), the Android 16 Google
Play image, the AVD `cloudphone` and `cloudphone-emulator.service`, then waits
for Android to boot. Re-running never recreates the AVD.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/03-android-emulator/scripts/verify.sh"
```

## Apply

The Android SDK licences must be accepted by the human. Either the human runs
it in a terminal and answers the licence prompt:

```sh
ssh -t "$TARGET" "$AS_ROOT $RELEASE/03-android-emulator/scripts/install.sh"
```

or, only after the human said they read and accept the licences:

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/03-android-emulator/scripts/install.sh --accept-android-sdk-license"
```

Takes 5–20 minutes (several GB downloaded, first boot). Do not interrupt it.
