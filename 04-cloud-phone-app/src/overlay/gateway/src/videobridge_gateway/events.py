"""What happened to Android and the server, for the page's Events list:
apps that crashed, froze (ANR) or that Android stopped while the user could
see them, Android's boot, and the emulator and gateway starts.

Android's side comes from logcat's "events" and "crash" buffers, which only
go back to Android's last boot (and a few hours at most). The server's side
comes from "systemctl show", which needs no privilege. Every event is
{time (Unix seconds), kind, app, reason}; the page writes the sentence.
"""

import re

LINE = re.compile(r"^\s*(\d+\.\d+)\s+\d+\s+\d+\s+([VDIWEF])\s+(\S+?)\s*:\s?(.*)$")
# Out-of-memory scores up to this one are apps on screen or that the user
# would notice (foreground, visible, perceptible); higher ones are cached
# background processes Android stops all the time.
NOTICEABLE_ADJ = 200


def _fields(text, before, after):
    """Splits "[a,b,c,...]" keeping commas inside the free-text field: the
    first `before` fields, the middle one, and the last `after` fields."""
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    head = text.split(",", before)
    if len(head) <= before:
        return None
    rest = head[before].rsplit(",", after) if after else [head[before]]
    if len(rest) <= after:
        return None
    return head[:before] + rest


def _isolated(process, reason=""):
    return ":sandboxed_process" in process or ":isolated" in process or "isolated not needed" in reason


def parse_logcat(text):
    """Events from `logcat -d -v epoch -b events,crash` output."""
    events = []
    native = None
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        time, _level, tag, message = float(match[1]), match[2], match[3], match[4]
        if tag == "am_crash":
            # [User,PID,Process,Flags,Exception,Message,File,Line,Recoverable]
            fields = _fields(message, 5, 3)
            if fields:
                reason = fields[4] + (f": {fields[5]}" if fields[5] else "")
                events.append({"time": time, "kind": "crash", "app": fields[2], "reason": reason})
        elif tag == "am_anr":
            # [User,PID,Package,Flags,Reason]
            fields = _fields(message, 4, 0)
            if fields:
                events.append({"time": time, "kind": "anr", "app": fields[2], "reason": fields[4]})
        elif tag == "am_kill":
            # [User,PID,Process,OomAdj,Reason,Rss]
            fields = _fields(message, 4, 1)
            if fields and fields[3].lstrip("-").isdigit() and int(fields[3]) <= NOTICEABLE_ADJ \
                    and not _isolated(fields[2], fields[4]):
                events.append({"time": time, "kind": "killed", "app": fields[2], "reason": fields[4]})
        elif tag == "am_low_memory":
            events.append({"time": time, "kind": "low_memory", "app": None, "reason": None})
        elif tag == "libc" and message.startswith("Fatal signal"):
            # Native crash: "Fatal signal 11 (SIGSEGV), code 1 ..., pid 123 (name)"
            name = re.search(r"pid \d+ \(([^)]*)\)", message)
            native = {"time": time, "kind": "crash", "app": name[1] if name else None,
                      "reason": message.split(",")[0]}
            events.append(native)
        elif tag == "DEBUG" and native and message.startswith("Cmdline:"):
            # The crash dump names the process better than the thread name.
            native["app"] = message.split(":", 1)[1].strip().split(" ")[0] or native["app"]
            native = None
    return events


def parse_unit(text, boot_time, kind):
    """The start of a systemd unit from `systemctl show -p
    ExecMainStartTimestampMonotonic -p NRestarts -p Result`, or None."""
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    started = values.get("ExecMainStartTimestampMonotonic", "0")
    if not started.isdigit() or int(started) == 0 or boot_time is None:
        return None
    restarts = values.get("NRestarts", "")
    return {
        "time": boot_time + int(started) / 1e6,
        "kind": kind,
        "app": None,
        "reason": values.get("Result") if values.get("Result") not in (None, "success") else None,
        "restarts": int(restarts) if restarts.isdigit() else None,
    }


def host_boot_time(proc_stat):
    """Unix time of the host's boot, from /proc/stat's btime line."""
    for line in proc_stat.splitlines():
        if line.startswith("btime "):
            return int(line.split()[1])
    return None
