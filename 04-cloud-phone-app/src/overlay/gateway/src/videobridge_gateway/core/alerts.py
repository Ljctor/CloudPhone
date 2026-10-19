"""Alerts on the user's phone through ntfy.sh, even with the page closed.

The Cloud Phone has one topic, a long random name made by the gateway and
kept in a small JSON file ({enabled, topic}) beside the other request
files; the user subscribes the ntfy app to https://ntfy.sh/<topic>. Anyone
who knows the name can read the alerts, so it is shown only on the page and
messages say nothing private. They go through the public ntfy.sh service.

The gateway sends alerts for Android's events (an app crashed or froze,
Android or the emulator restarted) and plugins send their own through
PluginContext.notify().

No I/O: the saved file's text, the state ({enabled, topic}) and the events
come in; what to save, show and send comes out.
"""

import json
import re
import secrets

SERVER = "https://ntfy.sh"
TOPIC = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def parse_saved(text):
    """{enabled, topic} from the saved file's text; a missing (None) or
    broken file means off."""
    try:
        saved = json.loads(text) if text is not None else None
    except ValueError:
        saved = None
    if saved is None:
        return {"enabled": False, "topic": None}
    topic = saved.get("topic")
    topic = topic if isinstance(topic, str) and TOPIC.match(topic) else None
    return {"enabled": bool(saved.get("enabled")) and topic is not None, "topic": topic}


def saved_text(state):
    return json.dumps({"enabled": state["enabled"], "topic": state["topic"]})


def describe(state, available):
    topic = state["topic"]
    return {
        "available": available,
        "enabled": state["enabled"],
        "topic": topic,
        "url": f"{SERVER}/{topic}" if topic else None,
    }


def configure(state, enabled, new_topic=False):
    """The state with alerts on or off; a topic is made the first time, or a
    new one when asked (the old name stops getting alerts)."""
    topic = state["topic"]
    if enabled and (topic is None or new_topic):
        topic = f"cloudphone-{secrets.token_hex(12)}"
    return {"enabled": bool(enabled), "topic": topic}


def url(state, force=False):
    """Where to post an alert, or None when alerts are off (force: even
    then, as long as there is a topic)."""
    topic = state["topic"]
    if not topic or not (state["enabled"] or force):
        return None
    return f"{SERVER}/{topic}"


def headers(title, tags=None):
    """ntfy's headers; HTTP headers are Latin-1."""
    result = {"Title": title.encode("utf-8").decode("latin-1", "replace")}
    if tags:
        result["Tags"] = tags
    return result


# Android's events worth an alert, and their sentence.
SENTENCES = {
    "crash": "{app} a planté",
    "anr": "{app} ne répond plus",
    "killed": "Android a arrêté {app}",
    "emulator_start": "L’émulateur a redémarré",
    "android_boot": "Android a redémarré",
}


def new_events(events, seen, kinds=SENTENCES):
    """The events of `events` (from read_events) of these kinds not taken
    yet, oldest first; updates `seen` ({time, boot}). The first call only
    takes note."""
    first = seen.get("time") is None
    latest = seen.get("time") or 0.0
    fresh = []
    for event in sorted(events, key=lambda e: e["time"]):
        kind = event.get("kind")
        if kind not in kinds:
            continue
        if kind == "android_boot":
            # Worked out from Android's uptime on each read: it moves by a
            # fraction of a second; a reboot moves it by much more.
            boot = seen.get("boot")
            seen["boot"] = event["time"]
            if boot is not None and event["time"] - boot > 60 and not first:
                fresh.append(event)
            continue
        if event["time"] > latest:
            latest = event["time"]
            if not first:
                fresh.append(event)
    seen["time"] = latest
    return fresh


def sentence(event):
    return SENTENCES[event["kind"]].format(app=event.get("app") or "Une appli") + (
        f" ({event['reason']})" if event.get("reason") and event["kind"] in ("crash", "anr") else "")
