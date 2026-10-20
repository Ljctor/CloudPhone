"""What the launch does at each look at the screen. Pure: the screen
recognised, what the launch remembers and the time go in; the move to make
and what to remember next come out.

The launch only ever taps "TAP TO START" (start), Confirm on the "last
save time" notice (confirm), "Close app" on Android's crash dialog
(close_crash, at most CRASH_TRIES times) and holds "Press here to finish
Power Saving Mode" (leave_saver, at most SAVER_TRIES times), each only when
the screen shows it. Any other screen that stays is for the user
(blocked_other).
"""

# The whole launch gives up after this long (seconds).
DEADLINE = 180
# Seconds between two looks at the screen.
LOOK_EVERY = 3
# After Confirm, the save loads for a while before the next look.
AFTER_CONFIRM = 3
# Seconds since the last press before pressing again: the saver's button,
# the title.
SAVER_GAP = 5
TITLE_GAP = 8
SAVER_TRIES = 3
# Android's crash dialog: closed this many times at most, then the game is
# opened again after this long (seconds).
CRASH_TRIES = 2
AFTER_CRASH = 2
# Loading and logging-in screens are "other" for a while; one that stays
# longer than this (seconds; longer once the save was confirmed) stops it.
OTHER_LIMIT = 45
OTHER_LIMIT_CONFIRMED = 60


def fresh():
    """What the launch remembers when it starts."""
    return {"confirmed": False, "last_tap": 0.0, "seen_other": None, "saver_taps": 0, "crashes": 0}


def step(screen, memory, now):
    """(move, memory) for screen at monotonic time now (crash: Android's
    crash dialog). Moves: close_crash, confirm, leave_saver, start, wait,
    blocked_crash, blocked_saver, blocked_other. The battle
    screen (done) is the caller's, which also checks the game is in front;
    the caller sets last_tap once a press is done."""
    if screen == "crash":
        if memory["crashes"] >= CRASH_TRIES:
            return "blocked_crash", memory
        return "close_crash", {**memory, "crashes": memory["crashes"] + 1, "seen_other": None}
    if screen == "save":
        # The notice shows the latest save's time; Confirm keeps it.
        return "confirm", {**memory, "confirmed": True, "seen_other": None}
    if screen == "saver" and now - memory["last_tap"] > SAVER_GAP:
        # Power Saving Mode: the game is already in battle; a long press
        # closes it. Give up after SAVER_TRIES.
        if memory["saver_taps"] >= SAVER_TRIES:
            return "blocked_saver", memory
        return "leave_saver", {**memory, "saver_taps": memory["saver_taps"] + 1, "seen_other": None}
    if screen == "title" and now - memory["last_tap"] > TITLE_GAP:
        return "start", {**memory, "seen_other": None}
    # An unknown screen that stays (Google sign-in, an update, an event
    # pop-up) is for the user.
    seen = memory["seen_other"] or now
    memory = {**memory, "seen_other": seen}
    if now - seen > (OTHER_LIMIT_CONFIRMED if memory["confirmed"] else OTHER_LIMIT):
        return "blocked_other", memory
    return "wait", memory
