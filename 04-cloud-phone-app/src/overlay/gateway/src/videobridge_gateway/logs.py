"""The gateway's log: one stream of records, two outputs.

Every record is {time (Unix seconds), level, source, text[, notify]}:

- level: "normal", "warning" or "error" (Python's DEBUG is never shown,
  INFO is normal, WARNING warning, ERROR and CRITICAL error);
- source: "gateway", "emulator", "adb" (or "page" on the page's side);
- notify: the page also shows the record as a toast.

Records go to journald with PRIORITY 6, 4 or 3 and SYSLOG_IDENTIFIER
cloudphone-gateway, so that `journalctl -t cloudphone-gateway -p warning`
keeps warnings and errors. Under systemd (JOURNAL_STREAM names our stderr)
they are sent to the journal's socket with its native protocol; if that
fails, written to stderr with a "<4>" prefix, which journald reads as the
priority. Outside systemd, plain lines on stderr.

The last RECORDS_KEPT records also stay in memory for GET /api/v1/logs.
Error records say what to do next, in one sentence after the event.
The same text logged again within REPEAT_SECONDS is dropped.

Logging with extra={"source": ..., "notify": True} sets the other fields:
see log() below.
"""

import collections
import logging
import os
import secrets
import socket
import struct
import sys
import threading
import time

IDENTIFIER = "cloudphone-gateway"
JOURNAL_SOCKET = "/run/systemd/journal/socket"
RECORDS_KEPT = 500
REPEAT_SECONDS = 30.0
SOURCES = ("gateway", "emulator", "adb")
# journald priorities: 3 err, 4 warning, 6 info.
PRIORITY = {"normal": 6, "warning": 4, "error": 3}

# Records of this gateway process, oldest first, with their number. The
# cursor is "<instance>-<number>": after a restart the instance changes and
# a page's old cursor gets every record again.
INSTANCE = secrets.token_hex(4)
RECORDS = collections.deque(maxlen=RECORDS_KEPT)
_state = {"next": 1, "recent": {}}
_lock = threading.Lock()


def level_of(levelno):
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    return "normal"


def _remember(level, source, text, notify, at, extra=None):
    with _lock:
        record = {"id": _state["next"], "time": round(at, 3), "level": level, "source": source, "text": text}
        if notify:
            record["notify"] = True
        if extra:
            record.update(extra)
        _state["next"] += 1
        RECORDS.append(record)


def _repeated(level, source, text, now):
    """True when the same record was kept less than REPEAT_SECONDS ago."""
    with _lock:
        recent = _state["recent"]
        key = (level, source, text)
        last = recent.get(key)
        if last is not None and now - last < REPEAT_SECONDS:
            return True
        recent[key] = now
        if len(recent) > 1000:
            for old in [k for k, t in recent.items() if now - t >= REPEAT_SECONDS]:
                del recent[old]
        return False


def since(cursor):
    """{cursor, records}: the records after `cursor`, all of them when the
    cursor is empty, unknown or from an earlier gateway process."""
    after = 0
    instance, _, number = (cursor or "").partition("-")
    if instance == INSTANCE and number.isdigit():
        after = int(number)
    with _lock:
        records = [dict(r) for r in RECORDS if r["id"] > after]
        last = _state["next"] - 1
    for record in records:
        del record["id"]
    return {"cursor": f"{INSTANCE}-{last}", "records": records}


def _journal_field(name, value):
    data = str(value).encode("utf-8", "replace")
    if b"\n" in data:
        return name.encode() + b"\n" + struct.pack("<Q", len(data)) + data + b"\n"
    return name.encode() + b"=" + data + b"\n"


def _under_journal():
    """True when stderr is connected to journald (systemd sets JOURNAL_STREAM
    to its device and inode)."""
    stream = os.environ.get("JOURNAL_STREAM", "")
    device, _, inode = stream.partition(":")
    if not device.isdigit() or not inode.isdigit():
        return False
    try:
        info = os.fstat(sys.stderr.fileno())
    except (OSError, ValueError, AttributeError):
        return False
    return info.st_dev == int(device) and info.st_ino == int(inode)


