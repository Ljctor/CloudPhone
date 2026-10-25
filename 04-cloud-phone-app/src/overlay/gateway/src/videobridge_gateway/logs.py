"""The gateway's log: one stream of records, two outputs.

Every record is {time (Unix seconds), level, source, text[, notify][,
params]}, its text in English whatever the page's language (the page shows
it as it is):

- level: "normal", "warning" or "error" (Python's DEBUG is never shown,
  INFO is normal, WARNING warning, ERROR and CRITICAL error);
- source: "gateway", "emulator", "adb", a plugin's id (its context.log,
  plugins.py), or "page" on the page's side;
- notify: an event worth the user's attention, a mark only (the page
  pops nothing up; phone alerts go through http/notify.send());
- params: the values its text was filled with, as data (log()).

Records go to journald with PRIORITY 6, 4 or 3 and SYSLOG_IDENTIFIER
cloudphone-gateway, so that `journalctl -t cloudphone-gateway -p warning`
keeps warnings and errors. Under systemd (JOURNAL_STREAM names our stderr)
they are sent to the journal's socket with its native protocol; if that
fails, written to stderr with a "<4>" prefix, which journald reads as the
priority. Outside systemd, plain lines on stderr.

The last RECORDS_KEPT records also stay in memory for GET /api/v1/logs,
and every record goes to JSON-lines files in the log directory
(configure(), adapters/log_files.py): at start the gateway reads the last
RECORDS_KEPT back, so the page shows records from before a restart, and
query() reads older ones from the files. If a write fails, one warning
record says so and records stay in memory only.
Error records say what to do next, in one sentence after the event.
The same text logged again within REPEAT_SECONDS is dropped.

Logging with extra={"source": ..., "notify": True} sets the other fields:
see log() below.
"""

import collections
import logging
import math
import os
import secrets
import socket
import struct
import sys
import threading
import time

from .adapters import log_files

IDENTIFIER = "cloudphone-gateway"
JOURNAL_SOCKET = "/run/systemd/journal/socket"
RECORDS_KEPT = 500
# GET /api/v1/logs with filters: limit's default and maximum.
QUERY_DEFAULT = RECORDS_KEPT
QUERY_MAX = 5000
LEVELS = ("normal", "warning", "error")
REPEAT_SECONDS = 30.0
SOURCES = ("gateway", "emulator", "adb")
# journald priorities: 3 err, 4 warning, 6 info.
PRIORITY = {"normal": 6, "warning": 4, "error": 3}

# Records of this gateway process, oldest first, with their number. The
# cursor is "<instance>-<number>": after a restart the instance changes and
# a page's old cursor gets every record again.
INSTANCE = secrets.token_hex(4)
RECORDS = collections.deque(maxlen=RECORDS_KEPT)
_state = {"next": 1, "recent": {}, "writer": None, "directory": None}
_lock = threading.Lock()


def level_of(levelno):
    if levelno >= logging.ERROR:
        return "error"
    if levelno >= logging.WARNING:
        return "warning"
    return "normal"


def _remember(level, source, text, notify, at, params=None, persist=True):
    with _lock:
        record = {"id": _state["next"], "time": round(at, 3), "level": level, "source": source, "text": text}
        if notify:
            record["notify"] = True
        if params:
            record["params"] = params
        if not persist:
            # Found again at each start (remember()): never written.
            record["found"] = True
        _state["next"] += 1
        RECORDS.append(record)
        writer = _state["writer"]
    if persist and writer:
        writer.put(_public(record))


def _public(record):
    return {k: v for k, v in record.items() if k not in ("id", "found")}


def _disk_failed(reason):
    log("warning", "gateway", "Log records are no longer written to disk · {reason} · "
        "The gateway keeps its last 500 records in memory until it restarts.", reason=reason)


def configure(directory):
    """Keeps records in `directory` from now on (created if needed, mode
    700) and puts its last RECORDS_KEPT records in memory before the ones
    of this process. Empty: memory only."""
    if not directory:
        return
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        loaded = log_files.read_tail(directory, RECORDS_KEPT)
    except OSError as e:
        _disk_failed(e.strerror or str(e))
        return
    writer = log_files.Writer(directory, _disk_failed)
    with _lock:
        mine = [r for r in RECORDS]
        RECORDS.clear()
        for number, record in enumerate(loaded + mine, start=1):
            record = dict(record)
            record["id"] = number
            RECORDS.append(record)
        _state["next"] = len(loaded) + len(mine) + 1
        _state["writer"] = writer
        _state["directory"] = directory
    for record in mine:
        if not record.get("found"):
            writer.put(_public(record))


def close():
    """Writes the records still queued (at exit)."""
    writer = _state["writer"]
    if writer:
        writer.close()


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
        records = [_public(r) for r in RECORDS if r["id"] > after]
        last = _state["next"] - 1
    return {"cursor": f"{INSTANCE}-{last}", "records": records}


