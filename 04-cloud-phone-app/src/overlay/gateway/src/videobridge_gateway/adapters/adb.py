"""adb, the Android Debug Bridge to the emulator. Every adb command the
gateway runs (hardware keys, Android's metrics and events, the plugins'
commands) goes through run(), which also tells logs whether adb still
reaches Android, from the error text of the calls made anyway (no extra
adb call)."""

import asyncio

from .. import logs

# Set from the command line (--adb, --adb_serial) by configure().
PATH = "/opt/android-sdk/platform-tools/adb"
SERIAL = "emulator-5558"
# What adb writes when it does not reach the emulator.
OFFLINE_MARKERS = ("not found", "offline", "no devices", "unauthorized", "cannot connect", "closed")


def configure(path, serial):
    global PATH, SERIAL
    PATH, SERIAL = path, serial


def reached(code, error_text):
    """True when the call reached Android, False when adb says it cannot,
    None when its error says neither."""
    if code == 0:
        return True
    text = (error_text or "").lower()
    return False if any(marker in text for marker in OFFLINE_MARKERS) else None


async def run(*args, timeout=10):
    """(exit code, stdout, stderr) of "adb -s SERIAL ARGS...". The code is
    None when adb could not start (stderr then says why), -1 when it did
    not finish within timeout seconds (it is then killed; None: no limit)."""
    try:
        process = await asyncio.create_subprocess_exec(
            PATH, "-s", SERIAL, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as e:
        return None, "", str(e)
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return -1, "", f"adb did not answer within {timeout} s"
    errors = err.decode("utf-8", "replace")
    logs.adb_reached(reached(process.returncode, errors), errors)
    return process.returncode, out.decode("utf-8", "replace"), errors
