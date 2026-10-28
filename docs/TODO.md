# Known bugs

## Active acceptance checklist

This list tracks requested outcomes, not the number of patches or captures.
An unchecked item stays open until its whole user-visible path is verified.
Implementation, automated tests, deployment and in-game verification are
separate milestones. Historical checked items below do not close a new regression.

### Immediate priorities

- [ ] Validate independent server capture, priority recognition, bounded readers
  and deferred archives with the browser closed. Measure frame age and actual
  screen transitions; HTTP response time alone is not recognition latency.
- [x] Stop and drain plugin background work before shared capture/analysis
  services close, including shielded readers and in-flight commands. Verify
  with the app lifecycle and production gateway restart; Android stays running.
- [x] Give every non-default mode a finite deadline and return to the default
  on expiry. Verify the actual Agent countdown, expiry to mpw18 and enlarged
  lowercase default label in desktop and mobile browser views.

- [x] Keep mode and timer visible when Gold/soul readings are absent, stale
  or failing; verify the actual browser overlay with a running timed Agent mode.
- [ ] Observe Free play navigation with trustworthy before/after captures and
  refresh visible readers on user-driven screen changes, including fast visits.
- [ ] Recognise the Title screen from a calibrated visual title landmark;
  distinguish screen-identification regions from navigation buttons.
- [ ] Add manual screen capture and wrong-screen reporting to navigation debug,
  preserving detected and user-declared identity with the screenshot.
- [ ] Show weapon/hour only on an observed weapon-drop stage and accessory/hour
  only on an observed accessory-drop stage; never infer this from mode alone.
- [ ] Restore hourly counters end to end: gold, cubes, green/blue/red souls,
  L3 weapons and L3 accessories. Read real changes, calculate per hour, show
  correct values and icons; no stone or white-soul rates. Verify farming,
  menu transitions, user inputs, spends/resets and stream reconnection.
- [ ] Finish automatic Soul Weapon selection and engraving for each farming
  target. Verify the actual weapon and pattern before acting; no successful
  status until the requested setup is observed in the game.
- [ ] Always select the highest-level eligible engraving pieces of the same
  shape; an option bonus must not outrank level. Replace an already placed
  lower-level piece. Unreadable levels cannot establish the best choice.
- [ ] Relock every removed engraving piece, verify locks after placement,
  and confirm all eight locks before closing. Preserve recovery after
  interruption; resume only with current identity and readings verified.
- [x] Obtain real Equip/Unequip calibration evidence: owned, unequipped
  Relax supplies Equip; equipped Ambition supplies Unequip. Read-only
  navigation produced the evidence; no Equip or engraving action was run.
- [ ] Complete the first supervised equipment/engraving run required by
  part 05, including actual target, highest-level choices and eight locks.

### Mode, interface and notifications

- [ ] Separate the persistent mode/consigne, execution status and current
  intention (destination and purpose). A scan excursion is normal activity,
  followed by a planned return; it is not itself a failure of the mode.
- [ ] Show the complete calculated path for a new redirection. Notifications
  name the destination, reason and outcome; replace opaque "repair" wording
  and suppress repeats of the same attempt without hiding real blocking errors.
- [ ] Simplify plugin options: editable target and one actionable status,
  nested game menus, separate resources/analysis/display, technical details
  folded. Avoid duplicate confirmations and implementation jargon.
- [ ] Keep the game overlay to mode plus timer/default: white/green when
  stable, blue during user control and the renewed five-second pause, orange
  while returning to the target, red only for an actual blocking condition.
- [ ] Confirm an expected overlay failure is visible in the web app and ntfy.
- [ ] Distinguish local draft, server-accepted target and observed result;
  handle rejected writes, deadlines and concurrent viewers without false success.

### Exhaustive screen and resource coverage

- [ ] Audit every reachable authorised screen with separate evidence for
  archived capture, recognition, navigation, scroll positions and live readers.
  Keep explicit reasons for unavailable data; a capture alone is not coverage.
- [ ] Complete Companion including Beasts, Advancement and all three passive
  panels for each companion; Skill; Adventure and region selection; Character
  EXP; Equipment, weapons, accessories, classes and Black Orb/Obtain feathers.
- [ ] Complete the requested resource catalogue with real icons and readings;
  compact one-line rows, aligned icons, timestamps on the right in grey,
  freshness white to light blue. Keep unknown values as `never read`.
