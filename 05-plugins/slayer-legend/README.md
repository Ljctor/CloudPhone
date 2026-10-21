# Slayer Legend plugin (part 05)

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Lancer le jeu** (Launch the game), button **Lancer** (Launch) | Starts the game and brings it to the battle screen. It opens the game as Android's launcher does (never killing it) and taps exactly four things, each only when the screen shows it: "TAP TO START", **Confirm** on the "last save time" notice (the latest save), **Close app** on Android's "Slayer Legend keeps stopping" dialog (found by uiautomator, at most twice, then the game is opened again), and "Press here to finish Power Saving Mode", held 4 s as the game requires (at most 3 times). It runs when you press it, or as the watchdog's relaunch (below). On any other screen (Google sign-in, an update, an event pop-up) it stops after about 45–60 s with "Écran inattendu : termine le lancement à la main" (Unexpected screen: finish the launch by hand), and in any case after 3 minutes. The status row **Lancement** (Launch) shows where it is. |
| **Écran détecté** (Detected screen) and the selected stage | While the options panel is open, every 3 s: the game's screen (title, save choice, battle, game menu, Power Saving Mode, other, or another app in front), and the stage being farmed: **Stage sélectionné** (Selected stage) with its number and name, **Monstres par vague** (Monsters per wave), **Équipement lâché** (Equipment dropped: weapon or accessory, and grade) and **Couleur des âmes** (Soul colour). The number is read in Power Saving Mode, where the game writes it big; the battle screen's header is too small for the number, but its Roman numeral confirms the stage has not changed (otherwise the row says "à confirmer", to be confirmed). The rest comes from `stages.json`, community data (see below). Read-only: it never taps. |
| **Mode** | What the game is set to do: the **Mode par défaut** (Default mode: **Farming mpw18** unless set to **Farming mpw4** or **Jeu libre**; never the mine; saved on change, mpw4 offered once its stage is chosen, the gateway refusing it before too), or for a time another one of **Farming mpw18**, **Farming mpw4**, **Jeu libre** (Free play: nothing is touched) or **Mine fermée** (Closed Mine, below). The default mode has no timer. When the timer (**Temps restant**, Time left, buttons +30 … −30 minutes) ends, or the mine ends, it goes back to the default mode by the same switch (« Minuteur écoulé : retour au farming mpw4 (stage 925) »). Changing the default does not change the mode running. Over the screen, under the player's level (top left), the selected mode is written in the gold counter's pixel font, with `MISE EN PLACE...` under it while the gateway sets the mode up, and `(DEFAUT)` or the time left below (only there: the game's top bar holds the gold rate, below), while the battle screen shows. A timed mode starts with 30 minutes on its timer. Each mode has its row: a radio button before its name chooses it, and **Configurer** (Configure) opens its settings in a dialog over the panel (**Jeu libre** has nothing to configure, so no button). **Farming mpw4** can be chosen only once its stage is set, **Mine fermée** only once its floor and area are set (greyed out until then; the gateway refuses them too). During free play the game may be open on another device; nothing is checked or alerted then. While **Farming mpw4** runs, the gateway looks for the **gold scroll** buff every 30 s on the battle screen (the mine's own check, `gold_scroll.py`; other screens, Power Saving Mode included, tell nothing); missing on 2 looks in a row, the status row **État** (State) ends with ` ⚠ plus de parchemin doré` (no gold scroll) and, with the phone alerts on, one alert says so; one more says « parchemin doré rétabli » (gold scroll back) once it is seen again, and only then can a new absence alert. `GET /mode` gives it as `gold` (true, false, or null: unknown or another mode). **Stage mpw18** / **Stage mpw4** list only the stages with 18 or 4 monsters per wave up to the highest stage the gateway has seen farmed (read in Power Saving Mode, kept in the plugin's data directory; all of them while none is known), as colour dot, mpw and number. The **Farming mpw18** and **Farming mpw4** dialogs also hold that mode's loadout: **Préréglage de combat** (Battle settings preset, I to V), **Soul Weapon** and **Gravure** (its engraving: a variant of the user's sheet, Atk, Balanced or Crit, or Gold-maxed / Gold-balanced, see below), its grid drawn read-only (fixed-size cells: the pieces in colour, an outlined cell left empty, nothing where the grid has no cell). Each choice is saved on change, half a second after the last one, with no button (`POST /loadout`, only the fields chosen in that browser); a refusal is a toast. The gateway keeps them in `state.json` with the mode's stage (`loadouts`). When **Farming mpw18** or **Farming mpw4** starts (chosen, or back as the default at the end of a timer), the gateway brings the game there by itself, in the background, under the shared lease (holder `stage_change`; while you played in the last minute or another holder has it, it waits for its next look, every 10 s). Each part has a switch, `GET /farming` / `POST /farming` `{stage_change, preset, auto}`, `"real"` or `"plan"`, kept in `state.json`: **plan by default**, the plan is written to the log and nothing is tapped; each is turned to real after a first run watched with you. The AUTO gear itself stays plan-only even when its switch is real, until a real capture with AUTO off has recalibrated its reading. Once real: it closes the bottom panel open (its own tab again), opens the stage map (« Select Region »), goes to the stage's region with the banner's arrows and to its row by scrolling, taps **Move** on the row whose name it read as that stage (the game's pixel font, `pixel_font.py`, `stage_select.py`), and reads the stage's name on the battle screen afterwards; then it chooses the loadout's **Préréglage de combat** in « Battle settings » (through the badge the arrow on the right edge unfolds, checked by its frame and on the badge) and makes sure **AUTO** is on (the gear spins on two screenshots a moment apart; it is tapped only when it reads still, `battle_controls.py`). Any step that does not show what it expects stops it; the switch is tried again from the start after 2, 4, 8, then 16 s while within 60 s of its trigger, and only then « Passage au stage N (mpwM) arrêté : … » names the step in **État** with one alert (the État row is back to farming once the watchdog sees the mode farm). Before stopping on a screen it does not know it waits up to 4 s for it to pass, and it leaves Power Saving Mode by its hold. Once set up, one notification says how long it took since the mode was chosen, the wait for the lease included: « Farming mpw18 prêt en 34 s » (with the slowest step when over 60 s). A change of the running farming mode's loadout (its stage, preset or soul weapon, saved from its dialog) is applied at once the same way, logged « loadout mpw18 changed → applied in N s » and notified « Configuration mpw18 appliquée en 21 s »; the soul weapon alone runs only its own step. Only the regions whose 20 stages share one name are reached this way (stages 561–580 and from 601 on, `stages.json`). Last, once AUTO is on (so that a slow step never delays farming), it equips the loadout's **Soul Weapon** (`features/soul_weapon.py`, `soul_weapon.py`): Equipment, the Weapon tab, the Soul Weapon icon; it picks cells in the list and reads the card's name (the game's pixel font, matched against the 89 names with a margin), scrolls the list, and taps the orange **Equip** tag only when the card reads that weapon, owned, and the tag reads Equip; afterwards the tag must read **Unequip** (never tapped: the guard refuses it). Then its **engraving** (`features/engraving_setup.py`, `engraving_screen.py`): the card's big icon, the title and the weapon's name checked; first every card whose padlock reads open is locked (a padlock not read is never tapped), then the highest-level cards of each shape the variant needs are dragged onto empty cells (only in their own orientation: turning a piece or taking one out is not learnt yet and is alerted, not guessed); the weapon is « prête » only once the grid is the variant's with those cards and all 8 cards read locked; otherwise one alert « … Gravure de <arme> (<variante>) pas prête : … ». Change, the gear and % are never touched. When it placed or locked something, one notice « Soul Weapon <arme> (<variante>) prête … » with its duration (said when over 60 s). Its switch `soul_weapon` (`POST /farming`) is real by default, `"off"` an emergency stop; after a check found it ready it is skipped while neither a relaunch nor an input of yours came since, and the watchdog's relaunch runs it once more. A failure is one alert « … Soul Weapon : <step> ». |
| The watchdog, at the end of the mode's **État** (State) row | It checks that the game does what the selected mode says, with no option rows of its own: its last look ends the mode's **État** row (« Farming mpw18 au stage 920 · OK », « · relance du jeu dans 4 min » with a **Réessayer** (Retry) button inline while a repair backs off, « · bail : agent (réglages) » while someone outside the plugin holds the shared lease). **Farming mpw18** and **Farming mpw4** are checked alike, each with its own loadout (stage, Battle settings preset, AUTO); **Mine fermée**'s screens are the mine's own; the game gone, crashed, not in front or back on its title screen is relaunched with the same backoff (an alert after 2 minutes), then the mine feature goes back in by its own way (Adventure, Dungeon, Closed Mine, then the floor, Area and feathers, tried again within a minute). While the Adventure and Dungeon screens are not calibrated on a capture it taps nothing there: the mine ends and the mode goes back to the default one, with one alert « Mine fermée arrêtée : retour dans la mine impossible (…), retour au farming mpw18 (stage 920) ». Out of feathers (read on the feathers pop-up, once calibrated) the same: « Mine fermée arrêtée : plus de plume, retour au farming mpw18 (stage 920) »; **Jeu libre** is not checked; a mode's entry (its stage change running under the lease) is waited for. Every alert names the mode (« Farming mpw4 : mauvais stage, pas le 915 »). The gateway looks at the game every 15 s: adb, Android's crash dialog, the game's process and focus, then the screen (battle or Power Saving Mode is farming; on the battle screen the stage read is compared with the mode's). A problem seen on 2 looks in a row is one warning with a phone alert (an unknown screen: after 4 looks, 60 s), and « rétabli » once the game has farmed 4 looks in a row (5 minutes when a repair was made); the same problem again within 30 minutes of its last phone alert is logged without a new one. On Android's « Slayer Legend isn't responding » dialog it taps **Wait** once and alerts if the dialog stays (never **Close app**, which would kill the game). When the game is not running, not in front, crashed, or back on its title or save screen, it **relaunches** it (the launch above; on the sign-in screen, « Sign in with Google » once and the one account), so that farming is back within about a minute. On the battle screen the stage is read whole (region and numeral); a wrong stage or Battle settings preset is repaired with the stage change above, and AUTO read off (the gear still, read on one unfold of the right edge's controls at most every 5 minutes, whoever watches the screen) with its AUTO step, only as a plan while its switch says so. Each kind of repair backs off on its own after a real failure (still there at the next look, its sequence stopped, or back before a durable recovery): 1, 2, 4, 8, 16, then 30 minutes between attempts, never for good; alerts at the first failure, at 8 and at 30 minutes, then « rétabli »; **Réessayer** starts the waiting ones over. A game menu open over a minute and the soul weapon are alerts only for now. In the 5 minutes after free play ended, another screen is likely « connected on another device » or a choice of saves (not mapped yet): one alert after 2 looks, for you to do by hand. A touch or key of yours pauses it a minute; while someone else holds the shared lease (`POST /lease`) its repair is deferred. After a gateway restart its first 2 looks only observe. `GET /watchdog` gives the mode checked, its line, the kinds waiting, its counters (looks, bad looks in a row, alerts, the next attempt per repair backing off), the lease and the profile (the mode's stage and loadout from `GET /loadout`). |
| Mode **Mine fermée**: **Étage à farmer** (Floor to farm), **Zone à farmer** (Area to farm) | Farms the Closed Mine from the gateway, so it goes on with the page closed. While a fight runs with "Repeat entry" ticked it only watches, every 10 s. When the game is back on the floor list (after 30 entries; there is no end pop-up) it taps the floor (read off the list, scrolling to it), the Area, then always 3 feathers. When the **gold scroll** buff is no longer shown it unticks "Repeat entry" and stops: the entry under way ends, no more feathers are spent; it never relaunches without having seen the gold scroll in the last 5 minutes. **Minuteur** (Timer): buttons +30, +5, +1, −1, −5, −30 minutes, usable while it farms, move when farming stops; once the time is up it unticks "Repeat entry" and does not relaunch. With a timer, a missing gold scroll is only a warning (⚠ in the status row and an alert). With the Cloud Phone's phone alerts on (cog → Options → **Alertes sur le téléphone**), it alerts when the gold scroll goes, when farming stops (timer, failure) and, through the watchdog (the one owner of that alert), when the game has left the screen for 2 minutes. Power Saving Mode hides the buffs, so it leaves it (4 s press) at most once a minute. The status row **Mine** says what it does. Start the first entry by hand; the options are sent to the gateway when they change and again after a gateway restart; a value this browser does not have (a stage, the floor, the area) is left out and the gateway keeps its own. The gateway also keeps the mode, its timer and the mine's floor, area and timer in `/var/lib/cloudphone/plugins/slayer-legend/state.json`: after a gateway restart (an upgrade, an emulator restart) farming goes on, page open or not. |
| **Gold par seconde** (Gold per second), **Overlay gold/s** (Gold/s overlay) | The gateway reads the gold counter ("111F" under the stage name) every 10 s while the game is in front, and takes the slope of the last 5 minutes of readings (from the second reading on, marked `~` until 5 minutes are there); only readings on the same stage count: at each reading, counter shown or not, the gateway checks where the game is (the battle screen's stage name line must look the same, Power Saving Mode must show the same stage number), and two checks in a row on another stage, another place, another screen or another app start the window again; spending gold starts it again too. Power Saving Mode hides the counter: no reading then. The rate is written in game notation (`2.70E/S`: 3 digits and the unit letter, `~` before it while partial, `...` before the first reading) in the game's top bar, right of the player's name and before the emeralds, in the counter's own pixel font (served by the gateway from `gold.py`) at the size of the mode's lines, in orange gold; it is not shown, nor are the mode's lines, while the counter has not been read for 25 s. **Masqué** (Hidden) removes it. |
| **Navigation**: **Enregistrer mes parcours** (Record my paths), **Activé** (On, the default) or **Désactivé** (Off) | While on, each touch you make on the game (tap, long press or swipe) is sent to the gateway, which notes the game's screen just before it and 2 s after it (or just before your next touch), and builds from them, as you play, a graph of the game's screens and of the touches leading from one to the other. A screen is kept as its detected name and a 12×26 grey thumbnail, never as a screenshot (one may show your account); nothing is recorded while another app is in front. The plugin never replays these touches. The status row **Parcours enregistrés** (Recorded paths) gives the counts, "N écrans, M appuis" (N screens, M taps). Stored on the server in `/var/lib/cloudphone/plugins/slayer-legend/trace.json` (at most 500 screens and 5,000 distinct touches; delete the file to start again). The graph is at `GET /api/v1/plugins/slayer-legend/trace/graph`. |
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
this directory (except this README and the tests) to `/opt/cloudphone/plugins/slayer-legend/` and restarts the
gateway (Android keeps running). Reload the page afterwards.
`sudo 05-plugins/scripts/install.sh --uninstall slayer-legend` removes it.

Check: `curl http://10.20.0.1:<WEB_PORT>/api/v1/plugins` lists
`slayer-legend`. If it does not, the load error is in
`journalctl -u cloudphone-gateway`. Upgrading part 04 keeps the plugins; the
release's `uninstall.sh` removes them with the rest of `/opt/cloudphone`.

## Files

Both sides are split by feature: one module per feature, each a function
of its ports (gateway side) or of the page API (page side) returning its
routes and background tasks, or its options and overlay hooks; `gateway.py`
and `page.js` only wire them together. A feature's rules (mode switching,
timers, the mine's stop conditions, the gold window, the launch's presses)
are a pure module beside it, `features/<feature>_rules.py`: state goes in,
a decision comes out.

| File | Role |
|---|---|
| `plugin.json` | id, title, version, plugin API (`api`) |
| `gateway.py` | gateway side: builds the ports and wires the features of `features/`; its docstring lists each route under `/api/v1/plugins/slayer-legend/` with the feature serving it |
| `features/ports.py` | the ports the features get from the gateway's context: screenshots (with `max_age`), analysis, tap, hold and swipe (each through the guard of `nav.py`, refused otherwise, and only under the shared lease), the lease (`Lease`: one holder at a time, a reason, a time to live of at most 15 minutes renewed by its holder, released by its holder only, its expiry logged as a warning; a user input stops every holder but the user's own press for a minute), whether the game is in front or running, starting it (the launch only), alerts, the clock, `state.json` |
| `features/lease.py` | `GET`/`POST`/`DELETE /lease`: the shared lease for a holder outside the plugin (`{holder, reason, seconds}`, the page token needed): while it holds it, the launch, the mine and the watchdog do not tap |
| `features/counters.py` | `GET /emerald-mask`: a counter's mask off a screenshot, for browsers that cannot read the video |
| `features/screen.py`, `screen_rules.py` | `GET /screen`, `GET /stages`: the screen and stage shown, the highest stage seen farmed |
| `features/launch.py`, `launch_rules.py` | `GET`/`POST /launch`: the launch, on the user's press or as the watchdog's relaunch |
| `features/watchdog.py`, `watchdog_rules.py` | `GET /watchdog`: the watchdog's looks at the selected mode, alerts and repairs; its symptom → repair table and timings are at the top of `watchdog_rules.py` |
| `features/trace.py` | `GET`/`POST /trace`, `GET /trace/graph`: the user's own taps, with the screen before and after each |
| `features/gold.py`, `gold_rules.py` | `GET /gold`, `GET /gold-font`: gold per second, and which readings count |
| `features/mine.py`, `mine_rules.py` | `GET`/`POST /mine`, `POST /mine/timer`: the Closed Mine's farming loop, its stop pass after a restart and the passive watch after it |
| `features/mode.py`, `mode_rules.py` | `GET`/`POST /mode`, `POST /mode/timer`: the mode, its timer and its end (a `POST /mode` without `until` keeps the timer, `until: null` clears it); its stages are the loadouts' (`features/engraving.py`) |
| `features/timer_rules.py`, `values.py` | the timers' arithmetic (mode and mine); the checks of values read back from `state.json` |
| `screens.py` | the game's main screens off a screenshot (title, save notice, battle, menu, Power Saving Mode, other) and where the plugin's own taps and hold go on them |
| `stage.py` | reads the stage number (Power Saving Mode) and the name's Roman numeral (battle screen) off a screenshot |
| `gold.py` | the gold counter off a screenshot: its glyphs, its unit letter (A is a thousand, B a thousand A…), and the rate's notation |
| `mine.py` | the Closed Mine's screens off a screenshot: fight, Repeat entry box, gold scroll, floor list and its numbers, Area and feathers pop-ups |
| `emerald_mask.py` | Python twin of `emerald_mask.js`, for browsers that cannot read the video's pixels (Firefox on Android); keep the two in step |
| `trace.py` | the navigation trace: screen signatures (name and grey thumbnail), the graph of screens and taps, its JSON file; the buttons never to press (`FORBIDDEN`) |
| `navigation.json` | the game's screens and every known way out of each (tap, area, hold, swipe or key), allowed or forbidden with the reason (Breakdown, Change, diamonds, Black Orb, equipment overwrites, raids and recipes in Dragon Valley, Promotion dice…) |
| `nav.py` | the guard: every tap, hold and swipe of the plugin names the screen it recognised and the move it wants, and is refused unless it is an allowed move of that screen landing where the move is and on no forbidden move (deterministic, refused by default) |
| `engravings.json` | per soul weapon (by id, the game's order): its engraving grid's active cells, the user's variants (Atk, Balanced, Crit) as pieces with shape, rotation and cells, the gold layout, the completion effect; see **Soul Weapon engraving data** below |
| `features/engraving.py` | `GET /engravings`, `GET /engraving?id=N`, `GET`/`POST /loadout`: the patterns and their variants, and each farming mode's loadout: its stage, Battle settings preset and soul weapon with its variant (by id), kept in `state.json` (`loadouts`), the one place of the mpw18 and mpw4 stages (`POST /mode` sets them there, `GET /mode` reads them back) |
| `features/soul_weapon.py`, `soul_weapon_rules.py` | the soul weapon step of a mode change (after AUTO) and after a watchdog relaunch: the sequence, its cache and its switch; the rules choose select, scroll, Equip, done or fail on what the screen shows (at most 10 moves) and learn which way the list runs (kept in `state.json`, `soul_weapon`) |
| `soul_weapon.py` | the Soul Weapon screen off a screenshot: its title, the card's name and Owned, the list's cells and selection, its Equip / Unequip tag, the Equipment tab, the card's badge |
| `engraving_screen.py` | the Soul Weapon Engraving screen off a screenshot (calibrated at 480x1040, 5x5 grids): its title and weapon name, the grid's cells and pieces, each of the 8 cards' shape, level, padlock, E (placed) and stat icon |
| `features/engraving_setup.py`, `engraving_setup_rules.py` | the engraving step after the equip: locks first, the highest-level cards dragged onto empty cells, ready only when the grid is the variant's and all 8 cards read locked; the rules choose the cards, the locks and the drags and name what is left for the alert |
| `features/engraving_rules.py` | the engraving's rules: rotations, the pieces a variant needs and whether they are there (and the alert when not), the gold layout's search, placement checks, lookups by name and id |
| `stages.json` | per stage: name, monsters per wave, drop (weapon `W` or accessory `A`) and grade, main soul colour |
| `page.js` | page side: assembles the page features below, starts them, shows their options in the panel's order, hands them the settings and disposes of them |
| `page_screen.js` | the "Jeu" section's screen and stage rows |
| `page_launch.js` | the **Lancer le jeu** button and its status row |
| `page_mode.js` | the "Mode et farming" section; its overlay hook: the mode's lines over the game (`MISE EN PLACE...` while it sets up, a timed mode's time left under its name) |
| `page_engraving.js` | in the **Farming mpw18** and **Farming mpw4** dialogs of `page_mode.js`: the mode's loadout (Battle settings preset, soul weapon, engraving variant), the variant's grid drawn read-only and the pieces it needs, **Enregistrer** (Save). A selector this browser never touched shows the saved value, and **Enregistrer** sends only what was chosen here: a field left out keeps the saved one |
| `page_gold.js` | the "Gold" section, the gold rate in the game's top bar, and the label over the game, top left: the features' overlay lines, under the same condition |
| `gold_text.js` | writes text in the gold counter's pixel font (from `GET /gold-font`) |
| `page_trace.js` | the "Navigation" section: sends the user's taps to the trace |
| `page_watchdog.js` | the watchdog's end of the mode's « État » row, and « Réessayer » |
| `page_counters.js` | the "Émeraudes" and "Diamants" sections |
| `counter_rewrite.js` | finds a counter on the video (or asks the gateway) and cuts it or writes over it |
| `emerald_mask.js` | finds the emerald counter on the video |
| `emerald_font.js` | the game's counter font at 480 px wide, for the rewritten number |
| `test_nav.py` | the graph is consistent; the guard lets the plugin's own actions through and refuses the forbidden ones (`python3 -m unittest test_nav`) |
| `test_watchdog.py` | the watchdog's rules on virtual time: timings, alerts said once, caps, the lease, a gateway restart, the profile, after a mode's end, one scenario per mode; its Wait on the ANR dialog (`python3 -m unittest test_watchdog`) |
| `test_screens.py` | `screens.classify` on synthetic screenshots drawn from the areas it reads (`python3 -m unittest test_screens`) |
| `test_trace.py` | tests of `trace.py` on synthetic screenshots (`python3 -m unittest test_trace`) |
| `test_engraving.py` | `engravings.json` is well formed and its variants fill their patterns; rotations, the gold layout, the pieces needed (`python3 -m unittest test_engraving`) |
| `test_soul_weapon.py` | the Soul Weapon readers on crops of real captures (`fixtures/sw_*`; the tag's own capture test is skipped until one exists), its rules, and the sequence on a scripted game through the guard, the engraving setup included (`python3 -m unittest test_soul_weapon`) |
| `test_engraving_screen.py`, `test_engraving_setup_rules.py` | the engraving screen's readers on crops of one real capture (`fixtures/eg_*`) and the setup's rules on its readings (`python3 -m unittest test_engraving_screen test_engraving_setup_rules`) |
| `test_mine.py` | the mine on a scripted game, on virtual time, through the guard: an untick that will not take, the mine turned off and on in one tick, its taps waiting for the lease (a user input, an outside holder), the lease's routes and expiry, the free-play warning (`python3 -m unittest test_mine`) |
| `test_switch.py` | a mode switch on virtual time with the phone's step latencies: under 60 s from a radio change, the timer's end switching back on time with no watchdog, the lease's wait said apart, one alert over budget (`python3 -m unittest test_switch`) |

The tests run in this directory and are not installed, nor is this README.

The plugin API (what `page.js` and `gateway.py` may use) is described at the
top of `04-cloud-phone-app/src/overlay/js/example/src/plugins.ts` and
`.../gateway/src/videobridge_gateway/plugins.py`.

## Soul Weapon engraving data

`engravings.json` holds, for every soul weapon (ids 1–89, in the game's
order; stage = 320 + 20 × (id − 13)), the cells of its engraving grid and
the ways to fill them. Weapons 1–12 have no engraving (it unlocks at
Pride); they are listed with `grid: null` so that a lookup by name never
fails silently.

- **Variants** (`source: "user-sheet"`): the user's own sheet of complete
  engravings, one per weapon and goal (**Atk**, **Balanced**, **Crit**),
  read from its pixels: each piece's shape (the 7 tetrominoes L, J, T, O,
  I, S, Z), rotation and cells. The sheet's colours only tell the pieces
  apart. Every variant covers the weapon's cells exactly.
- **Gold**, computed when the file is built, never by hand, in two
  variants beside the sheet's: **Gold-maxed**, the most 1×4 bars (the I
  piece, which gives gold) the grid holds, the rest left empty (ties go to
  the lexicographically smallest list of bars); **Gold-balanced**, a
  complete filling with as many bars as a complete filling can hold
  (`bars`; `max` is Gold-maxed's count, which it may not reach), its other
  pieces as close as can be to the weapon's Balanced mix of shapes, then
  the same tie-break; absent (`balanced: null`) when no complete filling
  exists. Both are given with rotation (horizontal and vertical
  bars) and without (vertical only).
- **Rotation**: `"rotation": "per-piece"`. In game, the unequipped
  pieces seen were all L in one orientation, with no control to turn
  them: a piece keeps the orientation it dropped with, and pieces drop
  in every orientation. Layouts therefore hold pieces in any
  orientation (the gold variants are the ones with rotation, every grid
  has a Gold-balanced: Vision's holds 2 bars, as no complete filling
  holds Gold-maxed's 3), every variant is placeable, and the inventory
  is counted by shape and orientation (`"L:1"`, `needed_oriented`;
  `feasible()` against the oriented pieces owned is the check before
  placing). With `null` (not confirmed) the gold variants would be the
  ones without rotation and a variant turning pieces not placeable;
  47 of the 77 grids cannot be filled exactly without turning any
  (`tileable_without`). Pieces are never mirrored. A sheet variant needs its
  pieces in the orientations it uses, and the gold variants are
  fitted to the pieces owned (`fit_gold_maxed`: the most bars of the
  orientations owned, from the layouts kept in `gold.per_piece`;
  `fit_gold_balanced`: the first complete filling with bars of
  either orientation, vertical only or horizontal only that the
  pieces cover, else the alert). Nothing is searched at run time.
- **Seen in game**: Ambition with 4 I bars equipped filling its grid,
  as Gold-maxed's count (its `note`; only vertical bars fit four
  there). Not `verified_in_game`: the cells were not compared yet.
- **Cross-check and completion effects**: the community wiki
  slayerlegend.wiki, from its repository
  https://github.com/BenDol/SlayerLegendWiki (no licence: its files are
  not copied here, only facts re-encoded in this file's own format). Its
  grids transcribed from screenshots (ids 13–54) and its players'
  submissions (ids 55–81) agree with the sheet wherever they exist
  (`wiki_check`, `"none"` when the wiki has no grid). Content (id 79) and
  Echo (id 80) are `"community-differs"`: their only submissions are
  junk; check them in game first, nothing is placed on them before they
  are `verified_in_game`. The completion effect (ATK %, HP %), the soul colour
  and the shapes' stats come from it alone. The wiki gives no soul colour
  for the last 8 weapons (ids 82–89): theirs follow the green, blue, red
  cycle by id that the 81 others keep (27 of each) and are marked
  `colour_deduced`; the page shows every weapon's colour without saying
  which are deduced, and of the data's confidence it only warns
  « grille à vérifier en jeu d’abord » on Content and Echo. The later weapons' names
  follow the sheet; the wiki's older names are kept as `aliases`.
- **Trust**: nothing is checked in game yet (`verified_in_game: false`).

Before the plugin places anything (`features/engraving_setup.py`), it
reads the grid on the engraving screen from pixels and compares the shape
of its active cells with the pattern's `cells`; the weapon's name is read
too and must be the target's. A mismatch blocks with an alert and places
nothing. It also reads the 8 pieces (shape, level, padlock, E); if the
chosen variant needs pieces that are not there, it alerts with what is
missing.

## Sign-in after a relaunch

The game may ask to sign in again (its sign-in screen: "Sign in with
Google" above "Sign in with Apple"). The launch taps "Sign in with Google"
once per launch (Apple's button is forbidden), then, on Google's own
account chooser (read by uiautomator), the account only when exactly one
is listed and only when the launch's tap opened it, then the save notice's
Confirm. The sign-in screen back after the tap, or a chooser with none or
several accounts: one alert, finish by hand.

First check in game (2026-10-21, the real phone): a relaunch ended on the
sign-in screen; the next launch went sign-in → "Sign in with Google" →
(the account) → save notice → battle, and the watchdog read "OK (stage
920)".

Hypothesis, not checked: the watchdog's « une autre application est au
premier plan » that night, right after the gateway's start, was Google's
own window (com.google.android.gms, the Play Games prompt) once the game's
Google session was lost; its relaunch then ended on the sign-in screen.
Since then a Google window in front is the sign-in path (symptom sign_in,
the relaunch's), another app counts only after 2 looks in a row, and the
away record names the window in front.

## Mode switch

A mode switch (a radio change on the page, or the end of the mpw4, free
play or mine timer back to mpw18) brings the battle screen to the target
stage, its preset and AUTO on in under 60 s of the plugin's own time
(`SWITCH_BUDGET`), the plugin alone. It starts at its trigger: POST /mode
starts it at once, and the timed mode's watch wakes right at the timer's
end (`next_look`), not at the watchdog's next look. Each step waits for its
screen by polling fresh captures (`settle`: every 0.25 s, at most 4 s, 8 s
for a stage to load), never a fixed long sleep; the fixed waits left are
the controls' own (0.5 s for the unfold, 0.4 s between the two looks at the
gear, and their folding away by themselves). While the lease cannot be had
(the user played in the last minute, another holder), it tries again every
2 s; that wait is the user's, logged apart and never counted. Each switch
is one log line, e.g. `switch mpw4→mpw18 in 38 s (stage 24 s, preset 4 s,
auto 6 s) (+12 s waiting for the lease)`; over budget the switch still
completes, and one alert names the slowest step. Should a real switch go
over, the number of Select Region moves is what to cut, never the waits
that make each tap safe.

Expected on the phone (not measured yet): a capture about 0.6 s, an adb
tap about 0.4 s, Select Region about 1.2 s to open, a stage about 4 s to
load. With these, `test_switch.py` gives 33–35 s: the stage 15–17 s (one
region arrow and a few scrolls), the preset 14 s (two readings of the
badge, each waiting for the controls to fold away), AUTO 4 s.

## Limits

- The watchdog's stage check reads only the Roman numeral ending the
  stage's name on the battle screen: another region's stage with the same
  numeral passes (the region's banner is not read yet). Power Saving Mode
  shows no name: there the stage is not checked.
- The watchdog takes a game menu with the skill bar showing (its blue
  mana bar) for the battle screen: classify() says "menu" there on a
  plain battle at 480×1040 (features/watchdog.py, facts). Pop-ups that
  leave the skill bar visible (a level-up, a reward) would then pass for
  battle; this needs tests on real captures of those pop-ups.
- The relaunch's timing: a crash or a game that stopped is seen within
  about 30 s (2 looks 15 s apart), the relaunch starts within a minute,
  then the game takes its own load time to reach the battle screen.
- "Connected elsewhere" (« connected on another device ») and the save
  chooser stay alert-only: the watchdog never taps them (not mapped yet);
  finish by hand.
- Screens are recognised from a few pixel areas measured at the page's
  device shape (19.5:9, e.g. 480×1040). Another shape may stop the launch on
  "unexpected screen"; finish it by hand.
- `stages.json` comes from the community wiki slayerlegend.wiki (datamined
  stage table, stages 1–1,360) and, for soul colours, namu.wiki and player
  guides; read 2026-10-18 and not checked in game. Soul colours past stage
  320 are deduced from the green, blue, red cycle every 20 stages (`soul_colour_confirmed`);
  the page shows the colour without saying so. Stages above 1,360
  show only their number.
- The counter font sizes come from screenshots of the game; a game update
  that changes its top bar can break the emerald rewrite (the panel then says
  "non détecté").