class GatewayHandler(logging.Handler):
    """Keeps records in memory and writes them to the journal or stderr."""

    def __init__(self):
        super().__init__(logging.INFO)
        self.journal = _under_journal()
        self.socket = None
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record):
        try:
            source = getattr(record, "source", "gateway")
            notify = bool(getattr(record, "notify", False))
            level = level_of(record.levelno)
            text = self.format(record)
            if _repeated(level, source, text, record.created):
                return
            _remember(level, source, text.split("\nTraceback", 1)[0][:2000], notify, record.created,
                      getattr(record, "fields", None))
            if self.journal and self._send(record, level, source, notify, text):
                return
            self._write(record, level, source, text)
        except Exception:
            self.handleError(record)

    def _send(self, record, level, source, notify, text):
        fields = [
            ("MESSAGE", text), ("PRIORITY", PRIORITY[level]), ("SYSLOG_IDENTIFIER", IDENTIFIER),
            ("CODE_FILE", record.pathname), ("CODE_LINE", record.lineno), ("CODE_FUNC", record.funcName),
            ("CLOUDPHONE_SOURCE", source), ("CLOUDPHONE_LEVEL", level),
        ]
        if notify:
            fields.append(("CLOUDPHONE_NOTIFY", 1))
        data = b"".join(_journal_field(name, value) for name, value in fields)
        try:
            if self.socket is None:
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            # Large datagrams need a memfd: shorten instead (tracebacks).
            self.socket.sendto(data[:200000], JOURNAL_SOCKET)
            return True
        except OSError:
            self.socket = None
            return False

    def _write(self, record, level, source, text):
        if self.journal:
            # journald reads "<N>" at the start of each line as its priority.
            line = "\n".join(f"<{PRIORITY[level]}>{part}" for part in f"{source}: {text}".splitlines())
        else:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
            line = f"{stamp} [{level}] {source} {record.filename}:{record.lineno}: {text}"
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


def setup():
    """Routes Python logging (the gateway's, its libraries' and plugins')
    to the handler above."""
    root = logging.getLogger()
    if any(isinstance(h, GatewayHandler) for h in root.handlers):
        return
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.addHandler(GatewayHandler())
    root.setLevel(logging.INFO)
    # One line per HTTP request (the page polls): never in the log.
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def log(level, source, text, notify=False, **params):
    """One record. level: "normal", "warning" or "error". The text is in
    French, the page's language; with params it is a template ("{app} a
    planté") that the record carries with its params, so that the page can
    translate it, and is filled for the journal."""
    levelno = {"normal": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}[level]
    fields = {"template": text, "params": params} if params else None
    logging.getLogger("cloudphone").log(levelno, text.format(**params) if params else text, stacklevel=2,
                                        extra={"source": source, "notify": notify, "fields": fields})


def remember(level, source, text, at, **params):
    """A record for the page only (not the journal): events from before
    this gateway started, found when it first reads Android's logs."""
    fields = {"template": text, "params": params} if params else None
    _remember(level, source, text.format(**params) if params else text, False, at, fields)


# adb's reachability, from the error messages of the calls the gateway
# makes anyway (keys, metrics, events, plugins): no extra adb call.
ADB = {"offline": None}
OFFLINE_MARKERS = ("not found", "offline", "no devices", "unauthorized", "cannot connect", "closed")


def adb_result(code, error_text=""):
    """Notes the outcome of one adb call; a change of reachability is a
    record."""
    text = (error_text or "").lower()
    if code == 0:
        if ADB["offline"]:
            log("normal", "adb", "adb joint de nouveau Android")
        ADB["offline"] = False
    elif any(marker in text for marker in OFFLINE_MARKERS):
        if not ADB["offline"]:
            log("error", "adb", "adb ne joint plus Android ({reason}). Si Android ne redémarre pas, "
                "relancez-le sur le serveur (systemctl restart cloudphone-emulator).",
                notify=True, reason=(error_text or "").strip()[:120] or "?")
        ADB["offline"] = True
