"""The gateway's log records on disk: JSON lines in a directory
(--log_dir, /var/lib/cloudphone/logs on a server), so that they outlive a
restart or an upgrade (see logs.py).

- One record per line, {time, level, source, text[, notify][, params]},
  in files records-YYYYMMDDTHHMMSSZ.jsonl named after their first write
  (UTC), so that their names sort in time order.
- A new file each UTC day and every FILE_BYTES; files last written more
  than GZIP_AFTER_SECONDS ago are gzipped (.jsonl.gz, same name).
- Files last written more than RETENTION_DAYS ago are deleted, then the
  oldest ones while all of them take more than TOTAL_BYTES.
- Writes happen in one thread fed by a bounded queue: a record never
  waits for the disk. When a write fails (disk full, directory gone), the
  thread stops and calls on_failure(reason) once: the gateway then keeps
  its records in memory only.
"""

import glob
import gzip
import json
import logging
import os
import queue
import threading
import time

# How long records are kept on disk: the one place to change it.
RETENTION_DAYS = 61
# All files together at most: a record is about 200 bytes, so even one
# every 5 s (3.5 MB a day, gzipped after a day) stays far below this.
TOTAL_BYTES = 1024 * 1024 * 1024
FILE_BYTES = 16 * 1024 * 1024
GZIP_AFTER_SECONDS = 86400
# Rotation, gzip and deletion run at most this often (and at each new file).
MAINTENANCE_SECONDS = 3600
QUEUE_SIZE = 10000
PATTERN = "records-*.jsonl*"

_logger = logging.getLogger(__name__)


def _file_name(at):
    return "records-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(at)) + ".jsonl"


def files(directory):
    """The record files of `directory`, oldest first: [(path, mtime, size)]."""
    found = []
    paths = set(glob.glob(os.path.join(directory, PATTERN)))
    for path in paths:
        # A file being gzipped: the plain one until it is gone.
        if path.endswith(".tmp") or (path.endswith(".gz") and path[:-3] in paths):
            continue
        try:
            info = os.stat(path)
        except OSError:
            continue
        found.append((path, info.st_mtime, info.st_size))
    found.sort(key=lambda item: os.path.basename(item[0]))
    return found


def _open(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def valid(record):
    return (isinstance(record, dict) and isinstance(record.get("time"), (int, float))
            and record.get("level") in ("normal", "warning", "error")
            and isinstance(record.get("source"), str) and isinstance(record.get("text"), str))


def read_file(path):
    """The valid records of one file, in file order; a line cut by a crash
    or a damaged gzip ends the file."""
    records = []
    if not path.endswith(".gz") and not os.path.exists(path) and os.path.exists(path + ".gz"):
        path += ".gz"  # gzipped since it was listed
    try:
        with _open(path) as f:
            for line in f:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if valid(record):
                    records.append(record)
    except (OSError, EOFError, ValueError):
        pass
    return records


def read_tail(directory, count):
    """The last `count` records on disk, oldest first, none older than
    RETENTION_DAYS (their file may not be deleted yet)."""
    found = []
    oldest = time.time() - RETENTION_DAYS * 86400
    for path, _, _ in reversed(files(directory)):
        found = [r for r in read_file(path) if r["time"] >= oldest] + found
        if len(found) >= count:
            break
    return found[-count:] if count else []


def read_range(directory, keep, since=None):
    """Every record on disk for which keep(record) is true, oldest first,
    skipping files last written before `since`."""
    out = []
    for path, mtime, _ in files(directory):
        if since is not None and mtime < since:
            continue
        out.extend(r for r in read_file(path) if keep(r))
    return out


def maintain(directory, current=None, now=None):
    """Gzips old files, deletes expired ones then the oldest over
    TOTAL_BYTES; never touches `current`, the file being written."""
    now = time.time() if now is None else now
    for path, mtime, _ in files(directory):
        if path == current or path.endswith(".gz") or now - mtime < GZIP_AFTER_SECONDS:
            continue
        _gzip(path, mtime)
    found = [item for item in files(directory) if item[0] != current]
    total = sum(size for _, _, size in found)
    if current:
        try:
            total += os.path.getsize(current)
        except OSError:
            pass
    for path, mtime, size in found:
        if now - mtime > RETENTION_DAYS * 86400 or total > TOTAL_BYTES:
            try:
                os.unlink(path)
                total -= size
            except OSError:
                pass


def _gzip(path, mtime):
    target = path + ".gz"
    tmp = target + ".tmp"
    try:
        with open(path, "rb") as source, gzip.open(tmp, "wb") as out:
            while True:
                chunk = source.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
        os.utime(tmp, (mtime, mtime))
        os.replace(tmp, target)
        os.unlink(path)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class Writer:
    """Appends records to the current file from its own thread."""

    def __init__(self, directory, on_failure):
        self.directory = directory
        self.on_failure = on_failure
        self.queue = queue.Queue(QUEUE_SIZE)
        self.failed = False
        self.dropped = 0
        self.file = None
        self.path = None
        self.day = None
        self.maintained = 0.0
        self.thread = threading.Thread(target=self._run, name="log-files", daemon=True)
        self.thread.start()

    def put(self, record):
        """Queues one record; never waits. False when it is not written."""
        if self.failed:
            return False
        try:
            self.queue.put_nowait(record)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def close(self, timeout=2.0):
        """Writes what is queued, within `timeout` seconds."""
        if not self.failed:
            try:
                self.queue.put(None, timeout=timeout)
            except queue.Full:
                return
            self.thread.join(timeout)

    def _run(self):
        try:
            self._maintain(time.time())
        except Exception:
            _logger.debug("log files maintenance", exc_info=True)
        while True:
            item = self.queue.get()
            batch = [item]
            while item is not None and len(batch) < 1000:
                try:
                    item = self.queue.get_nowait()
                except queue.Empty:
                    break
                batch.append(item)
            stop = batch[-1] is None
            records = [r for r in batch if r is not None]
            try:
                if records:
                    self._write(records)
            except Exception as e:
                self._fail(e)
                return
            if stop:
                if self.file:
                    self.file.close()
                return

    def _write(self, records):
        now = time.time()
        day = time.strftime("%Y%m%d", time.gmtime(now))
        if self.file is None or day != self.day or self.file.tell() >= FILE_BYTES:
            if self.file:
                self.file.close()
                self.file = None
            os.makedirs(self.directory, mode=0o700, exist_ok=True)
            self.path = os.path.join(self.directory, _file_name(now))
            self.file = open(self.path, "a", encoding="utf-8")
            self.day = day
            self._maintain(now)
        elif now - self.maintained >= MAINTENANCE_SECONDS:
            self._maintain(now)
        self.file.write("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records))
        self.file.flush()

    def _maintain(self, now):
        self.maintained = now
        maintain(self.directory, self.path, now)

    def _fail(self, error):
        self.failed = True
        try:
            if self.file:
                self.file.close()
        except OSError:
            pass
        self.file = None
        reason = getattr(error, "strerror", None) or str(error) or type(error).__name__
        self.on_failure(str(reason)[:200])
