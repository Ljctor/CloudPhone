"""Android's and the server's events over HTTP, and as records:

    GET /api/v1/events   what happened, newest first (cached CACHE_SECONDS)

watch() turns Android's new events into log records every minute, and
into phone alerts when they are on; log_start() says the gateway started.
See core/events.py for the parsing and the records; Android's side is read
with the adb callable the gateway gives, the emulator unit's with
adapters/systemd.py.
"""

import asyncio
import logging
import time

from aiohttp import web

from ..adapters import systemd
from ..adapters.host_files import read_file
from ..core import alerts, events
from .. import logs
from ..logs import log
from . import notify

# The emulator's systemd unit, set by gateway_server's main; empty: unknown.
UNIT = ""
STARTED = time.time()
CACHE = {"time": 0.0, "value": None, "lock": None}
CACHE_SECONDS = 10.0


async def read_unit_start():
    """The emulator unit's last start as an emulator_start event, or None."""
    if not UNIT:
        return None
    boot_time = events.host_boot_time(read_file("/proc/stat") or "")
    text = await systemd.show(UNIT, ("ExecMainStartTimestampMonotonic", "NRestarts", "Result"))
    if text is None:
        return None
    return events.parse_unit(text, boot_time, "emulator_start")


async def read_events(adb):
    """{events, android}: the events newest first; android is False when
    adb did not answer."""
    found = [events.gateway_start(STARTED)]
    unit = await read_unit_start()
    if unit:
        found.append(unit)
    code, uptime = await adb("shell", "cat", "/proc/uptime", timeout=5)
    if code == 0:
        boot = events.android_boot(time.time(), uptime)
        if boot:
            found.append(boot)
    code, logcat = await adb("logcat", "-d", "-v", "epoch", "-b", "events,crash", timeout=10)
    if code == 0:
        found.extend(events.parse_logcat(logcat))
    return events.newest_first(found, code == 0)


def get_events(adb):
    """The handler of GET /api/v1/events: what happened to Android and the
    server, newest first."""
    async def handle(request):
        if CACHE["lock"] is None:
            CACHE["lock"] = asyncio.Lock()
        loop = asyncio.get_running_loop()
        async with CACHE["lock"]:
            if CACHE["value"] is None or loop.time() - CACHE["time"] > CACHE_SECONDS:
                CACHE["value"] = await read_events(adb)
                CACHE["time"] = loop.time()
        return web.json_response(CACHE["value"], headers={"Cache-Control": "no-store"})
    return handle


def record(event, expected):
    """event's record; expected() is asked for a boot only."""
    return events.event_record(event, event["kind"] == "android_boot" and expected())


async def watch(adb, expected):
    """Every minute, Android's new events (an app crashed, froze or was
    stopped while in sight; Android restarted) become log records, and
    phone alerts when they are on. expected() tells whether Android may
    restart because the page asked for it."""
    seen, alerted = {}, {}
    while True:
        await asyncio.sleep(60)
        try:
            found = await read_events(adb)
        except Exception as e:
            logging.warning(f"Android events not read: {e!r}")
            continue
        if not found["android"]:
            continue
        first = seen.get("time") is None
        fresh = alerts.new_events(found["events"], seen, kinds=events.RECORDS)
        if first:
            # Before this gateway started: shown on the page, not journaled again.
            for event in reversed(found["events"]):
                if event["kind"] in events.RECORDS and event["kind"] != "android_boot" and event["time"] < STARTED:
                    level, text, params = record(event, expected)
                    logs.remember(level, "emulator", text, event["time"], **params)
        for event in fresh[:10]:
            level, text, params = record(event, expected)
            log(level, "emulator", text, notify=event["kind"] == "android_boot", **params)
        if not notify.STATE["enabled"]:
            alerted.clear()
            continue
        for event in alerts.new_events(found["events"], alerted)[:5]:
            await notify.send(alerts.sentence(event))


async def log_start(expected, version="unknown", commit="unknown"):
    """The gateway's start with its release, and an emulator restart just
    before it: the gateway restarts to follow the emulator, so the previous
    gateway's records of a crash are only in the journal and the log files."""
    log("normal", "gateway", "Gateway started · version {version} · commit {commit}", notify=True,
        version=version, commit=commit)
    unit = await read_unit_start()
    if unit and time.time() - unit["time"] < 180 and unit.get("reason") and not expected():
        log("error", "emulator", "Android restarted after an abnormal stop ({result}, {restarts} automatic "
            "restarts). If it is not back within two minutes, restart it on the server.",
            notify=True, result=unit["reason"], restarts=unit.get("restarts") or 0)
