# Part 05 — Slayer Legend plugin

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Lancer le jeu** | Starts the game and brings it to the battle screen: taps "TAP TO START", then **Confirm** on the "last save time" notice (the latest save). It only runs when you press it, and it taps nothing else: on any other screen (Google sign-in, an update, an event pop-up) it stops and says so. |
| **Réécrire le compteur d'émeraudes** | Covers the emerald counter of the top bar, on this screen only, and writes over it at the game's size for that many digits (6 digits are smaller than 5 or fewer): by default the digits after the comma, leading zeros dropped (`284,086` shows `86`), or the number typed in **Nombre affiché**. Nothing is sent to Android. |

## Install

Part 04 must be installed. From an unpacked release (or a checkout), on the
server:

```sh
sudo 05-slayer-legend/scripts/install.sh
```

or from a workstation: `packaging/deploy.sh SERVER 05`. The script copies
`files/plugin/` to `/opt/cloudphone/plugins/slayer-legend/` and restarts the
gateway (Android keeps running). Reload the page afterwards.
`sudo 05-slayer-legend/scripts/install.sh --uninstall` removes it.

## Files

| File | Role |
|---|---|
| `files/plugin/plugin.json` | id, title, version |
| `files/plugin/page.js` | page side: options, the emerald overlay, the launch button |
| `files/plugin/emerald_mask.js` | finds the emerald counter on the video |
| `files/plugin/gateway.py` | gateway side: `/api/v1/plugins/slayer-legend/launch` and `/emerald-mask` |
| `files/plugin/emerald_mask.py` | Python twin of `emerald_mask.js`, for browsers that cannot read the video's pixels (Firefox on Android); keep the two in step |

The plugin API (what `page.js` and `gateway.py` may use) is described at the
top of `04-cloud-phone-app/src/overlay/js/example/src/plugins.ts` and
`.../gateway/src/videobridge_gateway/plugins.py`.

## Limits

- Screens are recognised from a few pixel areas measured at the page's
  device shape (19.5:9, e.g. 480×1040). Another shape may stop the launch on
  "unexpected screen"; finish it by hand.
- The counter font sizes come from screenshots of the game; a game update
  that changes its top bar can break the emerald rewrite (the panel then says
  "non détecté").
