"""What the game is set to do: farming mpw18 (the default), or for a time
farming mpw4, free play or the Closed Mine; back to mpw18 when the timer
ends (the mine ends its last entry first).

GET  /mode         {mode, until, stage18, stage4, highest, configured, state, message, mine}
POST /mode         {mode, until, stage18, stage4, highest, floor, area}
POST /mode/timer   {add: minutes}: moves the end of the mode (and of the mine)

Switching stages in the game is not learned yet: it says what to do by
hand (and alerts) instead of tapping. The rules are in mode_rules.py; the
mode and its timer are kept in state.json ("mode") and go on after a
gateway restart.
"""

import asyncio
import logging

REASONS = {"mine done": "Mine terminée", "mine stopped": "Mine arrêtée", "timer": "Minuteur écoulé"}


def mode(ports, rules, timer, values, mines):
    """mines: the mine feature's api (start, stop, state, set_until, ended)."""
    status = {"mode": rules.DEFAULT, "until": None, "stage18": None, "stage4": None, "highest": None,
              "configured": False, "state": "idle", "message": "", "task": None}
    ports.store.register("mode", lambda: {key: status[key] for key in (
        "mode", "until", "stage18", "stage4", "highest", "configured")})

    def report(state, message):
        if (status["state"], status["message"]) != (state, message):
            logging.info(f"Slayer Legend mode {status['mode']}: {state} {message}")
        status["state"], status["message"] = state, message
        ports.store.save()

    def state():
        answer = {key: status[key] for key in ("mode", "until", "stage18", "stage4", "highest", "configured",
                                               "state", "message")}
        answer["mine"] = mines["state"]()
        return answer

    async def set_stage(number, mpw):
        """Brings the game to farming that stage with its loadout. The
        screens for it are not learned yet: says so instead of tapping."""
        report("todo", f"Passage au stage {number} (mpw{mpw}) : navigation pas encore apprise, fais-le à la main")
        await ports.notify(f"À faire à la main : passer au stage {number} (mpw{mpw})")
        return False

    async def enter(name):
        """What changing to mode name does (rules.entered)."""
        move = rules.entered(name, status["stage18"], status["stage4"])
        if move[0] == "stage":
            await set_stage(move[1], move[2])
        elif move[0] == "choose":
            report("idle", f"Farming mpw{move[1]} : choisis le stage")
        elif move[0] == "free":
            report("free", "Jeu libre : rien n’est touché jusqu’à la fin du minuteur")
        else:
            report("mine", "Mine")

    async def back_to_default(reason):
        status.update(mode=rules.DEFAULT, until=None)
        await ports.notify(f"{reason} : retour au farming mpw18"
                           + (f" (stage {status['stage18']})" if status["stage18"] else ""))
        await enter(rules.DEFAULT)

    async def watch():
        """Ends a timed mode: back to mpw18 farming once its time is up (the
        mine ends its last entry first)."""
        try:
            while status["mode"] != rules.DEFAULT:
                await ports.clock.sleep(rules.WATCH_EVERY)
                why = rules.due(status["mode"], status["until"], mines["state"](), ports.clock.wall())
                if why:
                    await back_to_default(REASONS[why])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mode failed")
            report("failed", f"Erreur : {e!r}"[:200])

    def watch_if_timed():
        task = status["task"]
        if status["mode"] != rules.DEFAULT and (task is None or task.done()):
            status["task"] = ports.spawn(watch())

    async def handle_state(request):
        return ports.respond(state())

    async def handle_mode(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        asked, error = rules.request(body)
        if error:
            return ports.respond({"error": error}, status=400)
        name, until, numbers = asked
        changed = name != status["mode"]
        status.update(mode=name, until=until, configured=True,
                      **{key: numbers[key] for key in ("stage18", "stage4", "highest")})
        if name == "mine":
            mines["start"](numbers["floor"], numbers["area"], until)
        else:
            mines["stop"]()
        if changed:
            await enter(name)
        watch_if_timed()
        ports.store.save()
        return ports.respond(state())

    async def handle_timer(request):
        """{add: minutes, may be negative}: moves the end of the timed mode
        (and of the mine); at or before now there is no time limit."""
        try:
            add = float((await request.json()).get("add"))
        except (ValueError, TypeError, AttributeError):
            return ports.respond({"error": "Expected {add: minutes}"}, status=400)
        status["until"] = timer.moved(status["until"], add, ports.clock.wall())
        if status["mode"] == "mine":
            mines["set_until"](status["until"])
        ports.store.save()
        return ports.respond(state())

    async def resume(app):
        """At the gateway's start: the timed mode state.json kept goes on."""
        if status["mode"] != rules.DEFAULT:
            report(*{"free": ("free", "Jeu libre : rien n’est touché jusqu’à la fin du minuteur"),
                     "mine": ("mine", "Mine")}.get(status["mode"], ("idle", f"Farming {status['mode']}")))
            status["task"] = ports.spawn(watch())

    saved = ports.store.saved.get("mode") or {}
    status.update(mode=saved.get("mode") if saved.get("mode") in rules.MODES else rules.DEFAULT,
                  until=values.time_or_none(saved.get("until")), configured=saved.get("configured") is True,
                  **{key: values.number_or_none(saved.get(key), 99999) for key in ("stage18", "stage4", "highest")})
    before = status["mode"]
    status["mode"], status["until"], ended = rules.restored(status["mode"], status["until"],
                                                            mines["state"]()["enabled"], ports.clock.wall())
    stopped = [f"mode {before}"] if ended else []
    if mines["ended"]:
        stopped.append("mine")
    if stopped:
        logging.info(f"Slayer Legend: timer ended while the gateway was stopped ({', '.join(stopped)}): "
                     "back to mpw18 farming, mine off"
                     + (" once Repeat entry is unticked" if mines["state"]()["state"] == "stopping" else ""))

    return {
        "routes": [("GET", "/mode", handle_state), ("POST", "/mode", handle_mode), ("POST", "/mode/timer", handle_timer)],
        "startup": [resume],
    }
