# Slayer Legend plugin (part 05)

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Lancer le jeu** (Launch the game), button **Lancer** (Launch) | Starts the game and brings it to the battle screen. It opens the game as Android's launcher does (never killing it) and taps exactly four things, each only when the screen shows it: "TAP TO START", **Confirm** on the "last save time" notice (the latest save), **Close app** on Android's "Slayer Legend keeps stopping" dialog (found by uiautomator, at most twice, then the game is opened again), and "Press here to finish Power Saving Mode", held 4 s as the game requires (at most 3 times). It runs when you press it, or as the mpw18 watchdog's relaunch (below). On any other screen (Google sign-in, an update, an event pop-up) it stops after about 45–60 s with "Écran inattendu : termine le lancement à la main" (Unexpected screen: finish the launch by hand), and in any case after 3 minutes. The status row **Lancement** (Launch) shows where it is. |
| **Écran détecté** (Detected screen) and the selected stage | While the options panel is open, every 3 s: the game's screen (title, save choice, battle, game menu, Power Saving Mode, other, or another app in front), and the stage being farmed: **Stage sélectionné** (Selected stage) with its number and name, **Monstres par vague** (Monsters per wave), **Équipement lâché** (Equipment dropped: weapon or accessory, and grade) and **Couleur des âmes** (Soul colour). The number is read in Power Saving Mode, where the game writes it big; the battle screen's header is too small for the number, but its Roman numeral confirms the stage has not changed (otherwise the row says "à confirmer", to be confirmed). The rest comes from `stages.json`, community data (see below). Read-only: it never taps. |
| **Mode** | What the game is set to do: **Farming mpw18 (par défaut)**, or for a time **Farming mpw4**, **Jeu libre** (Free play: nothing is touched) or **Mine fermée** (Closed Mine, below). When the **Minuteur** (Timer, buttons +30 … −30 minutes) ends, it goes back to mpw18 farming. Over the screen, under the player's level (top left), the selected mode is written in the gold counter's pixel font, with `(DEFAUT)` or the time left below it (only there: the game's top bar holds the gold rate, below), while the battle screen shows. A timed mode starts with 30 minutes on its timer. Each mode has its row: a radio button before its name chooses it, and **Configurer** (Configure) opens its settings in a dialog over the panel (**Jeu libre** has nothing to configure, so no button). **Farming mpw4** can be chosen only once its stage is set, **Mine fermée** only once its floor and area are set (greyed out until then; the gateway refuses them too). During free play the game may be open on another device; nothing is checked or alerted then. While **Farming mpw4** runs, the gateway looks for the **gold scroll** buff every 30 s on the battle screen (the mine's own check, `gold_scroll.py`; other screens, Power Saving Mode included, tell nothing); missing on 2 looks in a row, the status row **État** (State) ends with ` ⚠ plus de parchemin doré` (no gold scroll) and, with the phone alerts on, one alert says so; one more says « parchemin doré rétabli » (gold scroll back) once it is seen again, and only then can a new absence alert. `GET /mode` gives it as `gold` (true, false, or null: unknown or another mode). **Stage mpw18** / **Stage mpw4** list only the stages with 18 or 4 monsters per wave up to the highest stage the gateway has seen farmed (read in Power Saving Mode, kept in the plugin's data directory; all of them while none is known), as colour dot, mpw and number. The **Farming mpw18** and **Farming mpw4** dialogs also hold that mode's loadout: **Préréglage de combat** (Battle settings preset, I to V), **Soul Weapon** and **Gravure** (its engraving: a variant of the user's sheet, Atk, Balanced or Crit, or Gold-maxed / Gold-balanced, see below), its grid drawn read-only (⬛ not part of the grid, ⬜ left empty), **Pièces nécessaires** (Pieces needed) and **Enregistrer** (Save), kept by the gateway in `state.json` with the mode's stage (`loadouts`). Switching stages, soul weapon, engraving and battle settings in the game is not learned yet: the plugin says what to do by hand (and alerts). |
| **Surveillance mpw18** (mpw18 watch), **Bail** (Lease) | While the mode is **Farming mpw18** (not in free play, a timed mode or the mine) the gateway looks at the game every 15 s: adb, Android's crash dialog, the game's process and focus, then the screen (battle or Power Saving Mode is farming; on the battle screen the numeral ending the stage's name is compared with the mpw18 stage's). The row shows its last look. A problem seen on 2 looks in a row is one warning with a phone alert (an unknown screen: after 4 looks, 60 s), and « rétabli » once the game has farmed 4 looks in a row. On Android's « Slayer Legend isn't responding » dialog it taps **Wait** once and alerts if the dialog stays (never **Close app**, which would kill the game). When the game is not running, not in front, crashed, or back on its title or save screen, it **relaunches** it (the launch above, at most 3 times an hour, then « Réparation bloquée », for you to do by hand), so that farming is back within about a minute. A game menu open over a minute, the stage, the Battle settings preset and the soul weapon are alerts only for now. In the 5 minutes after a mode ended, another screen is likely « connected on another device » or a choice of saves (not mapped yet): one alert after 2 looks, for you to do by hand. A touch or key of yours pauses it a minute; while someone else holds the shared lease (**Bail**, `POST /lease`) its repair is deferred. After a gateway restart its first 2 looks only observe. `GET /watchdog` gives its counters (looks, bad looks in a row, alerts, repairs this hour, blocked since), the lease and the profile (the mpw18 stage and mpw18's loadout from `GET /loadout`). |
| Mode **Mine fermée**: **Étage à farmer** (Floor to farm), **Zone à farmer** (Area to farm) | Farms the Closed Mine from the gateway, so it goes on with the page closed. While a fight runs with "Repeat entry" ticked it only watches, every 10 s. When the game is back on the floor list (after 30 entries; there is no end pop-up) it taps the floor (read off the list, scrolling to it), the Area, then always 3 feathers. When the **gold scroll** buff is no longer shown it unticks "Repeat entry" and stops: the entry under way ends, no more feathers are spent; it never relaunches without having seen the gold scroll in the last 5 minutes. **Minuteur** (Timer): buttons +30, +5, +1, −1, −5, −30 minutes, usable while it farms, move when farming stops; once the time is up it unticks "Repeat entry" and does not relaunch. With a timer, a missing gold scroll is only a warning (⚠ in the status row and an alert). With the Cloud Phone's phone alerts on (cog → Options → **Alertes sur le téléphone**), it alerts when the gold scroll goes, when farming stops (timer, failure) and when the game has left the screen for 2 minutes. Power Saving Mode hides the buffs, so it leaves it (4 s press) at most once a minute. The status row **Mine** says what it does. Start the first entry by hand; the options are sent to the gateway when they change and again after a gateway restart; a value this browser does not have (a stage, the floor, the area) is left out and the gateway keeps its own. The gateway also keeps the mode, its timer and the mine's floor, area and timer in `/var/lib/cloudphone/plugins/slayer-legend/state.json`: after a gateway restart (an upgrade, an emulator restart) farming goes on, page open or not. |
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
| `features/watchdog.py`, `watchdog_rules.py` | `GET /watchdog`: the mpw18 watchdog's looks, alerts and relaunch; its symptom → repair table and timings are at the top of `watchdog_rules.py` |
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
| `features/engraving_rules.py` | the engraving's rules: rotations, the pieces a variant needs and whether they are there (and the alert when not), the gold layout's search, placement checks, lookups by name and id |
| `stages.json` | per stage: name, monsters per wave, drop (weapon `W` or accessory `A`) and grade, main soul colour |
| `page.js` | page side: assembles the page features below, starts them, shows their options in the panel's order, hands them the settings and disposes of them |
| `page_screen.js` | the "Jeu" section's screen and stage rows |
| `page_launch.js` | the **Lancer le jeu** button and its status row |
| `page_mode.js` | the "Mode et farming" section; its overlay hook: the mode's lines over the game (a timed mode's time left under its name) |
| `page_engraving.js` | in the **Farming mpw18** and **Farming mpw4** dialogs of `page_mode.js`: the mode's loadout (Battle settings preset, soul weapon, engraving variant), the variant's grid drawn read-only and the pieces it needs, **Enregistrer** (Save). A selector this browser never touched shows the saved value, and **Enregistrer** sends only what was chosen here: a field left out keeps the saved one |
| `page_gold.js` | the "Gold" section, the gold rate in the game's top bar, and the label over the game, top left: the features' overlay lines, under the same condition |
| `gold_text.js` | writes text in the gold counter's pixel font (from `GET /gold-font`) |
| `page_trace.js` | the "Navigation" section: sends the user's taps to the trace |
| `page_watchdog.js` | the "Surveillance mpw18" and "Bail" rows |
| `page_counters.js` | the "Émeraudes" and "Diamants" sections |
| `counter_rewrite.js` | finds a counter on the video (or asks the gateway) and cuts it or writes over it |
| `emerald_mask.js` | finds the emerald counter on the video |
| `emerald_font.js` | the game's counter font at 480 px wide, for the rewritten number |
| `test_nav.py` | the graph is consistent; the guard lets the plugin's own actions through and refuses the forbidden ones (`python3 -m unittest test_nav`) |
| `test_watchdog.py` | the watchdog's rules on virtual time: timings, alerts said once, caps, the lease, a gateway restart, the profile, after a mode's end; its Wait on the ANR dialog (`python3 -m unittest test_watchdog`) |
| `test_screens.py` | `screens.classify` on synthetic screenshots drawn from the areas it reads (`python3 -m unittest test_screens`) |
| `test_trace.py` | tests of `trace.py` on synthetic screenshots (`python3 -m unittest test_trace`) |
| `test_engraving.py` | `engravings.json` is well formed and its variants fill their patterns; rotations, the gold layout, the pieces needed (`python3 -m unittest test_engraving`) |
| `test_mine.py` | the mine on a scripted game, on virtual time, through the guard: an untick that will not take, the mine turned off and on in one tick, its taps waiting for the lease (a user input, an outside holder), the lease's routes and expiry, the free-play warning (`python3 -m unittest test_mine`) |

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
- **Rotation**: whether the game turns pieces is not confirmed yet
  (`"rotation": null`). Until it is `true`, the gold variants are the
  ones without rotation, and a sheet variant that turns pieces is listed
  but marked not placeable (« non plaçable tant que la rotation n’est pas
  confirmée »). The sheet's solutions turn pieces; 47 of the 77 grids
  cannot be filled exactly without turning any (`tileable_without`).
  Pieces are never mirrored. In game, the unequipped pieces seen were
  all L in one orientation, with no control to turn them: a piece may
  keep the orientation it dropped with. That is not confirmed; it is
  prepared as `"rotation": "per-piece"`. Then layouts hold pieces in
  any orientation, and the inventory is counted by shape and
  orientation (`"L:1"`, `needed_oriented`): a sheet variant needs its
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
  and the shapes' stats come from it alone. The later weapons' names
  follow the sheet; the wiki's older names are kept as `aliases`.
- **Trust**: nothing is checked in game yet (`verified_in_game: false`).

Before the plugin places anything (a later phase), it reads the grid on
the engraving screen from pixels and compares the shape of its active
cells with the pattern's `cells`: never a name, no OCR. A mismatch blocks
with an alert and places nothing. It also reads the pieces available; if
the chosen variant needs pieces that are not there, it alerts with the
list of what is missing and places nothing.

## Limits

- The watchdog's stage check reads only the Roman numeral ending the
  stage's name on the battle screen: another region's stage with the same
  numeral passes (the region's banner is not read yet). Power Saving Mode
  shows no name: there the stage is not checked.
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
  320 are deduced from the green, blue, red cycle every 20 stages: the page
  says "déduite, non vérifiée" (deduced, not checked). Stages above 1,360
  show only their number.
- The counter font sizes come from screenshots of the game; a game update
  that changes its top bar can break the emerald rewrite (the panel then says
  "non détecté").
