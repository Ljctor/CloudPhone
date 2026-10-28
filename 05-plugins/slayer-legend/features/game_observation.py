"""Bounded observation work and the independent server capture producer.

The pipeline publishes recognition before any resource reader finishes.
Background detection, each reader, and archiving retain only their latest
pending work. Explicit scans await the requested frame instead of treating
background work as fresh evidence. All spawned work is owned by the ports
lifecycle, including shielded reader jobs.
"""

import asyncio
import math
import time

# Recent gestures need prompt recognition; stable foreground is still observed
# without a browser. Process/focus probes remain slower than frame acquisition.
OBSERVE_ACTIVE = 0.5
OBSERVE_STABLE = 1.5
OBSERVE_PROBE = 5.0
READER_CONCURRENCY = 2
FRAME_HISTORY = 8


class ObservationPipeline:
    """Publish detection, schedule bounded reads, and await exact-frame demand."""

    def __init__(self, ports, registry, facts, archive=None):
        self.ports = ports
        self.clock = ports.clock
        self.registry = registry
        self.rules = registry.rules
        self.fact_store = facts
        self.archive = FrameArchive(ports, archive)
        self.last_runs = {}
        self.scans = 0
        self.last = None
        self.pending = None
        self.task = None
        self.epoch = 0
        self.relaunched_at = None
        self.input = None
        self.observations = []
        self.frames = []
        self.lanes = {}
        self.runtime = {
            "detected": 0,
            "discarded": 0,
            "errors": 0,
            "readers": {},
            "detection_seconds": None,
        }
        self.detector_lock = None
        self.explicit_lock = None
        self.reader_limit = None

    def observed(self, shot):
        """Capture acquisition time, never OCR completion time. Older ports
        fall back to the first hook/scan entry, before queueing or analysis."""
        for pixels, size, at, epoch in self.observations:
            if pixels is shot[2] and size == shot[:2]:
                return (at, epoch)
        timestamped = hasattr(self.ports, "capture_time")
        at = self.ports.capture_time(shot) if timestamped else self.clock.wall()
        if not isinstance(at, (int, float)) or isinstance(at, bool) or not math.isfinite(at):
            # Timestamp-capable ports losing metadata cannot turn old pixels
            # into a new capture. Only legacy ports use the entry-time fallback.
            return None
        self.observations.insert(0, (shot[2], shot[:2], at, self.epoch))
        del self.observations[FRAME_HISTORY:]
        return (at, self.epoch)

    def scanned(self, shot, force=()):
        """The last scan when it was of shot and ran every forced reader
        its screen shows."""
        last = self.last
        if not last or last["pixels"] is not shot[2]:
            return None
        if any(reader in last["shows"] and reader not in last["ran"] for reader in force):
            return None
        return last

    def valid_stamp(self, stamp):
        return (
            stamp is not None
            and stamp[1] == self.epoch
            and (self.relaunched_at is None or stamp[0] >= self.relaunched_at)
        )

    def valid(self, frame):
        return self.valid_stamp((frame["at"], frame["epoch"]))

    async def detect(self, shot, stamp):
        if not self.valid_stamp(stamp):
            self.runtime["discarded"] += 1
            return None
        at, epoch = stamp
        for frame in self.frames:
            if frame["pixels"] is shot[2]:
                return frame if self.valid(frame) else None
        if self.detector_lock is None:
            self.detector_lock = asyncio.Lock()
        async with self.detector_lock:
            for frame in self.frames:
                if frame["pixels"] is shot[2]:
                    return frame if self.valid(frame) else None
            frame = {
                "shot": shot,
                "pixels": shot[2],
                "size": [shot[0], shot[1]],
                "at": at,
                "epoch": epoch,
                "readings": {},
                "ran": set(),
                "jobs": {},
            }
            if not self.valid(frame):
                self.runtime["discarded"] += 1
                return None
            began = time.perf_counter()
            look = await getattr(self.ports, "detect", self.ports.analyse)(
                self.registry.identify, shot
            )
            self.runtime["detection_seconds"] = time.perf_counter() - began
            if not self.valid(frame):
                self.runtime["discarded"] += 1
                return None
            previous = self.last
            changed = previous is not None and self.registry.identity(
                previous["look"]
            ) != self.registry.identity(look)
            user = self.ports.last_input() if hasattr(self.ports, "last_input") else None
            mark = user.get("monotonic") if user else None
            changed_input = (
                mark is not None
                and (self.input is None or mark > self.input)
                and isinstance(user.get("wall"), (int, float))
                and (user["wall"] <= at)
            )
            if changed_input:
                self.input = mark
            frame.update(
                look=look, shows=self.registry.shown(look), changed=changed or changed_input
            )
            self.frames.insert(0, frame)
            del self.frames[FRAME_HISTORY:]
            # Recognition becomes visible before readers or archive complete.
            if previous is None or at >= previous["at"]:
                self.last = frame
            else:
                self.runtime["discarded"] += 1
            self.scans += 1
            self.runtime["detected"] += 1
            self.archive.submit(frame)
            return frame

    async def read(self, frame, reader):
        if self.reader_limit is None:
            self.reader_limit = asyncio.Semaphore(READER_CONCURRENCY)
        queued = time.perf_counter()
        metric = self.runtime["readers"].setdefault(
            reader, {"runs": 0, "errors": 0, "discarded": 0}
        )
        metric["queued"] = metric.get("queued", 0) + 1
        try:
            await self.reader_limit.acquire()
        except BaseException:
            metric["queued"] -= 1
            raise
        metric["queued"] -= 1
        try:
            if not self.valid(frame):
                metric["discarded"] += 1
                return {}
            metric["queue_seconds"] = time.perf_counter() - queued
            metric["running"] = metric.get("running", 0) + 1
            began = time.perf_counter()
            try:
                values = await self.ports.analyse(
                    self.registry.read, reader, frame["shot"], frame["look"]
                )
                if not self.valid(frame):
                    metric["discarded"] += 1
                    return {}
                values = {
                    field: value
                    for field, value in values.items()
                    if value is not None or frame["readings"].get(field) is None
                }
                frame["readings"].update(values)
                frame["ran"].add(reader)
                self.last_runs[reader] = max(self.last_runs.get(reader, 0), frame["started"])
                # FactStore includes unread observations in its watermarks:
                # delayed old OCR cannot reverify a newer unread result.
                metric["discarded"] += self.fact_store.publish(values, frame["at"])
                metric["at"] = frame["at"]
                metric["runs"] += 1
                return values
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                metric["errors"] += 1
                metric["error"] = str(exc)
                self.runtime["errors"] += 1
                self.ports.log("warning", f"Game reader {reader} failed: {exc!r}")
                return {}
            finally:
                metric["running"] -= 1
                metric["seconds"] = time.perf_counter() - began
        finally:
            self.reader_limit.release()

    def due(self, frame, force=()):
        frame.setdefault("started", self.clock.monotonic())
        return self.registry.due(frame, self.last_runs, frame["started"], force)

    def reader_task(self, frame, reader):
        task = asyncio.create_task(self.read(frame, reader))
        return getattr(self.ports, "track_task", lambda task: task)(task)

    async def reader_later(self, reader, lane):
        try:
            while lane["pending"] is not None:
                frame, lane["pending"] = (lane["pending"], None)
                task = self.reader_task(frame, reader)
                frame["jobs"][reader] = task
                await task
        finally:
            lane["task"] = None

    def enqueue(self, frame):
        for reader in self.due(frame):
            lane = self.lanes.setdefault(reader, {"pending": None, "task": None})
            if reader in frame["jobs"]:
                continue
            if lane["pending"] is not None and lane["pending"] is not frame:
                self.runtime["discarded"] += 1
            lane["pending"] = frame
            if lane["task"] is None:
                lane["task"] = self.ports.spawn(self.reader_later(reader, lane))

    async def scan(self, shot, force=()):
        """Wait for this frame's due/forced readers. Background detection never waits for OCR."""
        if not shot:
            return {}
        # Capture provenance is immutable across admission waits/cache eviction.
        stamp = self.observed(shot)
        return await self.scan_observed(shot, force, stamp)

    async def scan_observed(self, shot, force, stamp):
        """Scan with provenance already captured by the caller, before any await."""
        if not shot or not self.valid_stamp(stamp):
            self.runtime["discarded"] += 1
            return {}
        if self.explicit_lock is None:
            self.explicit_lock = asyncio.Lock()
        async with self.explicit_lock:
            frame = await self.detect(shot, stamp)
            if frame is None:
                return {}
            tasks = []
            for reader in self.due(frame, force):
                lane = self.lanes.get(reader)
                if lane and lane["pending"] is frame:
                    lane["pending"] = None
                task = frame["jobs"].get(reader)
                if task is None or task.done():
                    task = self.reader_task(frame, reader)
                    frame["jobs"][reader] = task
                tasks.append(task)
            if tasks:
                await self.wait_readers(tasks)
            return dict(frame["readings"]) if self.valid(frame) else {}

    async def wait_readers(self, tasks):
        """Keep explicit admission until this exact frame's batch is drained.

        Caller cancellation must not leave an unbounded series of shielded
        batches behind it. Shared background jobs remain intact; shutdown
        cancels their lifecycle-owned tasks and unblocks this drain.
        """
        batch = asyncio.gather(*tasks, return_exceptions=True)
        try:
            await asyncio.shield(batch)
        except asyncio.CancelledError:
            while not batch.done():
                try:
                    await asyncio.shield(batch)
                except asyncio.CancelledError:
                    # A second cancellation does not surrender admission early.
                    continue
            raise
        for result in batch.result():
            if isinstance(result, BaseException):
                raise result

    async def scan_later(self):
        try:
            while self.pending is not None:
                (shot, stamp), self.pending = (self.pending, None)
                try:
                    frame = await self.detect(shot, stamp)
                    if frame is not None:
                        self.enqueue(frame)
                except Exception as exc:
                    self.runtime["errors"] += 1
                    self.ports.log("warning", f"Game detection failed: {exc!r}")
        finally:
            self.task = None

    def saw(self, shot):
        """Capture hook: one detection in flight plus one latest pending frame."""
        if not shot or self.scanned(shot):
            return
        stamp = self.observed(shot)
        if not self.valid_stamp(stamp):
            self.runtime["discarded"] += 1
            return
        if self.pending is not None and self.pending[0][2] is not shot[2]:
            self.runtime["discarded"] += 1
        self.pending = (shot, stamp)
        if self.task is None:
            self.task = self.ports.spawn(self.scan_later())

    def relaunched(self, why):
        self.epoch += 1
        self.relaunched_at = self.clock.wall()
        self.last = None
        self.last_runs = {}
        self.pending = None
        for lane in self.lanes.values():
            lane["pending"] = None
        self.fact_store.invalidate(why)

    def telemetry(self):
        """Operational measurements only; absent timings mean no completed work."""
        return {
            **self.runtime,
            **self.archive.telemetry(),
            "readers": {
                reader: {
                    **metric,
                    "age_seconds": (
                        max(0, self.clock.wall() - metric["at"]) if "at" in metric else None
                    ),
                }
                for reader, metric in self.runtime["readers"].items()
            },
            "reader_concurrency": READER_CONCURRENCY,
            "reader_running": sum(
                metric.get("running", 0) for metric in self.runtime["readers"].values()
            ),
            "reader_waiting": sum(
                metric.get("queued", 0) for metric in self.runtime["readers"].values()
            ),
            "detection_queued": int(self.pending is not None),
            "reader_queued": sum(lane["pending"] is not None for lane in self.lanes.values()),
            "reader_workers": sum(lane["task"] is not None for lane in self.lanes.values()),
            "age_seconds": max(0, self.clock.wall() - self.last["at"]) if self.last else None,
        }

    def scan_summary(self):
        last = self.last
        if not last:
            return None
        answer = {
            "size": last["size"],
            "at": last["at"],
            "screen": last["look"]["screen"],
            "overlays": sorted(last["look"].get("overlays") or ()),
            "expected": sorted(last["shows"]),
            "ran": sorted(last["ran"]),
        }
        if "quest_tab" in last["look"]:
            answer["quest_tab"] = last["look"]["quest_tab"]
        return answer

    def view(self):
        return {"at": self.last["at"], "look": self.last["look"]} if self.last else None

    def readable_here(self):
        return self.rules.fields_of(self.last["shows"]) if self.last else set()


