# Part 05 — agent instructions: plugins

Default task: after part 04 converged, install the plugins with
`sudo 05-plugins/scripts/install.sh` (every plugin; or name them) or
`packaging/deploy.sh "$TARGET" 05`. Check:
`curl -fsS http://LISTEN_ADDRESS:WEB_PORT/api/v1/plugins` lists each one.

Rules:

- Everything specific to one game or app lives in its plugin directory
  here, never in parts 03–04.
- A plugin never launches or restarts an app by itself: only on a user's
  press, never from a timer or a script. The one exception, asked by the
  user: Slayer Legend's watchdog relaunches the game while the selected
  mode is mpw18 or mpw4 farming or the Closed Mine (backing off after each
  failure: 1, 2, 4, 8, 16, then 30 minutes between attempts; never in free
  play or during a mode's entry, a minute after a user input at the
  earliest, under the shared lease). In the mine the relaunch is followed
  by the mine's own way back in (below). No launch
  ever kills the app (`am start` without `-S`, no force-stop). On Android's
  "isn't responding" dialog the watchdog taps only "Wait", once, then
  alerts: never its "Close app", which kills the game.
- What Slayer Legend's plugin taps by itself: this list is exhaustive.
  Every move goes through the navigation guard (`navigation.json`) under
  the shared lease, on a fresh capture showing that screen; anything else
  stops the sequence with one alert. Nothing outside it is ever tapped.
  - Launch:
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
    - "Wait" on Android's "isn't responding" dialog: once per dialog, never
      its "Close app".
    - The right edge's arrow that unfolds the controls, to read the preset
      badge and AUTO: at most every 5 minutes, whoever watches (only a
      user's input pauses it, a minute), only while the preset or auto switch is real.
  - Stage change and preset (mode changes, a change of the running
    mode's loadout, and the watchdog's repairs,
    each only while its switch is real):
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
    - The AUTO gear: not tapped until a real AUTO-off capture calibrates
      its reading (`AUTO_TAP_LEARNED`).
  - Soul weapon (last step of a mode change, after AUTO, and once after a
    watchdog relaunch; never periodic; switch `soul_weapon`, real by
    default, "off" stops it; skipped while the last check read the target
    equipped and no relaunch or user input came since):
    - Equipment (the bottom tab), from the battle screen with nothing over
      it; the Weapon tab when the panel reads Accessories (whose same
      top-right spot opens Black Orb).
    - The Soul Weapon icon: only once the Weapon tab reads active; then its
      title must read "Soul Weapon". Closed with its red X, then the panel
      with its own tab. If an ordinary weapon's card opened instead (its
      button reads Enhance MAX), its red X only, then one alert; never its
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
      that changes nothing stops it, with one alert naming the step.
    - Never the « Better Soul Weapon / Equip » toast (below).
    - Never Unequip (any tap on a tag read Unequip is refused by the
      guard), Craft, Harvest or Breakdown.
  - Soul weapon engraving (right after the equip, the card's big icon;
    the step is done, the weapon « prête », only once the grid is the
    loadout's variant with the highest-level cards and all 8 cards read
    locked; otherwise one alert naming what is left):
    - Its title, then the weapon's name must read the target's; closed
      with its red X (bottom left).
    - A padlock: only on a card whose fresh capture reads it open, before
      any drag, once; a padlock read closed or not read is never tapped
      (a tap would unlock it). Never an unlock.
    - A drag: only once all 8 cards read locked, from a card read
      unplaced (no E) onto cells read empty, in the card's own
      orientation; afterwards those cells must form that piece, the card
      read E and nothing else change, else it stops. Turning a piece or
      taking one out of the grid is not learnt: alerted, never guessed.
    - Never Change, the gear or %.
  - Closed mine (mode "mine"): its floor row, the Area, 3 feathers,
    scrolling its floor list, and unticking "Repeat entry" (at most 3
    tries, then one alert). After the watchdog's relaunch, the way back
    in: Adventure in the bottom menu (on the battle screen read plain),
    its Dungeon tab (on Adventure read open), Closed Mine (on Dungeon read
    open), then the floor, Area and feathers; not one tap while Adventure
    and Dungeon have no reader calibrated on a capture (the mine ends,
    back to the default mode, one alert). The feathers are not tapped when
    the pop-up reads no feather left (once calibrated): the mine ends.
  - Never tapped, on any screen: the game's "Better Soul Weapon / Equip"
    toast (right edge, y 0.32-0.37; forbidden in `navigation.json`): it
    equips the game's pick, while the soul weapon is the mode's loadout.
    It is no obstacle either: the battle under it reads as such.
- Gates on readings (binding for every plugin): a tap or gesture
  conditioned on a reading is never real until its reader has a crop of a
  REAL capture (`fixtures/`) and a green test for EVERY state it must tell
  apart (Equip and Unequip; padlock open and closed; a preview invalid and
  valid; a popup open). Until then the gate is closed: the move is refused
  and the step ends with an error alert (red) stating the fact, e.g.
  « Soul Weapon: Equip tag not calibrated, not equipped », like
  `AUTO_TAP_LEARNED`. A gate is a module-level `*_LEARNED`, `*_TELLS` or
  `*_CALIBRATED` flag listed in `slayer-legend/test_gates.py` with its
  fixtures: an open gate missing one fails that test (red, not skipped).
  The first real run after a gate opens is made with the user present and
  recorded in `docs/TODO.md` (date, readings, result).
- No text ever asks the user to do something by hand: a step that cannot
  be done is an error alert stating what was not done, a report for the
  developer to fix.
- Screenshots of a game go in the repository only when reviewed one by one
  (no Google account, no server address); never commit raw captures.
