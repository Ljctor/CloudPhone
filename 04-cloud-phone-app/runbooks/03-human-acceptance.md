# 03 — Human acceptance

No automated Check: ask the human, on a device with WireGuard on, to open
`http://10.20.0.1:WEB_PORT/` and confirm:

1. the Android screen appears within ~10 s, status dot green;
2. touch and swipe respond, the toolbar keys (back, home, recents, power,
   volume) work;
3. `↻` brings the image back without restarting Android or the foreground app;
4. closing and reopening the tab reconnects.

Optional automated browser test: `docs/DEVELOPMENT.md`, "Browser acceptance
test".