class FrameArchive:
    """Latest-frame archive, outside detection and explicit scan readiness."""

    def __init__(self, ports, archive):
        self.ports = ports
        self.archive = archive
        self.pending = None
        self.task = None
        self.seconds = None
        self.errors = 0

    def submit(self, frame):
        if self.archive:
            self.pending = frame
            if self.task is None:
                self.task = self.ports.spawn(self.archive_later())

    def telemetry(self):
        return {
            "archive_seconds": self.seconds,
            "archive_errors": self.errors,
            "archive_queued": int(self.pending is not None),
        }

    async def archive_later(self):
        try:
            while self.pending is not None:
                frame, self.pending = (self.pending, None)
                began = time.perf_counter()
                try:
                    await self.ports.analyse(
                        self.archive, frame["look"], frame["shot"], frame["at"]
                    )
                except Exception as exc:
                    self.errors += 1
                    self.ports.log("warning", f"Game archive failed: {exc!r}")
                finally:
                    self.seconds = time.perf_counter() - began
        finally:
            self.task = None


class CaptureProducer:
    """One serial foreground capture loop, independent of observation/OCR completion."""

    def __init__(self, ports, pipeline):
        self.ports = ports
        self.clock = ports.clock
        self.pipeline = pipeline
        self.rules = pipeline.rules
        self.playing = False
        self.watcher = None
        self.runtime = {"captures": 0, "foreground": False, "interval_seconds": None}

    def telemetry(self):
        return dict(self.runtime)

    async def watch(self):
        """One serial server capture producer, independent of browser activity."""
        foreground = False
        probe_at = float("-inf")
        while True:
            interval = self.rules.PROCESS_EVERY
            try:
                enabled = getattr(self.ports, "enabled", lambda: True)()
                if not enabled:
                    foreground = False
                    probe_at = float("-inf")
                elif self.clock.monotonic() >= probe_at:
                    running = await self.ports.running()
                    foreground = bool(running and await self.ports.focused())
                    probe_at = self.clock.monotonic() + (
                        OBSERVE_PROBE if foreground else self.rules.PROCESS_EVERY
                    )
                last = self.ports.last_input() if hasattr(self.ports, "last_input") else None
                self.playing = bool(
                    last
                    and foreground
                    and (self.clock.monotonic() - last["monotonic"] < self.rules.PLAYING)
                )
                self.runtime["foreground"] = foreground
                if enabled and foreground:
                    interval = OBSERVE_ACTIVE if self.playing else OBSERVE_STABLE
                    began = time.perf_counter()
                    shot = await self.ports.capture(max_age=0)
                    self.runtime["capture_seconds"] = time.perf_counter() - began
                    if shot:
                        self.runtime["captures"] += 1
                        stamp = self.pipeline.observed(shot)
                        self.runtime["at"] = stamp[0] if stamp is not None else None
                        # New ports already publish through the capture hook.
                        # Older ports enter the same coalescing path here.
                        if not hasattr(self.ports, "on_capture"):
                            self.pipeline.saw(shot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.pipeline.runtime["errors"] += 1
                self.ports.log("warning", f"Game observer failed: {exc!r}")
            self.runtime["interval_seconds"] = interval
            await self.clock.sleep(interval)

    async def start(self, app):
        if self.watcher is None or self.watcher.done():
            self.watcher = self.ports.spawn(self.watch())
