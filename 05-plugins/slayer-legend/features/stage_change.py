"""Brings the game to farming a stage with its Battle settings preset:
the moves the mode feature makes when a farming mode starts, and the
watchdog's repairs. The AUTO button is never tapped (the user's order,
2026-10-22; forbidden in navigation.json): AUTO is only read, for the
watchdog's alerts.

GET  /farming   {switches: {stage_change, preset}, soul_weapon, last}
                (last: {result, text_t, timings, mode}, text_t a status text)
POST /farming   {stage_change, preset}: each "real" or "plan" (a
                field absent keeps its value); soul_weapon: "real" or
                "off"; engraving: "off" or "real" (only with the user
                present: features/soul_weapon.py); needs the page token

Each repair has its switch, kept in state.json ("farming"), "plan" by
default: then the plan is written to the log and nothing is tapped. Each
is turned to "real" after a first run watched with the user.
read_controls (the watchdog's: the preset and, as information, AUTO) only
while the preset switch is.

Each step looks first (a fresh screenshot), makes one guarded move
(ports, nav.py) and looks again for what it expects (settle: fresh
captures every POLL seconds until it shows, at most SETTLE seconds,
MOVE_SETTLE for a stage to load; no fixed long sleep: a mode switch has
60 s); anything else stops the whole sequence with the step that failed
(a status text, features/texts.py), for one alert by the caller. Nothing is tried twice. farm()'s
answer gives each step's seconds (timings: stage, preset, soul_weapon).

- Stage: closes the bottom panel open, only when its tab reads lit (else
  « écran inattendu »), opens the stage map (Select Region), goes to the
  target's region with the banner's arrows (the banner must read one region
  each time, else it stops) and to its row by scrolling
  (stage_change_rules.plan, at most MOST_MOVES), taps Move on the row whose
  name reads as the target, then reads the target's name on the battle
  screen.
- Preset: unfolds the right edge's controls and taps the badge (see
  unfold), checks Battle settings by its title, taps the preset unless it
  is the one framed, checks the frame, closes, then reads the badge.

Every sequence holds the shared lease (holder "stage_change", reason
"farm <mode>"): ports.Busy when another holder has it or the user played
in the last 5 s (the caller waits for its next look), and a user input
during it stops it at the next tap.

- Park (last of all, inside the 60 s): the farming mode's idle place,
  the Soul Weapon screen, the battle going on above it
  (features/soul_weapon.py's park: the soul weapon step's own moves, the
  screen left open after it). For mpw18, mpw4 and Soul Farming, while the soul
  weapon's switch is real. to_battle leaves it by its red X first;
  unpark(mode) does only that, when free play or the mine starts.
- Soul Weapon (a slow one never delays farming): the
  mode's loadout's soul weapon equipped (features/soul_weapon.py). Its
  switch, soul_weapon, is "real" by default (the user's choice: no plan
  mode), "off" an emergency stop; kept in state.json ("soul_weapon").
  Its failure is the sequence's, « Soul Weapon : <step> » (logged as an error) (stage and
  preset are normally done by then). Missing current engraving proof runs
  this step before stage/preset gates, including after a gateway restart
  and at five-minute intervals; a saved success alone is insufficient.
  A preset policy refusal returns to Soul Weapon parking and remains a
  failed mode. After a watchdog relaunch (relaunched(mode)) it
  runs alone, with one alert if it fails.

api: farm(stage, preset, mode) runs the three and parks; change_stage, set_preset,
ensure_soul_weapon(mode, loadout=None) alone (the last for a
loadout change of the active mode); each answers {result: "done", "plan"
or "failed", text_t: why or the plan, a status text, or None}. read_controls() for the watchdog: {preset, auto} read
on one unfold, or None. relaunched(mode) for the watchdog's relaunch.
"""

import asyncio
import copy
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
BATTLE_RETURN = (0.5, 0.18)
QUEST_CLOSE = (0.895, 0.183)
LEASE_SECONDS = 240
# After a relaunch, the soul weapon's check waits for the lease this often,
# this long at most (seconds).
RELAUNCH_RETRY = 10
RELAUNCH_WAIT = 300
HOLDER = "stage_change"
SWITCHES = ("stage_change", "preset")
# The modes that park on the Soul Weapon screen.
FARMED = ("mpw18", "mpw4", "soul")