- [ ] Schedule guarded data refresh excursions during farming and observe user
  navigation; persist examples and return to the mode's intended idle screen.
- [ ] Verify annotation capture for allowed/forbidden taps, scannable rectangles,
  vertical/horizontal sliders, before/after previews and visible feedback.
  Track which annotations have actually improved recognition/navigation.
- [ ] Verify fast screen-change detection, full/minimised/dimmed Battle,
  implicit return via combat, separate settings-arrow positions, and zones
  tracking scroll. Debug controls remain movable and minimisable.
- [ ] Preserve the prohibition on the top-right menu, Mailbox, Settings,
  Rankings, AUTO and other forbidden navigation/actions.

### Setup verification findings

- [x] Verify the native-height Unequip tag after the automatic route reaches
  Ambition. Calibrate the real nine-row tag with a reviewed crop, retain
  strict Equip/Unequip separation and verify the installed automatic path.
- [x] Inspect the live server observation metrics after deployment: bounded
  reader lanes, no recorded analysis/archive errors in the sampled interval.
  The browser remained connected; the browser-closed acceptance stays open.

- [x] Calibrate an additional real Ambition engraving header and cards:
  distinguish the narrower m, neutral level text over coloured crystals,
  the narrow 7 and the red T facets. Keep name/digit confidence thresholds.
- [x] Verify the calibrated Ambition reader through the installed automatic
  setup pipeline: stage 970, preset IV, Ambition Gold-maxed, eight closed
  locks and final Unequip proof. Recorded acceptance: 17.1 seconds for Soul
  Weapon, including 10 seconds engraving inspection and two navigation taps.
  No piece needed moving; removal, replacement and relocking acceptance
  remains open and must not be inferred from this already-correct setup.
- [x] Calibrate actual Soul Weapon name glyphs from Honor, Ecstasy, Friendship,
  Skilfulness and Relax. Keep ownership-zero refusal and identity ambiguity gates.
- [ ] Verify complete live list search and scroll endpoints before certifying
  automatic equipment selection; the first whole row can lie above the scroll lane.
- [ ] Retry an unchanged accepted configuration explicitly, under the current
  mode/revision and existing input lease; never report a queued attempt as ready.

- [x] Reproduce stale weapon identity during engraving: a changed name
  previously allowed further gestures and a ready result. Bind every raw
  reading, gesture and final verification to the expected weapon; stop with
  recovery required on missing or changed identity.
- [x] Require a fresh Soul Weapon/selected-target/Unequip read after engraving
  before publishing equipment facts or caching a successful setup.
- [x] Reject a red dragged piece as evidence of preview controls. The real
  negative capture is retained with its corrected identity, and both valid
  and invalid preview bars remain recognized.
- [x] Expose actual configuration blockers in the existing status row.
  Bind current attempt results to mode, target revision, timestamp and
  unchanged input/relaunch context; a saved target is not observed readiness.
- [x] Verify release `8386455`: 691 Python tests pass without skips, seven
  browser-module suites pass, exact-commit build and shell checks pass.
  Installed backend/browser files match the commit; live browser options
  show the real disabled-engraving blocker and no successful attempt.
- [ ] Complete the supervised game execution. Mocked transactions and
  read-only calibration do not establish the final in-game setup.

### Calibration follow-up

- [x] Keep the Cube number at the fixed average Gold anchor; regression
  coverage checks that Gold width changes do not move it, and that a valid
  rate advances the Cube total on each one-second tick.
- [x] Add real native Cube glyph evidence for the previously unread zero
  variant, without relaxing ambiguous-digit rejection.
- [x] Verify the new Cube reader and dated hourly model together in production:
  release `b4dac8a`, two new acquired readings produce a positive rate;
  the browser displays five increasing estimates at the same fixed position.
  This does not certify the still-pending automatic refresh circuit.
- [ ] Complete the first supervised resource circuit before enabling its
  automatic cadence. Calibration flags alone do not establish this first run.
- [x] Complete Equip calibration on the real owned Relax capture, including
  the bright owned-cell border and rejection of a clipped top cell.
- [ ] Complete supervised engraving and the first real Equip action when
  needed; a calibrated reader does not itself prove a successful operation.

### Counter presentation and release evidence

