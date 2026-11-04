"""The watchdog: it checks that the game does what the selected mode
says, looking at it every rules.EVERY seconds, and when it does not,
alerts and repairs: mpw18 and mpw4 farming each with its own loadout
(stage, Battle settings preset); the Closed Mine, whose screens are
the mine feature's: the game away (rules.mine_away) is relaunched, then
the mine re-entered by the mine feature (reenter); free play, nothing.

GET /watchdog   {mode, status: {template, params}, line: {template,
                 params}, symptom, paused_t, counters, waiting, lease,
                 repairing, profile, intention} (status, line, paused_t: status
                 texts, see texts.py; paused_t null unless paused)
POST /watchdog/retry   {kind}: « Réessayer », that repair's backoff starts
                 over (needs the page token)

line: the watchdog's part of the mode's État row ("OK", the symptom,
"relance du jeu dans 4 min" while a repair backs off); waiting: the kinds
backing off now (each its next attempt still ahead), for « Réessayer ».

Each look checks that adb answers, that Android's crash dialog is not in
front, that the game's process runs and is in front, then the screen
(the shared capture, at most rules.MAX_AGE seconds old): the battle screen
or Power Saving Mode is farming; on the battle screen the numeral ending
the stage's name is compared with the mpw18 stage's. What it makes of a
look is watchdog_rules.py's (judge, decide); its profile is the selected
mode's (rules.profile).

The repairs: the relaunch (the launch feature's, holder "watchdog" of the
shared lease, stopped by a user input): it never kills the game, closes
Android's crash dialog by its button, takes the latest save, and leaves
Power Saving Mode. A wrong stage or Battle settings preset: the stage
change feature's farm() (under its own holder "stage_change", and
plan-only while its switch says so, see features/stage_change.py). On the
battle screen the stage is read whole (region and numeral); the preset and
AUTO are read on one unfold of the right edge's controls (the arrow's tap,
under the lease) at most every CONTROLS_EVERY seconds, whoever watches the
screen (only a user's input pauses it, 5 s). AUTO is never tapped
(the user's order, 2026-10-22): its reading is only said in the alerts.

The stage progress bar (stage.progress, under the stage's name) is read
at each look on the plain battle screen or the parking screen (the Soul
Weapon screen, where it is drawn too) while mpw18 or mpw4 farms; still
for rules.STALL_LOOKS readable looks in a row (rules.bar_look) it is the
symptom progress_stalled: an error alert, no repair, no tap. Not counted
while paused (free play, a mode's entry, a user input), in the mine, on
another screen (a menu: its own symptom) or within rules.BAR_SETTLE of a
relaunch: the count starts over. The way
back to battle from a game menu is available only through the farming
feature's calibrated menu-recovery capability. It recognises Latent Power,
Growth and Promotion, closes only their calibrated X or lit Character tab,
confirms plain battle, then parks. After a user input, the five-second
pause is followed by two fresh observations of a recoverable menu (the
second after MENU_CONFIRM), without another menu grace. Startup observation,
lease ownership and failure backoff remain unchanged. Other
panels stay blocked; no relaunch or guessed close is substituted.

Parking (rules.park_wanted): while mpw18 or mpw4 farms, its idle place
is the Soul Weapon screen, the battle going on above it. The screen read
there (farming's parked: its title) counts as the battle: its stage,
preset and progress bar are read the same way (the bar is drawn there
too); the preset and AUTO are not unfolded there. The plain battle is
then the symptom unparked: the stage change feature's park() goes back,
through the soul weapon step's own moves (Equipment, the Weapon tab, the
Soul Weapon icon), never a tap inside the panel.

Free play suspends it, and so does a mode's entry while its sequence
runs (the mode feature's state "moving", under the lease): the watchdog
waits for it. A user input pauses it 5 s; another holder of the
lease defers its repair. At the gateway's start it only observes its first
looks; the repairs' hourly counts are kept in state.json ("watchdog").
"""

import asyncio
import copy
import random
import json

AVAILABLE = ("relaunch", "mine_relaunch")
# Repairs by the stage change feature, and the switch that makes each real.
FARMING = {"stage_change": "stage_change", "select_preset": "preset"}
# Seconds between two readings of the preset (each an unfold).
CONTROLS_EVERY = 300
# The farming modes (their own stage and preset).
FARMED = ("mpw18", "mpw4", "soul")
CRITICAL = ("not_running", "away", "crash", "anr", "progress_stalled", "progress_unverified", "adb_missing", "monitoring_unavailable")


