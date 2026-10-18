"""Alerts on the user's phone through ntfy.sh, even with the page closed.

The Cloud Phone has one topic, a long random name made by the gateway and
kept in a small JSON file ({enabled, topic}) beside the other request
files; the user subscribes the ntfy app to https://ntfy.sh/<topic>. Anyone
who knows the name can read the alerts, so it is shown only on the page and
messages say nothing private. They go through the public ntfy.sh service.

The gateway sends alerts for Android's events (an app crashed or froze,
Android or the emulator restarted) and plugins send their own through
PluginContext.notify().
"""

import asyncio
import json
import logging
import os
import re
import secrets

import aiohttp

SERVER = "https://ntfy.sh"
TOPIC = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
STATE = {"file": "", "enabled": False, "topic": None}


def load(path):
    """Reads the saved state; a missing or broken file means off."""
    STATE["file"] = path or ""
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    topic = saved.get("topic")
    STATE["topic"] = topic if isinstance(topic, str) and TOPIC.match(topic) else None
    STATE["enabled"] = bool(saved.get("enabled")) and STATE["topic"] is not None


def _save():
    if not STATE["file"]:
        return
    temporary = f"{STATE['file']}.tmp"
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump({"enabled": STATE["enabled"], "topic": STATE["topic"]}, f)
    os.chmod(temporary, 0o600)
    os.replace(temporary, STATE["file"])


def describe():
    topic = STATE["topic"]
    return {
        "available": bool(STATE["file"]),
        "enabled": STATE["enabled"],
        "topic": topic,
        "url": f"{SERVER}/{topic}" if topic else None,
    }


def configure(enabled, new_topic=False):
    """Turns alerts on or off; makes a topic the first time, or a new one
    when asked (the old name stops getting alerts)."""
    if enabled and (STATE["topic"] is None or new_topic):
        STATE["topic"] = f"cloudphone-{secrets.token_hex(12)}"
    STATE["enabled"] = bool(enabled)
    _save()
    return describe()


async def send(text, title="Cloud Phone", tags=None, force=False):
    """Posts one alert; True when ntfy.sh took it. Never raises."""
    topic = STATE["topic"]
    if not topic or not (STATE["enabled"] or force):
        return False
    headers = {"Title": title.encode("utf-8").decode("latin-1", "replace")}
    if tags:
        headers["Tags"] = tags
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(f"{SERVER}/{topic}", data=text.encode("utf-8"), headers=headers) as response:
                if response.status >= 300:
                    logging.warning(f"Alert not taken: ntfy.sh answered {response.status}")
                    return False
                return True
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logging.warning(f"Alert not sent: {e!r}")
        return False


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
