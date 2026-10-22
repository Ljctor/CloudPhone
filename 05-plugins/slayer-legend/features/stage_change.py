"""Brings the game to farming a stage with its Battle settings preset,
AUTO on: the moves the mode feature makes when a farming mode starts, and
the watchdog's repairs.

GET  /farming   {switches: {stage_change, preset, auto}, soul_weapon, last}
POST /farming   {stage_change, preset, auto}: each "real" or "plan" (a
                field absent keeps its value); soul_weapon: "real" or
                "off"; needs the page token

Each repair has its switch, kept in state.json ("farming"), "plan" by
default: then the plan is written to the log and nothing is tapped. Each
is turned to "real" after a first run watched with the user. The AUTO
gear itself stays plan-only (AUTO_TAP_LEARNED): its OFF reading is
calibrated on an ON frame only, until a real OFF capture recalibrates it;
until then POST /farming refuses auto "real" (400), and a "real" kept in
state.json reads as "plan". The auto switch is the gear's tap only: in a
sequence, AUTO is read (on the controls' unfold, as the preset is)
whenever a switch is real; read_controls (the watchdog's) only while the
preset or auto switch is.

Each step looks first (a fresh screenshot), makes one guarded move
(ports, nav.py) and looks again for what it expects (settle: fresh
captures every POLL seconds until it shows, at most SETTLE seconds,
MOVE_SETTLE for a stage to load; no fixed long sleep: a mode switch has
60 s); anything else stops the whole sequence with the step that failed,
in French, for one alert by the caller. Nothing is tried twice. farm()'s
answer gives each step's seconds (timings: stage, preset, auto).

- Stage: closes the bottom panel open, only when its tab reads lit (else
  "écran inattendu"), opens the stage map (Select Region), goes to the
  target's region with the banner's arrows (the banner must read one region
  each time, else it stops) and to its row by scrolling
  (stage_change_rules.plan, at most MOST_MOVES), taps Move on the row whose
  name reads as the target, then reads the target's name on the battle
  screen.
- Preset: unfolds the right edge's controls and taps the badge (see
  unfold), checks Battle settings by its title, taps the preset unless it
  is the one framed, checks the frame, closes, then reads the badge.
- AUTO: two looks at the unfolded controls a moment apart: a spinning
  gear is on. Off, the gear is tapped, then read again. Never tapped while
  it is on or cannot be told.

Every sequence holds the shared lease (holder "stage_change", reason
"farm <mode>"): ports.Busy when another holder has it or the user played
in the last minute (the caller waits for its next look), and a user input
during it stops it at the next tap.

- Soul Weapon (last, after AUTO: a slow one never delays farming): the
  mode's loadout's soul weapon equipped (features/soul_weapon.py). Its
  switch, soul_weapon, is "real" by default (the user's choice: no plan
  mode), "off" an emergency stop; kept in state.json ("soul_weapon").
  Its failure is the sequence's, "Soul Weapon: <step>" (logged as an error) (stage, preset and
  AUTO are done by then). After a watchdog relaunch (relaunched(mode)) it
  runs alone, with one alert if it fails.

api: farm(stage, preset, mode) runs the four; change_stage, set_preset,
ensure_auto, ensure_soul_weapon(mode, loadout=None) alone (the last for a
loadout change of the active mode); each answers {result: "done", "plan"
or "failed", text}. read_controls() for the watchdog: {preset, auto} read
on one unfold, or None. relaunched(mode) for the watchdog's relaunch.
"""

import logging
from types import SimpleNamespace

# After a move: a fresh capture every POLL seconds until the screen
# expected shows, at most SETTLE seconds (MOVE_SETTLE for a stage to load).
POLL = 0.25
SETTLE = 4.0
MOVE_SETTLE = 8.0
# The controls fold away about 2 s after the arrow unfolds them. Measured
# on the phone: two separate guarded taps (the guard, then each its
# ssh/adb round trip) missed the badge twice, so the arrow and the next
# tap go in one adb call (ports.taps), UNFOLD_GAP apart, both guarded
# first. Then UNFOLD_WAIT for the unfold, LOOK_GAP between the two looks at
# the gear; they fold away by themselves within FOLD_SETTLE.
UNFOLD_GAP = 0.4
UNFOLD_WAIT = 0.5
LOOK_GAP = 0.4
FOLD_SETTLE = 4.0
SETTINGS_CLOSE = (0.09, 0.965)
LEASE_SECONDS = 240
# After a relaunch, the soul weapon's check waits for the lease this often,
# this long at most (seconds).
RELAUNCH_RETRY = 10
RELAUNCH_WAIT = 300
HOLDER = "stage_change"
SWITCHES = ("stage_change", "preset", "auto")
# The AUTO gear's tap waits for a real OFF capture (see above).
AUTO_TAP_LEARNED = False


