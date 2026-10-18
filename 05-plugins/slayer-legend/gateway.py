"""Slayer Legend plugin, gateway side (loaded by the gateway's plugin loader).

GET  /api/v1/plugins/slayer-legend/emerald-mask[?counter=diamond]
     Where the emerald (or diamond) counter is, and the pixels of its digits after the
     comma, from an emulator screenshot: for browsers that cannot read the
     video's pixels.
GET  /api/v1/plugins/slayer-legend/screen
     The screen the game shows, {screen: title | save | battle | menu |
     saver | other | away (another app in front)}, and the farmed stage,
     {stage: {number, name, monsters_per_wave, drop, grade, soul_colour,
     soul_colour_confirmed, checked} or null}, from an emulator screenshot
     at most every 2 s. The number is read in Power Saving Mode; the
     battle screen only confirms it (checked: true when the numeral after
     the name still matches). ?known=N gives the number the page last saw,
     used while the gateway has not read one since it started. The rest
     comes from stages.json.
GET  /api/v1/plugins/slayer-legend/launch
     State of the last launch: {state, message}.
POST /api/v1/plugins/slayer-legend/launch
     Starts the game and brings it to the battle screen: taps "TAP TO START",
     then Confirm on the "last save time" notice (the latest save), or
     holds "Press here to finish Power Saving Mode" for 4 s. It never taps anything else;
     any other screen stops it and asks the user.

GET  /api/v1/plugins/slayer-legend/mine
     State of mine farming: {enabled, floor, area, until, state, message}.
POST /api/v1/plugins/slayer-legend/mine  {enabled, floor, area, until}
     Farms the Closed Mine: while the fight runs with "Repeat entry" ticked
     it only watches; when the game is back on the floor list (after 30
     entries) it taps the floor, the Area and 3 feathers again (always 3:
     the reward is multiplied by the feathers used). When the
     gold scroll buff is gone it unticks "Repeat entry" and stops: the
     entry under way ends, no more feathers are spent. It stops the same
     way at `until` (Unix seconds; null: no time limit). It leaves Power
     Saving Mode (4 s press) at most once a minute to see the buffs.

Screens are recognised from a few pixel areas, as fractions of the screen,
measured on a 360x780 screen (the page's device shapes keep this ratio).
"""

import asyncio
import base64
import importlib.util
import json
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
SAVER_TAP = (0.50, 0.88)
# The game leaves Power Saving Mode only after a press held a few seconds.
SAVER_HOLD_MS = 4000
MENU_LABELS = (0.0, 0.975, 1.0, 0.995)
# The emerald in the top bar: the game's own screens (battle and its menus).
TOP_EMERALD = (0.377, 0.018, 0.402, 0.030)
# Power Saving Mode: black screen, orange "In battle . . .", grey button.
SAVER_BUTTON = (0.33, 0.83, 0.67, 0.92)
SAVER_TEXT = (0.40, 0.465, 0.60, 0.48)
SAVER_TOP = (0.10, 0.10, 0.90, 0.25)  # bottom menu names, white on dark

LAUNCH = {"state": "idle", "message": "", "task": None, "since": 0.0}
EMERALD = {"time": 0.0, "value": None, "lock": None}
DIAMOND = {"time": 0.0, "value": None, "lock": None}
EMERALD_SECONDS = 0.4
SCREEN = {"time": 0.0, "value": None, "lock": None}
SCREEN_SECONDS = 2.0
MINE = {"enabled": False, "floor": None, "area": None, "until": None, "state": "off", "message": "", "task": None}
MINE_FEATHERS = 3
MINE_SECONDS = 10
# Checks in a row without the gold scroll before stopping (an animation
# can hide it for a moment).
MINE_NO_GOLD = 2
# The last stage number read in Power Saving Mode: {number, numeral}.
FARMED = {"number": None}


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


def dim_grey(r, g, b):
    return max(r, g, b) - min(r, g, b) < 20 and 35 < r < 110


def black(r, g, b):
    return r < 20 and g < 20 and b < 20


def light(r, g, b):
    # The bottom menu's names: light grey, darker under a panel.
    return min(r, g, b) > 150


def green(r, g, b):
    # Relative, so that it also holds when a panel darkens the screen.
    return g >= 64 and g > 1.3 * r and g > 2 * b


