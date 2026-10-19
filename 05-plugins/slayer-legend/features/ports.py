"""What the features may use, built from the gateway's plugin context
(plugins.py of part 04): the ports. A feature gets these and nothing else
of the gateway, so what it may do to the game is all here.

- capture(max_age=0): Android's screen (width, height, RGB bytes) or None,
  a capture at most max_age seconds old shared with the other callers.
- analyse(fn, *args): fn(*args) in a worker thread (pixel work).
- tap, hold, swipe: the only ways to touch the game. Each names the screen
  recognised and the move wanted, and goes through the navigation guard
  (nav.py, navigation.json) first: refused (RuntimeError) unless it is an
  allowed move of that screen landing where the move is.
- focused(): the game is the app in front. running(): its process is
  there (False when gone, None when adb cannot tell). start_game(): opens
  it (the launch, on the user's press only).
- notify(text): the Cloud Phone's phone alerts, when the user turned them on.
- clock: wall() (Unix seconds), monotonic(), sleep(seconds).
- spawn(coroutine): runs it as a background task.
- store: the state kept across gateway restarts (state.json, see State).
- data_path(name): a file in the plugin's data directory, or None.
- respond(value, status=200): a JSON answer.
"""

import asyncio
import json
import logging
import os
import time
from types import SimpleNamespace

PACKAGE = "com.gear2.growslayer"
ACTIVITY = f"{PACKAGE}/com.google.firebase.MessagingUnityPlayerActivity"


class State:
    """What a gateway restart must not lose, in the plugin's data directory
    (state.json): one section per feature, each given by the snapshot the
    feature registered, rewritten whole when any of them changed.
    saved: what the file held when the gateway started ({} when there is
    none or it cannot be read)."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, "state.json") if data_dir else None
        self.data_dir = data_dir
        self.sections = {}
        self.text = None
        self.saved = {}
        self.old = None
        self.read()

    def read(self):
        """state.json; the first time, highest.json of earlier versions
        instead (removed once state.json is written, see flush)."""
        if not self.path:
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
        except FileNotFoundError:
            old = os.path.join(self.data_dir, "highest.json")
            try:
                with open(old, encoding="utf-8") as f:
                    self.saved = {"highest": json.load(f).get("number")}
            except (OSError, ValueError, AttributeError):
                return
            self.old = old
            return
        except (OSError, ValueError) as e:
            logging.warning(f"Slayer Legend: state not read: {e!r}")
            return
        if isinstance(saved, dict):
            self.saved = saved

    def register(self, section, snapshot):
        self.sections[section] = snapshot

    def save(self):
        if not self.path:
            return
        text = json.dumps({section: snapshot() for section, snapshot in self.sections.items()}, sort_keys=True)
        if text == self.text:
            return
        try:
            with open(f"{self.path}.tmp", "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(f"{self.path}.tmp", self.path)
            self.text = text
        except OSError as e:
            logging.warning(f"Slayer Legend: state not kept: {e}")

    def flush(self):
        """Once every feature registered: highest.json read instead of
        state.json is written over as state.json, then removed."""
        if not self.old:
            return
        self.save()
        if self.text:
            try:
                os.remove(self.old)
            except OSError:
                pass
        self.old = None


def build(context, nav):
    async def adb(*args, timeout=10):
        return await context.adb(*args, timeout=timeout)

    def allowed(screen, move, point, kind="tap"):
        """Every action goes through the navigation graph's guard first:
        refused unless it is an allowed move of the screen recognised."""
        refusal = nav.guard(screen, move, point[0], point[1], kind)
        if refusal:
            logging.error(f"Slayer Legend: action refused: {refusal}")
            raise RuntimeError(f"Action refusée par le garde-fou : {refusal}")

    async def tap(shot, screen, move, point):
        allowed(screen, move, point)
        width, height, _ = shot
        await adb("shell", "input", "tap", str(round(point[0] * width)), str(round(point[1] * height)))

    async def hold(shot, screen, move, point, milliseconds):
        allowed(screen, move, point, "hold")
        width, height, _ = shot
        x, y = str(round(point[0] * width)), str(round(point[1] * height))
        await adb("shell", "input", "swipe", x, y, x, y, str(milliseconds), timeout=milliseconds / 1000 + 10)

    async def swipe(shot, screen, move, start, end, milliseconds):
        allowed(screen, move, start, "swipe")
        width, height, _ = shot
        await adb("shell", "input", "swipe", str(round(start[0] * width)), str(round(start[1] * height)),
                  str(round(end[0] * width)), str(round(end[1] * height)), str(milliseconds))

    async def focused():
        code, out = await adb("shell", "dumpsys", "window")
        return code == 0 and any("mCurrentFocus" in line and PACKAGE in line for line in out.splitlines())

    async def running():
        """False when the game's process is gone, None when adb cannot tell."""
        code, out = await adb("shell", "pidof", PACKAGE)
        if code == 0 and out.strip():
            return True
        return False if code == 1 and not out.strip() else None

    async def start_game():
        """True when Android started the game's activity."""
        code, _ = await adb("shell", "am", "start", "-n", ACTIVITY, timeout=20)
        return code == 0

    def spawn(coroutine):
        return asyncio.get_running_loop().create_task(coroutine)

    # Older gateways give plugins no data directory: then nothing is kept.
    data_dir = getattr(context, "data_dir", None)

    def data_path(name):
        return os.path.join(data_dir, name) if data_dir else None

    return SimpleNamespace(
        capture=context.screenshot, analyse=context.analyse,
        tap=tap, hold=hold, swipe=swipe,
        focused=focused, running=running, start_game=start_game,
        notify=context.notify,
        clock=SimpleNamespace(wall=time.time, monotonic=time.monotonic, sleep=asyncio.sleep),
        spawn=spawn, store=State(data_dir), data_path=data_path, respond=context.json,
    )
