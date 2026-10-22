# Known bugs

Tests of the black-box suite (`tests/e2e`) that fail on the current code,
each with what is known. Owner: the agent maintaining the gateway and the
page; fix or explain each before the hexagonal refactor reaches its domain.

None at the moment.

## Game incidents

- 2026-10-21, Slayer Legend: a guarded tap meant for the small arrow on
  the battle screen's right edge landed on the AUTO gear and turned AUTO
  off. Cause: the arrow unfolds the preset badge and the AUTO gear, which
  fold away again after about 2 s; a guarded tap (guard, then the ssh/adb
  round trip) arrived after the fold, on the gear. AUTO was turned back
  on the same night (gear spinning, skills on cooldown). Fix: unfold and
  next tap in one adb call, both guarded first, only when a fresh capture
  reads the controls folded. Since 2026-10-22 (the user's order) the AUTO
  button is never tapped at all (forbidden in navigation.json): a stage
  progress bar that stops moving is an error alert instead.

- 2026-10-21, Slayer Legend: the plugin equipped the soul weapon Vision in
  mpw18 by itself (the user saw the result) while the Equip tag reader had
  never read a real tag (its two fixture tests were skipped). No supervised
  run up to Equip was recorded; the run's records were not collected. Fix:
  Equip is planned only once fixtures/sw_tag_equip.txt and
  sw_tag_unequip.txt exist from real captures; until then the step raises
  an error alert and does not equip.

## First real runs of opened gates

Each gate on a reading (`05-plugins/AGENTS.md`) has its first real run
made with the user present, recorded here: date, readings, result.

- Slayer Legend engraving lock and swap (`PADLOCK_LEARNED`,
  `POPUP_LEARNED`, `PREVIEW_LEARNED`, opened 2026-10-22 on the captures
  eg2–eg10): to run with the user present (Vision, Atk to Gold-balanced),
  then recorded here. Until then the engraving switch (`POST /farming`
  `{engraving}`) stays "off" (its default: no lock, removal, placing or
  preview, an error alert "engraving not set up: first supervised run
  pending", the weapon not ready); it goes to "real" only with the user
  present, for that run.
- Slayer Legend Equip tap (`TAG_LEARNED`): closed until the Equip tag is
  captured.

# Planned work

In order of value. One worktree per track; never two black-box suites on
the machine at once (wrap `cargo test` in `flock` on one shared lock file).

1. fps uptime run (planned for 2026-10-20, with the emulator up about 24 h):
   steady state first; then relaunch the game only, wait the settle time,
   measure; then restart the emulator, relaunch, wait, measure. Same scene,
   same regime, three numbers: they say whether a scheduled game relaunch
   or a scheduled emulator restart (with no viewer connected) restores the
   frame rate. A relaunch costs about 5 minutes near 20 fps plus sign-in.
   Step 1 on 2026-10-20 03:07 found the game in Power Saving Mode (emulator
   up 23 h 08, game 22 h 25), so the battle reading waits for one guarded
   hold. Read-only reading of that scene instead, 180 s from 03:08, no
   baseline: 20.8 fps mean, p50 20.7, worst 10 s 19.9, UnityMain 98.6 %,
   host idle 33 %.
2. fps B7: the game's 30 fps cap through Game Mode (`cmd game set --mode 3
   --fps 30`), measured in both regimes (the first 5 minutes, where the
   paced steps become 30/15/10, and steady state); the worst-10 s column
   decides.
3. What the viewer sees: the browser's inbound-rtp stats (framesReceived,
   framesDecoded, framesDropped, framesPerSecond) beside SurfaceFlinger
   timestats in the same 60 s, on a battle and on a light screen. Needs the
   page open in the user's browser.
4. Hexagonal refactor: gateway domains (display next, with
   `adapters/host_files.py`), then the page, then the plugin.

# Pixel font: what is left

`05-plugins/slayer-legend/pixel_font.py` is cut from the fixtures by
`font_cut.py` (each glyph the average of at least two occurrences;
`fixtures/texts.json` holds the texts). `test_font.py` checks the lines
below; shrink them to nothing with the calibration captures (next
section), then run `python3 font_cut.py --write`.

Glyphs not cut yet: `B` `D` (drawn).

Read wrong at one size: `0` in `sw_owned_0` (reads O: the only small 0; capture 10's
Owned : 0 of another weapon gives a second one), `U` in `sw_tag_unequip` (reads u:
narrower than AUTO's two U; capture 10's tags give a second one).

Characters seen once: `1` `B` `H` `P` `b` `k` (a second occurrence cuts them).

Never seen: the capitals `F` `J` `L` `N` `Q` `Y` `Z`, lowercase `j` `x` `y`
`z`, the digits `5` `6` `8` `9`, and `-` `!` `?` `,`.

Not unified, on purpose: `stage.py`'s DIGITS (Power Saving Mode's "STAGE
920") are another face, 10 px high with 2 px strokes and no lowercase, so
they cannot share the font's CAP/ROWS grid, and no fixture of that screen
exists yet: capture 12 below gives one, and a second `font_cut.py`
texts file for that face can then cut them. `engraving_screen.py`'s
level digits (5 x 8, "Lv.NN") are the same case: the cards' crystals
overlap them in `eg_cards`, so they are not cut from it either.

The « Better Soul Weapon / Equip » toast's text (cap 7 px, a dark outline
merging the letters) is not read: the toast is told by its colours.

# Calibration captures (one session, about 20 minutes)

The plugin's readers that stay alert-only or plan-only until a real capture
calibrates them, and the pixel font's missing letters, all wait on the
captures below. One session takes them all, in this order, and ends with
the game back on mpw18 farming. Full screenshots stay in the scratchpad
and are deleted after; only small hex crops (`fixtures/*.txt`, the
`fixtures/` header format: screen size, crop origin, size) are committed,
each checked by eye: no account name, id, guild or chat in the crop.
All crops are at 480x1040, in pixels (left, top, width, height).

Before: the plugin on **Jeu libre** (free play), so that the watchdog
neither repairs nor alerts during the session; the game on the battle
screen, stage of mpw18, preset III, AUTO on. Two captures of the same
state, 0.5 s to 2 s apart, everywhere a reader needs two frames or a
glyph needs two occurrences.

| # | Screen to reach (how) | Crop(s) to take | Consumed by |
|---|---|---|---|
| 1 | Battle, plain, farming: the yellow progress bar in the middle of the screen | the bar's row, full width (0, y, 480, 16) with y measured on the first capture: 2 frames about 10 s apart while it advances → `battle_progress_1`, `_2`; and one while it is stalled, whenever it is seen stalled (opportunistic, never provoked: the AUTO button is never tapped) → `battle_progress_stalled` | the stalled-progress alert (another agent's work, replacing the AUTO tap) |
| 2 | Bottom panel **Character** (Enhance tab), then its **Growth** tab | each: menu labels (0, 1010, 480, 28) → `menu_labels_character`; panel tabs row (0, 548, 480, 22) → `panel_character_tabs`, `panel_character_growth_tabs` | `screens.open_tab()` per lit tab, the watchdog's `back_to_battle` (alert-only until every panel is classified); font: "Enhance Growth Promotion", "LEVEL UP" |
| 3 | Bottom panel **Skill** | menu labels → `menu_labels_skill`; the "Skill" title and Skill Proficiency line (0, 560, 480, 40) → `panel_skill_title` | same; font: k, f, y |
| 4 | Bottom panel **Equipment**, Weapon tab | menu labels → `menu_labels_equipment` (`sw_tabs` is already the tabs row) | same |
| 5 | Bottom panel **Companion** | menu labels → `menu_labels_companion`; tabs (0, 470, 480, 30) → `panel_companion_tabs` | same; font: B (Beast), k |
| 6 | Bottom panel **Shop** (Summon tab), look only | menu labels → `menu_labels_shop`; tabs (0, 445, 480, 30) → `shop_tabs` | `screens.open_tab()`; font: P, k, y, K |
| 7 | Bottom panel **Adventure** (Adventure tab) | menu labels → `menu_labels_adventure`; tabs row "Adventure Dungeon Guild" with the feathers count (0, 245, 480, 30) → `adventure_tabs` | `mine.adventure_open` (None until then: the mine's way back in stops before its first tap), `screens.open_tab()` |
| 8 | Adventure → **Dungeon** tab (wait 5 s) | tabs row again, Dungeon lit → `dungeon_tabs`; the "Closed Mine" label on the map (100, 640, 200, 30) → `dungeon_closed_mine` | `mine.dungeon_open` |
| 9 | Dungeon → **Closed Mine** → a floor row → **Area** pop-up → an Area → **feathers** pop-up; then close each with its X, **no feather tapped** | floor list title (180, 64, 120, 20) → `mine_list_title`; area row (60, 900, 360, 30) → `mine_area_row`; feathers pop-up buttons and count (48, 760, 384, 60) → `mine_feathers_2`, the same at another count when one is seen → `mine_feathers_1` | `mine.feathers_left` (None until then), `mine.feather_popup`, `test_mine` |
| 10 | Equipment → Weapon → **Soul Weapon**; select each of the 89 weapons in the left list one by one (a cell's upper part, never an orange tag), scrolling the list slowly | per weapon the card's name (199, 610, 207, 44) → one `sw_name_<name>` each; also once the "Equip Effect" line (199, 650, 207, 24) and the Craft/Harvest button text (150, 860, 150, 30); on an owned weapon not equipped: its orange Equip tag (0, 590, 90, 100) → `sw_tag_equip` and its card's sword badge (408, 608, 34, 42) → `sw_badge_owned_grey`; **never** Equip, Unequip, Craft, Harvest, Breakdown | the gates `soul_weapon.TAG_LEARNED` and `BADGE_TELLS` (`test_gates.py`), test A3 (render/read round trip on the real names), `soul_weapon.name()`, the font's remaining letters (every capital and most lowercase of `engravings.json`) |
| 11 | Close back to the battle; open **Select Region** (stage map button); browse the regions with the banner arrows (no Move), 39 regions | each banner (120, 307, 240, 31) → `banner_<region>`; the first row of a few regions (48, 429, 278, 29) | test A3 on real region names, `stage_select.banner()`; letters of `stages.json` names (B, D, F, H, K, L, M, P, U, Y, f, k, m, p, u, y, z, -) |
| 12 | ≡ top menu → **Settings**, look only; then ≡ → **Power Saving Mode**, capture, hold the button 4 s to leave | Settings title and its labels (0, 100, 480, 300) cut into line crops; Power Saving: "STAGE 920" (96, 382, 288, 26) → `saver_number`, name (48, 409, 384, 30) → `saver_name` | font letters; `stage.py` DIGITS (cut its 10 digits from real captures, see the font note below) |
| 13 | Toasts and pop-ups, whenever one shows during the session: the **Better Soul Weapon** toast (over the battle and over an open panel), event, offer, maintenance, update required | the toast (334, 328, 146, 60) → `toast_better_weapon_2`, `toast_over_panel`; a pop-up's title and buttons only, never its body if it shows an account | `screens.better_weapon_toast()` (second occurrence: its text is cap 7 and not read yet), part B's catalogue of named screens |
| 14 | Optional, the user's call: open the game on the user's own phone for a minute, then back here: the **connected on another device** screen and, after it, the **choice between two saves** | title and buttons only (no account, no save ids) → `other_another_device`, `other_save_choice` | part B's catalogue; **no move** on them until `05-plugins/AGENTS.md`'s precondition is validated by the user; the user resolves them on the device |
| 15 | Back to the battle: every panel closed, stage of mpw18, preset III, AUTO on (the gear spinning); the plugin back on **mpw18 farming** | none | the watchdog says OK within a minute |

Already captured (2026-10-22, upstream): the engraving card with an open padlock
(`eg_cards_unlocked`, `eg_cards_relocked`), its piece pop-up and the drag
preview; nothing more to take there.

Not in the session (they come when they come): the maintenance and update
required screens, and the event and offer pop-ups if no relaunch shows
them; their crops go in on the next sighting, same rule.
