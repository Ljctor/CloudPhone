"""When the Closed Mine farming relaunches, waits or stops. Pure: what the
last look saw (see mine_facts), what the loop remembers and the time go
in; the move to make comes out. The feature (mine.py beside this file)
makes the moves, every one through the navigation guard.

The loop remembers {scroll, gold_seen, last_hold, failures,
untick_failures}: the gold scroll's warning record (gold_scroll.py beside
the plugin's gateway.py, shared with mpw4 farming), when it was last seen and when Power Saving Mode was last left (monotonic
seconds, 0: never), the relaunches that failed in a row, and the tries in
a row to untick "Repeat entry" that did not take.
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "cloudphone_plugin_slayer_legend_mine_rules_gold_scroll",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gold_scroll.py"))
scroll = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(scroll)

# Seconds between two looks of the farming loop.
SECONDS = 10
# Feathers per entry: always 3, the reward is multiplied by the feathers used.
FEATHERS = 3
# Checks in a row without the gold scroll before stopping (an animation can
# hide it for a moment).
NO_GOLD = 2
# Power Saving Mode hides the buffs: it is left at most this often (seconds).
SAVER_EVERY = 60
# On the floor list, no relaunch without the gold scroll seen this recently.
GOLD_STALE = 5 * 60
# Relaunches failed in a row before giving up.
MAX_FAILURES = 3
# Tries in a row to untick "Repeat entry" that did not take before giving
# up (blocked, one alert): the same number.
MAX_UNTICK_FAILURES = MAX_FAILURES
# The moves that untick "Repeat entry".
UNTICKS = ("stop_timer", "stop_no_gold")
# The floor list: tries to find the floor, and the swipe (start and end
# heights, fractions of the screen) that scrolls by about three rows
# towards higher floors (up) or lower ones.
SCROLL_TRIES = 12
SCROLL_UP = (0.40, 0.65)
SCROLL_DOWN = (0.65, 0.40)
SCROLL_MS = 600
# The shared lease's time to live for one of the mine's tapping sequences
# (the longest, a relaunch scrolling the whole list, takes under a minute).
LEASE_SECONDS = 120
# A mine whose timer ended while the gateway was down, in a fight: how long
# its stop pass looks for the fight to untick "Repeat entry", then how long
# and how often it still watches for it, without touching anything else.
STOP_SECONDS = 180
WATCH_SECONDS = 15 * 60
WATCH_EVERY = 30


def fresh():
    return {"scroll": scroll.fresh(), "gold_seen": 0.0, "last_hold": 0.0, "failures": 0, "untick_failures": 0}


def request(body):
    """POST /mine's {enabled, floor, area, until}: ((enabled, floor, area,
    until), None) or (None, the error)."""
    try:
        enabled = bool(body.get("enabled"))
        floor, area = int(body.get("floor") or 0), int(body.get("area") or 0)
        until = float(body["until"]) if body.get("until") is not None else None
    except (ValueError, TypeError, AttributeError):
        return None, "Expected {enabled, floor, area, until}"
    if enabled and not valid(floor, area):
        return None, "floor 1-9999, area 1-5"
    return (enabled, floor, area, until), None


def valid(floor, area):
    return bool(floor and 1 <= floor <= 9999 and area and 1 <= area <= 5)


def step(facts, memory, now, wall, until):
    """The farming loop's (move, memory, gold, gone) for what a look saw:
    see _move(); gold: the gold scroll as last told (None, True, False).
    Any move but an untick ends a run of failed unticks."""
    move, memory, gone = _move(facts, memory, now, wall, until)
    gold = memory["scroll"]["gold"]
    if move not in UNTICKS:
        memory["untick_failures"] = 0
    return move, memory, gold, gone


def untick_failed(memory):
    """(memory, give up) after a try to untick "Repeat entry" that did not
    take: give up at the MAX_UNTICK_FAILURES-th in a row."""
    memory = {**memory, "untick_failures": memory["untick_failures"] + 1}
    return memory, memory["untick_failures"] >= MAX_UNTICK_FAILURES


def _move(facts, memory, now, wall, until):
    """The farming loop's move for what a look saw: (move, memory, gone).
    now: monotonic seconds; wall: Unix seconds; until: the mine's end or
    None. gone: the gold scroll was just found missing (alert once).

    Moves: leave_saver, wait, stop_timer (untick, the time is up),
    gold (fight with the gold scroll), warn_no_gold (with a timer the user
    chose how long: only warn), stop_no_gold (untick), other (a pop-up or
    a screen this does not know, maybe the user's own taps), finish_timer,
    finish_no_gold, wait_no_gold, finish_failures (no relaunch), relaunch.
    """
    memory = dict(memory)
    if facts["saver"]:
        # The buffs are hidden: leave Power Saving Mode to see them.
        return ("leave_saver" if now - memory["last_hold"] > SAVER_EVERY else "wait"), memory, False
    timed = until is not None
    over = timed and wall >= until
    if over and facts["fight"]:
        return "stop_timer", memory, False
    if facts["fight"]:
        memory["failures"] = 0
        memory["scroll"], news = scroll.look(memory["scroll"], facts["gold"], NO_GOLD)
        if facts["gold"]:
            memory["gold_seen"] = now
            return "gold", memory, False
        if memory["scroll"]["gold"] is not False:
            return "wait", memory, False
        return ("warn_no_gold" if timed else "stop_no_gold"), memory, news == "gone"
    if facts["other"]:
        return "other", memory, False
    # The floor list: the 30 entries are done.
    if over:
        return "finish_timer", memory, False
    if not timed and now - memory["gold_seen"] > GOLD_STALE:
        return ("finish_no_gold" if memory["gold_seen"] else "wait_no_gold"), memory, False
    if memory["failures"] >= MAX_FAILURES:
        return "finish_failures", memory, False
    return "relaunch", memory, False


def relaunched(memory, ok):
    return {**memory, "failures": 0 if ok else memory["failures"] + 1}


def floor_row(rows, floor):
    """The height of floor's row in the list's rows [(height, floor)], or None."""
    return next((y for y, n in rows if n == floor), None)


def scroll_towards(rows, floor):
    """The swipe (start, end heights) that brings floor nearer."""
    return SCROLL_UP if rows[0][1] > floor else SCROLL_DOWN


def stop_pass_ended(gone, in_front):
    """The stop pass ends at once when the game cannot be in a fight: its
    process gone, or another app in front. Why, or None."""
    if gone:
        return "not running"
    if not in_front:
        return "not in front"
    return None


def stop_look(screen, facts, last_hold, now):
    """The stop pass's move: restarted (the title or save screen: Android
    or the game restarted, nothing to untick), leave_saver, untick (the mine
    fight) or wait."""
    if screen in ("title", "save"):
        return "restarted"
    if facts["saver"] and now - last_hold > SAVER_EVERY:
        return "leave_saver"
    if facts.get("fight"):
        return "untick"
    return "wait"


def in_fight(facts):
    """The passive watch after a stop pass gave up only unticks on the mine
    fight, seen on its look and again on a screenshot taken at once."""
    return bool(facts.get("fight"))


def restored(mined, now):
    """The mine from state.json's "mine" section (floor, area and until
    already checked, see values.py): (values, timer ended). A timer that
    ended while the gateway was down: the mine is over, not resumed; in a
    fight "Repeat entry" goes on spending feathers, so a stop pass unticks
    it first (state "stopping"), also when the gateway restarted during a
    stop pass. values: {enabled, floor, area, until, state} (state None:
    unchanged)."""
    from_saved = mined.get("state")
    floor, area = mined.get("floor"), mined.get("area")
    values = {"enabled": mined.get("enabled") is True and bool(floor and area), "floor": floor, "area": area,
              "until": mined.get("until"), "state": None}
    if values["enabled"] and values["until"] is not None and values["until"] <= now:
        values["enabled"] = False
        values["state"] = "stopping" if from_saved == "farming" else "off"
        return values, True
    if from_saved == "stopping":
        values["state"] = "stopping"
    return values, False
