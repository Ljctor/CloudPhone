"""Starts the game and brings it to the battle screen, on the user's press
only.

GET  /launch   {state, message} of the last launch
POST /launch   starts one (409 while one runs)

What it presses and when is in launch_rules.py; every press goes through
the navigation guard (ports.tap, ports.hold).
"""

import asyncio
import logging


def launch(ports, screens, rules):
    status = {"state": "idle", "message": "", "task": None}

    def report(state, message=""):
        status["state"], status["message"] = state, message
        logging.info(f"Slayer Legend launch: {state} {message}".rstrip())

    async def run():
        try:
            report("starting", "Ouverture du jeu")
            if not await ports.start_game():
                report("failed", "Android ne répond pas")
                return
            deadline = ports.clock.monotonic() + rules.DEADLINE
            memory = rules.fresh()
            while ports.clock.monotonic() < deadline:
                await ports.clock.sleep(rules.LOOK_EVERY)
                shot = await ports.capture()
                if not shot:
                    continue
                screen = await ports.analyse(screens.classify, shot)
                if screen in ("battle", "menu") and await ports.focused():
                    report("done", "Le jeu est sur l’écran de combat")
                    return
                move, memory = rules.step(screen, memory, ports.clock.monotonic())
                if move == "confirm":
                    await ports.tap(shot, "save_notice", "confirm", screens.CONFIRM_TAP)
                    report("loading", "Dernière sauvegarde confirmée, chargement")
                    await ports.clock.sleep(rules.AFTER_CONFIRM)
                elif move == "leave_saver":
                    await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                    memory["last_tap"] = ports.clock.monotonic()
                    report("loading", "Sortie du mode économie d’énergie")
                elif move == "blocked_saver":
                    report("blocked", "Le mode économie d’énergie ne se ferme pas : touche son bouton à la main")
                    return
                elif move == "start":
                    await ports.tap(shot, "title", "start", screens.START_TAP)
                    memory["last_tap"] = ports.clock.monotonic()
                    report("starting", "Écran titre touché, connexion")
                elif move == "blocked_other":
                    report("blocked", "Écran inattendu : termine le lancement à la main")
                    return
            report("blocked", "Le jeu n’a pas atteint l’écran de combat en 3 minutes")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend launch failed")
            report("failed", f"Erreur : {e!r}"[:200])

    async def handle_state(request):
        return ports.respond({"state": status["state"], "message": status["message"]})

    async def handle_launch(request):
        task = status["task"]
        if task is not None and not task.done():
            return ports.respond({"error": "A launch is already running"}, status=409)
        status["task"] = ports.spawn(run())
        logging.info(f"Slayer Legend launch requested by {request.remote}")
        return ports.respond({"state": "starting"}, status=202)

    return {"routes": [("GET", "/launch", handle_state), ("POST", "/launch", handle_launch)]}
