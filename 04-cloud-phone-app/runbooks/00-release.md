# 00 — Release on the server

Parts 02–05 run their scripts from the unpacked release on the server.

```sh
: "${TARGET:?setup-agent@SERVER_ADDRESS}" "${RELEASE:?unpacked release directory on the server}"
: "${AS_ROOT:=sudo -n -u master sudo -n}"
```

## Check

```sh
ssh "$TARGET" "cd '$RELEASE' && sha256sum -c --quiet SHA256SUMS"
```

## Apply

From the repository root (build first with `packaging/build-release.sh` if
`dist/` is empty):

```sh
packaging/stage-release.sh "$TARGET"   # prints the directory to use as RELEASE
```

`packaging/deploy.sh "$TARGET" 04` stages and also runs runbook 02's Apply.
