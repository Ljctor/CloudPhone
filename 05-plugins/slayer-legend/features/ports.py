"""What the features may use, built from the gateway's plugin context
(plugins.py of part 04): the ports. A feature gets these and nothing else
of the gateway, so what it may do to the game is all here.

- capture(max_age=0): Android's screen (width, height, RGB bytes) or None,
  a capture at most max_age seconds old shared with the other callers;
  on_capture(listener): listener(shot) for each capture (the game's scan,
  features/game.py: every capture is scanned).
- on_relaunch(listener): listener(why) when running() finds the game's
  process gone or another one (a relaunch, Android restarted);
  relaunched(why) tells them.
- analyse(fn, *args): fn(*args) in a worker thread (pixel work).
- tap, hold, swipe, taps: the only ways to touch the game. Each names the
  screen recognised and the move wanted, and goes through the navigation
  guard (nav.py, navigation.json) first: refused (Refused, a RuntimeError) unless it
  is an allowed move of that screen landing where the move is; verified
  says the caller checked the move's precondition. taps sends several taps
  back to back in one adb call (controls that fold away within 2 s), all
  guarded before the first is sent. Each also needs the shared lease, held
  by the task's sequence: refused (Busy) without it, or once the user
  played since it was taken.
- lease, leased(holder, reason, seconds, user=False, pause=True), Busy:
  the one shared lease on the game's taps (see Lease); `async with
  leased(...)` runs a tapping sequence under it, Busy when another holder
  has it or the user plays (an input in the last 10 s with the game in
  front, looked at then: see Lease.playing; pause=False: the user's last 10 s are not
  waited for, e.g. a switch the user asked to resume now; an input during
  the sequence still stops it).
- pause_left(): the seconds left of the user-input pause (0: none).
- last_input(): the user's last input ({monotonic, wall}) or None, wherever
  it went (the launcher, another app, the stream's play button).
  user_input(): the same only when it counts as playing (Lease.playing:
  the game in front, looked at now when the input is recent), else None.
- viewers(): the viewers connected now (None on a gateway that does not
  say: then nothing that shows on screen is done for the watchdog).
- focused(): the game is the app in front (its window has the focus).
  focus(): for the watchdog, {game: True (in front), False (another app's
  window has the focus), None (cannot tell: no focus said, or a passing
  window over the game, the keyboard, a toast, a pop-up, the focus moving),
  window: the window that has it} (see focus_of). running(): its process is
  there (False when gone, None when adb cannot tell). start_game(): opens
  it as the launcher does (am start, MAIN/LAUNCHER, never -S: it never
  kills the game), for the launch (the user's press, or the mpw18
  watchdog's relaunch). dialog(): Android's dialog for the game in front,
  "crash" ("Slayer Legend keeps stopping") or "anr" ("Slayer Legend isn't
  responding"), system windows, or None; crashed(): the crash one.
  close_crash(shot): taps the crash dialog's "Close app" button;
  wait_anr(shot): the ANR dialog's "Wait" (its "Close app" would kill the
  game: never). Both are found by uiautomator (native, so their bounds are
  exact) and go through the guard (crash_dialog, anr_dialog).
- account_chooser(): Google's account chooser in front (after "Sign in
  with Google"): {count, point} of the accounts uiautomator lists (point:
  the one account's centre, pixels, when there is exactly one), or None
  when it is not in front; choose_account(shot, point) taps it through the
  guard (account_chooser/account). The accounts are never logged.
- notify(text, actions=None): the Cloud Phone's phone alerts, when the
  user turned them on; actions: its buttons [{label, path, body, token}]
  (left out on a gateway without them). action_token(path, seconds): a
  one-time token for one POST to the plugin's path from an alert's button
  (None on an older gateway); revoke_action(token) withdraws it.
- enabled(), set_enabled(on): the plugin's on/off switch (kept in
  state.json, on by default). While off the lease is refused to the
  plugin's own holders (PLUGIN_HOLDERS) and a sequence under way stops at
  its next tap: the plugin taps nothing; the watchdog, the mine and the
  mode switch wait.
- clock: wall() (Unix seconds), monotonic(), sleep(seconds).
- spawn(coroutine): runs it as a background task.
- store: the state kept across gateway restarts (state.json, see State).
- data_path(name): a file in the plugin's data directory, or None.
- respond(value, status=200): a JSON answer.
- t(template, **params): a status text ({template, params}, French, for
  the page to translate), is_t(value): one; english(text), french(text):
  its words filled (texts.py). fill(template, params): an English template
  filled, its status-text parameters in English. The log and the phone
  alerts are English.
- log(level, text, notify=False, **params): one record of the gateway's
  log, its source the plugin's id (context.log; Python logging tagged so
  on an older gateway): level "normal", "warning" or "error", notify marks
  it worth attention (a mark only: the page pops nothing up; the phone
  alert is notify(text)). exception(text): an error record with the traceback
  of the exception being handled.
"""