def _number(text, name):
    try:
        value = float(text)
    except ValueError:
        raise ValueError(f"{name} must be a Unix time in seconds") from None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a Unix time in seconds")
    return value


def is_time(text):
    """True when a `since` value is a Unix time rather than a cursor."""
    try:
        return math.isfinite(float(text))
    except ValueError:
        return False


def parse_query(query):
    """The filters of GET /api/v1/logs from its query string, or None when
    there are none (the plain cursor read). ValueError: an invalid one."""
    since = query.get("since", "")
    filters = {"cursor": query.get("cursor", "")[:64]}
    if since and is_time(since) and "cursor" not in query:
        filters["since"] = _number(since, "since")
    elif not filters["cursor"]:
        filters["cursor"] = since[:64]
    if "until" in query:
        filters["until"] = _number(query["until"], "until")
    if "level" in query:
        if query["level"] not in LEVELS:
            raise ValueError("level must be normal, warning or error")
        filters["level"] = query["level"]
    if query.get("source"):
        filters["source"] = query["source"][:64]
    if query.get("contains"):
        filters["contains"] = query["contains"][:200]
    if "limit" in query:
        try:
            limit = int(query["limit"])
        except ValueError:
            raise ValueError(f"limit must be a whole number from 1 to {QUERY_MAX}") from None
        if limit < 1:
            raise ValueError(f"limit must be a whole number from 1 to {QUERY_MAX}")
        filters["limit"] = min(limit, QUERY_MAX)
    if set(filters) == {"cursor"}:
        return None
    return filters


def _matcher(filters):
    since, until = filters.get("since"), filters.get("until")
    level = LEVELS.index(filters["level"]) if "level" in filters else 0
    source = filters.get("source")
    contains = (filters.get("contains") or "").casefold()

    def keep(record):
        return ((since is None or record["time"] >= since) and (until is None or record["time"] <= until)
                and LEVELS.index(record["level"]) >= level
                and (source is None or record["source"] == source)
                and (not contains or contains in record["text"].casefold()))
    return keep


def query(filters):
    """{cursor, records[, more]}: the records matching `filters`
    (parse_query()), oldest first, the newest `limit` of them; `more` when
    the limit left some out. Records after a cursor of this process come
    from memory only; otherwise the files are read too when memory does
    not reach back far enough. Reads files: call it off the event loop."""
    limit = filters.get("limit", QUERY_DEFAULT)
    keep = _matcher(filters)
    after = None
    instance, _, number = (filters.get("cursor") or "").partition("-")
    if instance == INSTANCE and number.isdigit():
        after = int(number)
    with _lock:
        kept = [r for r in RECORDS if after is None or r["id"] > after]
        last = _state["next"] - 1
        directory = _state["directory"]
    # Memory holds every record written from `boundary` on.
    written = [r["time"] for r in kept if not r.get("found")]
    boundary = min(written) if written else math.inf
    found = [_public(r) for r in kept if keep(r)]
    since = filters.get("since")
    if (after is None and directory and len(found) < limit
            and (since is None or since < boundary)):
        older = log_files.read_range(directory, lambda r: r["time"] < boundary and keep(r), since)
        found = older + found
    found.sort(key=lambda r: r["time"])
    answer = {"cursor": f"{INSTANCE}-{last}", "records": found[-limit:]}
    if len(found) > limit:
        answer["more"] = True
    return answer


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
                      getattr(record, "params", None))
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
    English, whatever the page's language (the page shows it as it is);
    with params it is a template ("{app} crashed") filled with them, the
    record keeping them as data (a viewer's id: the page that connected
    knows it is itself)."""
    levelno = {"normal": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}[level]
    logging.getLogger("cloudphone").log(levelno, text.format(**params) if params else text, stacklevel=2,
                                        extra={"source": source, "notify": notify, "params": params or None})


def remember(level, source, text, at, **params):
    """A record for the page only (not the journal): events from before
    this gateway started, found when it first reads Android's logs."""
    text = text.format(**params) if params else text
    with _lock:
        # Already kept by an earlier gateway, which logged it when it
        # found it, up to a few minutes after it happened.
        if any(r["source"] == source and r["text"] == text and 0 <= r["time"] - at < 600 for r in RECORDS):
            return
    _remember(level, source, text, False, at, params or None, persist=False)


# adb's reachability, from the calls the gateway makes anyway (keys,
# metrics, events, plugins): see adapters/adb.py.
ADB = {"offline": None}


def adb_reached(reached, error_text=""):
    """Notes whether one adb call reached Android (True), was told it
    cannot (False) or neither (None); a change of reachability is a
    record."""
    if reached:
        if ADB["offline"]:
            log("normal", "adb", "adb reaches Android again")
        ADB["offline"] = False
    elif reached is False:
        if not ADB["offline"]:
            log("error", "adb", "adb no longer reaches Android ({reason}). If Android does not restart, "
                "restart it on the server (systemctl restart cloudphone-emulator).",
                notify=True, reason=(error_text or "").strip()[:120] or "?")
        ADB["offline"] = True
