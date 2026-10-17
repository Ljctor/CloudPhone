# 03 — Human acceptance

No automated Check: ask the human, on a device with WireGuard on, to open
`http://10.20.0.1:WEB_PORT/` (page and API on that one port) and confirm:

1. the Android screen appears within ~10 s, the LED on `↻` is green and no
   message covers the screen;
2. touch and swipe respond, the toolbar keys (back, home, recents, power,
   volume) work; Information → Client (ping/fps block) shows touches going via
   `data channel`;
3. `↻` brings the image back without restarting Android or the foreground app;
4. closing and reopening the tab reconnects.

A message on the screen or a banner names the problem (see
`../../docs/TUTORIAL.md`, "Troubleshooting"). Optional automated browser
test: `docs/DEVELOPMENT.md`, "Browser acceptance test".
