# Part 05 — agent instructions: plugins

Default task: after part 04 converged, install the plugins with
`sudo 05-plugins/scripts/install.sh` (every plugin; or name them) or
`packaging/deploy.sh "$TARGET" 05`. Check:
`curl -fsS http://LISTEN_ADDRESS:WEB_PORT/api/v1/plugins` lists each one.

Rules:

- Free play reserves control for the user, including when the game is not
  in the foreground. An agent must not launch the game, switch to Agent mode,
  or run gameplay tests merely because the phone appears idle. A general
  authorization to develop/test/deploy does not override this mode. Use a
  user-selected Agent mode or an explicit request for the particular takeover;
  do not interrupt an active user session with a gateway restart for testing.
- Everything specific to one game or app lives in its plugin directory
  here, never in parts 03–04.
- A plugin never launches or restarts an app by itself: only on a user's
  press, never from a timer or a script. The one exception, asked by the
  user: Slayer Legend's watchdog relaunches the game while the selected
  mode is mpw18 or mpw4 farming or the Closed Mine (backing off after each
  failure: 1, 2, 4, 8, 16, then 30 minutes between attempts; never in free
  play or during a mode's entry, 5 s after a user input at the
  earliest, under the shared lease). In the mine the relaunch is followed
  by the mine's own way back in (below). No launch
  ever kills the app (`am start` without `-S`, no force-stop). On Android's
  "isn't responding" dialog the watchdog taps only "Wait", once, then
  alerts: never its "Close app", which kills the game.
