# Slayer Legend plugin (part 05)

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Lancer le jeu** (Launch the game), button **Lancer** (Launch) | Starts the game and brings it to the battle screen. It taps exactly three things, each only when the screen shows it: "TAP TO START", **Confirm** on the "last save time" notice (the latest save), and "Press here to finish Power Saving Mode", held 4 s as the game requires (at most 3 times). It only runs when you press it. On any other screen (Google sign-in, an update, an event pop-up) it stops after about 45–60 s with "Écran inattendu : termine le lancement à la main" (Unexpected screen: finish the launch by hand), and in any case after 3 minutes. The status row **Lancement** (Launch) shows where it is. |
| **Réécrire le compteur d’émeraudes** (Rewrite the emerald counter) | Covers the emerald counter of the top bar, on this screen only, and writes over it at the game's size for that many digits (6 digits are smaller than 5 or fewer): by default the digits after the comma, leading zeros dropped (`284,086` shows `86`), or the number typed in **Nombre affiché (vide : après la virgule)** (Number shown (empty: after the comma)). The status row **Compteur d’émeraudes** (Emerald counter) says détecté / non détecté (detected / not detected). Nothing is sent to Android. The option is stored per browser, like the page's other options. |

## Install

Part 04 must be installed, and the game installed from Google Play and
signed in once by hand, in the page: the plugin only taps, it never installs
anything or logs in. From an unpacked release (or a checkout), on the
server:

```sh
sudo 05-plugins/scripts/install.sh slayer-legend   # or no name: every plugin
```

or from a workstation: `packaging/deploy.sh SERVER 05`. The script copies
this directory (except this README) to `/opt/cloudphone/plugins/slayer-legend/` and restarts the
gateway (Android keeps running). Reload the page afterwards.
`sudo 05-plugins/scripts/install.sh --uninstall slayer-legend` removes it.

Check: `curl http://10.20.0.1:<WEB_PORT>/api/v1/plugins` lists
`slayer-legend`. If it does not, the load error is in
`journalctl -u cloudphone-gateway`. Upgrading part 04 keeps the plugins; the
release's `uninstall.sh` removes them with the rest of `/opt/cloudphone`.

## Files

| File | Role |
|---|---|
| `plugin.json` | id, title, version |
| `page.js` | page side: options, the emerald overlay, the launch button |
| `emerald_mask.js` | finds the emerald counter on the video |
| `gateway.py` | gateway side: `/api/v1/plugins/slayer-legend/launch` and `/emerald-mask` |
| `emerald_mask.py` | Python twin of `emerald_mask.js`, for browsers that cannot read the video's pixels (Firefox on Android); keep the two in step |

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
