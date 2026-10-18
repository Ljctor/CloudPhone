# Slayer Legend plugin (part 05)

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Lancer le jeu** (Launch the game), button **Lancer** (Launch) | Starts the game and brings it to the battle screen. It taps exactly three things, each only when the screen shows it: "TAP TO START", **Confirm** on the "last save time" notice (the latest save), and "Press here to finish Power Saving Mode", held 4 s as the game requires (at most 3 times). It only runs when you press it. On any other screen (Google sign-in, an update, an event pop-up) it stops after about 45–60 s with "Écran inattendu : termine le lancement à la main" (Unexpected screen: finish the launch by hand), and in any case after 3 minutes. The status row **Lancement** (Launch) shows where it is. |
| **Écran détecté** (Detected screen) and the farmed stage | While the options panel is open, every 3 s: the game's screen (title, save choice, battle, game menu, Power Saving Mode, other, or another app in front), and the stage being farmed: **Stage farmé** (Farmed stage) with its number and name, **Monstres par vague** (Monsters per wave), **Équipement lâché** (Equipment dropped: weapon or accessory, and grade) and **Couleur des âmes** (Soul colour). The number is read in Power Saving Mode, where the game writes it big; the battle screen's header is too small for the number, but its Roman numeral confirms the stage has not changed (otherwise the row says "à confirmer", to be confirmed). The rest comes from `stages.json`, community data (see below). Read-only: it never taps. |
| **Farmer la mine** (Farm the mine), **Étage à farmer** (Floor to farm), **Zone à farmer** (Area to farm), **Minuteur** (Timer), **Alertes sur le téléphone (ntfy)** | Farms the Closed Mine from the gateway, so it goes on with the page closed. While a fight runs with "Repeat entry" ticked it only watches, every 10 s. When the game is back on the floor list (after 30 entries; there is no end pop-up) it taps the floor (read off the list, scrolling to it), the Area, then always 3 feathers. When the **gold scroll** buff is no longer shown it unticks "Repeat entry" and stops: the entry under way ends, no more feathers are spent; it never relaunches without having seen the gold scroll in the last 5 minutes. **Minuteur** (Timer): buttons +30, +5, +1, −1, −5, −30 minutes, usable while it farms, move when farming stops; once the time is up it unticks "Repeat entry" and does not relaunch. With a timer, a missing gold scroll is only a warning (⚠ in the status row and an alert). **Alertes sur le téléphone (ntfy)**: the gateway posts to `ntfy.sh/<topic>`, a random topic made by this browser and shown as a link; subscribe the ntfy app to it (works with the page closed). Alerts: gold scroll gone, farming stopped (timer, failure), game out of the foreground for 2 minutes. Messages go through the public ntfy.sh service. **Alerte de test** sends one. Power Saving Mode hides the buffs, so it leaves it (4 s press) at most once a minute. The status row **Mine** says what it does. Start the first entry by hand; the options are sent to the gateway when they change and again after a gateway restart. |
| **Compteur d’émeraudes** (Emerald counter) | On this screen only, nothing is sent to Android. **Coupé à la virgule** (Cut at the comma): the comma and what follows are covered with the bar's colour (`284,086` shows `284`). **Réécrit** (Rewritten): the counter is covered and written again at the game's size for that many digits (6 digits are smaller than 5 or fewer), on the game's baseline: by default the digits after the comma, leading zeros dropped (`284,086` shows `86`), or the number typed in **Nombre affiché (vide : après la virgule)** (Number shown (empty: after the comma)), drawn in the game's own pixel font (`emerald_font.js`) and in the colour of the digits it replaces. The status row **Détection du compteur** (Counter detection) says détecté / non détecté (detected / not detected). Stored per browser, like the page's other options. |
| **Compteur de diamants** (Diamond counter) | The same three choices and the same font for the diamond counter, right of the emeralds: **Inchangé**, **Coupé à la virgule**, **Réécrit** with its own **Nombre affiché** field and **Détection du compteur** row. A counter under 1,000 has no comma and is left as it is. |

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
| `emerald_font.js` | the game's counter font at 480 px wide, for the rewritten number |
| `gateway.py` | gateway side: `/api/v1/plugins/slayer-legend/launch`, `/emerald-mask`, `/screen` and `/mine` |
| `mine.py` | the Closed Mine's screens off a screenshot: fight, Repeat entry box, gold scroll, floor list and its numbers, Area and feathers pop-ups |
| `stage.py` | reads the stage number (Power Saving Mode) and the name's Roman numeral (battle screen) off a screenshot |
| `stages.json` | per stage: name, monsters per wave, drop (weapon `W` or accessory `A`) and grade, main soul colour |
| `emerald_mask.py` | Python twin of `emerald_mask.js`, for browsers that cannot read the video's pixels (Firefox on Android); keep the two in step |

The plugin API (what `page.js` and `gateway.py` may use) is described at the
top of `04-cloud-phone-app/src/overlay/js/example/src/plugins.ts` and
`.../gateway/src/videobridge_gateway/plugins.py`.

## Limits

- Screens are recognised from a few pixel areas measured at the page's
  device shape (19.5:9, e.g. 480×1040). Another shape may stop the launch on
  "unexpected screen"; finish it by hand.
- `stages.json` comes from the community wiki slayerlegend.wiki (datamined
  stage table, stages 1–1,360) and, for soul colours, namu.wiki and player
  guides; read 2026-10-18 and not checked in game. Soul colours past stage
  320 are deduced from the green, blue, red cycle every 20 stages: the page
  says "déduite, non vérifiée" (deduced, not checked). Stages above 1,360
  show only their number.
- The counter font sizes come from screenshots of the game; a game update
  that changes its top bar can break the emerald rewrite (the panel then says
  "non détecté").
