# Configuration rate history

`GET /rate-history` returns `version: 1` and `configs` indexed by `mpw18`,
`mpw4`, `soul`, `free` and `mine`. Each entry contains its `mode`, `supported`,
`reason`, current accepted content `revision`, exact `target` and six `fields`:
Gold, Cubes, the stage's catalogue weapon-L3 or accessory-L3 drop, then green,
blue and red souls. Each row has `field`, `label`, `rate_per_hour`,
`measured_at`, `window_start`, `window_end`, `span` and `source`. A known row
uses `source: observed_window` and preserves its acquisition dates, original
revision, episode start and capture epoch. Unknown values and dates are null.
There is no client interpolation or rate inferred from a single balance.

The UI must match the response revision and exact accepted target to the
configuration being displayed. These are historical comparison values, not
proof that the equipment is currently correct. Free play and Mine have no
verified complete farming target in the current model: their entries are
unsupported (`mode_not_supported`) with six unknown rows. Missing stage,
preset, weapon or variant, or an uncatalogued drop, is unsupported
(`configuration_incomplete`). No other mode's observations fill those rows.

`rate_history` subscribes to the existing capture-local reader completions
and uses `gold_rules.counted/rate`. It does not poll an aggregate Gold model,
request additional captures or OCR, or control the game. A validated complete
Mode receipt or a current successful full watchdog repair starts an episode.
Its samples must be acquired after that proof, in the same mode session,
configuration, input identity and game capture epoch, with fresh matching
observed stage evidence. Late OCR from before the episode or a renewed proof
is excluded. Historical snapshots survive edits and restarts in the existing
state store; active samples do not restore after restart.

A read-only verification of the same target/session/input renews admission
without discarding the episode's earlier sparse samples. Reads during the
checking phase are not counted. Returning from another mode, even with no
intervening capture, changes the mode epoch and starts a new episode. Input,
relaunch, observed stage/preset mismatch, a real failed state, or a guarded
configuration mutation invalidates active samples while retaining history.

The passive action observer invalidates only these screen/action pairs:

- `stage_select / move`
- `battle_settings / preset`
- `soul_weapon / equip`
- `soul_weapon_engraving / remove_piece`
- `soul_weapon_engraving_preview / confirm`

These observers run after existing permission/lease guards and before the
Android input. An observer exception is logged and cannot turn an authorised
gesture into a control failure. The observer grants no input permission.
Navigation, selection, preview rotation/movement and padlock checks do not
reset the episode. Any future automated action that changes earning power
must be added to this invalidation contract before its rates can be trusted.

There are at most six saved rows per distinct configuration. Current episode
samples retain the existing finite rate windows and are never written as
restartable models. A new completed measurement saves its historical snapshot
through the existing state-store contract. Compilation and offline tests do
not prove installed persistence, reader coverage, or a full six-rate live run.