- [ ] Verify cube balance: actual game font, black outline, gold-aligned number,
  icon between the two gold-icon positions, separators, fixed position and
  one-second estimate derived from a valid rate; freshness colour preserved.
- [ ] Verify compact right-edge hourly rows with icons close to values, only
  on full/minimised combat, dimmed with the game. Abbreviate resources and
  hourly values; keep cube balance unabridged.
- [ ] Correlate stream connection failures/freezes with existing telemetry,
  including cases resumed by a hardware-key input, and verify the actual fix.
- [ ] Pass relevant unit/browser checks, build, push, deploy and check the
  served version. Keep live gameplay verification distinct from mocked tests.
- [x] Send ntfy for each production release with explicit sender
  **Agent Codex — déploiement**, version, shipped changes and verification
  outcome; report a failed release as failed. This is an agent announcement,
  not a CloudPhone or plugin alert.

Work stages for the current implementation batch:

- [x] Integrated regression suite passes after the final changes: 647 plugin
  tests (one real Equip calibration test still skipped), 20 gateway tests,
  browser-module suites and the additional fixed-cube regression.
- [x] Release containing the implementation commits `9bdd047` and `0c099a9`
  is built and deployed; app/plugin verification and served-source checks pass.
- [x] Browser behavior on that release is verified for rejected stop, complete
  target Apply, request deadline/reconciliation and dated lock evidence.
  Browser writes are intercepted; these checks do not validate live equipment changes.
- [ ] Soul Weapon/engraving, counters and mapping acceptance above are verified
  against actual gameplay, with remaining gaps still listed explicitly.

Follow-up release evidence:

- [x] `b4dac8a` passes 675 plugin tests (one missing Equip-fixture skip),
  seven browser-module suites, plus 31 focused tests after the acquisition-time
  and initial-sampling fixes. Shell checks and the exact-commit build pass.
- [x] Plugin deployment, read-only verification and served-source comparisons
  pass. Real Cube readings produce a new rate after restart; browser checks
  confirm a stationary number anchor and increasing one-second estimates.
- [x] Six additional private calibration examples are persisted; the weapon
  detail and Soul Weapon variants are referenced by the screen catalogue.
- [ ] The resource circuit's first supervised run and the engraving first run
  remain pending. Their inactive state must not be described as completed
  automatic gameplay; Equip was still uncalibrated in that release.

## CloudPhone Slayer Legend work in progress (2026-10-26)

- [x] Deploy five modes, with Free play first and Agent mode last.
- [x] Show `never read` for resources and screens without a reading.
- [x] Bind each engraving grid to the weapon read on that capture; discard old grids without an identity and verify Relax's pattern.
- [x] Show the highest observed stage as a lower bound; gray later stages while keeping them selectable.
- [x] Deploy and verify the engraving and stage fixes.
- [ ] Capture and persist one reviewed example for every reachable screen in the navigation graph.
- [x] Show archived examples and their observed details in the plugin's nested screen menus; remove empty `Données` rows.
- [ ] Turn the historical details into live readers where a changing value matters; a dated capture is not a current value.
- [ ] Calibrate the full-digit gold reader and restore gold/s measurement.
- [ ] Replace remaining placeholder resource icons with verified game icons and add readers for the unread resources.
- [ ] Alert in the web page and through ntfy when an expected overlay is absent.
- [ ] Let Agent mode explore approved screens between farming checks, then return to the selected mode under the navigation guard.

The 2026-10-26 tour has stored private full-screen examples for Character,
Skill, Equipment, Companion and Beast, including Promotion and equipment
scroll positions and all five Companion Advancement tiers. The `example`
paths in `screen_registry.json` identify those captures. A screen below may
still be listed as pending because its classifier crop has not been calibrated;
the full-screen image can already exist.
The Dungeon map's Dragon Valley label was checked twice on 2026-10-26: it
opens Airfield, whose red back arrow goes to Guild Hall. The old Raid camp
route is historical and remains unvisited until a current entry is found.
The later Adventure/Dungeon pass captured Story, quests, all five visible
dungeon destinations, and Closed Mine through the feather choice; no
episode, dungeon entry, or feather button was activated.
Audit of the 100 archived PNGs: each is referenced by `screen_registry.json`
and every `visit: true` node has an example. The Soul Weapon and Closed Mine
list scrolls still need before/after images in this archive; their gesture
coordinates come from the existing navigation graph.

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
- Slayer Legend Equip tap (`TAG_LEARNED`): calibrated on the owned Relax
  Equip capture and Ambition Unequip captures (2026-10-28). No actual Equip
  tap has been made for this calibration; its first supervised action remains
  pending. The whole farming preflight still refuses setup while engraving
  is off. The red sword badge is not equipment proof: owned, unequipped
  Relax displays it too, so `BADGE_TELLS` remains false.

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

