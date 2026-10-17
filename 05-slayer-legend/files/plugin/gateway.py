"""Slayer Legend plugin, gateway side (loaded by the gateway's plugin loader).

GET  /api/v1/plugins/slayer-legend/emerald-mask
     Where the emerald counter is, and the pixels of its digits after the
     comma, from an emulator screenshot: for browsers that cannot read the
     video's pixels.
GET  /api/v1/plugins/slayer-legend/launch
     State of the last launch: {state, message}.
POST /api/v1/plugins/slayer-legend/launch
     Starts the game and brings it to the battle screen: taps "TAP TO START",
     then Confirm on the "last save time" notice (the latest save). It never
     taps anything else; any other screen stops it and asks the user.

Screens are recognised from a few pixel areas, as fractions of the screen,
measured on a 360x780 screen (the page's device shapes keep this ratio).
"""

import asyncio
import base64
import importlib.util
import logging
import os
import time

PACKAGE = "com.gear2.growslayer"
ACTIVITY = f"{PACKAGE}/com.google.firebase.MessagingUnityPlayerActivity"

# Areas as (left, top, right, bottom) fractions of the screen.
START_TEXT = (0.30, 0.80, 0.70, 0.87)   # "TAP TO START", white on dark
START_TAP = (0.50, 0.836)
CONFIRM_BUTTON = (0.26, 0.735, 0.37, 0.755)  # orange
EXIT_BUTTON = (0.62, 0.735, 0.73, 0.755)     # grey
CONFIRM_TAP = (0.314, 0.745)
MENU_LABELS = (0.0, 0.975, 1.0, 0.995)  # bottom menu names, white on dark

LAUNCH = {"state": "idle", "message": "", "task": None, "since": 0.0}
EMERALD = {"time": 0.0, "value": None, "lock": None}
EMERALD_SECONDS = 0.4