- What Slayer Legend's plugin taps by itself: this list is exhaustive.
  Every move goes through the navigation guard (`navigation.json`) under
  the shared lease, on a fresh capture showing that screen; anything else
  stops the sequence with an initial alert. While a farming failure remains
  unresolved, read-only monitoring repeats its alert every 120 seconds;
  this reminder never authorises another gesture. Nothing outside the
  list below is ever tapped.
  - Launch:
    - If the process disappears during an authorised launch, two absent
      observations after the startup grace may reopen its normal activity,
      at most twice within the original three-minute deadline. Never kill
      a running process; uncertain ADB state permits no gesture or reopen.
    - "TAP TO START": on the title screen, at most every 8 s.
    - Confirm on the save notice: only when the notice shows (never Exit).
    - "Close app" on Android's crash dialog: found by uiautomator, at most
      2 times per launch.
    - "Sign in with Google": on the sign-in screen, once per launch; never
      "Sign in with Apple".
    - The account of Google's chooser: found by uiautomator, only when
      exactly one is listed and the launch's own tap opened the chooser.
    - "Press here to finish Power Saving Mode": held 4 s, at most 3 times.
  - Watchdog:
    - After the last game input, wait at least five seconds before farming
      menu recovery. Only Latent Power and Character Growth/Promotion with
      calibrated close readers get a second fresh observation shortly
      after that pause; the initial observation window, two-read threshold,
      shared lease and failure backoff remain required. Other menus keep
      their observation grace; Free play and Agent never trigger recovery.
    - "Wait" on Android's "isn't responding" dialog: once per dialog, never
      its "Close app".
    - The right edge's arrow that unfolds the controls, to read the preset
      badge and AUTO (AUTO only read, for the alerts): at most every 5
      minutes, whoever watches (only a user's input pauses it, 5 s),
      only while the preset switch is real.
    - Nothing for a stalled stage progress bar: an error alert only,
      repeated every 120 seconds while the stall remains unresolved.
      On battle or Soul Weapon parking, a bar unreadable for 120 seconds
      raises a recurring progress-unverified alert, never a claim of a
      stall and never an input. Other screens and user pauses reset this
      missing-reading timer.
    - During a mode entry, an independent read-only observer may check
      whether the process runs and repeat an unresolved critical alert
      every 120 seconds, even while a repair waits. It never takes the
      lease, launches the game, or performs an input; the entry sequence
      remains the only owner of its authorised moves. Free play and Agent
      mode keep automatic monitoring and reminders suspended.
  - Farming entry (mpw18, mpw4 and Soul Farming), including expiry of
    Free play's timer: before stage/preset/weapon setup, the entry coordinator
    checks the process and focus. A confirmed absent process or game away
    uses the existing bounded launch sequence under its own shared lease,
    without killing a running process. The complete setup runs afterwards,
    serially. Input, mode/loadout change or shutdown interrupts this entry;
    an unknown process or unknown focus for a running process never
    authorises a launch. Confirmed process absence suffices independently
    of focus. An already running
    launch is joined, never duplicated. Free play and Agent mode never
    initiate this automatic entry phase.
  - Stage change and preset (mode changes, a change of the running
    mode's loadout, and the watchdog's repairs,
    each only while its switch is real):
    - Closing Latent Power with its bottom-left red X: only when a fresh
      capture matches its fixed title, dragon-power instruction and X.
      One close only, then identify the exposed screen; an unknown return
      permits no further gesture. Never its tiers, stats, magnifiers,
      awakening, purchase or spending controls.
    - Closing Character Growth with its own Character tab: only when a
      fresh capture recognises Growth selected, reduced battle and the
      Character tab as the only lit tab. One close, then verify plain Battle;
      no stat +, LEVEL UP or sub-tab icon is authorised. The close-tab
      transition is calibrated by supervised gameplay; every return still
      requires its own fresh plain-Battle confirmation.
    - Closing a bottom panel with its own tab: only when that tab reads lit.
    - "Press here to finish Power Saving Mode": held 4 s, once per
      sequence, only when the screen reads Power Saving Mode.
    - Opening Select Region (the stage map button on the battle screen).
    - Select Region's region arrows: only while its banner reads one region.
    - Select Region's arrows and list scrolls: at most 10 moves for the whole
      sequence, arrows and scrolls together (`MOST_MOVES`).
    - Move: only on the row whose name reads as the target stage.
    - The preset badge: with the arrow that unfolds it, in one adb call,
      only when the fresh capture reads the controls folded and the badge
      reads another preset.
    - The preset's button in Battle settings: only once Battle settings
      reads open, and another preset reads selected.
    - Battle settings' close button: after its preset reads selected.
  - Soul weapon (last step of a mode change, after the preset, and once after a
    watchdog relaunch; switch `soul_weapon`, real by
    default, "off" stops it; skipped while the last check read the target
    equipped and no relaunch or user input came since). In mpw18, mpw4 and
    Soul Farming, current engraving readiness is verified on startup, after
    user input or relaunch, and every five minutes under the shared lease.
    A historical success without a current observation is unverified, even
    without a pending marker. Its engraving check/repair precedes unrelated
    preset policy refusals; a refusal leaves the mode failed and returns to
    Soul Weapon parking. Free play, Agent and the mine never initiate this
    farming verification:
    - Equipment (the bottom tab), from the battle screen with nothing over
      it; the Weapon tab when the panel reads Accessories (whose same
      top-right spot opens Black Orb).
    - The Soul Weapon icon: only once the Weapon tab reads active; then its
      title must read "Soul Weapon". Closed with its red X, then the panel
      with its own tab. If an ordinary weapon's card opened instead (its
      button reads Enhance MAX), its red X only, then an alert; never its
      Enhance MAX or Equip.
    - Selecting a weapon in the left list: a whole cell, in its upper part,
      never on an orange tag the fresh capture shows.
    - Scrolling that list: a slow drag from one whole cell's upper part to
      another's, never starting on a tag.
    - Equip (the orange tag): only when the fresh capture reads exactly one
      tag, reading "Equip", the tap on it, and the card's name read as the
      loadout's weapon, owned (Owned : 1 or more); afterwards the tag must
      read Unequip with the name unchanged. Gated by `TAG_LEARNED`
      (`soul_weapon.py`): closed until both tags read on real captures
      (`fixtures/sw_tag_equip`, `sw_tag_unequip`); until then no Equip tap,
      an error alert « Equip tag not calibrated, not equipped ».
    - At most 10 list moves (selects, scrolls and Equip together); a move
      that changes nothing stops it, with an alert naming the step; an
      unresolved farming blocker is then reported every 120 seconds.
    - Never the « Better Soul Weapon / Equip » toast (below).
    - Never Unequip (any tap on a tag read Unequip is refused by the
      guard), Craft, Harvest or Breakdown.
    - Parking (mpw18 and mpw4 only, the switch's last step and the
      watchdog's repair « retour à l’écran Soul Weapon »): the Soul Weapon
      screen left open as the farming mode's idle place, reached by the
      moves above (Equipment, the Weapon tab, the Soul Weapon icon). It is
      a navigation: nothing inside the panel is ever tapped to park or to
      stay parked. Left by its red X, then the panel's tab, before any
      sequence that needs the battle, and when free play or the mine
      starts. Never in free play, the mine, during a switch or its hold,
      nor with the switch `soul_weapon` off.
  - Before Equip clears the engraving, persist its exact target recipe with
    a required durable write. A write/fsync failure or a disabled mandatory
    engraving action refuses Equip. After Equip is confirmed, opening the
    engraving is the next game gesture under the same lease; interruptions
    leave recovery pending before stage/preset work.
  - Before repairing an already equipped weapon, also require a durable write
    of its exact pending engraving recipe. If writing or syncing fails, no
    engraving gesture is sent; a restart must retain the requested recipe.
  - Soul weapon engraving (right after the equip, the card's big icon;
    the step is done, the weapon « prête », only once the grid is the
    loadout's variant with the highest-level cards and all 8 cards read
    locked; otherwise an alert naming what is left, repeated every
    120 seconds while farming remains blocked). Only while its
    switch `engraving` is "real", set only with the user present for the
    first supervised run; "off" by default: not one engraving gesture, an
    error alert "engraving not set up: first supervised run pending", the
    weapon not ready:
    - Its title, then the weapon's name must read the target's; closed
      with its red X (bottom left).
    - A padlock: the padlock in a card's top right corner, only on a
      fresh capture reading it open (a tap on a closed one opens it);
      then it must read closed. If that corner tap changes nothing: one
      error alert, and the piece popup instead (a tap on the card's
      middle, its padlock tapped only while it reads open, closed by a
      tap above it, (0.5, 0.15)). Never an unlock; never left with a
      piece unlocked: all 8 padlocks read closed on a fresh capture
      before the screen is closed, else an error alert.
    - Taking a piece out (a placed piece that is not the variant's, or
      one holding a card that is not the best): a slow drag (800 ms) from
      one of its cells to the inventory; its cells must read empty and
      one card lose its E. It comes out unlocked: that card is locked
      again at once.
    - Placing a piece: a slow drag (1200 ms) from a card read locked and
      unplaced onto empty cells; on its preview, the rotate button until
      its shape is the target's, a drag of one of its cubes by the
      offset left, the check only once the preview lies on the target
      cells and the check reads valid (bright green), else the red X
      cancels it; afterwards the cells must form that piece, the card
      read E and its padlock closed.
    - At most 24 moves per setup, 8 preview moves per piece.
    - Never Change, the gear or %.
  - Resource refresh (Soul Farming, mpw18 and mpw4): a bounded read-only visit every five
    minutes after its first supervised circuit has returned successfully.
    Before that first run, the scheduler stays inactive. It keeps the mode's
    target unchanged and uses the shared lease; user input, mode/loadout
    change, plugin shutdown or pending engraving recovery interrupts it.
    Never-read counters have priority over unverified readings, then older
    dated readings; only calibrated readers and the existing safe circuit
    are scheduled. Unsupported catalogue fields remain explicitly pending,
    with no inferred zero, estimated balance or additional gesture.
    - Read gold, emeralds and diamonds on freshly recognised circuit screens;
      read all four soul colours on the recognised Soul Weapon screen.
      An unread colour remains independent of the other colours.
    - From a recognised Soul Weapon screen, its red X; from battle, Equipment;
      select Weapon only when Accessories is recognised.
    - Scroll only along a calibrated empty gap, at most four gestures per
      search, to inspect the complete first weapon card and read cubes.
      Never Enhance or Equip on the ordinary weapon card; close with its X.
    - Read the Legendary Grade 3 weapon count, then Accessories and its
      Legendary Grade 3 count; missing values remain unknown independently.
    - Return through Weapon to Soul Weapon. Every destination is freshly
      recognised, with no blind cleanup after user intervention. The entire
      visit is bounded; failure never certifies the first supervised run.
  - Closed mine (mode "mine"): its floor row, the Area, 3 feathers,
    scrolling its floor list, and unticking "Repeat entry" (at most 3
    tries, then one alert). After the watchdog's relaunch, the way back
    in: Adventure in the bottom menu (on the battle screen read plain),
    its Dungeon tab (on Adventure read open), Closed Mine (on Dungeon read
    open), then the floor, Area and feathers; not one tap while Adventure
    and Dungeon have no reader calibrated on a capture (the mine ends,
    back to the default mode, one alert). The feathers are not tapped when
    the pop-up reads no feather left (once calibrated): the mine ends.
  - Never tapped, on any screen: the AUTO button (the user's order,
    2026-10-22; forbidden in `navigation.json`, like Breakdown and Change):
    no switch, gate or repair taps it; AUTO is only read, and a stage
    progress bar that stops moving is an error alert instead.
  - Never tapped, on any screen: the game's "Better Soul Weapon / Equip"
    toast (right edge, y 0.32-0.37; forbidden in `navigation.json`): it
    equips the game's pick, while the soul weapon is the mode's loadout.
    It is no obstacle either: the battle under it reads as such.
  - Never tapped: a screen the classifier calls "other" (a pop-up, an
    event, an offer, maintenance, an update, another device, a choice of
    saves). The watchdog names it by its text, as read
    (`screens.other_name`), in an error-level alert repeated every
    120 seconds while farming remains blocked: « Unknown screen:
    "<title>" [<button>]; farming blocked », a bug report for the plugin.
    `navigation.json` refuses any move there by default. A screen enters
    `other_screens.json` only once seen for real, with a fixture cropped
    to its title and buttons (no account name or id); an entry names it,
    it adds no move.
  - « Connected on another device » (and the choice between two saves
    after it): resuming the session there touches the account, so no move
    is allowed until this precondition is written out and validated by the
    user, here, in a commit of its own. Proposed, NOT validated: the move
    is the screen's one button that keeps the game on this device, only
    when (1) the screen reads as its catalogue entry, cut from a real
    capture; (2) the selected mode is mpw18 or mpw4 farming and has been
    for at least AFTER_MODE, so that the user is not playing elsewhere;
    (3) no user input for PAUSE_AFTER_INPUT; (4) at most once per hour,
    one alert each time; never on the choice between two saves, which
    stays an alert. Until then: the error alert above, no move.
- Gates on readings (binding for every plugin): a tap or gesture
  conditioned on a reading is never real until its reader has a crop of a
  REAL capture (`fixtures/`) and a green test for EVERY state it must tell
  apart (Equip and Unequip; padlock open and closed; a preview invalid and
  valid; a popup open). Until then the gate is closed: the move is refused
  and the step ends with an error alert (red) stating the fact, e.g.
  « Soul Weapon: Equip tag not calibrated, not equipped ». A gate is a module-level `*_LEARNED`, `*_TELLS` or
  `*_CALIBRATED` flag listed in `slayer-legend/test_gates.py` with its
  fixtures: an open gate missing one fails that test (red, not skipped).
  The first real run after a gate opens is made with the user present and
  recorded in `docs/TODO.md` (date, readings, result).
- No text ever asks the user to do something by hand: a step that cannot
  be done is an error alert stating what was not done, a report for the
  developer to fix.
- Screenshots of a game go in the repository only when reviewed one by one
  (no Google account, no server address); never commit raw captures.