## Slayer Legend: every feature reads the game's state

The scan (`features/game.py`) is the one producer of game facts; each
feature should read the state (`game.get`, `game.require`, `scan(shot,
force)`) instead of its own pixels. Already on it: the gold and souls
rates, the highest stage, the watchdog's stage, numeral and progress bar,
`/screen`'s stage. Still reading pixels on their own, in this order:

1. the watchdog's screen naming (`screens.classify`, `known_name`,
   `plain_battle`, `other_name`) and its preset and AUTO read
   (`stage_change.read_controls`: two frames on one unfold, a reader of
   two captures to add to the scan);
2. the stage change's looks (`select.view`, `select.battle_stage`,
   `controls.badge`, `controls.selected`, `controls.controls`), each a
   check after its own tap: `scan(shot, force)` on the settled capture;
3. the soul weapon step (`soul_weapon.view`: name, owned, tag, rows,
   badge) and the engraving setup (`engraving_screen` grid, cards, popup,
   preview);
4. the mine (`mine.in_fight`, `repeat_ticked`, `gold_scroll`, `floors`,
   the pop-ups) once its screens are registered;
5. the launch (`screens.classify`, `sign_in`, the save notice) and the
   mode's gold scroll look (`gold_scroll.seen`);
6. `/screen`'s screen name and panel, `/emerald-mask`, the trace's
   signatures (kept apart: they serve the page and the trace, not the game
   state).

