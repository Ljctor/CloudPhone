"""Screen size and density changes: what may be asked, the state of the
last request, and one change every CHANGE_INTERVAL seconds.

A change of either kind (screen size, emulator settings) restarts Android,
so both share the limit, and neither starts while one is pending or being
applied. No I/O: the status file's text, the request's values and the
times come in, decisions come out.
"""

from .texts import t

LIMITS = {"width": (240, 1440), "height": (320, 3200), "density": (80, 640)}
CHANGE_INTERVAL = 120.0
BUSY = ("pending", "applying")


def json_int(value):
    """A JSON integer, never a string, float or boolean ("360" is refused)."""
    if type(value) is not int:
        raise TypeError("not an integer")
    return value


def size_error(wanted):
    """The error for a {width, height, density} out of LIMITS or with an odd
    side (a status text, core/texts.py), else None."""
    for key, (low, high) in LIMITS.items():
        if not low <= wanted[key] <= high:
            return t("{key} doit être entre {low} et {high}", key=key, low=low, high=high)
    if wanted["width"] % 2 or wanted["height"] % 2:
        return t("width et height doivent être pairs")
    return None


def parse_status(pending, text):
    """The state of the last screen size request: pending while its request
    file is there, else what the status file says (text None: unreadable)."""
    if pending:
        return {"state": "pending"}
    words = (text or "").split()
    if not words:
        return {"state": "idle"}
    state = words[0] if words[0] in ("applying", "done", "failed") else "idle"
    result = {"state": state}
    if state in ("applying", "done") and len(words) == 4:
        try:
            result["width"], result["height"], result["density"] = map(int, words[1:])
        except ValueError:
            pass
    if state == "failed":
        result["message"] = " ".join(words[1:])
    return result


def busy(*statuses):
    """True while a change of any kind is pending or being applied."""
    return any(status["state"] in BUSY for status in statuses)


def last_change(remembered, times):
    """When the last change was asked for or done (Unix time): what this
    process remembers (None: nothing) or the request and status files' times."""
    return max(remembered or 0.0, *times)


def wait_seconds(now, last):
    """None when a change may start at now, else the seconds to wait."""
    since = now - last
    if since < CHANGE_INTERVAL:
        return int(CHANGE_INTERVAL - since) + 1
    return None