import asyncio
import contextlib
import contextvars
import importlib.util
import json
import logging
import os
import re
import time
import traceback
from types import SimpleNamespace

PACKAGE = "com.gear2.growslayer"
ACTIVITY = f"{PACKAGE}/com.google.firebase.MessagingUnityPlayerActivity"
# Android's crash and "not responding" dialogs: their windows' titles,
# whatever the language.
CRASH_WINDOW = f"Application Error: {PACKAGE}"
ANR_WINDOW = f"Application Not Responding: {PACKAGE}"
GMS = "com.google.android.gms"
NODE = re.compile(r"<node\b[^>]*>")
TEXT = re.compile(r'\btext="([^"]*)"')
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BOUNDS = re.compile(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')


def _sibling(name):
    spec = importlib.util.spec_from_file_location(f"cloudphone_plugin_slayer_legend_features_{name}",
                                                  os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The status texts ({template, params}) and their English (texts.py).
texts = _sibling("texts")
LEVELS = {"normal": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}


def python_log(source):
    """log(level, text, notify=False, **params) for a gateway without
    context.log: Python logging, tagged with source and notify as the
    gateway's log handler reads them."""
    def log(level, text, notify=False, **params):
        logging.getLogger(f"cloudphone.{source}").log(
            LEVELS[level], text.format(**params) if params else text, extra={"source": source, "notify": notify})
    return log


def text_ports():
    """The ports' texts: t, is_t, english, french, fill (texts.py)."""
    return {"t": texts.t, "is_t": texts.is_t, "english": texts.english, "french": texts.french,
            "fill": lambda text, params: texts.fill(text, params, texts.english)}


def exception_log(log):
    """exception(text): an error record with the traceback being handled."""
    def exception(text):
        log("error", f"{text}\n{traceback.format_exc()}")
    return exception


def crash_window(dumpsys):
    """The game's Android dialog that has the focus, from `dumpsys window`:
    "crash" (keeps stopping), "anr" (isn't responding) or None."""
    for line in dumpsys.splitlines():
        if "mCurrentFocus" in line:
            if CRASH_WINDOW in line:
                return "crash"
            if ANR_WINDOW in line:
                return "anr"
    return None


# Windows that take the focus for a moment over the app in front.
PASSING = ("InputMethod", "Toast", "PopupWindow")
WINDOW_NAME = re.compile(r"(?:Window|ActivityRecord)\{\S+ u\d+ ([^}\s]+(?: [^}\s]+)*?)(?: t\d+)?\}")


def window_name(window):
    """"com.android.launcher3/.Launcher" of "Window{6 u0
    com.android.launcher3/.Launcher}" (an ActivityRecord alike)."""
    found = WINDOW_NAME.search(window or "")
    return found.group(1) if found else window


def focus_of(dumpsys):
    """(game, window) from `dumpsys window`: game True when the game's
    window has the focus (mCurrentFocus); None when no window has it (null,
    the focus moving between windows) or a passing window has it (PASSING)
    while the game is still the focused app (mFocusedApp), or when dumpsys
    says neither; else False, with the window that has the focus."""
    current = [line.split("mCurrentFocus=", 1)[1].strip() for line in dumpsys.splitlines() if "mCurrentFocus=" in line]
    apps = [line.split("mFocusedApp=", 1)[1].strip() for line in dumpsys.splitlines() if "mFocusedApp=" in line]
    if not current and not apps:
        return None, None
    if any(PACKAGE in window for window in current):
        return True, window_name(next(window for window in current if PACKAGE in window))
    window = next((w for w in current if w != "null"), None)
    if any(PACKAGE in app for app in apps) and (window is None or any(kind in window for kind in PASSING)):
        return None, window_name(window)
    return False, window_name(window or next((app for app in apps if app != "null"), None))


def close_button(hierarchy, name="aerr_close"):
    """The centre (x, y, pixels) of a button of Android's app dialogs in
    `uiautomator dump`, by its id: "Close app" (aerr_close), "Wait"
    (aerr_wait); None when it is not there."""
    for node in NODE.findall(hierarchy):
        if f'resource-id="android:id/{name}"' in node:
            found = BOUNDS.search(node)
            if found:
                left, top, right, bottom = map(int, found.groups())
                return (left + right) // 2, (top + bottom) // 2
    return None


def chooser_window(dumpsys):
    """Google's own window has the focus (`dumpsys window`): its account
    chooser, the one Google window the launch expects."""
    return any("mCurrentFocus" in line and GMS in line for line in dumpsys.splitlines())


def accounts(hierarchy):
    """The centres (x, y, pixels) of the accounts Google's chooser lists in
    `uiautomator dump`: its nodes whose text is an e-mail address, one per
    address."""
    found = {}
    for node in NODE.findall(hierarchy):
        text = TEXT.search(node)
        bounds = BOUNDS.search(node)
        if f'package="{GMS}"' in node and text and bounds and EMAIL.match(text.group(1).strip()):
            left, top, right, bottom = map(int, bounds.groups())
            found.setdefault(text.group(1).strip().lower(), ((left + right) // 2, (top + bottom) // 2))
    return list(found.values())


class State:
    """What a gateway restart must not lose, in the plugin's data directory
    (state.json): one section per feature, each given by the snapshot the
    feature registered, rewritten whole when any of them changed.
    saved: what the file held when the gateway started ({} when there is
    none or it cannot be read)."""

    def __init__(self, data_dir, log=None):
        self.log = log or python_log("slayer-legend")
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
            self.log("warning", f"State not read: {e!r}")
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
            self.log("warning", f"State not kept: {e}")

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


# The lease's longest time to live, and how long a user input pauses every
# holder that did not come from the user's own press (seconds).
LEASE_MAX = 15 * 60
INPUT_PAUSE = 10
# Who holds the lease in the running task (and the tasks it spawns).
HOLDER = contextvars.ContextVar("slayer_legend_lease_holder", default=None)


# The plugin's own holders of the lease: refused while the plugin is off.
PLUGIN_HOLDERS = ("launch", "mine", "watchdog", "mode", "stage_change")
OFF = "plugin désactivé"
HELD = "bail tenu par {holder}"
PLAYING = "l’utilisateur joue"
NO_LEASE = "pas de bail"


class Refused(RuntimeError):
    """A move the navigation guard refused. t: a status text, the guard's
    reason (English) as its data; its str, the English."""

    def __init__(self, refusal):
        self.t = texts.t("action refusée par le garde-fou : {refusal}", refusal=refusal)
        super().__init__(texts.english(self.t))


class Busy(RuntimeError):
    """A tapping sequence that may not run now: another holder has the
    lease, the user plays, or the lease expired. t: why, a status text
    ({template, params}: OFF, HELD, PLAYING, NO_LEASE); its str, the
    English."""

    def __init__(self, why, /, **params):
        self.t = why if texts.is_t(why) else texts.t(why, **params)
        super().__init__(texts.english(self.t))


class Lease:
    """The one shared lease on the game's taps: the launch, the mine, the
    watchdog's repairs and the modes' sequences take it for each tapping
    sequence (ports.leased), an outside holder through POST /lease. It has
    a holder's name, a reason and a time to live (at most LEASE_MAX), is
    renewed explicitly by the same holder (take again) and released by its
    holder only; one that expires is logged as a warning. A user input (a
    touch, a swipe or a key, context.last_input) refuses it for
    INPUT_PAUSE seconds and stops the sequence under way, unless it was
    taken on the user's own press (user=True), but only while the game is
    in front: an input on the launcher or another app, the game not
    running, is not playing (front: the focus last seen, saw_focus). pause=False takes it
    within those 10 s (the user asked for it elsewhere), an input after
    it still stopping the sequence."""

    def __init__(self, clock, last_input, enabled=lambda: True, log=None):
        self.log = log or python_log("slayer-legend")
        self.clock = clock
        self.last_input = last_input
        self.enabled = enabled
        self.held = None
        self.front = None  # the game in front at the last look (None: not looked, cannot tell)

    def saw_focus(self, game):
        """The focus seen (focus_of's game: True, False, None)."""
        self.front = game

    def current(self):
        """{holder, reason, since, until (Unix), user, mark}, or None."""
        held = self.held
        if held and self.clock.wall() >= held["until"]:
            self.log("warning", f"Lease of {held['holder']} expired ({held['reason']})")
            self.held = held = None
        return held

    def input_since(self, mark):
        """The user's last input came after monotonic time mark."""
        last = self.last_input()
        return last is not None and last["monotonic"] > mark

    def recent(self):
        """An input in the last INPUT_PAUSE seconds, wherever it went."""
        return self.input_since(self.clock.monotonic() - INPUT_PAUSE)

    def playing(self):
        """The user plays: a recent input, and the game not seen away at
        the last look (the callers look first: leased, user_input)."""
        return self.recent() and self.front is not False

    def pause_left(self):
        """Seconds before the user-input pause ends (0: none)."""
        last = self.last_input()
        if not last or not self.playing():
            return 0.0
        return max(0.0, last["monotonic"] + INPUT_PAUSE - self.clock.monotonic())

    def take(self, holder, reason, seconds, user=False, pause=True):
        """None once holder has it (taken or renewed until now + seconds),
        or why not (a status text, see Busy)."""
        seconds = min(float(seconds), LEASE_MAX)
        if holder in PLUGIN_HOLDERS and not self.enabled():
            return texts.t(OFF)
        held = self.current()
        if held and held["holder"] != holder:
            return texts.t(HELD, holder=held["holder"])
        if not user and pause and self.playing():
            return texts.t(PLAYING)
        now = self.clock.wall()
        self.held = {"holder": holder, "reason": reason, "since": held["since"] if held else now,
                     "until": now + seconds, "user": user, "mark": self.clock.monotonic()}
        self.log("normal", f"Lease {'renewed' if held else 'taken'} by {holder} for {seconds:.0f} s: {reason}")
        return None

    def release(self, holder):
        """True when holder had it (only its own holder releases it)."""
        held = self.current()
        if not held or held["holder"] != holder:
            return False
        self.held = None
        self.log("normal", f"Lease released by {holder}")
        return True

    def check(self, holder):
        """Before a tap, hold or swipe: Busy unless holder has the lease and
        the user has not played since it was taken (or it was the user's)."""
        held = self.current()
        if not held or held["holder"] != holder or holder is None:
            raise Busy(HELD, holder=held["holder"]) if held else Busy(NO_LEASE)
        if holder in PLUGIN_HOLDERS and not self.enabled():
            raise Busy(OFF)
        if not held["user"] and self.input_since(held["mark"]):
            raise Busy(PLAYING)

    def state(self):
        held = self.current()
        return {key: held[key] for key in ("holder", "reason", "since", "until")} if held else None


def build(context, nav):
    # An addition to the plugin API: an older gateway has no context.log.
    log = getattr(context, "log", None) or python_log(context.id)

    async def adb(*args, timeout=10):
        return await context.adb(*args, timeout=timeout)

    def allowed(screen, move, point, kind="tap", verified=False, seen=None):
        """Every action goes through the navigation graph's guard first:
        refused unless it is an allowed move of the screen recognised (seen:
        what the fresh capture showed, for the moves that need it)."""
        refusal = nav.guard(screen, move, point[0], point[1], kind, verified, seen)
        if refusal:
            log("error", f"Action refused: {refusal}")
            raise Refused(refusal)

    clock = SimpleNamespace(wall=time.time, monotonic=time.monotonic, sleep=asyncio.sleep)
    # The game's process last seen (its pid), and who hears of a relaunch
    # and of each capture (features/game.py).
    process = {"pid": None}
    relaunch_listeners, capture_listeners = [], []
    # Older gateways do not say when the user plays.
    last_input = getattr(context, "last_input", None) or (lambda: None)
    power = {"on": True}
    lease = Lease(clock, last_input, lambda: power["on"], log)
    viewers = getattr(context, "viewers", None) or (lambda: None)

    @contextlib.asynccontextmanager
    async def leased(holder, reason, seconds, user=False, pause=True):
        """The tapping sequence in the with block holds the lease (Busy
        when it cannot); released at its end."""
        if not user and pause and lease.recent():
            await focus()  # is the game in front now? (lease.front)
        why = lease.take(holder, reason, seconds, user, pause)
        if why:
            raise Busy(why)
        token = HOLDER.set(holder)
        try:
            yield
        finally:
            HOLDER.reset(token)
            lease.release(holder)

    async def tap(shot, screen, move, point, verified=False, seen=None):
        lease.check(HOLDER.get())
        allowed(screen, move, point, verified=verified, seen=seen)
        width, height, _ = shot
        await adb("shell", "input", "tap", str(round(point[0] * width)), str(round(point[1] * height)))

    async def taps(shot, screen, moves, gap, verified=()):
        """moves: [(move, point)], tapped gap seconds apart in one adb call;
        verified: the moves whose precondition the caller checked."""
        lease.check(HOLDER.get())
        for move, point in moves:
            allowed(screen, move, point, verified=move in verified)
        width, height, _ = shot
        script = f"; sleep {gap}; ".join(f"input tap {round(point[0] * width)} {round(point[1] * height)}"
                                         for _, point in moves)
        await adb("shell", script, timeout=gap * len(moves) + 10)

    async def hold(shot, screen, move, point, milliseconds):
        lease.check(HOLDER.get())
        allowed(screen, move, point, "hold")
        width, height, _ = shot
        x, y = str(round(point[0] * width)), str(round(point[1] * height))
        await adb("shell", "input", "swipe", x, y, x, y, str(milliseconds), timeout=milliseconds / 1000 + 10)

    async def swipe(shot, screen, move, start, end, milliseconds, verified=False, seen=None):
        lease.check(HOLDER.get())
        allowed(screen, move, start, "swipe", verified, seen)
        width, height, _ = shot
        await adb("shell", "input", "swipe", str(round(start[0] * width)), str(round(start[1] * height)),
                  str(round(end[0] * width)), str(round(end[1] * height)), str(milliseconds))

    async def focused():
        code, out = await adb("shell", "dumpsys", "window")
        lease.saw_focus(focus_of(out)[0] if code == 0 else None)
        return code == 0 and any("mCurrentFocus" in line and PACKAGE in line for line in out.splitlines())

    async def focus():
        code, out = await adb("shell", "dumpsys", "window")
        game, window = focus_of(out) if code == 0 else (None, None)
        lease.saw_focus(game)
        return {"game": game, "window": window}

    async def user_input():
        """last_input() when it counts as playing (the game in front, looked
        at now when the input is recent), else None."""
        if not lease.recent():
            return last_input()
        await focus()
        return last_input() if lease.playing() else None

    async def running():
        """False when the game's process is gone, None when adb cannot tell.
        A process gone, or another one than last time (the game relaunched,
        Android restarted), is told to the relaunch listeners."""
        code, out = await adb("shell", "pidof", PACKAGE)
        if code == 0 and out.strip():
            pid = out.split()[0]
            if process["pid"] is not None and pid != process["pid"]:
                relaunched("relaunched (another process)")
            process["pid"] = pid
            return True
        if code == 1 and not out.strip():
            if process["pid"] is not None:
                relaunched("stopped (process gone)")
            process["pid"] = None
            return False
        return None

    def relaunched(why):
        for listener in list(relaunch_listeners):
            try:
                listener(why)
            except Exception:
                exception_log(log)(f"Relaunch listener failed ({why})")

    async def capture(max_age=0):
        """The shared capture, each one handed to the capture listeners
        (the game's scan) as it comes."""
        shot = await context.screenshot(max_age=max_age)
        if shot:
            for listener in list(capture_listeners):
                try:
                    listener(shot)
                except Exception:
                    exception_log(log)("Capture listener failed")
        return shot

    async def start_game():
        """True when Android started (or brought to the front) the game's
        activity, as the launcher does; never -S: a running game is not
        killed."""
        code, _ = await adb("shell", "am", "start", "-n", ACTIVITY, "-a", "android.intent.action.MAIN",
                            "-c", "android.intent.category.LAUNCHER", timeout=20)
        return code == 0

    async def dialog():
        code, out = await adb("shell", "dumpsys", "window")
        return crash_window(out) if code == 0 else None

    async def crashed():
        return await dialog() == "crash"

    async def press_dialog(shot, screen, move, name):
        """Taps button name of an Android dialog where uiautomator says it
        is; False when it is not there."""
        lease.check(HOLDER.get())
        code, out = await adb("shell", "uiautomator", "dump", "/dev/tty", timeout=20)
        point = close_button(out, name) if code == 0 else None
        if not point:
            return False
        width, height, _ = shot
        refusal = nav.guard(screen, move, point[0] / width, point[1] / height, verified=True)
        if refusal:
            log("error", f"Action refused: {refusal}")
            raise Refused(refusal)
        await adb("shell", "input", "tap", str(point[0]), str(point[1]))
        return True

    async def close_crash(shot):
        return await press_dialog(shot, "crash_dialog", "close", "aerr_close")

    async def wait_anr(shot):
        return await press_dialog(shot, "anr_dialog", "wait", "aerr_wait")

    async def account_chooser():
        code, out = await adb("shell", "dumpsys", "window")
        if code != 0 or not chooser_window(out):
            return None
        code, out = await adb("shell", "uiautomator", "dump", "/dev/tty", timeout=20)
        found = accounts(out) if code == 0 else []
        return {"count": len(found), "point": found[0] if len(found) == 1 else None}

    async def choose_account(shot, point):
        lease.check(HOLDER.get())
        width, height, _ = shot
        allowed("account_chooser", "account", (point[0] / width, point[1] / height), verified=True)
        await adb("shell", "input", "tap", str(point[0]), str(point[1]))

    # Additions to the plugin API: an older gateway has no alert buttons.
    issue = getattr(context, "action_token", None)
    withdraw = getattr(context, "revoke_action", None)

    def action_token(path, seconds):
        return issue(path, seconds) if issue else None

    def revoke_action(token):
        if withdraw and token:
            withdraw(token)

    async def notify(text, actions=None):
        if actions and issue:
            return await context.notify(text, actions=actions)
        return await context.notify(text)

    def spawn(coroutine):
        return asyncio.get_running_loop().create_task(coroutine)

    # Older gateways give plugins no data directory: then nothing is kept.
    data_dir = getattr(context, "data_dir", None)

    def data_path(name):
        return os.path.join(data_dir, name) if data_dir else None

    store = State(data_dir, log)
    power["on"] = store.saved.get("enabled") is not False
    store.register("enabled", lambda: power["on"])

    def enabled():
        return power["on"]

    def set_enabled(on):
        if bool(on) == power["on"]:
            return
        power["on"] = bool(on)
        store.save()
        log("normal", f"Plugin turned {'on' if on else 'off'}")

    return SimpleNamespace(
        capture=capture, analyse=context.analyse, on_capture=capture_listeners.append,
        on_relaunch=relaunch_listeners.append, relaunched=relaunched,
        tap=tap, taps=taps, hold=hold, swipe=swipe, lease=lease, leased=leased, Busy=Busy, Refused=Refused,
        last_input=last_input, user_input=user_input, **text_ports(),
        pause_left=lease.pause_left,
        viewers=viewers,
        focused=focused, focus=focus, running=running, start_game=start_game, dialog=dialog, crashed=crashed, close_crash=close_crash, wait_anr=wait_anr,
        account_chooser=account_chooser, choose_account=choose_account,
        notify=notify, action_token=action_token, revoke_action=revoke_action, enabled=enabled, set_enabled=set_enabled,
        clock=clock,
        spawn=spawn, store=store, data_path=data_path, respond=context.json,
        log=log, exception=exception_log(log),
    )
