"""Brings the game to farming a stage with its Battle settings preset,
AUTO on: the moves the mode feature makes when a farming mode starts (and
the watchdog's repairs).

Each step looks first (a fresh screenshot), makes one guarded move
(ports, nav.py) and looks again for what it expects; anything else stops
the whole sequence with the step that failed, in French, for one alert by
the caller. Nothing is tried twice.

- Stage: closes the bottom panel open (its own tab again), opens the
  stage map (Select Region), goes to the target's region with the banner's
  arrows and to its row by scrolling (stage_change_rules.plan, at most
  MOST_MOVES), taps Move on the row whose name reads as the target, then
  reads the target's name on the battle screen.
- Preset: unfolds the right edge's controls (arrow, then badge, in one
  adb call: they fold away within 2 s), checks Battle settings by its
  title, taps the preset unless it is the one framed, checks the frame,
  closes, then reads the badge.
- AUTO: two looks at the unfolded controls a moment apart: a spinning
  gear is on. Off, the gear is tapped (unfold and gear in one adb call),
  then read again. Never tapped while it is on or cannot be told.

api: farm(stage, preset) runs the three (None, or why it stopped);
change_stage, set_preset, ensure_auto alone; auto_state() for a check.
They take turns on one lock: a lease shared with the other features that
touch the game can take its place.
"""

import asyncio
import logging

# Seconds to wait after a move before the next look.
WAIT = 1.5
MOVE_WAIT = 3.0
# The controls: between the arrow and the next tap in one adb call, for
# the unfold, between the two looks at the gear, for them to fold away.
UNFOLD_GAP = 0.4
UNFOLD_WAIT = 0.5
LOOK_GAP = 0.4
FOLD_WAIT = 2.5
SETTINGS_CLOSE = (0.09, 0.965)


class Stop(Exception):
    """The sequence stops: the step that failed, in French."""