def watchdog(ports, screens, stage, rules, numeral_of, modes, mines, launches, loadout, farming=None, gold=None):
    """numeral_of(number): the numeral ending stage number's name; modes,
    mines, launches: the mode, mine and launch features' api; loadout(mode):
    the engraving feature's loadout of a farming mode ({stage, preset,
    soul_weapon}), read only; farming: the stage change feature's api (None:
    the relaunch only); gold: the gold feature's api (current: gold/s), whose
    rate at 0 raises an alert once confirmed (rules.gold_zero)."""
    memory = rules.fresh(ports.store.saved.get("watchdog"))
    saved_block = ports.store.saved.get("watchdog_policy_block")
    context = saved_block.get("context") if isinstance(saved_block, dict) else None
    if not (isinstance(context, dict) and context.get("mode") in FARMED
            and isinstance(context.get("target"), dict)
            and "input" in context and (context["input"] is None or isinstance(context["input"], dict))
            and isinstance(context.get("preset_allowed"), bool)
            and saved_block.get("kind") in (*FARMING, "loadout")
            and saved_block.get("failure_code") == "preset_action_paused"
            and ports.is_t(saved_block.get("text_t"))):
        saved_block = None
    status = {"text": ports.t("Démarrage"), "symptom": None, "paused": None, "repairing": None,
              "mode": None, "ended_at": None, "resumed": False, "anr_waited": False, "controls": None,
              "intention": None, "redirect_episode": None, "failure_notices": {}, "gold": rules.gold_fresh(),
              "bar": rules.bar_fresh(), "relaunched_at": None,
              "policy_block": copy.deepcopy(saved_block), "last_input": None,
              "observed_input": None, "menu_confirm_at": None,
              "notice_wall": None, "notice_attempt": None, "notice_mode": None, "observed": None,
              "critical_observation": None, "entry_mode": None, "entry_since": None,
              "setup_failure": None, "verification_since": None}
    notice_lock = asyncio.Lock()
    setup_listeners = []

    def notice_context():
        name = mode_now()
        return {"mode": name, "symptom": status["symptom"],
                "critical": copy.deepcopy(status["critical_observation"]),
                "target": policy_context(name) if name in FARMED else None,
                "block": copy.deepcopy(active_policy_block())}

    async def send_notice(text, *, periodic=False):
        """Serialize transport and acknowledge only successful delivery.
        The passive reminder runs even while a repair awaits game work."""
        async with notice_lock:
            now, name = ports.clock.wall(), mode_now()
            context = notice_context()
            family = rules.REPAIRS.get(context["symptom"]) or context["symptom"]
            block = active_policy_block() if periodic else None
            block_context = copy.deepcopy(block) if block else None
            if periodic:
                if not reminder_wanted():
                    return False
                last = status["notice_wall"] if status["notice_mode"] == name else None
                attempt = status["notice_attempt"] if status["notice_mode"] == name else None
                if ((last is not None and now - last < rules.REMIND_EVERY)
                        or attempt is not None and now - attempt < 30):
                    return False
            status["notice_mode"], status["notice_attempt"] = name, now
            # Real ports return bool. Older embedding adapters return None
            # after delivery; only explicit False reports transport failure.
            delivered = await ports.notify(text) is not False
            unchanged = notice_context() == context
            if not unchanged:
                # The delivered message belongs to an older observation.
                # It cannot acknowledge or delay a newer fault or target.
                status["notice_mode"], status["notice_attempt"] = None, None
                return False
            if delivered:
                status["notice_wall"] = ports.clock.wall()
                if family and periodic:
                    memory["incidents"] = {**memory.get("incidents", {}), family: status["notice_wall"]}
                if block and active_policy_block() is block and block == block_context:
                    block["notified_at"] = status["notice_wall"]
                    block.pop("notice_retry_at", None)
                    ports.store.save()
            return delivered

    def entry_elapsed(state=None):
        name = mode_now()
        state = state if state is not None else modes["state"]()
        if name not in FARMED or state.get("state") != "moving":
            status["entry_mode"], status["entry_since"] = None, None
            return None
        if status["entry_mode"] != name or status["entry_since"] is None:
            status["entry_mode"], status["entry_since"] = name, ports.clock.monotonic()
        return ports.clock.monotonic() - status["entry_since"]

    def reminder_wanted():
        name = mode_now()
        state = modes["state"]()
        elapsed = entry_elapsed(state)
        entry_overdue = elapsed is not None and elapsed >= rules.REMIND_EVERY
        last = ports.last_input() if callable(getattr(ports, "last_input", None)) else status["last_input"]
        return bool(name in rules.MODE_NAMES and name == status["mode"] and ports.enabled()
                    and not state.get("hold")
                    and not rules.paused(name, last.get("monotonic") if last else None,
                                         ports.clock.monotonic(), False)
                    and (state.get("state") != "moving" or status["critical_observation"] or entry_overdue)
                    and (status["repairing"] or active_policy_block()
                         or entry_overdue
                         or state.get("state") == "moving" and status["critical_observation"]
                         or memory["alerted"] and status["symptom"] not in (None, "unknown", "pending")))

    async def reminders():
        while True:
            delay = rules.EVERY
            if status["notice_mode"] == mode_now():
                wall = ports.clock.wall()
                due = max((status["notice_wall"] or wall) + rules.REMIND_EVERY,
                          (status["notice_attempt"] or wall) + 30)
                if due > wall:
                    delay = min(delay, due - wall)
            await ports.clock.sleep(delay)
            try:
                name = mode_now()
                # Entry can itself wait for a long operation. Read-only
                # process checks remain independent of its lease and gestures.
                if (name in FARMED and name == status["mode"] and ports.enabled()
                        and modes["state"]().get("state") == "moving"
                        and not status["critical_observation"]):
                    running = await ports.running()
                    if running is not True:
                        symptom = "not_running" if running is False else "adb_missing"
                        status["critical_observation"] = ports.t(rules.SYMPTOMS[symptom])
                if reminder_wanted():
                    observation = ((active_policy_block() or {}).get("text_t") or status["critical_observation"]
                                   or status["observed"] or status["text"])
                    elapsed = entry_elapsed()
                    if elapsed is not None and elapsed >= rules.REMIND_EVERY and not status["critical_observation"]:
                        observation = ports.t("Configuration du mode non vérifiée après {seconds} s", seconds=int(elapsed))
                    reason = ports.t("Dernière observation : {observation} ; reprise non vérifiée", observation=observation)
                    await send_notice(ports.english(rules.blocked_notice(mode_now(), reason)), periodic=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                ports.exception("Watchdog reminder failed")

    parking = bool(farming) and "park" in farming
    available = AVAILABLE + (tuple(FARMING) + ("loadout",) if farming else ()) + (("park",) if parking else ())
    if farming and callable(farming.get("back_to_battle")):
        available += ("back_to_battle",)
    ports.store.register("watchdog", lambda: rules.persisted(memory))
    ports.store.register("watchdog_policy_block", lambda: copy.deepcopy(status["policy_block"]))

    def forget_controls(why):
        """The game relaunched: the preset is read again."""
        status["controls"] = None
        status["policy_block"] = None
        ports.store.save()

    if hasattr(ports, "on_relaunch"):
        ports.on_relaunch(forget_controls)

    def say(level, text, params=None, notify=False):
        """One record for the gateway's log (and the page), in English: an
        English template filled with params, or a status text (rules.record);
        notify: also a phone alert. Its text."""
        said = ports.english(text) if ports.is_t(text) else ports.fill(text, params)
        ports.log(level, said, notify)
        return said

    def show(text):
        """The status: a status text."""
        status["text"] = text

    def mode_now():
        """The mode's name ("mine" while the mine farms)."""
        return "mine" if mines["state"]()["enabled"] else modes["state"]()["mode"]

    def profile():
        """The selected mode's stage and loadout (none for the mine)."""
        name = status["mode"] or mode_now()
        if name not in FARMED:
            return rules.profile(None, None, name)
        part = loadout(name) or {}
        state = modes["state"]()
        park = parking and rules.park_wanted(name, farming["soul_weapon_switch"](), state.get("state"),
                                             state.get("hold"))
        return rules.profile(part, part.get("stage"), name, park)

    def policy_context(name):
        # Pure accepted-target and input getters: no modes.state/profile call
        # here, because modes.state itself consumes the watchdog's last look.
        allowed = getattr(ports, "action_allowed", None)
        input_reader = getattr(ports, "last_input", None)
        return {"mode": name, "target": copy.deepcopy(loadout(name) or {}),
                "input": copy.deepcopy(input_reader() if callable(input_reader) else status["last_input"]),
                "preset_allowed": bool(callable(allowed) and allowed("battle_settings", "preset"))}

    def active_setup_failure():
        failed = status["setup_failure"]
        name = status["mode"]
        return failed if failed and name in FARMED and failed["context"] == policy_context(name) else None

    def active_menu_failure():
        failure = memory.get("menu_failure")
        if (not memory["backoff"].get("back_to_battle") or not isinstance(failure, dict)
                or not ports.is_t(failure.get("text_t"))):
            return None
        try:
            context = json.loads(memory.get("menu_context") or "null")
        except (TypeError, ValueError):
            return None
        name = status["mode"]
        return (failure if isinstance(context, dict) and name in FARMED
                and context.get("mode") == name and context.get("target") == (loadout(name) or {}) else None)

    def pending_engraving():
        """Unfinished work or no current proof: both outrank preset policy."""
        soul = farming.get("soul_weapon_state", lambda: None)() if farming else None
        name = status["mode"] or mode_now()
        return bool(((soul or {}).get("recovery") or {}).get("required")
                    or farming and name in FARMED
                    and farming.get("soul_verification_needed", lambda mode: False)(name))

    def active_policy_block():
        block = status["policy_block"]
        name = status["mode"]
        return (block if block and name in FARMED and block["context"] == policy_context(name)
                and not pending_engraving() else None)

    def release_policy_block():
        nonlocal memory
        block = status["policy_block"]
        if block:
            memory = rules.retry(memory, block["kind"])
            status["policy_block"] = None

    def setup_verified(receipt):
        """A current complete receipt only acknowledges its setup fault family."""
        nonlocal memory
        name = receipt.get("mode")
        if (receipt.get("result") != "done" or name not in FARMED or status["mode"] != name
                or receipt.get("target") != (loadout(name) or {})):
            return
        status["setup_failure"] = None
        status["verification_since"] = None
        setup_kinds = (*FARMING, "loadout")
        block = status["policy_block"]
        if block and block["context"]["mode"] == name and block["context"]["target"] == receipt["target"]:
            release_policy_block()
        for kind in setup_kinds:
            memory = rules.retry(memory, kind)
        if memory["verifying"] in setup_kinds:
            memory["verifying"] = None
        if rules.REPAIRS.get(status["symptom"]) in setup_kinds:
            status["symptom"] = None
            memory["symptom"] = None
            memory["incidents"] = {kind: stamp for kind, stamp in memory.get("incidents", {}).items()
                                   if kind not in setup_kinds}
            show(ports.t("Configuration vérifiée"))
        for listener in setup_listeners:
            try:
                listener(copy.deepcopy(dict(receipt, at=receipt.get("at", ports.clock.wall()))))
            except Exception as exc:
                ports.log("warning", f"Setup observer failed: {type(exc).__name__}")

    if "on_setup_verified" in modes:
        modes["on_setup_verified"](setup_verified)

    game = getattr(ports, "game", None)

    def naming(shot):
        """The screen the look names (its stage and progress bar are the
        scan's: features/game.py), and whether the battle shows plain."""
        if farming and farming.get("engraving_open", lambda shot: False)(shot):
            return "engraving", "Soul Weapon Engraving", False
        name = screens.classify(shot)
        known = screens.known_name(shot) if name == "other" else None
        if known:
            return "known", known, False
        if name == "menu" and farming and screens.plain_battle(shot):
            name = "battle"
        elif name == "menu" and parking and farming["parked"](shot):
            name = "parked"
        plain = name == "battle" and screens.plain_battle(shot)
        return name, screens.other_name(shot) if name == "other" else None, plain

    async def scanned_facts(shot):
        """facts() with the stage, its numeral and the bar from the game's
        scan of the same capture."""
        name, named, plain = await ports.analyse(naming, shot)
        if name == "known":
            return "known", None, None, None, named
        readings = await game["scan"](shot, ("battle_stage", "progress"))
        battle = name in ("battle", "parked")
        return (name, readings.get("stage_numeral") if battle else None,
                readings.get("stage") if battle and farming else None,
                readings.get("progress") if name == "parked" or plain else None, named)

    def facts(shot):
        if farming and farming.get("engraving_open", lambda shot: False)(shot):
            return "engraving", None, None, None, "Soul Weapon Engraving"
        name = screens.classify(shot)
        known = screens.known_name(shot) if name == "other" else None
        if known:
            return "known", None, None, None, known
        if name == "menu" and farming and screens.plain_battle(shot):
            name = "battle"  # the skill bar shows: no panel over the battle
        elif name == "menu" and parking and farming["parked"](shot):
            name = "parked"  # the Soul Weapon screen, the battle above it
        battle = name in ("battle", "parked")
        return (name, stage.read_battle(shot) if battle else None,
                farming["battle_stage"](shot, *((screens.PARKED_SHADE,) if name == "parked" else ()))
                if battle and farming else None,
                stage.progress(shot) if name == "parked" or battle and screens.plain_battle(shot) else None,
                screens.other_name(shot) if name == "other" else None)

    async def look(max_age=rules.MAX_AGE):
        """What one look sees (watchdog_rules.judge's seen)."""
        running = await ports.running()
        seen = {"adb": running is not None, "running": bool(running), "crash": False, "anr": False,
                "focused": False, "screen": None, "numeral": None, "stage": None, "bar": None}
        if running is None:
            return seen
        dialog = await ports.dialog()
        seen["crash"], seen["anr"] = dialog == "crash", dialog == "anr"
        if running and not dialog:
            focus = await ports.focus()
            seen["focused"], seen["window"] = focus["game"], focus["window"]
            if not focus["game"]:
                # Which window, for the diagnosis (a launcher, a system
                # dialog, Google's; never the account's).
                ports.log("normal", f"Watchdog: the game is not in front: {focus['window']}")
        if seen["focused"]:
            shot = await ports.capture(max_age=max_age)
            if shot:
                seen["screen"], seen["numeral"], seen["stage"], seen["bar"], seen["named"] = \
                    await (scanned_facts(shot) if game is not None else ports.analyse(facts, shot))
                if seen["screen"] == "menu" and farming and callable(farming.get("menu_recoverable")):
                    if callable(farming.get("menu_recovery_key")):
                        seen["menu_key"] = await ports.analyse(farming["menu_recovery_key"], shot)
                        seen["menu_recoverable"] = seen["menu_key"] is not None
                    else:
                        seen["menu_recoverable"] = bool(await ports.analyse(farming["menu_recoverable"], shot))
                        seen["menu_key"] = "recognized" if seen["menu_recoverable"] else None
        return seen

    async def read_controls(seen):
        """Read the preset periodically; report confirmed zero gold/s
        without inspecting AUTO or unfolding controls for that alert."""
        if not farming or seen["screen"] != "battle" or status["mode"] not in FARMED:
            return
        now = ports.clock.monotonic()
        if gold:
            status["gold"], trigger = rules.gold_zero(status["gold"], gold["current"](), ports.clock.wall())
            if trigger:
                status["gold"], alert = rules.gold_alert(status["gold"])
                if alert:
                    await send_notice(say("warning", rules.GOLD_ALERT, {}, notify=True))
        kept = status["controls"]
        if kept is None or now - kept[1] >= CONTROLS_EVERY:
            reading = await farming["read_controls"]()
            kept = status["controls"] = (reading, now) if reading else None
            if reading and game is not None:
                game["note"]({"preset": reading["preset"]})
            block = active_policy_block()
            if (reading and block and reading.get("preset") is not None
                    and reading["preset"] == block["context"]["target"].get("preset")):
                # Only this newly captured reading may clear the policy
                # obstacle. A cached badge can predate a manual correction.
                release_policy_block()
        if kept:
            seen["battle_settings"] = kept[0]["preset"]

    async def notify_all(actions):
        for _, level, text, values, notify in actions:
            said = say(level, text, values, notify)
            if notify:
                await send_notice(said)

    async def farm_repair(kind):
        """A stage change repair: farm() for the stage and the preset, park()
        back to the parking screen; read again at the next look. Deferred
        or a plan: not a failure (rules.not_run); stopped: one
        (rules.stopped)."""
        nonlocal memory
        status["controls"] = None
        part = profile()
        name = part["mode"]
        attempt_context = policy_context(name)
        epoch_reader = modes.get("mode_epoch", lambda: None)
        epoch = epoch_reader()

        def require_current_repair():
            if (mode_now() != name or epoch_reader() != epoch
                    or modes["state"]().get("state") == "moving"
                    or policy_context(name) != attempt_context):
                raise ports.Busy("Configuration demandée non vérifiée")

        attempt = None
        status["repairing"] = kind
        status["intention"] = rules.redirect_intention(kind, profile())
        show(ports.t("Vers {destination} : {purpose}", destination=status["intention"]["destination_t"],
                     purpose=status["intention"]["purpose_t"]))
        try:
            async def operation():
                nonlocal attempt
                if kind == "back_to_battle":
                    return await farming["back_to_battle"](name)
                if kind == "park":
                    return await farming["park"](name)
                attempt = modes["begin_verification"](name)
                if attempt is None:
                    raise ports.Busy("Configuration demandée non vérifiée")
                return await farming["farm"](part["stage"], part["preset"], name, modes["state"]().get("highest"))
            require_current_repair()
            if "guarded" in farming:
                answer = await farming["guarded"](operation, require_current_repair)
            else:
                answer = await operation()
            require_current_repair()
        except ports.Busy as e:
            memory = rules.not_run(memory, kind)
            say("normal", "Action waiting: {repair}; {why}", {"repair": rules.REPAIR_NAMES[kind], "why": e.t})
            return
        finally:
            status["repairing"] = None
            status["intention"] = None
        policy_refusal = (answer["result"] == "failed" and answer.get("retryable") is False
                          and answer.get("failure_code") == "preset_action_paused")
        if policy_refusal and (mode_now() != name or policy_context(name) != attempt_context):
            # This refusal belongs to the old attempt. It must neither block
            # the new request nor add a failure/backoff to its repair.
            memory = rules.not_run(memory, kind)
            ports.store.save()
            return
        if policy_refusal and not pending_engraving():
            # A policy refusal cannot heal through timed retries. Keep its
            # precise reason until target, input, policy or launch changes.
            memory = rules.not_run(memory, kind)
            for repair in (*FARMING, "loadout"):
                memory = rules.retry(memory, repair)
            block = {"context": attempt_context, "kind": kind,
                     "failure_code": answer["failure_code"], "text_t": copy.deepcopy(answer["text_t"])}
            previous = status["policy_block"]
            status["policy_block"] = block
            show(block["text_t"])
            if previous != block:
                say("warning", "Action stopped: {repair}; {why}",
                    {"repair": rules.REPAIR_NAMES[kind], "why": answer["text_t"]})
                if await send_notice(ports.english(rules.blocked_notice(name, answer["text_t"]))) is not False:
                    block["notified_at"] = ports.clock.wall()
                else:
                    block["notice_retry_at"] = ports.clock.wall() + 30
            ports.store.save()
            return
        if answer["result"] == "failed":
            if mode_now() == name and policy_context(name) == attempt_context:
                # Only an actual failed check for this target/input may make
                # missing proof a fault. Lifetime backoff is not evidence.
                status["setup_failure"] = {"context": attempt_context, "text_t": copy.deepcopy(answer["text_t"])}
                if status["symptom"] not in CRITICAL:
                    status["symptom"] = "setup_check_failed"
            memory, actions = rules.stopped(memory, kind, ports.clock.wall(), random.uniform(-1.0, 1.0), name)
            if kind == "back_to_battle" and mode_now() == name and policy_context(name) == attempt_context:
                memory["menu_failure"] = {"text_t": copy.deepcopy(answer["text_t"]), "at": ports.clock.wall()}
                ports.store.save()
            # Why it stopped, with the backoff's alert (if it is one).
            notify = any(action[4] for action in actions)
            failure_key = json.dumps({"target": part, "reason": answer["text_t"]}, sort_keys=True)
            notify = notify or status["failure_notices"].get(kind) != failure_key
            say("warning", "Action stopped: {repair}; {why}",
                {"repair": rules.REPAIR_NAMES[kind], "why": answer["text_t"]})
            if notify:
                await send_notice(ports.english(rules.blocked_notice(name, answer["text_t"])))
                status["failure_notices"][kind] = failure_key
            await notify_all([(*action[:4], False) for action in actions])
        elif answer["result"] == "done" and kind == "back_to_battle":
            memory["menu_failure"] = None
            ports.store.save()
        elif answer["result"] == "done" and answer.get("verified_setup") is True:
            if mode_now() == name and policy_context(name) == attempt_context:
                receipt = modes["confirm"](name, verified_setup=True, attempt=attempt)
                if receipt is None:
                    memory = rules.not_run(memory, kind)
        elif answer["result"] == "plan":
            memory = rules.not_run(memory, kind)
            say("normal", "Plan only: {repair}: {plan}", {"repair": rules.REPAIR_NAMES[kind], "plan": answer["text_t"]})

    async def wait_anr():
        """Android says the game is not responding: "Wait", once per
        dialog (its "Close app" would kill the game). Still there at the
        next look, it is the alert's."""
        if status["anr_waited"]:
            return
        status["anr_waited"] = True
        shot = await ports.capture(max_age=rules.MAX_AGE)
        if not shot:
            # No capture: Wait is tried again at the next look.
            status["anr_waited"] = False
            return
        try:
            async with ports.leased("watchdog", "Wait on the not responding dialog", 60):
                pressed = await ports.wait_anr(shot)
        except ports.Busy as e:
            ports.log("normal", f"Watchdog: Wait on the ANR dialog deferred: {e}")
            status["anr_waited"] = False
            return
        say("normal", "The game is not responding: Wait pressed" if pressed
            else "The game is not responding: Wait button not found")

    async def relaunch(kind="relaunch"):
        """The launch, holder "watchdog". Deferred (the lease, a user
        input) or the user's own launch: not a failure; stopped (blocked,
        failed): one. kind mine_relaunch: then the mine's way back in."""
        nonlocal memory
        task = launches["start"]("watchdog", False)
        if task is None:
            # The user's own launch runs: it is the repair.
            memory = rules.not_run(memory, kind)
            return
        status["repairing"] = kind
        status["intention"] = rules.redirect_intention(kind, profile())
        show(ports.t("Vers {destination} : {purpose}", destination=status["intention"]["destination_t"],
                     purpose=status["intention"]["purpose_t"]))
        try:
            await task
        finally:
            status["repairing"] = None
            status["intention"] = None
        ended = launches["state"]()
        status["relaunched_at"] = ports.clock.monotonic()
        if ended["state"] == "done" and farming and "relaunched" in farming:
            # Opening the game is not proof of farming readiness. Invalidate
            # its proof now; the next mode-checked full transaction verifies it.
            farming["relaunched"](mode_now())
        if ended["state"] == "deferred":
            memory = rules.not_run(memory, kind)
        elif ended["state"] in ("blocked", "failed"):
            memory, actions = rules.stopped(memory, kind, ports.clock.wall(), random.uniform(-1.0, 1.0),
                                            status["mode"])
            await notify_all(actions)
        elif kind == "mine_relaunch" and "reenter" in mines:
            # Back in the mine by its own way; out of feathers or no way in,
            # the mine ends and the mode goes back to the default (its alert).
            status["repairing"] = kind
            status["intention"] = rules.redirect_intention(kind, profile())
            try:
                answer = await mines["reenter"]()
            finally:
                status["repairing"] = None
                status["intention"] = None
            say("normal", "Back into the mine: {result} {text}", {"result": answer["result"],
                                                                  "text": answer["text_t"]})

    async def tick():
        nonlocal memory
        name = mode_now()
        now, wall = ports.clock.monotonic(), ports.clock.wall()
        confirming_menu = status["menu_confirm_at"] is not None
        status["menu_confirm_at"] = None
        last = await ports.user_input()  # only an input with the game in front
        if last != status["last_input"]:
            # A manual preset correction must be freshly observed as soon as
            # the normal input pause ends, not from the five-minute cache.
            status["controls"] = None
            # Menu observations before a new user interaction cannot be
            # reused as the two confirmations after its pause. Keep backoff.
            if memory.get("symptom") == "menu":
                memory = {**memory, "streak": 0, "since_repair": 0, "menu_since": None}
            status["last_input"] = copy.deepcopy(last)
        if name != status["mode"]:
            status["critical_observation"] = None
            status["setup_failure"] = None
            status["verification_since"] = None
            status["redirect_episode"] = None
            status["failure_notices"] = {}
            if status["mode"] is not None:
                # Another mode: its own symptoms, from scratch (the backoff
                # kept). Look at once, no menu grace; after free play,
                # another screen for a while may be the disconnect screen
                # or the saves.
                memory = rules.suspended(memory)
                status.update(resumed=True, controls=None,
                              ended_at=now if status["mode"] == "free" else status["ended_at"])
            status["mode"] = name
        mode_state = modes["state"]()
        entry_elapsed(mode_state)
        moving = mode_state.get("state") == "moving"
        why = rules.paused(name, last["monotonic"] if last else None, now, moving)
        if not why and (mode_state.get("intention") or {}).get("kind") == "resource_refresh":
            why = "Actualisation des ressources en cours"
        if not ports.enabled():
            # Off: no look at all, from scratch once back on.
            why = "Plugin désactivé"
            memory = rules.suspended(memory)
            status["resumed"] = True
        status["paused"] = why
        if why or launches["running"]():
            status["bar"] = rules.bar_fresh()
        if why:
            status["verification_since"] = None
            if name not in rules.MODE_NAMES or moving:
                memory = rules.suspended(memory)
                status["resumed"] = True
            status["symptom"] = None
            show(ports.t(why, mode=rules.MODE_NAMES.get(name, name)) if "{mode}" in why else ports.t(why))
            return False
        if launches["running"]():
            show(ports.t("Lancement du jeu en cours"))
            return False
        stamp = last["monotonic"] if last else None
        fresh_input = stamp is not None and stamp != status["observed_input"]
        seen = await look(max_age=0 if fresh_input or confirming_menu else rules.MAX_AGE)
        if seen.get("screen") is not None:
            status["observed_input"] = stamp
        if seen["screen"] == "menu" and name in FARMED:
            memory = rules.menu_observed(memory, name, loadout(name) or {}, seen.get("menu_key"))
        # A healthy battle/parking frame says nothing about an interrupted
        # engraving. Keep its durable repair intent visible after a restart.
        if name in FARMED:
            soul = farming.get("soul_weapon_state", lambda: None)() if farming else None
            unfinished = bool(((soul or {}).get("recovery") or {}).get("required"))
            failed = active_setup_failure()
            if unfinished:
                seen["loadout"] = ports.t("configuration demandée non vérifiée")
                status["verification_since"] = None
            elif failed or mode_state.get("state") == "failed":
                seen["setup_failure"] = failed["text_t"] if failed else (
                    mode_state.get("message_t") or ports.t("configuration demandée non vérifiée"))
                status["verification_since"] = None
            elif pending_engraving():
                # Expired, invalidated or absent proof requests a check. It
                # is not an observation of wrong equipment/incomplete cells.
                seen["verification_due"] = True
                if status["verification_since"] is None:
                    status["verification_since"] = now
                elapsed = now - status["verification_since"]
                if elapsed >= rules.REMIND_EVERY:
                    seen["verification_overdue"] = elapsed
            else:
                status["verification_since"] = None
        if seen["anr"]:
            await wait_anr()
        else:
            status["anr_waited"] = False
        await read_controls(seen)
        settled = status["relaunched_at"] is None or now - status["relaunched_at"] >= rules.BAR_SETTLE
        if name in FARMED and seen["screen"] in ("battle", "parked") and settled:
            status["bar"], seen["stalled"] = rules.bar_look(status["bar"], seen["bar"], now)
            seen["progress_unverified"] = rules.bar_unverified(status["bar"], now)
        else:
            status["bar"] = rules.bar_fresh()
        after_mode = status["ended_at"] is not None and now - status["ended_at"] < rules.AFTER_MODE
        symptom, text, params, memory = rules.judge(
            seen, profile(), numeral_of, last["monotonic"] if last else None, status["resumed"], memory, now,
            after_mode)
        menu_failure = active_menu_failure() if symptom == "menu" else None
        if menu_failure:
            text, params = "Dernier échec du retour au combat : {why}", {"why": menu_failure["text_t"]}
        status["resumed"] = False
        status["symptom"] = symptom
        status["critical_observation"] = ports.t(text, **params) if symptom in CRITICAL else None
        held = ports.lease.state()
        context = {"input_wall": last["wall"] if last else None,
                   "lease": held["holder"] if held and held["holder"] != "watchdog" else None,
                   "act": {kind: farming["switches"]()[switch] == "real" for kind, switch in FARMING.items()}
                   if farming else {}, "available": available, "jitter": random.uniform(-1.0, 1.0),
                   "mode": name}
        if farming:
            context["act"]["loadout"] = (farming.get("soul_weapon_switch", lambda: "off")() == "real"
                                             and farming.get("engraving_switch", lambda: "off")() == "real")
            # The full transaction checks each stage/preset switch itself.
            # Those unrelated plan switches must not suppress its first step:
            # recovering an interrupted engraving or refreshing its proof.
        block = status["policy_block"]
        if block and (name not in FARMED or block["context"] != policy_context(name)):
            release_policy_block()
        block = active_policy_block()
        if block and rules.REPAIRS.get(symptom) in (*FARMING, "loadout"):
            # Do not generate another repair, countdown, redirect notice or
            # failure counter for the exact same immutable policy obstacle.
            show(block["text_t"])
            if (wall >= block.get("notice_retry_at", 0)
                    and wall - block.get("notified_at", float("-inf")) >= rules.REMIND_EVERY):
                if await send_notice(ports.english(rules.blocked_notice(name, block["text_t"]))) is not False:
                    block["notified_at"] = ports.clock.wall()
                    block.pop("notice_retry_at", None)
                else:
                    block["notice_retry_at"] = ports.clock.wall() + 30
            ports.store.save()
            return False
        if symptom in (None, "unparked") and name in FARMED:
            modes["confirm"](name)
        memory, actions = rules.decide(memory, symptom, text, params, context, wall)
        if (symptom == "menu" and seen.get("menu_recoverable") and name in FARMED
                and last is not None and now - last["monotonic"] >= rules.PAUSE_AFTER_INPUT
                and memory["looks"] > rules.OBSERVE_FIRST
                and memory["since_repair"] == 1 and memory["verifying"] is None):
            status["menu_confirm_at"] = ports.clock.monotonic() + rules.MENU_CONFIRM
        if symptom == "unknown" and memory.get("symptom") == "monitoring_unavailable":
            symptom = status["symptom"] = "monitoring_unavailable"
            text, params = "Monitoring unavailable: no reliable game observation; farming unverified", {}
            status["critical_observation"] = ports.t(text)
        if symptom is None and memory["good"] >= rules.RECOVERED_AFTER:
            # One transient healthy frame or another input is not a new
            # redirect episode; a confirmed healthy return is.
            status["redirect_episode"] = None
            status["failure_notices"] = {}
        ports.store.save()
        minutes = rules.waiting(memory, symptom, wall)
        if minutes is not None:
            show(ports.t("{what} ; prochain essai dans {minutes} min", what=ports.t(text, **params), minutes=minutes))
        else:
            show(ports.t(text, **params))
        observed = status["observed"] = ports.t(text, **params)
        redirect = next((action[1] for action in actions if action[0] == "repair"), None)
        intention = rules.redirect_intention(redirect, profile()) if redirect else None
        redirect_key = json.dumps(intention, sort_keys=True) if intention else None
        new_redirect = bool(redirect and status["redirect_episode"] != redirect_key)
        redirect_notified = False

        async def deliver(text):
            nonlocal memory
            context = notice_context()
            delivered = await send_notice(text) is not False
            if not delivered and symptom and notice_context() == context:
                memory = rules.notification_failed(memory, rules.REPAIRS.get(symptom) or symptom, wall)
            return delivered

        async def announce_redirect():
            nonlocal redirect_notified
            if new_redirect and not redirect_notified:
                notice = rules.redirect_notice(intention, observed)
                say("normal", rules.redirect_details(intention, observed))
                if await deliver(ports.english(notice)):
                    status["redirect_episode"] = redirect_key
                    memory["notified"] = {**memory["notified"], redirect: wall}
                    memory["incidents"] = {**memory.get("incidents", {}), redirect: wall}
                redirect_notified = True

        repaired = False
        for action in actions:
            if action[0] == "record":
                _, level, text, values, notify = action
                if notify and new_redirect and not redirect_notified:
                    say("normal", rules.redirect_details(intention, observed))
                    delivered = await deliver(ports.english(rules.redirect_notice(intention, observed)))
                    notify = False
                    redirect_notified = True
                    if delivered:
                        status["redirect_episode"] = redirect_key
                said = say(level, text, values, notify)
                if notify:
                    await deliver(said)
            elif action[0] == "repair" and action[1] in ("relaunch", "mine_relaunch"):
                await announce_redirect()
                if (mode_now() != name or status["symptom"] != symptom
                        or modes["state"]().get("state") == "moving"):
                    memory = rules.not_run(memory, action[1])
                    return False
                ports.store.save()
                await relaunch(action[1])
                repaired = True
            elif action[0] == "repair" and (action[1] in FARMING or action[1] in ("park", "loadout", "back_to_battle")):
                await announce_redirect()
                if (mode_now() != name or status["symptom"] != symptom
                        or modes["state"]().get("state") == "moving"):
                    memory = rules.not_run(memory, action[1])
                    return False
                ports.store.save()
                await farm_repair(action[1])
                ports.store.save()
                repaired = True
            elif action[0] == "plan":
                say("normal", "Plan only (switch on plan): {repair}", {"repair": rules.REPAIR_NAMES[action[1]]})
        return repaired

    async def watch_steps():
        # Poll only the input timestamp between regular looks. A fresh input
        # is reflected at once, then the first look after the 5 s pause is
        # scheduled at its expiry. Full checks normally keep their 15 s cadence;
        # only a recognised recoverable menu gets one close confirmation.
        input_stamp = None
        resume_at = None
        next_look = ports.clock.monotonic() + rules.EVERY
        monitor_input = callable(getattr(ports.lease, "last_input", None))
        while True:
            try:
                if not monitor_input and status["menu_confirm_at"] is None:
                    await ports.clock.sleep(rules.EVERY)
                    await tick()
                    continue
                now = ports.clock.monotonic()
                last = ports.last_input() if monitor_input else status["last_input"]
                stamp = last["monotonic"] if last else None
                if stamp != input_stamp:
                    input_stamp = stamp
                    if stamp is not None and now - stamp < rules.PAUSE_AFTER_INPUT:
                        resume_at = stamp + rules.PAUSE_AFTER_INPUT
                        await tick()
                        next_look = ports.clock.monotonic() + rules.EVERY
                now = ports.clock.monotonic()
                if resume_at is not None and now >= resume_at:
                    resume_at = None
                    await tick()
                    next_look = ports.clock.monotonic() + rules.EVERY
                elif status["menu_confirm_at"] is not None and now >= status["menu_confirm_at"]:
                    await tick()
                    next_look = ports.clock.monotonic() + rules.EVERY
                elif now >= next_look:
                    await tick()
                    next_look = ports.clock.monotonic() + rules.EVERY
                now = ports.clock.monotonic()
                due = min(next_look, status["menu_confirm_at"]) if status["menu_confirm_at"] is not None else next_look
                await ports.clock.sleep(rules.input_wake_delay(now, due, resume_at))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                ports.exception("Watchdog failed")
                show(ports.t("Erreur : {error}", error=f"{e!r}"[:200]))

    async def watch():
        reminder = asyncio.create_task(reminders(), name="slayer-watchdog-reminders")
        try:
            await watch_steps()
        finally:
            reminder.cancel()
            await asyncio.gather(reminder, return_exceptions=True)

    async def start(app):
        ports.spawn(watch())

    def line():
        """The watchdog's part of the mode's État row: "OK", the pause, the
        repair under way, "{repair} dans {minutes} min" while the symptom's
        repair backs off, else the symptom (as the status)."""
        block = active_policy_block()
        if block:
            return block["text_t"]
        if status["paused"] or status["repairing"] or status["symptom"] in ("unknown", "pending"):
            return status["text"]
        if status["symptom"] is None:
            return ports.t("OK")
        minutes = rules.waiting(memory, status["symptom"], ports.clock.wall())
        kind = rules.REPAIRS.get(status["symptom"])
        if minutes is not None:
            return ports.t("{repair} dans {minutes} min", repair=rules.REPAIR_NAMES[kind], minutes=minutes)
        return status["text"]

    def state():
        held = ports.lease.state()
        wall = ports.clock.wall()
        return {"mode": status["mode"], "status": status["text"], "line": line(),
                "waiting": sorted(kind for kind, kept in memory["backoff"].items() if kept["next"] > wall),
                "symptom": status["symptom"], "paused_t": status["text"] if status["paused"] else None,
                "repairing": status["repairing"], "intention": status["intention"],
                "counters": rules.counters(memory, wall), "lease": held,
                "profile": profile(),
                "execution_blocker_t": copy.deepcopy((active_policy_block() or {}).get("text_t")),
                "execution_blocker_kind": (active_policy_block() or {}).get("kind")}

    async def handle_state(request):
        return ports.respond(state())

    async def handle_retry(request):
        nonlocal memory
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        kind = body.get("kind") if isinstance(body, dict) else None
        if kind not in rules.REPAIR_NAMES:
            return ports.respond({"error_t": ports.t("{field} : un de {choices}", field="kind",
                                                     choices=", ".join(rules.REPAIR_NAMES))}, status=400)
        memory = rules.retry(memory, kind)
        if kind in (*FARMING, "loadout"):
            release_policy_block()
        ports.store.save()
        say("normal", "Retry now: {repair}", {"repair": rules.REPAIR_NAMES[kind]})
        return ports.respond(state())

    def last_look():
        """Its last look, for the mode's overlay tone: {mode, level}."""
        symptom = status["symptom"]
        block = active_policy_block()
        failed = active_setup_failure() if symptom == "setup_check_failed" else None
        if symptom == "menu" and active_menu_failure():
            failed = {"text_t": status["text"]}
        return {"mode": status["mode"], "symptom": symptom,
                "level": "error" if block or failed else rules.level(symptom),
                "message_t": copy.deepcopy((block or failed)["text_t"]) if block or failed else status["text"],
                "repairing": status["repairing"], "intention": status["intention"],
                "execution_blocker_t": copy.deepcopy(block["text_t"]) if block else None,
                "execution_blocker_mode": block["context"]["mode"] if block else None,
                "execution_blocker_target": copy.deepcopy(block["context"]["target"]) if block else None,
                "execution_blocker_kind": block["kind"] if block else None,
                "blocked": bool(block or failed and not status["repairing"] or memory["alerted"] and symptom in rules.ERRORS
                                and not status["repairing"])}

    return {"routes": [("GET", "/watchdog", handle_state), ("POST", "/watchdog/retry", handle_retry)],
            "startup": [start], "api": {"look": last_look, "on_setup_verified": setup_listeners.append}}
