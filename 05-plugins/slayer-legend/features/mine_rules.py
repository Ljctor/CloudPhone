"""When the Closed Mine farming relaunches, waits or stops. Pure: what the
last look saw (see mine_facts), what the loop remembers and the time go
in; the move to make comes out. The feature (mine.py beside this file)
makes the moves, every one through the navigation guard.

The loop remembers {no_gold, gold_seen, last_hold, failures}: the checks
in a row without the gold scroll, when it was last seen and when Power
Saving Mode was last left (monotonic seconds, 0: never), and the
relaunches that failed in a row.
"""

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
# The game not in front this long (seconds): one alert.
AWAY_ALERT = 120
# The floor list: tries to find the floor, and the swipe (start and end
# heights, fractions of the screen) that scrolls by about three rows
# towards higher floors (up) or lower ones.
SCROLL_TRIES = 12
SCROLL_UP = (0.40, 0.65)
SCROLL_DOWN = (0.65, 0.40)
SCROLL_MS = 600
# A mine whose timer ended while the gateway was down, in a fight: how long
# its stop pass looks for the fight to untick "Repeat entry", then how long
# and how often it still watches for it, without touching anything else.
STOP_SECONDS = 180
WATCH_SECONDS = 15 * 60
WATCH_EVERY = 30


def fresh():
    return {"no_gold": 0, "gold_seen": 0.0, "last_hold": 0.0, "failures": 0}


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


def away(since, now):
    """The game is not in front: (since, alert). since is when it left
    (-1 once the alert was sent: one alert per absence)."""
    since = since or now
    if now - since > AWAY_ALERT and since > 0:
        return -1.0, True
    return since, False


def step(facts, memory, now, wall, until, gold):
    """The farming loop's move for what a look saw: (move, memory, gold,
    gone). now: monotonic seconds; wall: Unix seconds; until: the mine's
    end or None; gold: the gold scroll as last told (None, True, False).
    gone: the gold scroll was just found missing (alert once).

    Moves: leave_saver, wait, stop_timer (untick, the time is up),
    gold (fight with the gold scroll), warn_no_gold (with a timer the user
    chose how long: only warn), stop_no_gold (untick), other (a pop-up or
    a screen this does not know, maybe the user's own taps), finish_timer,
    finish_no_gold, wait_no_gold, finish_failures (no relaunch), relaunch.
    """
    memory = dict(memory)
    if facts["saver"]:
        # The buffs are hidden: leave Power Saving Mode to see them.
        return ("leave_saver" if now - memory["last_hold"] > SAVER_EVERY else "wait"), memory, gold, False
    timed = until is not None
    over = timed and wall >= until
    if over and facts["fight"]:
        return "stop_timer", memory, gold, False
    if facts["fight"]:
        memory["failures"] = 0
        if facts["gold"]:
            memory["no_gold"], memory["gold_seen"] = 0, now
            return "gold", memory, True, False
        memory["no_gold"] += 1
        if memory["no_gold"] < NO_GOLD:
            return "wait", memory, gold, False
        return ("warn_no_gold" if timed else "stop_no_gold"), memory, False, gold is not False
    if facts["other"]:
        return "other", memory, gold, False
    # The floor list: the 30 entries are done.
    if over:
        return "finish_timer", memory, gold, False
    if not timed and now - memory["gold_seen"] > GOLD_STALE:
        return ("finish_no_gold" if memory["gold_seen"] else "wait_no_gold"), memory, gold, False
    if memory["failures"] >= MAX_FAILURES:
        return "finish_failures", memory, gold, False
    return "relaunch", memory, gold, False


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
