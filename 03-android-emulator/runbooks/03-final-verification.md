# 03 — Final verification

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "$AS_ROOT $RELEASE/03-android-emulator/scripts/verify.sh"
```

Passes on `PASS: Android Emulator is converged`. Continue with part 04.