Game state values with no reader yet (schema entries marked pending in
`features/game_rules.py`): the emerald and diamond counts (the page reads
only the digits after the comma; a reader of the whole count in the pixel
font is to write from the top bar's crops), the mine's feathers
(`mine.feathers_left`, row 9 below), and the mine's floor and area read on
its screens (only noted by the mine's own entry until `mine_list` and
`mine_area` are registered).

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
| 12 | **Power Saving Mode**, only if it appears naturally; never open the forbidden top-right menu or Settings. Capture, then hold the calibrated exit button 4 s to leave. | Power Saving stage number and name only → `saver_number`, `saver_name` | `stage.py` DIGITS |
| 13 | Toasts and pop-ups, whenever one shows during the session: the **Better Soul Weapon** toast (over the battle and over an open panel), event, offer, maintenance, update required | the toast (334, 328, 146, 60) → `toast_better_weapon_2`, `toast_over_panel`; a pop-up's title and buttons only, never its body if it shows an account | `screens.better_weapon_toast()` (second occurrence: its text is cap 7 and not read yet), part B's catalogue of named screens |
| 14 | Optional, the user's call: open the game on the user's own phone for a minute, then back here: the **connected on another device** screen and, after it, the **choice between two saves** | title and buttons only (no account, no save ids) → `other_another_device`, `other_save_choice` | part B's catalogue; **no move** on them until `05-plugins/AGENTS.md`'s precondition is validated by the user; the user resolves them on the device |
| 15 | The screens with no crop yet, look only, each reached by its allowed move in `navigation.json` and closed by its X: Character **Promotion** tab, a **weapon's detail** (a weapon cell in Equipment), Equipment **Accessories** and **Relic** tabs, **Black Orb** and an accessory's card in it, **Spirit**, **Beast**, Adventure's **quest** pop-up, **Dragon Valley** raid camp, **Guild**, the **Quest** panel; and whenever they show: **Loading**, the **title** screen and the **save notice** (both at a relaunch), the mine's **fight** (row 9), the **quit dialog**; **never** a Promotion bonus page (no move there) | each screen's title or tab row, full width, its y measured on the capture → `screen_<id>` (the `navigation.json` id); the title screen’s SLAYER LEGEND logo (bounds measured on an authentic capture), independently of TAP TO START → `screen_title`; the save notice's two buttons (100, 750, 280, 40) → `screen_save_notice` | `screens.look()` (`screen_registry.json`): each one registered from its crop, else pending capture and never matched |
| 16 | Back to the battle: every panel closed, stage of mpw18, preset III, AUTO on (the gear spinning); the plugin back on **mpw18 farming** | none | the watchdog says OK within a minute |

Screens pending capture: `title` `loading` `character_enhance` `character_growth` `character_promotion` `skill` `skill_refinement_grounds` `skill_rave_mantra` `familiar` `equipment_relic` `spirit` `companion` `companion_advancement` `beast` `beast_mount` `beast_scouting` `beast_scouting_info` `adventure_map` `adventure_quest` `adventure_story_main` `adventure_story_easy` `adventure_story_sub` `adventure_story_ellie` `dungeon_map` `dungeon_shelter` `dungeon_rift` `dungeon_forest` `dungeon_kingdom` `dungeon_training` `raid_camp` `mine_list` `mine_area` `mine_feathers` `mine_fight` `top_menu` `scroll` `shop_summon` `shop_package` `shop_goods` `shop_golden_key` `shop_event` `guild` `guild_divine_beast` `guild_shop_normal` `guild_shop_appearance` `airfield` `airfield_recipes_appetizer` `airfield_recipes_main` `airfield_recipes_dessert` `airfield_boarding_status` `guild_request` `guild_info_basic` `guild_info_members` `promotion_bonus` `quit_dialog` `black_orb` `black_orb_accessory` `black_orb_obtain` `top_ranking` `top_settings` `top_mail` `character_growth_icon_1` `character_growth_icon_2` `character_class` `equipment_weapon_icon` `equipment_relic_icon_1` `equipment_relic_icon_2` `raid_ranking` `raid_bag` `shop_summon_equipment` `shop_summon_relic` `quest_daily` `quest_repeat` `quest_achievement` `event` `top_achievements` `top_collection` `top_events` `top_guild_entry` `event_popup` `daily_reward` `offer_popup` `maintenance` `update_required` `another_device` `save_choice`.
`screen_registry.json`'s tree says how each is reached; `tour.py` visits the ones it may and the discovery mode saves the others when they show; `screens.look()` never names them until then.

Character → Enhance/Growth shows EXP as current / required at x≈110–278, y≈627–639 on the 480×1040 captures. `fixtures/character_exp_{enhance,growth}.txt` retain only the counter. Its tiny, touching digits defeat the existing pixel-font reader, so EXP remains `never read` until a reader validates both exact integers. Black feathers are reportedly under Equipment → Accessories → Black Orb → Obtain, but `black_orb/obtain` is forbidden because it may spend Black Orb; no Obtain capture exists, and `feather_black` remains `never read`.

Companion → Ellie, Zeke, Miho, Luna → PASSIVE, PASSIVE II, PASSIVE III holds nine passive levels per companion (36 values). No identified capture of these 12 screens exists yet; `screenshots/companion.png` is a battle view without the Companion panel. Map safe entry and return moves, capture every tab, then calibrate the level reader before exposing values.

Quest is calibrated from privacy-reviewed title and tab-text crops of real manual annotations: `quest_title`, `quest_tabs_daily`, `quest_tabs_repeat`, `quest_tabs_achievement`. The named overlay is `quest_panel`; the scan reports its active tab as `quest_tab`. Opening animations, missing titles and ambiguous active tabs remain unidentified. Quest progress values, completed reward bars and Claim are not calibrated by these crops; no reward action was authorized or added. The separate tree entries `quest_daily`, `quest_repeat`, `quest_achievement` remain aliases beneath this panel, not standalone classifier screens.

Screens recognised without a fixture: `save_notice` `panel`.
Their areas were measured on real captures never committed; rows 2 and 15 take their crops.
`panel` checks the dark bottom-menu names and the absence of the blue battle mana bar. The plain battle also has grey menu names, so those names alone cannot identify a panel.

Already captured (2026-10-22, upstream): the engraving card with an open padlock
(`eg_cards_unlocked`, `eg_cards_relocked`), its piece pop-up and the drag
preview; nothing more to take there.

Not in the session (they come when they come): the maintenance and update
required screens, and the event and offer pop-ups if no relaunch shows
them; their crops go in on the next sighting, same rule.