def t(template, **params):
    """A status text (features/texts.py)."""
    return {"template": template, "params": params}


class Said(Exception):
    """t: a status text, given whole or as a template and its params."""

    def __init__(self, text, /, **params):
        self.t = text if isinstance(text, dict) else t(text, **params)
        super().__init__(self.t["template"])


class Stop(Said):
    """The sequence stops: t, the step that failed."""


class Blocked(Stop):
    """A policy refusal that waiting and repeating cannot resolve."""

    def __init__(self, text, /, *, failure_code, **params):
        super().__init__(text, **params)
        self.failure_code = failure_code


class Plan(Said):
    """A plan-only step: t, what it would do."""


def joined(texts):
    """Status texts one after the other, « a ; b »; None for none."""
    if not texts:
        return None
    if len(texts) == 1:
        return texts[0]
    return t("{first} ; {then}", first=texts[0], then=joined(texts[1:]))


def kept_switches(saved):
    saved = saved if isinstance(saved, dict) else {}
    return {name: "real" if saved.get(name) == "real" else "plan" for name in SWITCHES}


def stage_change(ports, screens, select, controls, rules, table, soul=None):
    """select: stage_select.py; controls: battle_controls.py; table:
    stages.json; soul: {feature (features/soul_weapon.py's soul_weapon),
    reader, rules, table, loadout, engraving} for the soul weapon step
    (None: no such step)."""
    names = select.regions(table)
    switches = kept_switches((ports.store.saved.get("farming") or {}).get("switches"))
    status = {"last": None}
    agent_context = [lambda: False]
    agent_guards = {}
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
        guard = agent_guards.get(asyncio.current_task())
        if guard:
            guard()
        if not await ports.focused():
            raise Stop("le jeu n’est plus au premier plan")
        if guard:
            guard()

    async def tap(shot, screen, move, point, verified=False, seen=None):
        await front()
        if seen is None:
            await ports.tap(shot, screen, move, point, verified=verified)
        else:
            await ports.tap(shot, screen, move, point, verified=verified, seen=seen)

    def parked(shot):
        """The Soul Weapon screen shows (its title): the one parking check,
        for the watchdog too (api parked)."""
        return bool(souls) and bool(soul["reader"].title(shot))

    def battle_or_panel(shot):
        """"plain", the open panel's tab, "saver", "parked" (the Soul
        Weapon screen), or None (another screen)."""
        if screens.quest_panel(shot):
            return "quest"
        if controls.settings_open(shot) and "battle_settings" in screens.look(shot)["overlays"]:
            return "settings"
        if screens.plain_battle(shot):
            return "plain"
        if screens.classify(shot) == "saver":
            return "saver"
        if parked(shot):
            return "parked"
        if souls and soul.get("engraving") and soul["engraving"]["screen"].title(shot):
            return "engraving"
        return screens.open_tab(shot)

    async def to_battle(may_tap=True, recovery_target=None):
        """A fresh look at the battle screen with nothing over it, waiting
        up to SETTLE for it (a screen passing by, a toast sliding in): a
        bottom panel open is closed with its own tab, only when that tab
        reads lit (no guess); Power Saving Mode is left by its hold (once:
        the game shows battle again behind it); the Soul Weapon screen (the
        parking) by its red X first. The game's « Better Soul Weapon »
        toast is no obstacle (screens.better_weapon_toast)."""
        shot, seen = await settle(battle_or_panel)
        if seen == "settings":
            if not may_tap:
                raise Plan("fermer Battle settings")
            await tap(shot, "battle_settings", "close", SETTINGS_CLOSE, verified=True)
            shot, seen = await settle(battle_or_panel, accept=lambda value: value not in (None, "settings"))
        if seen == "quest":
            if not may_tap:
                raise Plan("fermer Quest")
            # Quest can cover Battle or Shop. Close only its calibrated X,
            # then identify the exposed screen before any further move.
            await tap(shot, "quest_panel", "close_overlay", QUEST_CLOSE, verified=True)
            shot, seen = await settle(battle_or_panel, accept=lambda v: v not in (None, "quest"))
        if seen == "engraving":
            if not may_tap:
                raise Plan("quitter l’écran Soul Weapon")
            # A timed-out opening may finish after the previous attempt.
            # Recover the identified engraving, including all eight locks,
            # before any stage/preset navigation in this existing lease.
            await souls["recover_engraving"](shot, target=recovery_target)
            shot, seen = await settle(battle_or_panel)
        if seen == "parked":
            if not may_tap:
                raise Plan("quitter l’écran Soul Weapon")
            await souls["leave"](shot)
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
            raise Stop("écran inattendu (ni le combat, ni un panneau du menu du bas reconnu ; lu : {screen})",
                       screen=await ports.analyse(screens.classify, shot))
        if not may_tap:
            raise Plan("fermer le panneau ({panel})", panel=tab[1])
        reduced = await ports.analyse(screens.look, shot)
        # The Equipment tab toggles its panel; tapping visible combat can
        # leave this panel unchanged. Only use the tab the fresh reader lit.
        move, point = ("close_tab", (tab[0], screens.TAB_TAP_Y)) if tab[1] == "equipment_weapon" else ("close", BATTLE_RETURN)
        await tap(shot, tab[1], move, point, verified=True,
                  seen={"look": reduced, "combat_visible": reduced["screen"] == "battle",
                        "active_tab": tab[1]})
        shot, plain = await settle(screens.plain_battle, timeout=10.0 if move == "close_tab" else SETTLE)
        if not plain:
            raise Stop("fermeture du panneau du menu du bas")
        return shot

    async def change_stage(target, recovery_target=None):
        if not rules.supported(target, names):
            raise Stop("stage {stage} hors des régions connues", stage=target)
        shot = await look()
        if parked(shot) and await ports.analyse(select.battle_stage, shot, names, screens.PARKED_SHADE) == target:
            return  # parked on the target stage: nothing to leave
        # An interrupted attempt may have left Select Region open. Its
        # recognised title is the entry point; never close a guessed bottom
        # panel or tap the battle map through this overlay.
        view = await ports.analyse(select.view, shot, names)
        if not view["popup"]:
            shot = await to_battle(real("stage_change"), recovery_target=recovery_target)
            seen = await ports.analyse(select.battle_stage, shot, names)
            if seen == target:
                return
            if not real("stage_change"):
                raise Plan("stage {seen} → {stage} : Select Region, région {region}, Move sur la ligne lue comme {stage}",
                           seen=seen or t("illisible"), stage=target, region=names[rules.region_of(target)])
            await tap(shot, "battle", "stage_select", select.STAGE_MAP_TAP)
        elif not real("stage_change"):
            raise Plan("stage {seen} → {stage} : Select Region, région {region}, Move sur la ligne lue comme {stage}",
                       seen=t("illisible"), stage=target, region=names[rules.region_of(target)])
        shot, view = await settle(select.view, names,
                                  accept=lambda v: v["popup"] and v["region"] is not None and v["rows"],
                                  stable=True)
        if not view["popup"]:
            raise Stop("ouverture de Select Region")
        for _ in range(rules.MOST_MOVES):
            step = rules.plan(view, target)
            if step[0] == "fail":
                raise Stop("Select Region : {why}", why=step[1])
            if step[0] == "move":
                await tap(shot, "stage_select", "move", (select.MOVE_TAP_X, step[1]), verified=True)
                shot, seen = await settle(select.battle_stage, names, accept=lambda v: v is not None,
                                          timeout=MOVE_SETTLE)
                if seen != target:
                    ports.log("normal", f"Stage change: stage {target} not opened by the game "
                              f"(read after Move: {seen or 'nothing'})")
                    raise Stop("stage {stage} non ouvert par le jeu (lu après Move : {seen})", stage=target,
                               seen=seen or t("rien"))
                noted({"stage": target})
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
                raise Stop("Select Region : flèche sans effet" if step[0] == "arrow"
                           else "Select Region : défilement sans effet")
            view = after
        raise Stop("Select Region : stage {stage} pas atteint en {moves} gestes", stage=target, moves=rules.MOST_MOVES)

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

    def preset_policy(name, seen):
        """Only a read mismatch requires permission to change a preset."""
        allowed = getattr(ports, "action_allowed", lambda screen, move: False)
        if seen is not None and seen != name and not allowed("battle_settings", "preset"):
            raise Blocked("Préréglage {wanted} demandé, {seen} lu : changement bloqué, actions en pause",
                          failure_code="preset_action_paused", wanted=name, seen=seen)

    async def preflight_preset(name):
        """Read an already accessible preset before stage navigation.
        An unread badge is unknown, never evidence that a change is needed.
        The regular preset step will read it after unfolding under the lease.
        """
        if not name or not real("preset"):
            return
        shot = await look()
        if await ports.analyse(controls.settings_open, shot):
            seen = await ports.analyse(controls.selected, shot)
        elif await ports.analyse(screens.plain_battle, shot) or parked(shot):
            seen = await ports.analyse(controls.badge, shot)
        else:
            return
        preset_policy(name, seen)

    async def set_preset(name):
        if not real("preset"):
            raise Plan("préréglage de combat {preset} : badge, Battle settings, {preset}, fermer", preset=name)
        first, second = await controls_look()
        seen = await badge_of(first, second)
        if seen == name:
            return
        preset_policy(name, seen)
        await unfold(await folded_battle(), ("preset_badge", controls.BADGE_TAP))
        shot, opened = await settle(controls.settings_open)
        if not opened:
            raise Stop("ouverture de Battle settings")
        seen = await ports.analyse(controls.selected, shot)
        if seen != name:
            preset_policy(name, seen)
            await tap(shot, "battle_settings", "preset", controls.preset_tap(name))
            shot, chosen = await settle(controls.selected, accept=lambda v: v == name)
            if chosen != name:
                raise Stop("choix du preset {preset} dans Battle settings (lu : {seen})", preset=name,
                           seen=chosen or t("rien"))
        await tap(shot, "battle_settings", "close", SETTINGS_CLOSE)
        await settle(screens.plain_battle)
        if await badge_of(*await controls_look()) != name:
            raise Stop("vérification du preset {preset} sur le badge", preset=name)
        noted({"preset": name})

    async def run(mode, steps, force=False, preflight=None, park_on_block=False):
        """Runs steps ((name, step) pairs) under the lease: {result, text,
        timings: {name: seconds}}; ports.Busy when the lease cannot be had
        (the caller tries again shortly). A plan step is written to the log
        and the next steps go on. force: the user's last 5 s are not
        waited for (they asked to resume now)."""
        plans = []
        timings = {}
        async with ports.leased(HOLDER, f"farm {mode}", LEASE_SECONDS, **({"pause": False} if force else {})):
            try:
                if preflight is not None:
                    preflight()
                for name, step in steps:
                    if preflight is not None:
                        preflight()
                    began = ports.clock.monotonic()
                    try:
                        await step()
                    except Plan as e:
                        plans.append(e.t)
                        ports.log("normal", f"Stage change, plan only: {ports.english(e.t)}")
                    finally:
                        timings[name] = round(ports.clock.monotonic() - began, 1)
            except Plan as e:
                answer = {"result": "plan", "text_t": e.t}
            except Blocked as e:
                answer = {"result": "failed", "text_t": e.t, "retryable": False,
                          "failure_code": e.failure_code}
                if park_on_block and parks(mode):
                    try:
                        await park(mode)
                    except (Stop, RuntimeError) as parking_error:
                        ports.log("error", f"Stage change: parking after preset refusal failed: {parking_error}")
            except Stop as e:
                answer = {"result": "failed", "text_t": e.t}
            except ports.Busy:
                raise
            except RuntimeError as e:  # a move the navigation guard refused (ports.Refused)
                ports.log("error", f"Stage change: {e}")
                answer = {"result": "failed", "text_t": getattr(e, "t", None) or t("Erreur : {error}", error=f"{e!r}"[:200])}
            else:
                answer = {"result": "plan" if plans else "done", "text_t": joined(plans)}
        answer["timings"] = timings
        status["last"] = {**answer, "mode": mode}
        return answer

    souls = None
    if soul:
        souls = soul["feature"](ports, screens, soul["reader"], soul["rules"], soul["table"],
                                SimpleNamespace(look=look, tap=tap, front=front, to_battle=to_battle, Stop=Stop),
                                soul.get("engraving"))
        if hasattr(ports, "on_relaunch"):
            # A relaunch seen anywhere: the weapon read equipped is read again.
            ports.on_relaunch(lambda why: souls["relaunched"]())

    def noted(readings):
        """What a step checked, noted in the game's state (source setup)."""
        game = getattr(ports, "game", None)
        if game is not None:
            game["note"](readings, "setup")

    def parks(mode):
        return bool(souls) and mode in FARMED and souls["switch"]() == "real"

    def soul_verification_needed(mode, loadout=None):
        part = loadout if loadout is not None else (soul["loadout"](mode) if souls else None)
        chosen = (part or {}).get("soul_weapon")
        return bool(chosen and souls and souls.get("verification_needed", lambda *args: False)(
            chosen["id"], chosen.get("variant")))

    def preflight_soul(mode, loadout=None):
        """Reject an impossible or unauthorized requested loadout before
        changing its stage/preset. Static support is never runtime readiness."""
        part = loadout if loadout is not None else (soul["loadout"](mode) if souls else None)
        chosen = (part or {}).get("soul_weapon")
        if not chosen:
            return
        if souls is None:
            raise Stop("capacité de configuration Soul Weapon indisponible")
        if souls["switch"]() != "real":
            raise Plan("Soul Weapon désactivée : configuration demandée non appliquée")
        capability = soul.get("applicability")
        if capability is None:
            raise Stop("capacité de configuration Soul Weapon indisponible")
        applicability = capability(chosen)
        if not applicability["supported"]:
            raise Stop(applicability["reason_t"] or t("capacité de configuration Soul Weapon indisponible"))
        if applicability.get("engraving_required", True):
            if not soul.get("engraving"):
                raise Stop("capacité de configuration Soul Weapon indisponible")
            if souls["state"]()["engraving"] != "real":
                reason = t("gravure pas mise en place : premier passage supervisé en attente")
                ports.log("error", f"Soul weapon: {ports.english(reason)}")
                raise Stop("Soul Weapon : {why}", why=reason)

    async def equip_soul_weapon(mode, loadout=None):
        """The mode's loadout's soul weapon equipped (loadout: that one
        instead of the stored one; none chosen, or the switch off:
        nothing); its screen left open when the mode parks there."""
        part = loadout if loadout is not None else (soul["loadout"](mode) if souls else None)
        chosen = (part or {}).get("soul_weapon") if souls else None
        if not chosen or souls["switch"]() != "real":
            return
        try:
            await souls["ensure"](chosen["id"], chosen.get("variant"), parks(mode))
        except Stop as e:
            ports.log("error", f"Soul weapon: {ports.english(e.t)}")
            raise Stop("Soul Weapon : {why}", why=e.t) from None

    async def park(mode):
        """The farming mode's idle place: the Soul Weapon screen (only for
        mpw18 and mpw4, the soul weapon's switch real)."""
        if not parks(mode):
            return
        try:
            await souls["park"]()
        except Stop as e:
            raise Stop("Soul Weapon : {why}", why=e.t) from None

    def soul_steps(mode, loadout=None):
        steps = [("soul_weapon", lambda: equip_soul_weapon(mode, loadout))]
        return steps + ([("park", lambda: park(mode))] if souls else [])

    async def leave_park():
        """The Soul Weapon screen closed when it shows (back to the plain
        battle), else nothing."""
        if parked(await look()):
            await to_battle()

    async def unpark(mode, force=False):
        """Free play or the mine starts: the Soul Weapon screen left, when
        the game shows it ({result, text_t}); ports.Busy when the lease
        cannot be had (the user plays: nothing is touched)."""
        return await run(mode, [("unpark", leave_park)], force)

    async def ensure_soul_weapon(mode, loadout=None, force=False):
        """The soul weapon step alone, under the lease (e.g. the active
        mode's loadout just changed): {result: "done" or "failed", text};
        ports.Busy when the lease cannot be had (the caller retries). A
        weapon read equipped since the last relaunch or user input is not
        read again (≈0 s); another one is."""
        return await run(mode, soul_steps(mode, loadout), force, lambda: preflight_soul(mode, loadout))

    async def farm(stage, preset, mode, highest=None, force=False):
        """Farming stage with preset (None: kept as it is), then the
        loadout's soul weapon. A stage past highest (the highest seen
        farmed, None: unknown) is tried too: the gateway may never have
        seen a stage the game has unlocked. Only a region the stage change
        cannot read is refused (change_stage), and a stage the game does
        not open fails at the check after Move. force: see run."""
        if highest and stage > highest:
            ports.log("normal", f"Stage change: stage {stage} past the highest seen farmed ({highest}), tried")
        target = copy.deepcopy(soul["loadout"](mode)) if soul else None
        recovery = (souls["state"]().get("recovery") or {}) if souls else {}
        # A restarted game may already be on battle with an unfinished grid.
        # Restore its completion bonus before unrelated stage/preset gates
        # can stop the full transaction. This stays inside the same lease.
        steps = ([("engraving_recovery", lambda: equip_soul_weapon(mode, target))]
                 if recovery.get("required") or soul_verification_needed(mode, target) else [])
        if preset:
            steps.append(("preset_preflight", lambda: preflight_preset(preset)))
        steps.append(("stage", lambda: change_stage(stage, (target or {}).get("soul_weapon"))))
        if preset:
            steps.append(("preset", lambda: set_preset(preset)))
        steps += soul_steps(mode)
        answer = await run(mode, steps, force, lambda: preflight_soul(mode), park_on_block=True)
        # Only the complete transaction can acknowledge a failed setup.
        # A parking move and a healthy battle frame carry no such evidence.
        current = soul["loadout"](mode) if soul else None
        recovery = (souls["state"]().get("recovery") or {}) if souls else {}
        chosen = (target or {}).get("soul_weapon")
        engraving_required = bool(chosen and chosen.get("variant"))
        answer["verified_setup"] = bool(
            answer["result"] == "done" and target == current
            and (not target or target.get("stage") == stage and target.get("preset") == preset)
            and (not engraving_required or recovery.get("verified") and not recovery.get("required")
                 and recovery.get("weapon_id") == chosen.get("id")
                 and recovery.get("variant") == chosen.get("variant")))
        return answer

    async def after_relaunch(mode):
        """The soul weapon read again once the game is back: the lease
        waited for (every RELAUNCH_RETRY, at most RELAUNCH_WAIT), one alert
        on a failure."""
        since = ports.clock.monotonic()
        while True:
            try:
                answer = await run(mode, soul_steps(mode), preflight=lambda: preflight_soul(mode))
                break
            except ports.Busy:
                if ports.clock.monotonic() - since >= RELAUNCH_WAIT:
                    ports.log("normal", "Soul weapon after a relaunch: lease still taken, dropped")
                    return
                await ports.clock.sleep(RELAUNCH_RETRY)
        if answer["result"] == "failed":
            await ports.notify(f"After the game's relaunch ({mode}): {ports.english(answer['text_t'])}")

    def relaunched(mode):
        """For the watchdog, once its relaunch brought the game back."""
        if not souls or mode not in ("mpw18", "mpw4", "soul"):
            return None
        souls["relaunched"]()
        if not (soul["loadout"](mode) or {}).get("soul_weapon") or souls["switch"]() != "real":
            return None
        return ports.spawn(after_relaunch(mode))

    async def read_controls():
        """{preset} read on one guarded unfold, or None when unavailable."""
        if not real("preset"):
            return None
        try:
            async with ports.leased(HOLDER, "reading the preset", 30):
                first, second = await controls_look()
                return {"preset": await badge_of(first, second)}
        except (Stop, RuntimeError):  # Busy included
            return None

    async def handle_get(request):
        last = status["last"]
        return ports.respond({"switches": dict(switches), "last": last,
                              "soul_weapon": souls["state"]() if souls else None})

    async def handle_soul_weapon(request):
        """Explicit Agent test of one accepted weapon; no stage/preset repair."""
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if (not isinstance(body, dict) or set(body) != {"mode", "if_revision"}
                or body.get("mode") not in FARMED or not isinstance(body.get("if_revision"), str)):
            return ports.respond({"error_t": t("Attendu : {expected}", expected="{mode, if_revision}")}, status=400)
        name = body["mode"]
        revision = (soul or {}).get("revision")
        target = copy.deepcopy(soul["loadout"](name)) if soul else None
        input_mark = copy.deepcopy(ports.last_input()) if callable(getattr(ports, "last_input", None)) else None

        def guard():
            if not ports.enabled():
                raise Stop("Test Soul Weapon arrêté : plugin désactivé")
            if callable(getattr(ports, "last_input", None)) and ports.last_input() != input_mark:
                raise Stop("Test Soul Weapon arrêté : vous avez repris la main")
            if not agent_context[0]():
                raise Stop("Test Soul Weapon arrêté : mode Agent indisponible")
            if (not revision or revision(name) != body["if_revision"]
                    or soul["loadout"](name) != target or not (target or {}).get("soul_weapon")):
                raise Stop("Test Soul Weapon arrêté : configuration modifiée")

        try:
            guard()
        except Stop as exc:
            return ports.respond({"error_t": exc.t}, status=409)
        task = asyncio.current_task()
        agent_guards[task] = guard
        try:
            answer = await ensure_soul_weapon(name, target)
            guard()
        except ports.Busy as exc:
            return ports.respond({"error_t": exc.t}, status=409)
        except Stop as exc:
            return ports.respond({"result": "failed", "verified_weapon": False, "text_t": exc.t})
        finally:
            agent_guards.pop(task, None)
        answer = dict(answer, mode=name, if_revision=body["if_revision"],
                      verified_weapon=answer["result"] == "done")
        # This route deliberately has no verified_setup receipt and never
        # acknowledges the selected mode's stage or battle preset.
        return ports.respond(answer)

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        # No auto switch: the AUTO button is never tapped (refused).
        if not isinstance(body, dict) or "auto" in body \
                or any(body.get(k) not in (None, "real", "plan") for k in SWITCHES) \
                or body.get("soul_weapon") not in (None, "real", "off") \
                or body.get("engraving") not in (None, "real", "off"):
            return ports.respond({"error_t": t("Attendu : {expected}", expected='{stage_change, preset}: "real" | '
                                               '"plan"; soul_weapon, engraving: "real" | "off"')}, status=400)
        for name in SWITCHES:
            if body.get(name):
                if switches[name] != body[name]:
                    ports.log("normal", f"Stage change: {name} switched to {body[name]}")
                switches[name] = body[name]
        if body.get("soul_weapon") and souls:
            souls["set_switch"](body["soul_weapon"])
        if body.get("engraving") and souls:
            souls["set_engraving"](body["engraving"])
        ports.store.save()
        return await handle_get(request)

    api = {"farm": farm,
           "bind_agent_context": lambda current: agent_context.__setitem__(0, current),
           "change_stage": lambda stage, mode="mpw18": run(mode, [("stage", lambda: change_stage(stage))]),
           "set_preset": lambda name, mode="mpw18": run(mode, [("preset", lambda: set_preset(name))]),
           "read_controls": read_controls, "switches": lambda: dict(switches),
           "relaunched": relaunched, "ensure_soul_weapon": ensure_soul_weapon,
           "park": lambda mode: run(mode, [("park", lambda: park(mode))]), "parked": parked, "unpark": unpark,
           "soul_weapon_switch": lambda: souls["switch"]() if souls else "off",
           "soul_weapon_state": lambda: souls["state"]() if souls else None,
           "soul_verification_needed": soul_verification_needed,
           "engraving_open": lambda shot: bool(soul and soul.get("engraving")
                                                and soul["engraving"]["screen"].title(shot)),
           "engraving_switch": lambda: souls["state"]()["engraving"] if souls else "off",
           "soul_weapon": lambda mode="mpw18": ensure_soul_weapon(mode),
           "battle_stage": lambda shot, shade=1.0: select.battle_stage(shot, names, shade)}
    return {"api": api, "routes": [("GET", "/farming", handle_get), ("POST", "/farming", handle_post),
                                    ("POST", "/farming/soul-weapon", handle_soul_weapon)]}
