"""Starts the game and brings it to the battle screen, on the user's press
or as the watchdog's relaunch (api: start(holder, user)). It never
kills the game: Android brings a running one to the front.

GET  /launch   {state, message} of the last launch
POST /launch   starts one (409 while one runs)

What it presses and when is in launch_rules.py; every press goes through
the navigation guard (ports.tap, ports.hold), under the shared lease
(holder "launch"): while another holder has it, the launch does not start.
Android's crash dialog ("Slayer Legend keeps stopping") is closed by its
"Close app" button (ports.close_crash), then the game is opened again.
The sign-in screen the game may show after a relaunch gets "Sign in with
Google" once (the user's choice, 2026-10-17), then Google's chooser its one
account (read by uiautomator, ports.account_chooser), then the save notice
its Confirm; anything else there is one alert, for the user.
"""

import asyncio


def launch(ports, screens, rules):
    t = ports.t
    status = {"state": "idle", "message": None, "task": None, "quiet": False}

    def report(state, message=None):
        """The launch's state and its message (a status text, or None)."""
        status["state"], status["message"] = state, message
        # The watchdog's relaunch is one record of the watchdog's own.
        if not status["quiet"]:
            ports.log("normal", f"Launch: {state} {ports.english(message)}".rstrip())

    async def steps():
        report("starting", t("Ouverture du jeu"))
        if not await ports.start_game():
            report("failed", t("Android ne répond pas"))
            return
        deadline = ports.clock.monotonic() + rules.DEADLINE
        memory = rules.fresh()
        while ports.clock.monotonic() < deadline:
            await ports.clock.sleep(rules.LOOK_EVERY)
            shot = await ports.capture()
            if not shot:
                continue
            crash = await ports.crashed()
            chooser = None
            if not crash and memory["signed_in"] is not None:
                chooser = await ports.account_chooser()
            if crash:
                screen = "crash"
            elif chooser is not None:
                screen = "chooser_one" if chooser["count"] == 1 else "chooser_other"
            else:
                screen = await ports.analyse(screens.classify, shot)
            if screen in ("battle", "menu") and await ports.focused():
                report("done", t("Le jeu est sur l’écran de combat"))
                return
            move, memory = rules.step(screen, memory, ports.clock.monotonic())
            if move == "close_crash":
                if not await ports.close_crash(shot):
                    report("blocked", t("Fenêtre « l’application s’arrête » : bouton introuvable, ferme-la à la main"))
                    return
                report("starting", t("Fenêtre « l’application s’arrête » fermée, réouverture du jeu"))
                await ports.clock.sleep(rules.AFTER_CRASH)
                if not await ports.start_game():
                    report("failed", t("Android ne répond pas"))
                    return
            elif move == "blocked_crash":
                report("blocked", t("Le jeu plante encore : relance-le à la main"))
                return
            elif move == "confirm":
                await ports.tap(shot, "save_notice", "confirm", screens.CONFIRM_TAP)
                report("loading", t("Dernière sauvegarde confirmée, chargement"))
                await ports.clock.sleep(rules.AFTER_CONFIRM)
            elif move == "leave_saver":
                await ports.hold(shot, "saver", "leave", screens.SAVER_TAP, screens.SAVER_HOLD_MS)
                memory["last_tap"] = ports.clock.monotonic()
                report("loading", t("Sortie du mode économie d’énergie"))
            elif move == "blocked_saver":
                report("blocked", t("Le mode économie d’énergie ne se ferme pas : touche son bouton à la main"))
                return
            elif move == "start":
                await ports.tap(shot, "title", "start", screens.START_TAP)
                memory["last_tap"] = ports.clock.monotonic()
                report("starting", t("Écran titre touché, connexion"))
            elif move == "sign_in":
                await ports.tap(shot, "sign_in", "google", screens.SIGN_IN_GOOGLE_TAP)
                memory["last_tap"] = ports.clock.monotonic()
                report("starting", t("« Sign in with Google » touché"))
            elif move == "choose_account":
                await ports.choose_account(shot, chooser["point"])
                memory["last_tap"] = ports.clock.monotonic()
                report("loading", t("Compte Google choisi"))
            elif move in ("blocked_sign_in", "blocked_chooser"):
                if move == "blocked_sign_in":
                    report("blocked", t("reconnexion Google impossible : à faire à la main"))
                    await ports.notify("Google sign-in impossible: to do by hand")
                else:
                    report("blocked", t("reconnexion Google : {count} comptes proposés au lieu d’un, à faire à la main",
                                        count=chooser["count"]))
                    await ports.notify(f"Google sign-in: {chooser['count']} accounts offered instead of one, "
                                       "to do by hand")
                return
            elif move == "blocked_other":
                report("blocked", t("Écran inattendu : termine le lancement à la main"))
                return
        report("blocked", t("Le jeu n’a pas atteint l’écran de combat en 3 minutes"))

    async def run(holder="launch", user=True):
        """The launch under the shared lease: holder "launch" on the user's
        press (user: a user input does not stop it)."""
        status["quiet"] = holder == "watchdog"
        try:
            async with ports.leased(holder, "Game launch", rules.DEADLINE + 60, user=user):
                await steps()
        except ports.Busy as e:
            # Not a failure of the launch: the lease or the user (the
            # watchdog does not count it).
            report("deferred", t("Lancement différé : {why}", why=e.t))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            ports.exception("Launch failed")
            report("failed", t("Erreur : {error}", error=f"{e!r}"[:200]))

    async def handle_state(request):
        return ports.respond({"state": status["state"], "message": ports.french(status["message"]),
                              "message_t": status["message"]})

    def running():
        task = status["task"]
        return task is not None and not task.done()

    def start(holder="launch", user=True):
        """A launch task, or None while one runs."""
        if running():
            return None
        status["task"] = ports.spawn(run(holder, user))
        return status["task"]

    async def handle_launch(request):
        if not start():
            return ports.respond({"error": "A launch is already running"}, status=409)
        ports.log("normal", f"Launch requested by {request.remote}")
        return ports.respond({"state": "starting"}, status=202)

    return {"routes": [("GET", "/launch", handle_state), ("POST", "/launch", handle_launch)],
            # For the watchdog: its relaunch (holder "watchdog", stopped by a
            # user input), whether one runs, and how the last one ended.
            "api": {"start": start, "running": running,
                    "state": lambda: {"state": status["state"], "message": status["message"]}}}
