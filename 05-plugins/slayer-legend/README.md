# Slayer Legend plugin (part 05)

The mode overlay shows the mode name in white and the timer (or « défaut ») in green when stable. Both are blue during user input and the rolling 5-second pause, orange while returning to the selected instruction, and red only when actually blocked. Every input restarts the pause.
Blocked states display their error on the game overlay as well as the existing
ntfy notification. Observations continue while automated actions are paused.

Features for the game Slayer Legend only, installed as a plugin of the Cloud
Phone app (part 04). They show in the page's options panel (the cog in the
toolbar), under **Plugins → Slayer Legend**. Without this part the page has
no game-specific code.

| Feature | What it does |
|---|---|
| **Plugin**: **Activé** (On, the default) or **Désactivé** (Off), first in the block | Kept by the gateway (`GET`/`POST /enabled`, `state.json`, `features/power.py`). While off the plugin taps nothing: the lease is refused to its own holders and a sequence under way stops at its next tap, the watchdog does not look (**État** ends with « Plugin désactivé »), the mine and the mode switch wait without alerting, and the page draws nothing over the game. |
| The launch (the watchdog's relaunch; no button) | Starts the game and brings it to the battle screen. It opens the game as Android's launcher does (never killing it) and taps exactly four things, each only when the screen shows it: "TAP TO START", **Confirm** on the "last save time" notice (the latest save), **Close app** on Android's "Slayer Legend keeps stopping" dialog (found by uiautomator, at most twice, then the game is opened again), and "Press here to finish Power Saving Mode", held 4 s as the game requires (at most 3 times). It runs as the watchdog's relaunch (below), or on `POST /launch`. On any other screen (Google sign-in, an update, an event pop-up) it stops after about 45–60 s with an error, « Lancement arrêté : écran inattendu (lu : …), pas encore catalogué » (Launch stopped: unexpected screen (read: …), not catalogued yet), and in any case after 3 minutes. A step that cannot go on (the crash dialog's button not found, Power Saving Mode that stays, Google's sign-in) is an error record and alert that says what was seen and why, never an instruction for the user. `GET /launch` says where it is. |
| **Stage**, under the mode's **État** | While the options panel is open, every 3 s: the stage being farmed in one row, « 920 · 🔴 · Arme · 5 par vague »: its number, its soul colour as a dot, the drop (**Arme**, weapon, or **Accessoire**, accessory) and the monsters per wave, or « inconnu » (unknown). The number is the game's state (`GET /game`): read in Power Saving Mode, where the game writes it big, and on the battle screen's header, its region's name and Roman numeral; it is kept by the gateway across restarts, never in the browser. The rest comes from `stages.json`, community data (see below). Read-only: it never taps. |
| **Mode** | What the game is set to do: the **Mode par défaut** (Default mode: **Farming mpw18** unless set to **Farming mpw4** or **Jeu libre**; never the mine; saved on change, mpw4 offered once its stage is chosen, the gateway refusing it before too), or for a time another one of **Farming mpw18**, **Farming mpw4**, **Jeu libre** (Free play: nothing is touched) or **Mine fermée** (Closed Mine, below). The default mode has no timer. When the timer (**Temps restant**, Time left, buttons +30 … −30 minutes) ends, or the mine ends, it goes back to the default mode by the same switch ("Timer ended: back to farming mpw4 (stage 925)"). Changing the default does not change the mode running. Over the screen, under the player's level (top left), the selected mode is written in the gold counter's pixel font, with `MISE EN PLACE...` under it while the gateway sets the mode up (`EN ATTENTE` while the switch is on hold because you play), and `(DEFAUT)` or the time left below (only there: the game's top bar holds the gold rate, below), while the battle screen shows. A timed mode starts with 30 minutes on its timer. Each mode has its row: a radio button before its name chooses it, and **Configurer** (Configure) opens its settings in a dialog over the panel (**Jeu libre** has nothing to configure, so no button). **Farming mpw4** can be chosen only once its stage is set, **Mine fermée** only once its floor and area are set (greyed out until then; the gateway refuses them too). During free play the game may be open on another device; nothing is checked or alerted then. While **Farming mpw4** runs, the gateway looks for the **gold scroll** buff every 30 s on the battle screen (the mine's own check, `gold_scroll.py`; other screens, Power Saving Mode included, tell nothing); missing on 2 looks in a row, the status row **État** (State) ends with ` ⚠ plus de parchemin doré` (no gold scroll) and, with the phone alerts on, one alert says so; one more says "Farming mpw4: gold scroll back" once it is seen again, and only then can a new absence alert. `GET /mode` gives it as `gold` (true, false, or null: unknown or another mode). **Stage mpw18** / **Stage mpw4** list every stage with 18 or 4 monsters per wave (`stages.json`), as colour dot, mpw and number; one past the highest stage seen farmed is marked « jamais atteint » (never reached) and can still be chosen: the switch tries it, and its check after Move fails with one alert "… stage N not opened by the game" (État: « stage N non ouvert par le jeu ») if the game does not open it. The **Farming mpw18** and **Farming mpw4** dialogs also hold that mode's loadout: **Préréglage de combat** (Battle settings preset, I to V), **Soul Weapon** and **Gravure** (its engraving: a variant of the user's sheet, Atk, Balanced or Crit, or Gold-maxed / Gold-balanced, see below), its grid drawn read-only (fixed-size cells: the pieces in colour, an outlined cell left empty, nothing where the grid has no cell). Each choice is saved on change, half a second after the last one, with no button (`POST /loadout`, only the fields chosen in the page); a refusal is a warning in the page's client log, nothing pops up over the game. The gateway keeps them in `state.json` with the mode's stage (`loadouts`). When **Farming mpw18** or **Farming mpw4** starts (chosen, or back as the default at the end of a timer), the gateway brings the game there by itself, in the background, under the shared lease (holder `stage_change`; while you played in the last minute with the game in front or another holder has it, it waits for its next look, every 10 s). While you play, the switch is **on hold**: one alert says so with the real delay before its next try ("Switch to farming mpw18 on hold: you are playing. Next try in 60 s."), once per switch even when your inputs make the wait longer; the **État** row says « Farming mpw18 · en attente : tu joues · nouvel essai dans 42 s » with **Jeu libre** and **Reprendre** inline, and the phone alert has the same two buttons (with a one-time token for this hold, never the page's: it works once, 10 minutes at most, and no longer once the hold is over); you may answer **Passer en jeu libre** (free play instead, timed as its radio button) or **Reprendre maintenant** (the switch now, your last minute not waited for; a touch during it still stops it); with no answer it goes on by itself once the minute is over. `GET /mode` gives the hold as `hold` ({id, mode, left: seconds}, null without one), `POST /mode/hold` `{action: "free" | "resume"[, hold]}` answers it (409 when nothing is on hold; the same answer again changes nothing). Each part has a switch, `GET /farming` / `POST /farming` `{stage_change, preset}`, `"real"` or `"plan"`, kept in `state.json`: **plan by default**, the plan is written to the log and nothing is tapped; each is turned to real after a first run watched with you. The **AUTO** button is never tapped (the user's order, 2026-10-22; forbidden in `navigation.json`, and `POST /farming` refuses an `auto` field): AUTO is only read, for the alerts. Once real: it closes the bottom panel open (its own tab again), opens the stage map (« Select Region »), goes to the stage's region with the banner's arrows and to its row by scrolling, taps **Move** on the row whose name it read as that stage (the game's pixel font, `pixel_font.py`, `stage_select.py`), and reads the stage's name on the battle screen afterwards; then it chooses the loadout's **Préréglage de combat** in « Battle settings » (through the badge the arrow on the right edge unfolds, checked by its frame and on the badge). Any step that does not show what it expects stops it; the switch is tried again from the start after 2, 4, 8, then 16 s while within 60 s of its trigger, and only then « Passage au stage N (mpwM) arrêté : … » names the step in **État** with one alert (the État row is back to farming once the watchdog sees the mode farm). Before stopping on a screen it does not know it waits up to 4 s for it to pass, and it leaves Power Saving Mode by its hold. Once set up, one notification says how long it took since the mode was chosen, the wait for the lease included: "Farming mpw18 ready in 34 s" (with the slowest step when over 60 s), the hold said apart: "ready in 95 s (including 60 s waiting: you were playing)". A change of the running farming mode's loadout (its stage, preset or soul weapon, saved from its dialog) is applied at once the same way, logged « loadout mpw18 changed → applied in N s » and notified "Loadout mpw18 applied in 21 s"; the soul weapon alone runs only its own step. Only the regions whose 20 stages share one name are reached this way (stages 561–580 and from 601 on, `stages.json`). Last (so that a slow step never delays farming), it equips the loadout's **Soul Weapon** (`features/soul_weapon.py`, `soul_weapon.py`): Equipment, the Weapon tab, the Soul Weapon icon; it picks cells in the list and reads the card's name (the game's pixel font, matched against the 89 names with a margin), scrolls the list, and taps the orange **Equip** tag only when the card reads that weapon, owned, and the tag reads Equip; afterwards the tag must read **Unequip** (never tapped: the guard refuses it). The tag is read against templates cut from real captures; until both tags are captured (only Unequip is so far) the Equip tap stays closed: an error alert "… <weapon>: Equip tag not calibrated, not equipped". Then its **engraving** (`features/engraving_setup.py`, `engraving_screen.py`): the card's big icon, the title and the weapon's name checked; then one move at a time, each on a fresh capture: a card whose padlock reads open is locked first (the padlock in its corner; if that tap does nothing, one error alert and its piece popup instead); a piece that is not where the variant puts one, or that holds a card that is not the best, is dragged out to the inventory and its card, unlocked by that, locked again at once; the best cards of each shape (a Gold variant takes the cards with the gold option first, then the highest levels) are dragged onto their cells, turned with the preview's rotate button, moved by a drag of one of its cubes, and placed with its check only once it lies on those cells and the check reads valid. Before the screen is closed all 8 padlocks must read closed; one still open or unreadable is one error alert naming the card, and the engraving is not ready. The weapon is ready only once the grid is the variant's with those cards and all 8 cards read locked; otherwise one error alert "… Engraving of <weapon> (<variant>) not ready: …". Change, the gear and % are never touched. The engraving has its own switch, `engraving` (`POST /farming`, `"off"` or `"real"`, kept in `state.json`), **off by default**: until a first run supervised with you, not one engraving gesture is made (not even the card's big icon), one error alert says "… Soul Weapon: engraving not set up: first supervised run pending" (État: « gravure pas mise en place : premier passage supervisé en attente ») and the weapon is not ready; it is turned to `"real"` only with you present. When it moved or locked something, one notice "Soul Weapon <weapon> (<variant>) ready: …" with its duration and the engraving's own (seconds and gestures, also logged "engraving step took N s (K gestures)"; said when over 60 s). A change of the running mode's variant is applied at once. Its switch `soul_weapon` (`POST /farming`) is real by default, `"off"` an emergency stop; after a check found it ready it is skipped while neither a relaunch nor an input of yours came since, and the watchdog's relaunch runs it once more. A failure is one alert "… Soul Weapon: <step>". |
| The watchdog, at the end of the mode's **État** (State) row | It checks that the game does what the selected mode says, with no option rows of its own (the lease and its counters are in **Debug & développement**): its last look ends the mode's **État** row (« Farming mpw18 au stage 920 · OK », « · relance du jeu dans 4 min » with a **Réessayer** (Retry) button inline while a repair backs off). **Farming mpw18** and **Farming mpw4** are checked alike, each with its own loadout (stage, Battle settings preset); **Mine fermée**'s screens are the mine's own; the game gone, crashed, not in front or back on its title screen is relaunched with the same backoff (an alert after 2 minutes), then the mine feature goes back in by its own way (Adventure, Dungeon, Closed Mine, then the floor, Area and feathers, tried again within a minute). While the Adventure and Dungeon screens are not calibrated on a capture it taps nothing there: the mine ends and the mode goes back to the default one, with one alert "Closed Mine stopped: …, back to farming mpw18 (stage 920)". Out of feathers (read on the feathers pop-up, once calibrated) the same: "Closed Mine stopped: no feather left, back to farming mpw18 (stage 920)"; **Jeu libre** is not checked; a mode's entry (its stage change running under the lease) is waited for. Every alert names the mode ("Farming mpw4: wrong stage, not 915"); alerts and log records are in English. The gateway looks at the game every 15 s, and wakes at the end of a user-input pause (5 s after the latest input): adb, Android's crash dialog, the game's process and focus, then the screen (battle or Power Saving Mode is farming; on the battle screen the stage read is compared with the mode's). A problem seen on 2 looks in a row is one warning with a phone alert (an unknown screen: after 4 looks, 60 s), and "recovered" once the game has farmed 4 looks in a row (5 minutes when a repair was made); the same problem again within 30 minutes of its last phone alert is logged without a new one. On Android's « Slayer Legend isn't responding » dialog it taps **Wait** once and alerts if the dialog stays (never **Close app**, which would kill the game). When the game is not running, not in front, crashed, or back on its title or save screen, it **relaunches** it (the launch above; on the sign-in screen, « Sign in with Google » once and the one account), so that farming is back within about a minute. On the battle screen the stage is read whole (region and numeral); a wrong stage or Battle settings preset is repaired with the stage change above (the preset, and AUTO as information, read on one unfold of the right edge's controls at most every 5 minutes, whoever watches the screen). AUTO is never tapped: instead the watchdog watches the **stage progress bar** under the stage's name (`stage.py`'s `progress`, calibrated on real captures: empty, partial, full, and a grey flash frame read as unknown), read at each look on the battle screen with nothing over it, or on the Soul Weapon screen where the mode parks (the bar is drawn there the same: `fixtures/bar_parked_*`), while mpw18 or mpw4 farms. It fills in about 55–60 s and starts over at each stage; 3 readable looks in a row without a move (over 10 of its 214 px, or a drop over 100 px at a stage's end), 45 s, are one red error alert "Farming mpw18: Stage progress bar stalled for 45 s (AUTO reads on)", no repair and no tap; said again at 8 and 30 minutes, then "recovered" once it moves again. An unreadable look (a flash) counts neither way; another screen, Power Saving Mode included (no bar there, and nothing on it counts the battle: its "In battle . . ." dots cycle on their own), a menu, free play, the mine, a mode's entry and the minute after a relaunch start the count over. Each kind of repair backs off on its own after a real failure (still there at the next look, its sequence stopped, or back before a durable recovery): 1, 2, 4, 8, 16, then 30 minutes between attempts, never for good; alerts at the first failure, at 8 and at 30 minutes, then "recovered"; **Réessayer** starts the waiting ones over. A game menu open over a minute and the soul weapon are alerts only for now. In the 5 minutes after free play ended, another screen is likely « connected on another device » or a choice of saves (not mapped yet): one error alert after 2 looks, "not catalogued yet"; on Android's not responding dialog that stays after **Wait**, one error alert too. A touch or key of yours pauses it a minute; while someone else holds the shared lease (`POST /lease`) its repair is deferred. After a gateway restart its first 2 looks only observe. `GET /watchdog` gives the mode checked, its line, the kinds waiting, its counters (looks, bad looks in a row, alerts, the next attempt per repair backing off), the lease and the profile (the mode's stage and loadout from `GET /loadout`). |
| Mode **Mine fermée**: **Étage à farmer** (Floor to farm), **Zone à farmer** (Area to farm) | Farms the Closed Mine from the gateway, so it goes on with the page closed. While a fight runs with "Repeat entry" ticked it only watches, every 10 s. When the game is back on the floor list (after 30 entries; there is no end pop-up) it taps the floor (read off the list, scrolling to it), the Area, then always 3 feathers. When the **gold scroll** buff is no longer shown it unticks "Repeat entry" and stops: the entry under way ends, no more feathers are spent; it never relaunches without having seen the gold scroll in the last 5 minutes. **Temps restant** (Time left): buttons +30, +5, +1, −1, −5, −30 minutes, usable while it farms, move when farming stops; once the time is up it unticks "Repeat entry" and does not relaunch. With a timer, a missing gold scroll is only a warning (⚠ in the status row and an alert). With the Cloud Phone's phone alerts on (cog → Options → **Alertes sur le téléphone**), it alerts when the gold scroll goes, when farming stops (timer, failure) and, through the watchdog (the one owner of that alert), when the game has left the screen for 2 minutes. Power Saving Mode hides the buffs, so it leaves it (4 s press) at most once a minute. The status row **Mine** says what it does. Start the first entry by hand; the options are sent to the gateway when they change and again after a gateway restart; a value the page's options do not have (a stage, the floor, the area) is left out and the gateway keeps its own. The page's options are kept by the gateway for every browser (part 04, `GET`/`POST /api/v1/settings`, in this plugin's data directory, `page-options.json`). The gateway also keeps the mode, its timer and the mine's floor, area and timer in `/var/lib/cloudphone/plugins/slayer-legend/state.json`: after a gateway restart (an upgrade, an emulator restart) farming goes on, page open or not. |
| **Débits horaires** | La colonne à droite affiche, dans cet ordre : gold/h, cubes/h, âmes vertes/h, bleues/h, rouges/h, armes L3/h, accessoires L3/h. Le gateway mesure le gold et les âmes en secondes ; la page multiplie par 3 600 et abrège les chiffres. Cubes et équipements L3 exigent deux relevés vérifiés distincts. `.../h` signifie que le débit n’est pas encore mesurable. Les soldes L3 sont lus seulement quand la case rouge Grade 3 est entièrement visible dans le bon onglet Equipment, sur une capture 480 × 1040 ou 720 × 1560 ; à 720, la géométrie a été testée par agrandissement de captures 480 mais attend encore une capture native de la grille. Les chiffres non calibrés restent inconnus. Les pierres restent visibles dans l’onglet Ressources, mais leurs débits sont retirés de l’overlay. Aucune âme blanche ne figure dans cette colonne. |
| **Compteur de Cubes** | Le total des Cubes reste entier et non abrégé sur le jeu. Son icône reste sur l’axe de la pièce Gold, à mi-hauteur entre ses positions en vue Battle et combat réduit. Il utilise les glyphes du compteur Gold, ramenés à la hauteur observée du Gold sur une capture native 720 × 1560 (environ 10–11 pixels physiques), avec les séparateurs de milliers et une icône de 18 pixels de jeu. Entre deux lectures réelles, le dernier débit Cubes/h mesuré fait avancer le total affiché chaque seconde ; la teinte vire progressivement du blanc au bleu quand la lecture vieillit. Le total et les débits horaires suivent la luminosité mesurée du texte Gold pour rester cohérents quand Battle est grisé. Les débits Arme L3/h et Accessoire L3/h portent leurs icônes tirées du jeu. |
| **Debug & développement** | « Zones de navigation » affiche le nom de l’écran reconnu, les clics permis en jaune et les zones de glissement vertical en bleu ou horizontal en violet ; un contour pointillé signale une précondition à vérifier. « Enregistrer un clic » capture l’écran avant le geste suivant et deux secondes après, puis conserve les deux PNG et le geste dans le dossier privé `manual-clicks/` du plugin. Le graphe passif continue de suivre les clics de la webapp avec des vignettes, limité à 2 000 écrans et 20 000 arêtes ; la capture manuelle fonctionne même si ce graphe est plein. |
| **Compteur d’émeraudes** (Emerald counter) | On this screen only, nothing is sent to Android. **Coupé à la virgule** (Cut at the comma): the comma and what follows are covered with the bar's colour (`284,086` shows `284`). **Réécrit** (Rewritten): the counter is covered and written again at the game's size for that many digits (6 digits are smaller than 5 or fewer), on the game's baseline: by default the digits after the comma, leading zeros dropped (`284,086` shows `86`), or the number typed in **Nombre affiché (vide : après la virgule)** (Number shown (empty: after the comma)), drawn in the game's own pixel font (`emerald_font.js`) and in the colour of the digits it replaces. The status row **Détection du compteur** (Counter detection) says détecté / non détecté (detected / not detected). Kept by the gateway for every browser, like the page's other options. |
| **Compteur de diamants** (Diamond counter) | The same three choices and the same font for the diamond counter, right of the emeralds: **Inchangé**, **Coupé à la virgule**, **Réécrit** with its own **Nombre affiché** field and **Détection du compteur** row. A counter under 1,000 has no comma and is left as it is. |
| **Debug & développement** (Debug & development), last and folded | For the developer: **Écran détecté** (Detected screen: the panel open over the battle, Growth, Skill, Equipment, Companion, Adventure or Shop, « Aucun panneau ouvert » on the bare battle screen, or the title, the save choice, a game menu, Power Saving Mode, another app), **Enregistrer mes parcours** and its counts (above), **Détection des émeraudes** / **Détection des diamants** (whether each counter is found on the screen), **Bail** (Lease: its holder and reason, or « libre »), **Surveillance** (the watchdog's looks, bad looks in a row and alerts), then the plugin's own records of the server's log, with the level filter. |

| **Jeu · Combat**, **Jeu · Select Region**, **Jeu · Soul Weapon**, **Jeu · Gravure**, **Jeu · Mine fermée** (Game · …), folded, before Debug | The game's state as the gateway keeps it (`GET /game`, see **Architecture: the scan** below): one section per screen of the game, a row per value, « 925 · vu à 14:32 » (its time seen), the engraving grid drawn read-only; a value not read again since the game was stopped or relaunched is greyed out; « lecteur en attente de capture » for a value whose reader waits for its calibration captures, « jamais lu » before the first reading. Asked at load, then every 10 s while a row shows. |

The plugin's icon (a sword) and the Gold, Émeraudes and Diamants sections' icons are pixel art drawn in `page_icons.js`, nothing copied from the game.

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

## Architecture: the scan

Everything is scanned, then the features do what they must with it: the
scan is the one producer of what the plugin knows of the game
(`features/game.py`, `features/game_rules.py`).

- Every capture any feature takes (`ports.capture`) is looked at once
  (`screens.look`) and the readers its screen and overlays show run on it
  (`game_rules.READERS`, `readers_for`: a pure mapping, base screen and
  overlay to readers), only reading, never a tap. They are the plugin's
  existing readers, wired (`game.reader_table`): `stage.py`,
  `stage_select.py`, `gold.py`, `soul_counters.py`, `soul_weapon.py`,
  `engraving_screen.py`, `battle_controls.py`. A slow reader (the pixel
  font's text: the battle's stage name, the gold and souls counters, the
  soul weapon's name, Select Region's rows) runs on a capture scanned as it
  comes at most every few seconds, so that the looks keep their pace; a
  feature that needs its value on its own capture forces it
  (`scan(shot, force)`). `test_game.py` prints each reader's time on the
  fixtures.
- What they read is the game's state: per field its value, `seen` (Unix
  time), `verified` and `source` (`scan`, `setup`: what a setup step
  checked, the stage after Move, the preset on the badge, the soul weapon
  and its variant once ready, the mine's floor and area once in the fight;
  `page`: a stage a page saw). Kept in `state.json` (`game`): the highest
  stage reached, the stage, the preset, AUTO, the gold and souls readings,
  Select Region's region, the soul weapon selected and equipped, the
  engraving variant and grid, the mine's floor and area. A value once seen
  is never null again; the highest stage only goes up (a stage read, Select
  Region's highest row with a Move button, `/stages?known=N`).
- While the user plays (an input in the last minute, the game in front) a
  capture is scanned every 5 s: what the user changes in the game becomes
  the state, logged « User changed preset from II to III » when no feature
  of the plugin holds the lease. A switch then compares the loadout with
  the game as it reads it and acts only on what differs.
- The game's process is looked at every few seconds (`ports.running`): gone,
  or another process (relaunched, Android restarted), and every value turns
  unverified (kept, greyed in the page) and the features' caches are
  dropped: the soul weapon read equipped (its `cached` shortcut), the
  preset and AUTO the watchdog read. The next setup reads again what it
  depends on.
- Features read the state: `game.get(field, max_age)`,
  `game.require(fields, max_age)` give a value seen within `max_age`
  seconds, else scan a fresh capture, else `{value: null, why: "not
  readable on this screen"}` (or `"unread"`). Already on it: the gold and
  souls rates, the highest stage (`/mode`, `/stages`, the stage change),
  the watchdog's stage, numeral and progress bar, `/screen`'s stage. The
  features still reading pixels on their own are listed in `docs/TODO.md`
  (Planned work), the migration plan.
- Values with no reader yet are in the schema marked pending (emeralds,
  diamonds, the mine's feathers): their captures are on `docs/TODO.md`'s
  calibration list.

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
| `features/ports.py` | the ports the features get from the gateway's context: screenshots (with `max_age`), analysis, tap, hold and swipe (each through the guard of `nav.py`, refused otherwise, and only under the shared lease), the lease (`Lease`: one holder at a time, a reason, a time to live of at most 15 minutes renewed by its holder, released by its holder only, its expiry logged as a warning; a user input stops every holder but the user's own press for 5 s after the last input, only while the game is in front: an input on the launcher or another app, the game not running, is not playing and the relaunch or the switch goes on), whether the game is in front or running, starting it (the launch only), alerts, the clock, `state.json` |
| `features/lease.py` | `GET`/`POST`/`DELETE /lease`: the shared lease for a holder outside the plugin (`{holder, reason, seconds}`, the page token needed): while it holds it, the launch, the mine and the watchdog do not tap |
| `features/counters.py` | `GET /emerald-mask`: a counter's mask off a screenshot, for browsers that cannot read the video |
| `features/game.py`, `game_rules.py` | `GET /game`: the scan of every capture and the game's state (see **Architecture: the scan**); `game_rules.py` holds the schema by screen, the screen → readers mapping and how a reading becomes the state |
| `features/screen.py`, `screen_rules.py` | `GET /screen`, `GET /stages`: the screen and stage shown, every mpw18 and mpw4 stage and the highest seen (the game's state) |
| `features/power.py` | `GET`/`POST /enabled`: the plugin's on/off switch (`ports.enabled`) |
| `features/launch.py`, `launch_rules.py` | `GET`/`POST /launch`: the launch, as the watchdog's relaunch |
| `features/watchdog.py`, `watchdog_rules.py` | `GET /watchdog`: the watchdog's looks at the selected mode, alerts and repairs; its symptom → repair table and timings are at the top of `watchdog_rules.py` |
| `features/trace.py` | `GET`/`POST /trace`, `GET /trace/graph`: the user's own taps, with the screen before and after each |
| `features/gold.py`, `gold_rules.py` | `GET /gold`, `GET /gold-font`: gold per second, and which readings count |
| `features/mine.py`, `mine_rules.py` | `GET`/`POST /mine`, `POST /mine/timer`: the Closed Mine's farming loop, its stop pass after a restart and the passive watch after it |
| `features/mode.py`, `mode_rules.py` | `GET`/`POST /mode`, `POST /mode/timer`: the mode, its timer and its end (a `POST /mode` without `until` keeps the timer, `until: null` clears it); its stages are the loadouts' (`features/engraving.py`) |
| `features/timer_rules.py`, `values.py` | the timers' arithmetic (mode and mine); the checks of values read back from `state.json` |
| `screens.py` | the screen model: `look(shot)`, one pass per capture shared by every feature, gives the screen, the overlays over it and a margin (`unknown` under it); `classify` gives the names the features know (title, save notice, battle, menu, Power Saving Mode, other); where the plugin's own taps and hold go |
| `screen_registry.json` | every screen and overlay `look()` recognises, by `navigation.json` id: its anchors (crops of real captures compared as downscaled grey signatures, shares of colour, readers) and fixtures; every other `navigation.json` screen is pending capture, never matched, and listed in `docs/TODO.md`; its tree holds every screen of the game known so far, recognised or not: parent, the move to it and back, whether the capture tour visits it, and its scroll areas |
| `scrolling.py` | scrolls a list through its `navigation.json` swipe until an item is read, and tells its start and end: two frames alike in the area after a swipe |
| `pixel_font.py`, `font_cut.py`, `fixtures/texts.json` | the game's pixel font: its reader, and its glyphs, cut by `font_cut.py --write` from the fixtures whose text `fixtures/texts.json` gives (each the average of two occurrences or more; `docs/TODO.md` lists the ones still drawn or missing) |
| `other_screens.json` | the catalogue of « other » screens seen for real, named by their text (`screens.other_name`); empty until one is captured; nothing on them is ever tapped |
| `stage.py` | reads the stage number (Power Saving Mode), the name's Roman numeral and the stage progress bar's fill (battle screen) off a screenshot |
| `gold.py` | the gold counter off a screenshot: its glyphs, its unit letter (A is a thousand, B a thousand A…), the notation's parser (abbreviated or full digits, `parse`), and the rate's notation |
| `soul_counters.py` | the Equipment panel's souls row off a screenshot: the four counters (green, blue, red, white) in the pixel font, parsed as gold's |
| `mine.py` | the Closed Mine's screens off a screenshot: fight, Repeat entry box, gold scroll, floor list and its numbers, Area and feathers pop-ups |
| `emerald_mask.py` | Python twin of `emerald_mask.js`, for browsers that cannot read the video's pixels (Firefox on Android); keep the two in step |
| `trace.py` | the navigation trace: screen signatures (name and grey thumbnail), the graph of screens and taps, its JSON file; the buttons never to press (`FORBIDDEN`) |
| `navigation.json` | the game's screens and every known way out of each (tap, area, hold, swipe or key), allowed or forbidden with the reason (Breakdown, Change, diamonds, Black Orb, equipment overwrites, raids and recipes in Dragon Valley, Promotion dice…) |
| `nav.py` | the guard: every tap, hold and swipe of the plugin names the screen it recognised and the move it wants, and is refused unless it is an allowed move of that screen landing where the move is and on no forbidden move (deterministic, refused by default) |
| `engravings.json` | per soul weapon (by id, the game's order): its engraving grid's active cells, the user's variants (Atk, Balanced, Crit) as pieces with shape, rotation and cells, the gold layout, the completion effect; see **Soul Weapon engraving data** below |
| `features/engraving.py` | `GET /engravings`, `GET /engraving?id=N`, `GET`/`POST /loadout`: the patterns and their variants, and each farming mode's loadout: its stage, Battle settings preset and soul weapon with its variant (by id), kept in `state.json` (`loadouts`), the one place of the mpw18 and mpw4 stages (`POST /mode` sets them there, `GET /mode` reads them back) |
| `features/soul_weapon.py`, `soul_weapon_rules.py` | the soul weapon step of a mode change (after the preset) and after a watchdog relaunch: the sequence, its cache and its switch; the rules choose select, scroll, Equip, done or fail on what the screen shows (at most 10 moves) and learn which way the list runs (kept in `state.json`, `soul_weapon`) |
| `soul_weapon.py` | the Soul Weapon screen off a screenshot: its title, the card's name and Owned, the list's cells and selection, its Equip / Unequip tag, the Equipment tab, the card's badge |
| `engraving_screen.py` | the Soul Weapon Engraving screen off a screenshot (calibrated at 480x1040, 5x5 grids): its title and weapon name, the grid's cells and pieces, each of the 8 cards' shape, level, padlock (open or closed), E (placed) and option icon; the piece popup (its padlock, its gold option); a piece's preview (its cubes, red ones, the bar's buttons, whether its check reads valid) |
| `features/engraving_setup.py`, `engraving_setup_rules.py` | the engraving step after the equip: locks, removals (each relocked at once) and placements through the preview, ready only when the grid is the variant's and all 8 cards read locked; the rules choose the cards and the next move, the preview's turns and shifts, and name what is left for the alert |
| `features/engraving_rules.py` | the engraving's rules: rotations, the pieces a variant needs and whether they are there (and the alert when not), the gold layout's search, placement checks, lookups by name and id |
| `stages.json` | per stage: name, monsters per wave, drop (weapon `W` or accessory `A`) and grade, main soul colour |
| `page.js` | page side: assembles the page features below, starts them, shows their options in the panel's order, hands them the settings and disposes of them |
| `page_screen.js` | the **Stage** row (under the mode's État) and the debug row **Écran détecté** |
| `page_game.js` | the game's state sections (`GET /game`), one per screen, unverified values greyed |
| `page_power.js` | the **Plugin** switch, first in the block |
| `page_icons.js` | the icons: pixel art for the plugin, Émeraudes and Diamants; the game's gold coin and souls |
| `page_mode.js` | the "Mode et farming" section; its overlay hook: the mode name and timer (or « défaut ») over the game, coloured by the current state |
| `page_engraving.js` | in the **Farming mpw18** and **Farming mpw4** dialogs of `page_mode.js`: the mode's loadout (Battle settings preset, soul weapon, engraving variant), the variant's grid drawn read-only and the pieces it needs, **Enregistrer** (Save). A selector this browser never touched shows the saved value, and **Enregistrer** sends only what was chosen here: a field left out keeps the saved one |
| `page_gold.js` | the "Gold" section, the gold rate in the game's top bar, and the label over the game, top left: the features' overlay lines, under the same condition |
| `gold_text.js` | writes text in the gold counter's pixel font (from `GET /gold-font`) |
| `page_trace.js` | sends the user's taps to the trace; its debug rows |
| `page_watchdog.js` | the watchdog's end of the mode's « État » row, and « Réessayer »; the debug rows **Bail** and **Surveillance** |
| `page_counters.js` | the "Émeraudes" and "Diamants" sections; the debug rows of their detection |
| `counter_rewrite.js` | finds a counter on the video (or asks the gateway) and cuts it or writes over it |
| `emerald_mask.js` | finds the emerald counter on the video |
| `emerald_font.js` | the game's counter font at 480 px wide, for the rewritten number |
| `test_game.py` | the scan's mapping on real fixtures (each screen gives its fields and only those, the readers' times printed), the state's rules, and the feature on fake ports: kept across a gateway restart, the old highest taken over, a relaunch, the user's changes logged (`python3 -m unittest test_game`) |
| `test_nav.py` | the graph is consistent; the guard lets the plugin's own actions through and refuses the forbidden ones (`python3 -m unittest test_nav`) |
| `test_watchdog.py` | the watchdog's rules on virtual time: timings, alerts said once, caps, the lease, a gateway restart, the profile, after a mode's end, one scenario per mode; its Wait on the ANR dialog (`python3 -m unittest test_watchdog`) |
| `test_font.py` | the pixel font on the fixtures it was cut from: every text read back, close letters apart by a margin, the 89 soul weapons' and the regions' names through render then read, the glyphs still drawn as `docs/TODO.md` lists them (`python3 -m unittest test_font`) |
| `test_screen_model.py` | the screen model on crops of real captures: every registered screen and overlay from its fixtures with a margin over every other one, the confusion across all fixtures, unknown on images of no screen, the screens pending capture as `docs/TODO.md` lists them, one pass per capture under 20 ms, the tree of every screen: allowed moves only, measured scroll areas (`python3 -m unittest test_screen_model`) |
| `test_scrolling.py` | `scrolling` on a scripted list: found, the end, back to the start, every swipe a slow one through the guard (`python3 -m unittest test_scrolling`) |
| `test_screens.py` | `screens.classify` on synthetic screenshots drawn from the areas it reads, the battle and Power Saving Mode from their fixtures (`python3 -m unittest test_screens`) |
| `test_trace.py` | tests of `trace.py` on synthetic screenshots (`python3 -m unittest test_trace`) |
| `test_engraving.py` | `engravings.json` is well formed and its variants fill their patterns; rotations, the gold layout, the pieces needed (`python3 -m unittest test_engraving`) |
| `test_souls.py` | the counters' notation (abbreviated and full digits), the souls row and the shaded gold counter on crops of real captures (`fixtures/souls_row*`, `gold_parked*`), the rates' windows (abbreviated, full digits, spending left out) (`python3 -m unittest test_souls`) |
| `test_soul_weapon.py` | the Soul Weapon readers on crops of real captures (`fixtures/sw_*`; the Equip tag's capture test is skipped until one exists, the Unequip one reads a real capture), its rules, and the sequence on a scripted game through the guard, the engraving setup included (`python3 -m unittest test_soul_weapon`) |
| `test_gates.py` | every gate on a reading (`*_LEARNED`, `*_TELLS`, `*_CALIBRATED`) is listed with the real-capture fixtures of each state it tells apart; an open gate missing one fails (`python3 -m unittest test_gates`) |
| `test_engraving_screen.py`, `test_engraving_setup_rules.py` | the engraving screen's readers on crops of one real capture (`fixtures/eg_*`) and the setup's rules on its readings (`python3 -m unittest test_engraving_screen test_engraving_setup_rules`) |
| `test_mine.py` | the mine on a scripted game, on virtual time, through the guard: an untick that will not take, the mine turned off and on in one tick, its taps waiting for the lease (a user input, an outside holder), an input with the game away not waited for, the lease's routes and expiry, the free-play warning (`python3 -m unittest test_mine`) |
| `test_switch.py` | a mode switch on virtual time with the phone's step latencies: under 60 s from a radio change, the timer's end switching back on time with no watchdog, the lease's wait said apart, one alert over budget, the hold while you play (one alert, resume now, free play instead, refused with nothing on hold) (`python3 -m unittest test_switch`) |
| `test_i18n.py` | English means English, a source lint of this plugin's page side and part 04's page: every French literal has its English entry, no entry is orphaned (a literal, or a template of `templates.json` or of part 04's `core/texts.py` TEMPLATES), both map each template to English with the same placeholders (`python3 -m unittest test_i18n`) |

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
several accounts: the launch stops with one error alert that says which
("Google sign-in failed: the chooser listed 2 accounts").

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
stage and its preset in under 60 s of the plugin's own time
(`SWITCH_BUDGET`), the plugin alone. It starts at its trigger: POST /mode
starts it at once, and the timed mode's watch wakes right at the timer's
end (`next_look`), not at the watchdog's next look. Each step waits for its
screen by polling fresh captures (`settle`: every 0.25 s, at most 4 s, 8 s
for a stage to load), never a fixed long sleep; the fixed waits left are
the controls' own (0.5 s for the unfold, 0.4 s between the two looks at the
gear, and their folding away by themselves). While the lease cannot be had
(the user played in the last 5 s, another holder), it tries again every
2 s; that wait is the user's, logged apart and never counted. Each switch
is one log line, e.g. `switch mpw4→mpw18 in 38 s (stage 24 s, preset 4 s,
soul_weapon 6 s) (+12 s waiting for the lease)`; over budget the switch still
completes, and one alert names the slowest step. Should a real switch go
over, the number of Select Region moves is what to cut, never the waits
that make each tap safe.

Expected on the phone (not measured yet): a capture about 0.6 s, an adb
tap about 0.4 s, Select Region about 1.2 s to open, a stage about 4 s to
load. With these, `test_switch.py` gives 29–31 s: the stage 15–17 s (one
region arrow and a few scrolls), the preset 14 s (two readings of the
badge, each waiting for the controls to fold away).

### Parking

While mpw18 or mpw4 farms, its idle place is the Soul Weapon screen: the
battle goes on above it, and the souls counters show (souls per second).
It is a navigation, never a tap inside the panel: the switch's last step
(`park`, counted in its 60 s) and the soul weapon step leave the screen
open, reached by Equipment, the Weapon tab and the Soul Weapon icon, the
soul weapon step's own moves. The watchdog takes that screen for the
battle (its stage numeral, preset and progress bar read there; the
controls are not unfolded there, so AUTO reads unknown) and the plain
battle for the symptom « hors de l’écran Soul Weapon », whose repair goes
back (after a relaunch, a stage change, a preset change: every repair
that leaves it), alerted only after 8 looks. Any sequence that needs the
battle leaves it first by its red X, then the panel's tab. Never in free
play, the mine, while a switch runs or is on hold, nor with the soul
weapon switch off; entering free play or the mine leaves it (unless the
user plays: then nothing is touched).

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
  chooser stay alert-only: the watchdog never taps them (not mapped yet)
  and raises one error alert, "not catalogued yet".
- Screens are recognised from a few pixel areas measured at the page's
  device shape (19.5:9, e.g. 480×1040). Another shape may stop the launch on
  "unexpected screen" (an error alert naming the screen read).
- `stages.json` comes from the community wiki slayerlegend.wiki (datamined
  stage table, stages 1–1,360) and, for soul colours, namu.wiki and player
  guides; read 2026-10-18 and not checked in game. Soul colours past stage
  320 are deduced from the green, blue, red cycle every 20 stages (`soul_colour_confirmed`);
  the page shows the colour without saying so. Stages above 1,360
  show only their number.
- The counter font sizes come from screenshots of the game; a game update
  that changes its top bar can break the emerald rewrite (the panel then says
  "non détecté").

## Game state and resources

The Resources section contains diamonds, gold, emeralds, cubes, crystals,
green/blue/red/white souls, dice, green/blue/red/yellow stones,
white/green/purple/black feathers, Dragon Power, Dragon Spark and Black Mana.
Counters show the last observed value and observation time. Unknown values
are not zero. Gold and souls have calibrated readers; the other counters
remain pending calibration. Gold and soul icons are game crops; the other
symbols are vector illustrations. Each soul colour retains its own observation
time even when another colour cannot be read.

Other state sections follow the access paths in `screen_registry.json`.
All catalogued screens are listed, including screens whose state reader is
still pending. This catalogue does not imply complete state recognition.
`05-plugins/scripts/verify.sh BASE_URL` checks the installed resource and
navigation response without interacting with the game.