class Stop(Exception):
    """The sequence stops: the step that failed, in French."""


class Plan(Exception):
    """A plan-only step: what it would do, in French."""


AUTO_NOT_LEARNED = "Le bouton AUTO n’est pas encore appris (pas de capture AUTO arrêté) : « auto » reste en plan"


def kept_switches(saved):
    saved = saved if isinstance(saved, dict) else {}
    return {name: "real" if saved.get(name) == "real" and (name != "auto" or AUTO_TAP_LEARNED) else "plan"
            for name in SWITCHES}


def stage_change(ports, screens, select, controls, rules, table, soul=None):
    """select: stage_select.py; controls: battle_controls.py; table:
    stages.json; soul: {feature (features/soul_weapon.py's soul_weapon),
    reader, rules, table, loadout, engraving} for the soul weapon step
    (None: no such step)."""
    names = select.regions(table)
    switches = kept_switches((ports.store.saved.get("farming") or {}).get("switches"))
    status = {"last": None}
    ports.store.register("farming", lambda: {"switches": dict(switches)})

    def real(name):
        return switches[name] == "real"

    async def look():
        shot = await ports.capture()
        if not shot:
            raise Stop("pas de capture d’écran")
        return shot

    async def settle(read, *args, accept=bool, timeout=SETTLE, stable=False):
        """(shot, value): fresh captures every POLL seconds until read(shot,
        *args) is accepted (stable: the same value on two in a row, a list
        that stopped scrolling), at most timeout seconds; the last one
        then, for the caller to judge."""
        deadline = ports.clock.monotonic() + timeout
        previous = None
        while True:
            shot = await look()
            value = await ports.analyse(read, shot, *args)
            if accept(value) and (not stable or value == previous):
                return shot, value
            if ports.clock.monotonic() >= deadline:
                return shot, value
            previous = value
            await ports.clock.sleep(POLL)

    async def front():
        if not await ports.focused():
            raise Stop("le jeu n’est plus au premier plan")

    async def tap(shot, screen, move, point, verified=False, seen=None):
        await front()
        if seen is None:
            await ports.tap(shot, screen, move, point, verified=verified)
        else:
            await ports.tap(shot, screen, move, point, verified=verified, seen=seen)

    def battle_or_panel(shot):
        """"plain", the open panel's tab, "saver", or None (another screen)."""
        if screens.plain_battle(shot):
            return "plain"
        if screens.classify(shot) == "saver":
            return "saver"
        return screens.open_tab(shot)

    async def to_battle(may_tap=True):
        """A fresh look at the battle screen with nothing over it, waiting
        up to SETTLE for it (a screen passing by, a toast sliding in): a
        bottom panel open is closed with its own tab, only when that tab
        reads lit (no guess); Power Saving Mode is left by its hold (once:
        the game shows battle again behind it). The game's « Better Soul
        Weapon » toast is no obstacle (screens.better_weapon_toast)."""
        shot, seen = await settle(battle_or_panel)
        if seen == "saver":
            if not may_tap:
                raise Plan("quitter le mode économie d’énergie")
            await front()
            await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
            shot, seen = await settle(battle_or_panel, accept=lambda v: v not in (None, "saver"))
        if seen == "plain":
            return shot
        tab = seen if isinstance(seen, tuple) else None
        if tab is None:
            raise Stop(f"écran inattendu (ni le combat, ni un panneau du menu du bas reconnu ; lu : "
                       f"{await ports.analyse(screens.classify, shot)})")
        if not may_tap:
            raise Plan(f"fermer le panneau ({tab[1]})")
        await tap(shot, tab[1], "close", (tab[0], screens.TAB_TAP_Y))
        shot, plain = await settle(screens.plain_battle)
        if not plain:
            raise Stop("fermeture du panneau du menu du bas")
        return shot

    async def change_stage(target):
        if not rules.supported(target, names):
            raise Stop(f"stage {target} hors des régions connues")
        shot = await to_battle(real("stage_change"))
        seen = await ports.analyse(select.battle_stage, shot, names)
        if seen == target:
            return
        if not real("stage_change"):
            raise Plan(f"stage {seen or 'illisible'} → {target} : Select Region, région "
                       f"{names[rules.region_of(target)]}, Move sur la ligne lue comme {target}")
        await tap(shot, "battle", "stage_select", select.STAGE_MAP_TAP)
        shot, view = await settle(select.view, names, accept=lambda v: v["popup"] and v["rows"], stable=True)
        if not view["popup"]:
            raise Stop("ouverture de Select Region")
        for _ in range(rules.MOST_MOVES):
            step = rules.plan(view, target)
            if step[0] == "fail":
                raise Stop(f"Select Region : {step[1]}")
            if step[0] == "move":
                await tap(shot, "stage_select", "move", (select.MOVE_TAP_X, step[1]), verified=True)
                shot, seen = await settle(select.battle_stage, names, accept=lambda v: v is not None,
                                          timeout=MOVE_SETTLE)
                if seen != target:
                    raise Stop(f"vérification après Move (lu : {seen or 'rien'})")
                return
            if step[0] == "arrow":
                await tap(shot, "stage_select", step[1], select.ARROW_TAPS[step[1]])
            else:
                start, end = rules.SWIPE_DOWN if step[1] == "down" else rules.SWIPE_UP
                await front()
                await ports.swipe(shot, "stage_select", "scroll", start, end, rules.SWIPE_MS)
            moved_from = view
            shot, after = await settle(select.view, names, accept=lambda v: rules.progressed(moved_from, v),
                                       stable=True)
            if step[0] == "arrow" and after["region"] != view["region"] + (1 if step[1] == "next_region" else -1):
                raise Stop("Select Region : la bannière ne lit pas la région suivante")
            if not rules.progressed(view, after):
                raise Stop(f"Select Region : {'flèche' if step[0] == 'arrow' else 'défilement'} sans effet")
            view = after
        raise Stop(f"Select Region : stage {target} pas atteint en {rules.MOST_MOVES} gestes")

    async def unfold(shot, then=None, verified=()):
        """From the battle screen (shot): taps then (move, point) on the
        unfolded controls. The fresh shot must read them folded: then the
        arrow and then go in one adb call. Read unfolded, the arrow would
        fold them and then land behind: then alone. Unknown: nothing."""
        state = await ports.analyse(controls.controls, shot)
        if state is None:
            raise Stop("contrôles de droite illisibles (ni repliés ni dépliés)")
        await front()
        if state == "unfolded":
            if then:
                await ports.taps(shot, "battle", [then], UNFOLD_GAP, verified=set(verified))
            return
        moves = [("preset_arrow", controls.ARROW_TAP)] + ([then] if then else [])
        await ports.taps(shot, "battle", moves, UNFOLD_GAP, verified={"preset_arrow", *verified})

    async def folded_battle():
        """A battle look with the controls folded (they fold by themselves)."""
        shot = await to_battle()
        if await ports.analyse(controls.unfolded_now, shot):
            await settle(controls.unfolded_now, accept=lambda v: not v, timeout=FOLD_SETTLE)
            shot = await to_battle()
        return shot

    async def controls_look():
        """Two fresh looks at the unfolded controls, a moment apart."""
        await unfold(await folded_battle())
        await ports.clock.sleep(UNFOLD_WAIT)
        first = await look()
        await ports.clock.sleep(LOOK_GAP)
        return first, await look()

    async def badge_of(first, second):
        return (await ports.analyse(controls.badge, first)) or (await ports.analyse(controls.badge, second))

    async def set_preset(name):
        if not real("preset"):
            raise Plan(f"préréglage de combat {name} : badge, Battle settings, {name}, fermer")
        first, second = await controls_look()
        if await badge_of(first, second) == name:
            return
        await unfold(await folded_battle(), ("preset_badge", controls.BADGE_TAP))
        shot, opened = await settle(controls.settings_open)
        if not opened:
            raise Stop("ouverture de Battle settings")
        if await ports.analyse(controls.selected, shot) != name:
            await tap(shot, "battle_settings", "preset", controls.preset_tap(name))
            shot, chosen = await settle(controls.selected, accept=lambda v: v == name)
            if chosen != name:
                raise Stop(f"choix du preset {name} dans Battle settings (lu : {chosen or 'rien'})")
        await tap(shot, "battle_settings", "close", SETTINGS_CLOSE)
        await settle(screens.plain_battle)
        if await badge_of(*await controls_look()) != name:
            raise Stop(f"vérification du preset {name} sur le badge")

    async def auto_state():
        """"on", "off" or None (cannot tell) on the next two looks."""
        first, second = await controls_look()
        return await ports.analyse(controls.auto, first, second)

    async def ensure_auto():
        if not any(real(name) for name in SWITCHES):
            raise Plan("vérifier AUTO (l’engrenage tourne), le toucher s’il est arrêté")
        state = await auto_state()
        if state == "on":
            return
        if state is None:
            raise Stop("état d’AUTO illisible")
        if not (AUTO_TAP_LEARNED and real("auto")):
            raise Plan("AUTO lu arrêté : toucher l’engrenage (en attente d’une capture AUTO arrêté pour "
                       "recalibrer la lecture)")
        await unfold(await folded_battle(), ("auto", controls.AUTO_TAP), verified={"auto"})
        if await auto_state() != "on":
            raise Stop("AUTO pas en marche après l’avoir activé")

    async def run(mode, steps, force=False):
        """Runs steps ((name, step) pairs) under the lease: {result, text,
        timings: {name: seconds}}; ports.Busy when the lease cannot be had
        (the caller tries again shortly). A plan step is written to the log
        and the next steps go on. force: the user's last minute is not
        waited for (they asked to resume now)."""
        plans = []
        timings = {}
        async with ports.leased(HOLDER, f"farm {mode}", LEASE_SECONDS, **({"pause": False} if force else {})):
            try:
                for name, step in steps:
                    began = ports.clock.monotonic()
                    try:
                        await step()
                    except Plan as e:
                        plans.append(str(e))
                        logging.info(f"Slayer Legend stage change, plan only: {e}")
                    finally:
                        timings[name] = round(ports.clock.monotonic() - began, 1)
            except Stop as e:
                answer = {"result": "failed", "text": str(e)}
            except ports.Busy:
                raise
            except RuntimeError as e:  # a move the navigation guard refused
                logging.error(f"Slayer Legend stage change: {e}")
                answer = {"result": "failed", "text": str(e)}
            else:
                answer = {"result": "plan" if plans else "done", "text": " ; ".join(plans)}
        answer["timings"] = timings
        status["last"] = {**answer, "mode": mode}
        return answer

    souls = None
    if soul:
        souls = soul["feature"](ports, screens, soul["reader"], soul["rules"], soul["table"],
                                SimpleNamespace(look=look, tap=tap, front=front, to_battle=to_battle, Stop=Stop),
                                soul.get("engraving"))

    async def equip_soul_weapon(mode, loadout=None):
        """The mode's loadout's soul weapon equipped (loadout: that one
        instead of the stored one; none chosen, or the switch off:
        nothing)."""
        part = loadout if loadout is not None else (soul["loadout"](mode) if souls else None)
        chosen = (part or {}).get("soul_weapon") if souls else None
        if not chosen or souls["switch"]() != "real":
            return
        try:
            await souls["ensure"](chosen["id"], chosen.get("variant"))
        except Stop as e:
            logging.error(f"Slayer Legend soul weapon: {e}")
            raise Stop(f"Soul Weapon: {e}") from None

    async def ensure_soul_weapon(mode, loadout=None, force=False):
        """The soul weapon step alone, under the lease (e.g. the active
        mode's loadout just changed): {result: "done" or "failed", text};
        ports.Busy when the lease cannot be had (the caller retries). A
        weapon read equipped since the last relaunch or user input is not
        read again (≈0 s); another one is."""
        return await run(mode, [("soul_weapon", lambda: equip_soul_weapon(mode, loadout))], force)

    async def farm(stage, preset, mode, highest=None, force=False):
        """Farming stage with preset (None: kept as it is), AUTO on, then the
        loadout's soul weapon. A stage past highest (the highest seen
        farmed, None: unknown) is tried too: the gateway may never have
        seen a stage the game has unlocked. Only a region the stage change
        cannot read is refused (change_stage), and a stage the game does
        not open fails at the check after Move. force: see run."""
        if highest and stage > highest:
            logging.info(f"Slayer Legend stage change: stage {stage} past the highest seen farmed ({highest}), tried")
        steps = [("stage", lambda: change_stage(stage))]
        if preset:
            steps.append(("preset", lambda: set_preset(preset)))
        steps.append(("auto", ensure_auto))
        steps.append(("soul_weapon", lambda: equip_soul_weapon(mode)))
        return await run(mode, steps, force)

    async def after_relaunch(mode):
        """The soul weapon read again once the game is back: the lease
        waited for (every RELAUNCH_RETRY, at most RELAUNCH_WAIT), one alert
        on a failure."""
        since = ports.clock.monotonic()
        while True:
            try:
                answer = await run(mode, [("soul_weapon", lambda: equip_soul_weapon(mode))])
                break
            except ports.Busy:
                if ports.clock.monotonic() - since >= RELAUNCH_WAIT:
                    logging.info("Slayer Legend soul weapon after a relaunch: lease still taken, dropped")
                    return
                await ports.clock.sleep(RELAUNCH_RETRY)
        if answer["result"] == "failed":
            await ports.notify(f"Après la relance du jeu ({mode}) : {answer['text']}"[:200])

    def relaunched(mode):
        """For the watchdog, once its relaunch brought the game back."""
        if not souls or mode not in ("mpw18", "mpw4"):
            return None
        souls["relaunched"]()
        if not (soul["loadout"](mode) or {}).get("soul_weapon") or souls["switch"]() != "real":
            return None
        return ports.spawn(after_relaunch(mode))

    async def read_controls():
        """{preset, auto} read on one unfold of the controls (a tap: under
        the lease), or None: the preset and auto switches are both plan,
        the lease cannot be had, or anything unexpected."""
        if not (real("preset") or real("auto")):
            return None
        try:
            async with ports.leased(HOLDER, "lecture du préréglage et d’AUTO", 30):
                first, second = await controls_look()
                return {"preset": await badge_of(first, second),
                        "auto": await ports.analyse(controls.auto, first, second)}
        except (Stop, RuntimeError):  # Busy included
            return None

    async def handle_get(request):
        return ports.respond({"switches": dict(switches), "last": status["last"],
                              "soul_weapon": souls["state"]() if souls else None})

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if not isinstance(body, dict) or any(body.get(k) not in (None, "real", "plan") for k in SWITCHES) \
                or body.get("soul_weapon") not in (None, "real", "off"):
            return ports.respond({"error": "Expected {stage_change, preset, auto}: \"real\" or \"plan\"; "
                                           "soul_weapon: \"real\" or \"off\""}, status=400)
        if body.get("auto") == "real" and not AUTO_TAP_LEARNED:
            return ports.respond({"error": AUTO_NOT_LEARNED}, status=400)
        for name in SWITCHES:
            if body.get(name):
                if switches[name] != body[name]:
                    logging.info(f"Slayer Legend stage change: {name} switched to {body[name]}")
                switches[name] = body[name]
        if body.get("soul_weapon") and souls:
            souls["set_switch"](body["soul_weapon"])
        ports.store.save()
        return await handle_get(request)

    api = {"farm": farm,
           "change_stage": lambda stage, mode="mpw18": run(mode, [("stage", lambda: change_stage(stage))]),
           "set_preset": lambda name, mode="mpw18": run(mode, [("preset", lambda: set_preset(name))]),
           "ensure_auto": lambda mode="mpw18": run(mode, [("auto", ensure_auto)]),
           "read_controls": read_controls, "switches": lambda: dict(switches),
           "relaunched": relaunched, "ensure_soul_weapon": ensure_soul_weapon,
           "soul_weapon": lambda mode="mpw18": ensure_soul_weapon(mode),
           "battle_stage": lambda shot: select.battle_stage(shot, names)}
    return {"api": api, "routes": [("GET", "/farming", handle_get), ("POST", "/farming", handle_post)]}