def stage_change(ports, screens, select, controls, rules, table):
    """select: stage_select.py; controls: battle_controls.py; table:
    stages.json."""
    names = select.regions(table)
    lock = asyncio.Lock()

    async def look():
        shot = await ports.capture()
        if not shot:
            raise Stop("pas de capture d’écran")
        return shot

    async def tap(shot, screen, move, point, verified=False):
        if not await ports.focused():
            raise Stop("le jeu n’est plus au premier plan")
        await ports.tap(shot, screen, move, point, verified=verified)

    async def to_battle():
        """A fresh look at the battle screen with nothing over it: a bottom
        panel open is closed with its own tab."""
        shot = await look()
        if await ports.analyse(screens.plain_battle, shot):
            return shot
        tab = await ports.analyse(screens.open_tab, shot)
        if tab is None:
            raise Stop("écran inattendu (ni le combat, ni un panneau du menu du bas)")
        await tap(shot, tab[1], "close", (tab[0], screens.TAB_TAP_Y))
        await ports.clock.sleep(WAIT)
        shot = await look()
        if not await ports.analyse(screens.plain_battle, shot):
            raise Stop("fermeture du panneau du menu du bas")
        return shot

    async def change_stage(target):
        if not rules.supported(target, names):
            raise Stop(f"stage {target} hors des régions connues")
        shot = await to_battle()
        if await ports.analyse(select.battle_stage, shot, names) == target:
            return
        await tap(shot, "battle", "stage_select", select.STAGE_MAP_TAP)
        await ports.clock.sleep(WAIT)
        shot = await look()
        view = await ports.analyse(select.view, shot, names)
        if not view["popup"]:
            raise Stop("ouverture de Select Region")
        for _ in range(rules.MOST_MOVES):
            step = rules.plan(view, target)
            if step[0] == "fail":
                raise Stop(f"Select Region : {step[1]}")
            if step[0] == "move":
                await tap(shot, "stage_select", "move", (select.MOVE_TAP_X, step[1]), verified=True)
                await ports.clock.sleep(MOVE_WAIT)
                shot = await look()
                seen = await ports.analyse(select.battle_stage, shot, names)
                if seen != target:
                    raise Stop(f"vérification après Move (lu : {seen or 'rien'})")
                return
            if step[0] == "arrow":
                await tap(shot, "stage_select", step[1], select.ARROW_TAPS[step[1]])
            else:
                start, end = rules.SWIPE_DOWN if step[1] == "down" else rules.SWIPE_UP
                if not await ports.focused():
                    raise Stop("le jeu n’est plus au premier plan")
                await ports.swipe(shot, "stage_select", "scroll", start, end, rules.SWIPE_MS)
            await ports.clock.sleep(WAIT)
            shot = await look()
            after = await ports.analyse(select.view, shot, names)
            if not rules.progressed(view, after):
                raise Stop(f"Select Region : {'flèche' if step[0] == 'arrow' else 'défilement'} sans effet")
            view = after
        raise Stop(f"Select Region : stage {target} pas atteint en {rules.MOST_MOVES} gestes")

    async def unfold(shot, then=None, verified=()):
        """Unfolds the controls from the battle screen (shot), and taps then
        (move, point) in the same adb call. The arrow's spot is on the AUTO
        tile while they are unfolded: they must read folded first."""
        if not await ports.analyse(controls.folded, shot):
            await ports.clock.sleep(FOLD_WAIT)
            shot = await look()
            if not (await ports.analyse(screens.plain_battle, shot) and await ports.analyse(controls.folded, shot)):
                raise Stop("les contrôles de droite ne se replient pas")
        if not await ports.focused():
            raise Stop("le jeu n’est plus au premier plan")
        moves = [("preset_arrow", controls.ARROW_TAP)] + ([then] if then else [])
        await ports.taps(shot, "battle", moves, UNFOLD_GAP, verified={"preset_arrow", *verified})

    async def controls_look():
        """Two fresh looks at the unfolded controls, a moment apart."""
        await unfold(await to_battle())
        await ports.clock.sleep(UNFOLD_WAIT)
        first = await look()
        await ports.clock.sleep(LOOK_GAP)
        return first, await look()

    async def badge_reads(name):
        first, second = await controls_look()
        return name in (await ports.analyse(controls.badge, first), await ports.analyse(controls.badge, second))

    async def set_preset(name):
        if await badge_reads(name):
            return
        await unfold(await to_battle(), ("preset_badge", controls.BADGE_TAP))
        await ports.clock.sleep(WAIT)
        shot = await look()
        if not await ports.analyse(controls.settings_open, shot):
            raise Stop("ouverture de Battle settings")
        if await ports.analyse(controls.selected, shot) != name:
            await tap(shot, "battle_settings", "preset", controls.preset_tap(name))
            await ports.clock.sleep(WAIT)
            shot = await look()
            chosen = await ports.analyse(controls.selected, shot)
            if chosen != name:
                raise Stop(f"choix du preset {name} dans Battle settings (lu : {chosen or 'rien'})")
        await tap(shot, "battle_settings", "close", SETTINGS_CLOSE)
        await ports.clock.sleep(WAIT)
        if not await badge_reads(name):
            raise Stop(f"vérification du preset {name} sur le badge")

    async def auto_state():
        """"on", "off" or None (cannot tell) on the next two looks."""
        first, second = await controls_look()
        return await ports.analyse(controls.auto, first, second)

    async def ensure_auto():
        state = await auto_state()
        if state == "on":
            return
        if state is None:
            raise Stop("état d’AUTO illisible")
        await unfold(await to_battle(), ("auto", controls.AUTO_TAP), verified={"auto"})
        await ports.clock.sleep(WAIT)
        if await auto_state() != "on":
            raise Stop("AUTO pas en marche après l’avoir activé")

    async def guarded(steps):
        """Runs steps under the lock: None, or why it stopped."""
        async with lock:
            try:
                for step in steps:
                    await step()
            except Stop as e:
                return str(e)
            except RuntimeError as e:  # a move the navigation guard refused
                logging.error(f"Slayer Legend stage change: {e}")
                return str(e)
        return None

    async def farm(stage, preset):
        """Farming stage with preset (None: kept as it is), AUTO on."""
        steps = [lambda: change_stage(stage)]
        if preset:
            steps.append(lambda: set_preset(preset))
        steps.append(ensure_auto)
        return await guarded(steps)

    async def checked_auto():
        """auto_state under the lock; None when it cannot tell."""
        async with lock:
            try:
                return await auto_state()
            except (Stop, RuntimeError):
                return None

    api = {"farm": farm,
           "change_stage": lambda stage: guarded([lambda: change_stage(stage)]),
           "set_preset": lambda name: guarded([lambda: set_preset(name)]),
           "ensure_auto": lambda: guarded([ensure_auto]),
           "auto_state": checked_auto}
    return {"api": api, "routes": []}