def classify(shot):
    if share(shot, CONFIRM_BUTTON, orange) > 0.6 and share(shot, EXIT_BUTTON, grey) > 0.6:
        return "save"
    # The top bar's emerald: the battle screen, or one of its panels over it
    # (the bottom menu names then go dark or are covered).
    if share(shot, TOP_EMERALD, green) > 0.15:
        return "battle" if share(shot, MENU_LABELS, light) > 0.01 else "menu"
    if (share(shot, SAVER_BUTTON, dim_grey) > 0.8 and share(shot, SAVER_TOP, black) > 0.95
            and share(shot, SAVER_TEXT, orange) > 0.08):
        return "saver"
    if 0.02 < share(shot, START_TEXT, white) < 0.4:
        return "title"
    return "other"


def setup(context):
    emerald = load_sibling(context.directory, "emerald_mask")

    async def read_emerald_mask(area):
        shot = await context.screenshot()
        if not shot:
            return {"mask": None, "reason": "screenshot"}
        width, height, image = shot
        scale = width / 360
        x0, y0 = emerald.js_round(area["x"] * scale), emerald.js_round(area["y"] * scale)
        w, h = emerald.js_round(area["width"] * scale), emerald.js_round(area["height"] * scale)
        pixels = bytearray()
        for y in range(y0, y0 + h):
            start = (y * width + x0) * 3
            pixels += image[start:start + w * 3]
        if len(pixels) != w * h * 3:
            return {"mask": None, "reason": "screenshot"}
        mask, reason = emerald.find_emerald_mask(pixels, w, h, scale, channels=3, area=area)
        if mask:
            # The page redraws the digits after the comma: send their pixels.
            box = mask["decimals"]["pixels"]
            crop = bytearray()
            for y in range(box["y"], box["y"] + box["height"]):
                start = (y * w + box["x"]) * 3
                crop += pixels[start:start + box["width"] * 3]
            box["rgb"] = base64.b64encode(bytes(crop)).decode("ascii")
            # The finder counts from AREA; the crop starts at a whole pixel.
            dx, dy = x0 / scale - area["x"], y0 / scale - area["y"]
            for part in (mask, mask["number"]):
                part["x"] += dx
                part["y"] += dy
            mask["decimals"]["x"] += dx
        return {"mask": mask, "reason": reason}

    async def handle_emerald_mask(request):
        diamond = request.query.get("counter") == "diamond"
        cache = DIAMOND if diamond else EMERALD
        if cache["lock"] is None:
            cache["lock"] = asyncio.Lock()
        loop = asyncio.get_running_loop()
        async with cache["lock"]:
            if cache["value"] is None or loop.time() - cache["time"] > EMERALD_SECONDS:
                try:
                    cache["value"] = await read_emerald_mask(emerald.DIAMOND_AREA if diamond else emerald.AREA)
                except Exception as e:
                    logging.warning(f"Counter mask: no screenshot: {e!r}")
                    cache["value"] = {"mask": None, "reason": "screenshot"}
                cache["time"] = loop.time()
        return context.json(cache["value"])

    stage = load_sibling(context.directory, "stage")
    with open(os.path.join(context.directory, "stages.json"), encoding="utf-8") as f:
        table = json.load(f)

    def stage_info(number, checked):
        if not number or number > len(table["stages"]):
            return {"number": number, "name": None, "checked": checked}
        info = dict(zip(table["fields"], table["stages"][number - 1]))
        return {"number": number, "checked": checked, **info}

    def name_numeral(number):
        """The Roman numeral ending the stage's name in the table, or None."""
        if not number or number > len(table["stages"]):
            return None
        last = table["stages"][number - 1][0].rsplit(" ", 1)[-1]
        if not last or any(c not in "IVX" for c in last):
            return None
        return stage._roman(last)

    async def read_screen(remembered):
        if not await in_focus():
            return {"screen": "away", "stage": None}
        shot = await context.screenshot()
        if not shot:
            return {"screen": None, "stage": None}
        screen = classify(shot)
        known = FARMED["number"] or remembered
        if screen == "saver":
            number, numeral = stage.read_saver(shot)
            # Trust a number whose numeral agrees with the table.
            if number and (numeral is None or name_numeral(number) in (None, numeral)):
                FARMED["number"] = number
                return {"screen": screen, "stage": stage_info(number, True)}
        elif screen in ("battle", "menu") and known:
            numeral = stage.read_battle(shot)
            return {"screen": screen, "stage": stage_info(known, numeral is not None and numeral == name_numeral(known))}
        return {"screen": screen, "stage": stage_info(known, False) if known else None}

    async def handle_screen(request):
        try:
            remembered = int(request.query.get("known", ""))
        except ValueError:
            remembered = None
        if remembered is not None and not 1 <= remembered <= len(table["stages"]) + 400:
            remembered = None
        if SCREEN["lock"] is None:
            SCREEN["lock"] = asyncio.Lock()
        loop = asyncio.get_running_loop()
        async with SCREEN["lock"]:
            if SCREEN["value"] is None or loop.time() - SCREEN["time"] > SCREEN_SECONDS:
                try:
                    SCREEN["value"] = await read_screen(remembered)
                except Exception as e:
                    logging.warning(f"Slayer Legend screen: no screenshot: {e!r}")
                    SCREEN["value"] = {"screen": None}
                SCREEN["time"] = loop.time()
        return context.json(SCREEN["value"])

    def report(state, message=""):
        LAUNCH["state"], LAUNCH["message"] = state, message
        logging.info(f"Slayer Legend launch: {state} {message}".rstrip())

    async def hold(shot, point, milliseconds):
        width, height, _ = shot
        x, y = str(round(point[0] * width)), str(round(point[1] * height))
        await context.adb("shell", "input", "swipe", x, y, x, y, str(milliseconds),
                          timeout=milliseconds / 1000 + 10)

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
            saver_taps = 0
            while time.monotonic() < deadline:
                await asyncio.sleep(3)
                shot = await context.screenshot()
                if not shot:
                    continue
                screen = classify(shot)
                if screen in ("battle", "menu") and await in_focus():
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
                if screen == "saver" and time.monotonic() - last_tap > 5:
                    # Power Saving Mode: the game is already in battle; a
                    # long press closes it. Give up after 3.
                    if saver_taps >= 3:
                        report("blocked", "Le mode économie d’énergie ne se ferme pas : touche son bouton à la main")
                        return
                    saver_taps += 1
                    await hold(shot, SAVER_TAP, SAVER_HOLD_MS)
                    last_tap = time.monotonic()
                    seen_other = None
                    report("loading", "Sortie du mode économie d’énergie")
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

    mine = load_sibling(context.directory, "mine")

    def mine_report(state, message):
        if (MINE["state"], MINE["message"]) != (state, message):
            logging.info(f"Slayer Legend mine: {state} {message}")
        MINE["state"], MINE["message"] = state, message

    async def mine_step(shot, point, wait=2.5):
        """Taps point if the game is still in front; the next screenshot."""
        if not await in_focus():
            return None
        await tap(shot, point)
        await asyncio.sleep(wait)
        return await context.screenshot()

    async def mine_relaunch(shot):
        """From the floor list: floor, Area, feathers. True once the fight
        shows again."""
        floor = MINE["floor"]
        for _ in range(12):
            rows = mine.floors(shot)
            row = next((y for y, n in rows if n == floor), None)
            if row is not None:
                break
            if not rows:
                return False
            # Scroll by about three rows towards the floor.
            width, height, _ = shot
            x = str(round(0.5 * width))
            up = rows[0][1] > floor
            a, b = (0.40, 0.65) if up else (0.65, 0.40)
            await context.adb("shell", "input", "swipe", x, str(round(a * height)), x, str(round(b * height)), "600")
            await asyncio.sleep(1.5)
            shot = await context.screenshot()
            if not shot or not mine.floor_list(shot):
                return False
        else:
            mine_report("blocked", f"Étage {floor} introuvable dans la liste")
            return False
        shot = await mine_step(shot, (0.5, row))
        if not shot or not mine.area_popup(shot):
            return False
        shot = await mine_step(shot, mine.AREA_TAPS[MINE["area"] - 1])
        if not shot or not mine.feather_popup(shot):
            return False
        shot = await mine_step(shot, mine.FEATHER_TAPS[MINE_FEATHERS - 1], 6)
        return bool(shot) and mine.in_fight(shot)

    async def mine_stop(shot, reason):
        """Unticks "Repeat entry" so that the entry under way is the last.
        True once it is unticked and farming is off."""
        if mine.repeat_ticked(shot):
            shot = await mine_step(shot, mine.REPEAT_TAP)
            if not shot or mine.repeat_ticked(shot):
                mine_report("blocked", f"{reason}, mais « Repeat entry » ne se décoche pas")
                return False
        MINE["enabled"] = False
        mine_report("stopped", f"{reason} : « Repeat entry » décoché, la mine s’arrête après cette entrée")
        return True

    async def farm_mine():
        no_gold = 0
        gold_seen = 0.0
        last_hold = 0.0
        failures = 0
        try:
            while MINE["enabled"]:
                await asyncio.sleep(MINE_SECONDS)
                if not await in_focus():
                    mine_report("waiting", "Le jeu n’est pas au premier plan")
                    continue
                shot = await context.screenshot()
                if not shot:
                    continue
                if classify(shot) == "saver":
                    # The buffs are hidden: leave Power Saving Mode to see them.
                    if time.monotonic() - last_hold > 60:
                        last_hold = time.monotonic()
                        await hold(shot, SAVER_TAP, SAVER_HOLD_MS)
                    continue
                over = MINE["until"] is not None and time.time() >= MINE["until"]
                if over and mine.in_fight(shot):
                    if await mine_stop(shot, "Durée écoulée"):
                        return
                    continue
                if mine.in_fight(shot):
                    failures = 0
                    if mine.gold_scroll(shot):
                        no_gold, gold_seen = 0, time.monotonic()
                        mine_report("farming", "Combat en cours, parchemin doré actif")
                        continue
                    no_gold += 1
                    if no_gold < MINE_NO_GOLD:
                        continue
                    if await mine_stop(shot, "Plus de parchemin doré"):
                        return
                    continue
                if mine.area_popup(shot) or mine.feather_popup(shot) or not mine.floor_list(shot):
                    # The user's own taps, or a screen this does not know.
                    mine_report("waiting", "Écran autre que la mine : rien à faire")
                    continue
                # The floor list: the 30 entries are done.
                if over:
                    MINE["enabled"] = False
                    mine_report("stopped", "Durée écoulée : pas de relance")
                    return
                if time.monotonic() - gold_seen > 5 * 60:
                    mine_report("stopped" if gold_seen else "waiting",
                                "Parchemin doré pas vu depuis 5 minutes : pas de relance")
                    if gold_seen:
                        MINE["enabled"] = False
                        return
                    continue
                if failures >= 3:
                    MINE["enabled"] = False
                    mine_report("blocked", "La relance a échoué 3 fois : relance la mine à la main")
                    return
                mine_report("relaunching", f"Relance : étage {MINE['floor']}, zone {MINE['area']}")
                if await mine_relaunch(shot):
                    failures = 0
                    mine_report("farming", "Mine relancée")
                elif MINE["state"] != "blocked":
                    failures += 1
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("Slayer Legend mine failed")
            MINE["enabled"] = False
            mine_report("failed", f"Erreur : {e!r}"[:200])

    def mine_state():
        return {key: MINE[key] for key in ("enabled", "floor", "area", "until", "state", "message")}

    async def handle_mine_state(request):
        return context.json(mine_state())

    async def handle_mine(request):
        try:
            body = await request.json()
            enabled = bool(body.get("enabled"))
            floor, area = int(body.get("floor") or 0), int(body.get("area") or 0)
            until = float(body["until"]) if body.get("until") is not None else None
        except (ValueError, TypeError, AttributeError):
            return context.json({"error": "Expected {enabled, floor, area, until}"}, status=400)
        if enabled and not (1 <= floor <= 9999 and 1 <= area <= 5):
            return context.json({"error": "floor 1-9999, area 1-5"}, status=400)
        MINE.update(floor=floor or None, area=area or None, until=until)
        task = MINE["task"]
        if enabled and not MINE["enabled"]:
            MINE["enabled"] = True
            mine_report("waiting", "Surveillance de la mine")
            if task is None or task.done():
                MINE["task"] = asyncio.get_running_loop().create_task(farm_mine())
        elif not enabled and MINE["enabled"]:
            MINE["enabled"] = False
            if task is not None and not task.done():
                task.cancel()
            mine_report("off", "")
        return context.json(mine_state())

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
    context.add_get("/screen", handle_screen)
    context.add_get("/launch", handle_launch_state)
    context.add_post("/launch", handle_launch)
    context.add_get("/mine", handle_mine_state)
    context.add_post("/mine", handle_mine)
