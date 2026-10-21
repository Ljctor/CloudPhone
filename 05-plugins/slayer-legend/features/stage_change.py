"""Brings the game to farming a stage with its Battle settings preset,
AUTO on: the moves the mode feature makes when a farming mode starts, and
the watchdog's repairs.

GET  /farming   {switches: {stage_change, preset, auto}, last}
POST /farming   {stage_change, preset, auto}: each "real" or "plan" (a
                field absent keeps its value); needs the page token

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
(ports, nav.py) and looks again for what it expects; anything else stops
the whole sequence with the step that failed, in French, for one alert by
the caller. Nothing is tried twice.

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

api: farm(stage, preset, mode) runs the three; change_stage, set_preset,
ensure_auto alone; each answers {result: "done", "plan" or "failed",
text}. read_controls() for the watchdog: {preset, auto} read on one
unfold, or None.
"""

import logging

# Seconds to wait after a move before the next look.
WAIT = 1.5
MOVE_WAIT = 3.0
# The controls fold away about 2 s after the arrow unfolds them. Measured
# on the phone: two separate guarded taps (the guard, then each its
# ssh/adb round trip) missed the badge twice, so the arrow and the next
# tap go in one adb call (ports.taps), UNFOLD_GAP apart, both guarded
# first. Then UNFOLD_WAIT for the unfold, LOOK_GAP between the two looks at
# the gear, FOLD_WAIT for them to fold away.
UNFOLD_GAP = 0.4
UNFOLD_WAIT = 0.5
LOOK_GAP = 0.4
FOLD_WAIT = 2.5
SETTINGS_CLOSE = (0.09, 0.965)
LEASE_SECONDS = 240
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


def stage_change(ports, screens, select, controls, rules, table):
    """select: stage_select.py; controls: battle_controls.py; table:
    stages.json."""
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

    async def front():
        if not await ports.focused():
            raise Stop("le jeu n’est plus au premier plan")

    async def tap(shot, screen, move, point, verified=False):
        await front()
        await ports.tap(shot, screen, move, point, verified=verified)

    async def to_battle(may_tap=True):
        """A fresh look at the battle screen with nothing over it: a bottom
        panel open is closed with its own tab, only when that tab reads
        lit (the reading is not calibrated yet: no guess)."""
        shot = await look()
        if await ports.analyse(screens.plain_battle, shot):
            return shot
        tab = await ports.analyse(screens.open_tab, shot)
        if tab is None:
            raise Stop("écran inattendu (ni le combat, ni un panneau du menu du bas reconnu)")
        if not may_tap:
            raise Plan(f"fermer le panneau ({tab[1]})")
        await tap(shot, tab[1], "close", (tab[0], screens.TAB_TAP_Y))
        await ports.clock.sleep(WAIT)
        shot = await look()
        if not await ports.analyse(screens.plain_battle, shot):
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
                await front()
                await ports.swipe(shot, "stage_select", "scroll", start, end, rules.SWIPE_MS)
            await ports.clock.sleep(WAIT)
            shot = await look()
            after = await ports.analyse(select.view, shot, names)
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
            await ports.clock.sleep(FOLD_WAIT)
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
        await ports.clock.sleep(WAIT)
        if await auto_state() != "on":
            raise Stop("AUTO pas en marche après l’avoir activé")

    async def run(mode, steps):
        """Runs steps under the lease: {result, text}; ports.Busy when the
        lease cannot be had (the caller waits for its next look). A plan
        step is written to the log and the next steps go on."""
        plans = []
        async with ports.leased(HOLDER, f"farm {mode}", LEASE_SECONDS):
            try:
                for step in steps:
                    try:
                        await step()
                    except Plan as e:
                        plans.append(str(e))
                        logging.info(f"Slayer Legend stage change, plan only: {e}")
            except Stop as e:
                answer = {"result": "failed", "text": str(e)}
            except ports.Busy:
                raise
            except RuntimeError as e:  # a move the navigation guard refused
                logging.error(f"Slayer Legend stage change: {e}")
                answer = {"result": "failed", "text": str(e)}
            else:
                answer = {"result": "plan" if plans else "done", "text": " ; ".join(plans)}
        status["last"] = {**answer, "mode": mode}
        return answer

    async def farm(stage, preset, mode, highest=None):
        """Farming stage with preset (None: kept as it is), AUTO on; never a
        stage past highest (the highest seen farmed, None: unknown)."""
        if highest and stage > highest:
            return {"result": "failed", "text": f"stage {stage} au-delà du plus haut vu farmé ({highest})"}
        steps = [lambda: change_stage(stage)]
        if preset:
            steps.append(lambda: set_preset(preset))
        steps.append(ensure_auto)
        return await run(mode, steps)

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
        return ports.respond({"switches": dict(switches), "last": status["last"]})

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if not isinstance(body, dict) or any(body.get(k) not in (None, "real", "plan") for k in SWITCHES):
            return ports.respond({"error": "Expected {stage_change, preset, auto}: \"real\" or \"plan\""}, status=400)
        if body.get("auto") == "real" and not AUTO_TAP_LEARNED:
            return ports.respond({"error": AUTO_NOT_LEARNED}, status=400)
        for name in SWITCHES:
            if body.get(name):
                if switches[name] != body[name]:
                    logging.info(f"Slayer Legend stage change: {name} switched to {body[name]}")
                switches[name] = body[name]
        ports.store.save()
        return await handle_get(request)

    api = {"farm": farm,
           "change_stage": lambda stage, mode="mpw18": run(mode, [lambda: change_stage(stage)]),
           "set_preset": lambda name, mode="mpw18": run(mode, [lambda: set_preset(name)]),
           "ensure_auto": lambda mode="mpw18": run(mode, [ensure_auto]),
           "read_controls": read_controls, "switches": lambda: dict(switches),
           "battle_stage": lambda shot: select.battle_stage(shot, names)}
    return {"api": api, "routes": [("GET", "/farming", handle_get), ("POST", "/farming", handle_post)]}
