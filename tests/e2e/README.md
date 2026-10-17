# End-to-end tests

Black-box tests of a running Cloud Phone instance, written in Rust. They
know only what a user's browser reaches: the page and its HTTP and
WebSocket API. They never read the application's code or the server's
files, so they stay valid whatever the implementation language.

```sh
# From a WireGuard peer, or through an SSH tunnel to the page:
#   ssh -N -L 18100:10.20.0.1:8000 USER@SERVER
CLOUDPHONE_URL=http://127.0.0.1:18100/ cargo test
# Also the tests that restart Android (several minutes, closes open apps):
CLOUDPHONE_URL=http://127.0.0.1:18100/ cargo test -- --include-ignored
```

| File | What it checks |
|---|---|
| `tests/page.rs` | the page carries a fresh token, is not cached; its assets are |
| `tests/guard.rs` | POSTs need the page's token; other sites are refused; no CORS |
| `tests/state.rs` | server state and, on request, host, emulator and Android metrics |
| `tests/settings.rs` | renderer, cores and memory: reported, invalid choices refused, a change applied (ignored by default) |
| `tests/display.rs` | screen size reported; invalid sizes refused |
| `tests/stream.rs` | the signalling WebSocket offers a video track |
| `tests/emerald.rs` | the game helper answers with a mask or a reason |

Opening a test stream counts as one more viewer for a few seconds: the
phone shows "another device is watching" meanwhile.
