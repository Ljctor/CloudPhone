"""The timers of the mode and of the mine. Pure."""

# A timer ending this close to now (seconds) is no timer.
MINIMUM = 30


def moved(until, minutes, now):
    """The end `until` (Unix seconds, None: no time limit) moved by minutes
    (may be negative), counted from now when it is unset or past; None when
    that ends at or before now + MINIMUM."""
    moved_to = max(until or now, now) + minutes * 60
    return moved_to if moved_to > now + MINIMUM else None


def ended(until, now):
    """A timer that is set and over."""
    return until is not None and until <= now