def load_sibling(directory, name):
    spec = importlib.util.spec_from_file_location(f"cloudphone_plugin_slayer_legend_{name}",
                                                  os.path.join(directory, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def share(shot, area, test):
    """Fraction of the pixels in area (fractions of the screen) passing test(r, g, b)."""
    width, height, pixels = shot
    left, top = int(area[0] * width), int(area[1] * height)
    right, bottom = max(left + 1, int(area[2] * width)), max(top + 1, int(area[3] * height))
    hits = total = 0
    for y in range(top, bottom, 2):
        for x in range(left, right, 2):
            i = (y * width + x) * 3
            total += 1
            hits += bool(test(pixels[i], pixels[i + 1], pixels[i + 2]))
    return hits / total if total else 0.0


def white(r, g, b):
    return r > 200 and g > 200 and b > 200


def orange(r, g, b):
    return r > 190 and 90 < g < 200 and b < 80


def grey(r, g, b):
    return max(r, g, b) - min(r, g, b) < 25 and 50 < r < 170


def classify(shot):
    if share(shot, CONFIRM_BUTTON, orange) > 0.6 and share(shot, EXIT_BUTTON, grey) > 0.6:
        return "save"
    if share(shot, MENU_LABELS, white) > 0.03:
        return "battle"
    if 0.02 < share(shot, START_TEXT, white) < 0.4:
        return "title"
    return "other"


def setup(context):
    emerald = load_sibling(context.directory, "emerald_mask")

    async def read_emerald_mask():
        shot = await context.screenshot()
        if not shot:
            return {"mask": None, "reason": "screenshot"}
        width, height, image = shot
        area = emerald.AREA
        scale = width / 360
        x0, y0 = emerald.js_round(area["x"] * scale), emerald.js_round(area["y"] * scale)
        w, h = emerald.js_round(area["width"] * scale), emerald.js_round(area["height"] * scale)
        pixels = bytearray()
        for y in range(y0, y0 + h):
            start = (y * width + x0) * 3
            pixels += image[start:start + w * 3]
        if len(pixels) != w * h * 3:
            return {"mask": None, "reason": "screenshot"}
        mask, reason = emerald.find_emerald_mask(pixels, w, h, scale, channels=3)
        if mask:
            # The page redraws the digits after the comma: send their pixels.
            box = mask["decimals"]["pixels"]
            crop = bytearray()
            for y in range(box["y"], box["y"] + box["height"]):
                start = (y * w + box["x"]) * 3
                crop += pixels[start:start + box["width"] * 3]
            box["rgb"] = base64.b64encode(bytes(crop)).decode("ascii")
        return {"mask": mask, "reason": reason}

    async def handle_emerald_mask(request):
        if EMERALD["lock"] is None:
            EMERALD["lock"] = asyncio.Lock()
        loop = asyncio.get_running_loop()
        async with EMERALD["lock"]:
            if EMERALD["value"] is None or loop.time() - EMERALD["time"] > EMERALD_SECONDS:
                try:
                    EMERALD["value"] = await read_emerald_mask()
                except Exception as e:
                    logging.warning(f"Emerald mask: no screenshot: {e!r}")
                    EMERALD["value"] = {"mask": None, "reason": "screenshot"}
                EMERALD["time"] = loop.time()
        return context.json(EMERALD["value"])

    def report(state, message=""):
        LAUNCH["state"], LAUNCH["message"] = state, message
        logging.info(f"Slayer Legend launch: {state} {message}".rstrip())

    async def tap(shot, point):
        width, height, _ = shot
        await context.adb("shell", "input", "tap", str(round(point[0] * width)), str(round(point[1] * height)))

    async def in_focus():
        code, out = await context.adb("shell", "dumpsys", "window")
        return code == 0 and any("mCurrentFocus" in line and PACKAGE in line for line in out.splitlines())

    async def launch():
        try:
            report("starting", "Ouverture du jeu")
            code, _ = await context.adb("shell", "am", "start", "-n", ACTIVITY, timeout=20)
            if code != 0:
                report("failed", "Android ne répond pas")
                return
            deadline = time.monotonic() + 180
            confirmed = False
            last_tap = 0.0
            seen_other = None
            while time.monotonic() < deadline:
                await asyncio.sleep(3)
                shot = await context.screenshot()
                if not shot:
                    continue
                screen = classify(shot)
                if screen == "battle" and await in_focus():
                    report("done", "Le jeu est sur l’écran de combat")
                    return
                if screen == "save":
                    # The notice shows the latest save's time; Confirm keeps it.
                    await tap(shot, CONFIRM_TAP)
                    confirmed = True
                    seen_other = None
                    report("loading", "Dernière sauvegarde confirmée, chargement")
                    await asyncio.sleep(3)
                    continue
                if screen == "title" and time.monotonic() - last_tap > 8:
                    await tap(shot, START_TAP)
                    last_tap = time.monotonic()
                    seen_other = None
                    report("starting", "Écran titre touché, connexion")
                    continue
                # Loading and logging-in screens are "other" for a while; an
                # unknown screen that stays (Google sign-in, an update, an
                # event pop-up) is for the user.
                seen_other = seen_other or time.monotonic()
                if time.monotonic() - seen_other > (60 if confirmed else 45):
                    report("blocked", "Écran inattendu : termine le lancement à la main")
                    return
            report("blocked", "Le jeu n’a pas atteint l’écran de combat en 3 minutes")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend launch failed")
            report("failed", f"Erreur : {e!r}"[:200])

    async def handle_launch_state(request):
        return context.json({"state": LAUNCH["state"], "message": LAUNCH["message"]})

    async def handle_launch(request):
        task = LAUNCH["task"]
        if task is not None and not task.done():
            return context.json({"error": "A launch is already running"}, status=409)
        LAUNCH["task"] = asyncio.get_running_loop().create_task(launch())
        logging.info(f"Slayer Legend launch requested by {request.remote}")
        return context.json({"state": "starting"}, status=202)

    context.add_get("/emerald-mask", handle_emerald_mask)
    context.add_get("/launch", handle_launch_state)
    context.add_post("/launch", handle_launch)
