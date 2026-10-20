"""The mpw18 watchdog: while the game should farm mpw18 (the default mode,
no mine), it looks at the game every rules.EVERY seconds and, when the
farming is not going on, alerts and relaunches the game.

GET /watchdog   {status: {template, params}, text, symptom, paused,
                 counters, lease, repairing, profile}

Each look checks that adb answers, that Android's crash dialog is not in
front, that the game's process runs and is in front, then the screen
(the shared capture, at most rules.MAX_AGE seconds old): the battle screen
or Power Saving Mode is farming; on the battle screen the numeral ending
the stage's name is compared with the mpw18 stage's. What it makes of a
look is watchdog_rules.py's (judge, decide).

The only repair done here is the relaunch (the launch feature's, holder
"watchdog" of the shared lease, stopped by a user input): it never kills
the game, closes Android's crash dialog by its button, takes the latest
save, and leaves Power Saving Mode. The way back to battle from a game
menu stays an alert (its close buttons differ per panel); the stage, the
Battle settings preset and the loadout wait for phases 2 and 3.

Free play, the timed modes and the mine (with or without a time limit)
suspend it: the mine's own "jeu absent" alert and the watchdog's never
overlap. A user input pauses it a minute; another holder of the lease
defers its repair. At the gateway's start it only observes its first
looks; the repairs' hourly counts are kept in state.json ("watchdog").
"""

import asyncio
import logging

LEVELS = {"normal": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
AVAILABLE = ("relaunch",)


def watchdog(ports, screens, stage, rules, numeral_of, modes, mines, launches, loadout):
    """numeral_of(number): the numeral ending stage number's name; modes,
    mines, launches: the mode, mine and launch features' api; loadout(mode):
    the engraving feature's loadout of a farming mode ({stage, preset,
    soul_weapon}), read only."""
    memory = rules.fresh(ports.store.saved.get("watchdog"))
    status = {"template": "Démarrage", "params": {}, "symptom": None, "paused": None, "repairing": None,
              "mode": None, "ended_at": None, "resumed": False, "anr_waited": False}
    ports.store.register("watchdog", lambda: rules.persisted(memory))

    def say(level, template, params, notify=False):
        """One record for the gateway's log (and the page), in French with
        its template for translation; notify: also a phone alert."""
        text = template.format(**params) if params else template
        logging.getLogger("cloudphone.slayer-legend").log(
            LEVELS[level], text, extra={"source": "slayer-legend", "notify": notify,
                                        "fields": {"template": template, "params": params} if params else None})
        return text

    def show(template, params=None):
        status["template"], status["params"] = template, params or {}

    def mode_now():
        """The mode's name ("mine" while the mine farms)."""
        return "mine" if mines["state"]()["enabled"] else modes["state"]()["mode"]

    def profile():
        """The mpw18 stage and mpw18's loadout."""
        part = loadout("mpw18") or {}
        return rules.profile(part, part.get("stage"))

    def facts(shot):
        name = screens.classify(shot)
        return name, stage.read_battle(shot) if name == "battle" else None

    async def look():
        """What one look sees (watchdog_rules.judge's seen)."""
        running = await ports.running()
        seen = {"adb": running is not None, "running": bool(running), "crash": False, "anr": False,
                "focused": False, "screen": None, "numeral": None}
        if running is None:
            return seen
        dialog = await ports.dialog()
        seen["crash"], seen["anr"] = dialog == "crash", dialog == "anr"
        if running and not dialog:
            seen["focused"] = await ports.focused()
        if seen["focused"]:
            shot = await ports.capture(max_age=rules.MAX_AGE)
            if shot:
                seen["screen"], seen["numeral"] = await ports.analyse(facts, shot)
        return seen

    async def wait_anr():
        """Android says the game is not responding: "Wait", once per
        dialog (its "Close app" would kill the game). Still there at the
        next look, it is the alert's."""
        if status["anr_waited"]:
            return
        status["anr_waited"] = True
        shot = await ports.capture(max_age=rules.MAX_AGE)
        if not shot:
            return
        try:
            async with ports.leased("watchdog", "« Attendre » sur « ne répond pas »", 60):
                pressed = await ports.wait_anr(shot)
        except ports.Busy as e:
            logging.info(f"Slayer Legend watchdog: Wait on the ANR dialog deferred: {e}")
            status["anr_waited"] = False
            return
        say("normal", "Le jeu ne répond pas : « Attendre » touché" if pressed
            else "Le jeu ne répond pas : bouton « Attendre » introuvable", {})

    async def relaunch():
        task = launches["start"]("watchdog", False)
        if task is None:
            # The user's own launch runs: it is the repair.
            return
        status["repairing"] = "relaunch"
        show("Réparation en cours : {repair}", {"repair": rules.REPAIR_NAMES["relaunch"]})
        try:
            await task
        finally:
            status["repairing"] = None
        ended = launches["state"]()
        # Said by the next look (repair done or without effect).
        logging.debug(f"Slayer Legend watchdog: relaunch ended: {ended['state']} {ended['message']}".rstrip())

    async def tick():
        nonlocal memory
        name = mode_now()
        now, wall = ports.clock.monotonic(), ports.clock.wall()
        last = ports.last_input()
        if name != status["mode"]:
            if status["mode"] is not None and name == "mpw18":
                # A mode ended: look at once, no menu grace; another screen
                # for a while may be the disconnect screen or the saves.
                status.update(ended_at=now, resumed=True)
            status["mode"] = name
        why = rules.paused(name, last["monotonic"] if last else None, now)
        status["paused"] = why
        if why:
            if name != "mpw18":
                memory = rules.suspended(memory)
            show(why, {"mode": name})
            return False
        if launches["running"]():
            show("Lancement du jeu en cours")
            return False
        seen = await look()
        if seen["anr"]:
            await wait_anr()
        else:
            status["anr_waited"] = False
        after_mode = status["ended_at"] is not None and now - status["ended_at"] < rules.AFTER_MODE
        symptom, text, params, memory = rules.judge(
            seen, profile(), numeral_of, last["monotonic"] if last else None, status["resumed"], memory, now,
            after_mode)
        status["resumed"] = False
        status["symptom"] = symptom
        held = ports.lease.state()
        context = {"input_wall": last["wall"] if last else None,
                   "lease": held["holder"] if held and held["holder"] != "watchdog" else None,
                   "act": {}, "available": AVAILABLE}
        memory, actions = rules.decide(memory, symptom, text, params, context, wall)
        ports.store.save()
        show(text, params)
        repaired = False
        for action in actions:
            if action[0] == "record":
                _, level, template, values, notify = action
                said = say(level, template, values, notify)
                if notify:
                    await ports.notify(said)
            elif action[0] == "repair" and action[1] == "relaunch":
                ports.store.save()
                await relaunch()
                repaired = True
        return repaired

    async def watch():
        while True:
            await ports.clock.sleep(rules.EVERY)
            try:
                await tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.exception("Slayer Legend watchdog failed")
                show("Erreur : {error}", {"error": f"{e!r}"[:200]})

    async def start(app):
        ports.spawn(watch())

    def state():
        held = ports.lease.state()
        return {"status": {"template": status["template"], "params": status["params"]},
                "text": status["template"].format(**status["params"]) if status["params"] else status["template"],
                "symptom": status["symptom"], "paused": status["paused"], "repairing": status["repairing"],
                "counters": rules.counters(memory, ports.clock.wall()), "lease": held,
                "profile": profile()}

    async def handle_state(request):
        return ports.respond(state())

    return {"routes": [("GET", "/watchdog", handle_state)], "startup": [start]}
