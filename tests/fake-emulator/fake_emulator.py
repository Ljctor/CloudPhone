#!/usr/bin/env python3
"""A fake Android emulator, and the surroundings of the real one, for the
Cloud Phone end-to-end tests.

The gateway under test is the repository's, unchanged: this process starts
it the way production does (files/libexec/cloudphone-gateway under systemd)
and plays everything around it:

- the emulator's gRPC services (EmulatorController and Rtc v2) with its
  bearer token, and its WebRTC side (aiortc): the emulator is the offerer;
  it sends a synthetic video (screen.py) and opens the data channels the
  page writes touches and keys to;
- the discovery file (pid_*.ini), the AVD's config.ini, the emulator's
  systemd unit as `systemctl show` reports it (fake `systemctl` on PATH),
  `adb` (fake binary given with --adb), the host's /proc/loadavg and
  /proc/meminfo and the unit's cgroup (redirected by gateway_shim.py);
- the root services of part 03 that apply screen size and settings
  requests (cloudphone-display-apply, cloudphone-settings-apply): same
  validation, same status lines, and an emulator restart that the gateway
  must follow (new discovery file, new token);
- systemd for the gateway: Restart=on-failure, so the gateway comes back
  after it exits to follow a restarted emulator.

A control HTTP server lets tests read what the emulator received
(GET /record) and put it in states no real phone can be put in on demand
(POST /control). See tests/e2e/README.md.

Values marked UNVERIFIED are guesses about the real emulator 36.6.11 that
nothing in the repository confirms; tests/e2e/tests/contract.rs prints what
a real session sends. The values it covers were checked against a live
emulator (2026-10).

Prints one line "READY {json}" on stdout once the gateway answers.
"""

import argparse
import asyncio
import ctypes
import fractions
import json
import logging
import os
import re
import secrets
import signal
import sys
import time
import uuid
from pathlib import Path

# The fake forks the gateway, adb and others while its gRPC server runs:
# gRPC's fork handlers then sometimes abort the child (SIGABRT before exec).
# Nothing here uses gRPC in a child process.
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "false"

import grpc  # noqa: E402
from aiohttp import ClientSession, ClientTimeout, web

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from screen import Screen  # noqa: E402

log = logging.getLogger("fake-emulator")

RENDERERS = ("lavapipe", "swiftshader", "swangle", "software")
# Larger than any pid Linux hands out (pid_max <= 2^22): the emulator
# process the gateway reads in the unit's cgroup never collides with a real
# one. gateway_shim.py redirects /proc/<it>/cmdline.
FAKE_EMULATOR_PID = 4194304
EMULATOR_UNIT = "cloudphone-emulator.service"
# The version string emulator 36.6.11 reports in getStatus (checked against
# a live emulator, 2026-10).
EMULATOR_VERSION = "36.6.11.0 (36.6.11-15507667)"
# The data channels the emulator opens, in this order (checked against a
# live emulator, 2026-10): all ordered and reliable (no maxRetransmits nor
# maxPacketLifeTime), not negotiated, no protocol, odd ids 1, 3, 5, 7 (the
# emulator is the DTLS server).
DATA_CHANNELS = ("mouse", "keyboard", "touch", "adb")
FPS = 15

DEFAULTS = {
    # Install default (03-android-emulator/files/cloudphone.conf).
    "display": {"width": 480, "height": 1040, "density": 213},
    # Cores above a small workstation's thread count on purpose: the page
    # then offers at least two core counts (its even values, plus this one).
    "settings": {"renderer": "lavapipe", "cores": 4, "memoryMb": 4096},
    "options": {
        "data_channels": True,     # new sessions get the emulator's data channels
        "offer": True,             # new sessions get an SDP offer
        "touch_fails": False,      # gRPC sendTouch fails (HTTP touch fallback)
        "adb_fails": False,        # the fake adb fails (keys, Android metrics)
        "hold_requests": False,    # leave request files pending (path units stalled)
        "status_lcd": False,       # getStatus platformConfig carries hw.lcd.* (real 36.6.11 omits them: checked against a live emulator, 2026-10)
        "apply_seconds": 0.5,      # time spent "applying" before stopping Android
        "stop_seconds": 0.3,       # time Android takes to stop
        "boot_seconds": 1.5,       # time Android takes to boot (booted false)
        "crash_seconds": 3.0,      # unit in auto-restart after a crash
        "gateway_restart_seconds": 1.0,  # systemd RestartSec of the gateway (5 s in production)
        "fail_next": {},           # {"display": "message", "settings": "message"}: next request fails
    },
    "load": 0.1,
    "host_memory_mb": 16384,
    # Plugins installed for the gateway (--plugins_dir, as files/libexec
    # passes /opt/cloudphone/plugins): plugin directories relative to the
    # repository, e.g. "tests/fake-emulator/plugins/e2e-probe". None by
    # default (an empty directory).
    "plugins": [],
}


def deep_update(target, changes):
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            deep_update(target[key], value)
        else:
            target[key] = value


def die_with_parent():
    """In the child, before exec: killed when the fake dies."""
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except OSError:
        pass


def write_atomic(path, text):
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


class Record:
    """Everything the fake received, for GET /record."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.touches = []
        self.keys = []
        self.mouse = []
        self.channel_messages = []
        self.grpc = []
        self.jsep_from_browser = []
        self.jsep_to_browser = []
        self.requests = {"display": [], "settings": []}
        self.sessions = []
        self.gateway = []
        self.events = []
        self.adb_offset = 0
        self.adb = []


class Participant:
    """One WebRTC session (RequestRtcStream), the emulator as offerer."""

    def __init__(self, emulator, guid, ice_servers):
        self.emulator = emulator
        self.guid = guid
        self.ice_servers = ice_servers
        self.outbox = asyncio.Queue()
        self.pc = None
        self.closed = False
        self.channels = {}
        self.info = {"guid": guid, "opened": time.time(), "closed": None, "browser_channels": [],
                     "state": "new", "data_channels": emulator.options["data_channels"],
                     "offer": emulator.options["offer"]}
        self.screen = Screen(emulator.display["width"], emulator.display["height"])

    def send(self, message):
        if self.closed:
            return
        self.emulator.record.jsep_to_browser.append({"guid": self.guid, "message": summarize(message)})
        self.outbox.put_nowait(json.dumps(message))

    async def start(self):
        from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCRtpSender

        # The "start" message's keys are block_status, ice_servers,
        # ice_transport_policy and unblock_ice_servers: snake_case, no
        # iceServers (checked against a live emulator, 2026-10).
        # UNVERIFIED: their values (the contract prints the keys only); the
        # fake echoes the ICE servers the gateway asked for in
        # RequestRtcStream.
        self.send({"start": {"block_status": False, "ice_servers": self.ice_servers,
                             "ice_transport_policy": "all", "unblock_ice_servers": []}})
        if not self.emulator.options["offer"]:
            return
        self.pc = pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))

        @pc.on("connectionstatechange")
        async def state_changed():
            self.info["state"] = pc.connectionState
            log.info("session %s: %s", self.guid, pc.connectionState)

        @pc.on("datachannel")
        def browser_channel(channel):
            # The page's driver creates "input" (upstream InputEvent channel).
            self.info["browser_channels"].append(channel.label)
            self.watch(channel)

        transceiver = pc.addTransceiver(VideoTrack(self), direction="sendonly")
        # The emulator offers VP8, VP9, red and ulpfec (with RTX), no H264
        # (checked against a live emulator, 2026-10). aiortc cannot send
        # VP9, red nor ulpfec: the fake offers VP8 (and its RTX) only.
        codecs = [c for c in RTCRtpSender.getCapabilities("video").codecs if c.mimeType in ("video/VP8", "video/rtx")]
        transceiver.setCodecPreferences(codecs)
        # The offer's m-lines are video, audio, application (checked against
        # a live emulator, 2026-10): the emulator sends an audio track too,
        # Opus first. The fake's is silence.
        pc.addTransceiver(AudioStreamTrack(), direction="sendonly")
        if self.emulator.options["data_channels"]:
            for label in DATA_CHANNELS:
                channel = pc.createDataChannel(label)
                self.channels[label] = channel
                self.watch(channel)
        await pc.setLocalDescription(await pc.createOffer())
        if self.closed:
            return
        # aiortc gathers before it gives the offer; the emulator (libwebrtc)
        # trickles. Send the SDP without candidates, then each candidate.
        lines = pc.localDescription.sdp.split("\r\n")
        sdp = "\r\n".join(l for l in lines if not l.startswith("a=candidate:") and l != "a=end-of-candidates")
        # The offer as {"type": "offer", "sdp": "..."} at the top level, its
        # SDP without candidates, then candidates as {"candidate": string,
        # "sdpMid": string, "sdpMLineIndex": number} (checked against a live
        # emulator, 2026-10). The driver also accepts the nested
        # {"sdp": {...}} form.
        self.send({"type": "offer", "sdp": sdp})
        mid, index = None, -1
        for line in lines:
            if line.startswith("m="):
                index += 1
            elif line.startswith("a=mid:"):
                mid = line[6:]
            elif line.startswith("a=candidate:") and index == 0:
                self.send({"candidate": line[2:], "sdpMid": mid or "0", "sdpMLineIndex": 0})

    def watch(self, channel):
        @channel.on("message")
        def message(data):
            self.emulator.channel_message(channel.label, data)

    async def handle(self, message):
        from aiortc import RTCSessionDescription
        from aiortc.sdp import candidate_from_sdp

        if message.get("bye"):
            await self.close("bye from browser")
            return
        description = message.get("sdp") if isinstance(message.get("sdp"), dict) else message
        if isinstance(description, dict) and description.get("type") == "answer" and self.pc:
            await self.pc.setRemoteDescription(RTCSessionDescription(sdp=description["sdp"], type="answer"))
            return
        candidate = message.get("candidate")
        if candidate and self.pc:
            if isinstance(candidate, dict):
                text, mid, index = candidate.get("candidate", ""), candidate.get("sdpMid"), candidate.get("sdpMLineIndex")
            else:
                text, mid, index = candidate, message.get("sdpMid"), message.get("sdpMLineIndex")
            if not text:
                return
            parsed = candidate_from_sdp(text.split(":", 1)[1] if text.startswith("candidate:") else text)
            parsed.sdpMid, parsed.sdpMLineIndex = mid, index
            try:
                await self.pc.addIceCandidate(parsed)
            except Exception as error:  # an mDNS name that does not resolve, for instance
                log.warning("candidate %s refused: %s", text, error)

    async def close(self, why, bye=False):
        if self.closed:
            return
        if bye:
            self.send({"bye": True})
        self.closed = True
        self.info["closed"] = time.time()
        self.info["why"] = why
        self.outbox.put_nowait(None)
        if self.pc:
            await self.pc.close()
        self.emulator.participants.pop(self.guid, None)


class VideoTrack:
    """The emulator's screen as a WebRTC video track, FPS frames a second."""

    kind = "video"

    def __new__(cls, participant):
        from aiortc import MediaStreamTrack

        class Track(MediaStreamTrack):
            kind = "video"

            def __init__(self):
                super().__init__()
                self.start = None
                self.timestamp = 0

            async def recv(self):
                import av

                if self.start is None:
                    self.start = time.time()
                else:
                    self.timestamp += 90000 // FPS
                    wait = self.start + self.timestamp / 90000 - time.time()
                    if wait > 0:
                        await asyncio.sleep(wait)
                emulator = participant.emulator
                image = emulator.frame(participant.screen)
                frame = av.VideoFrame.from_ndarray(image, format="rgb24")
                frame.pts = self.timestamp
                frame.time_base = fractions.Fraction(1, 90000)
                return frame

        return Track()


def summarize(message):
    """A JSEP message as recorded: its keys, the SDP's media lines and codecs."""
    if not isinstance(message, dict):
        return {"raw": str(message)[:200]}
    out = {"keys": sorted(message)}
    sdp = message.get("sdp")
    if isinstance(sdp, dict):
        out["sdp_keys"] = sorted(sdp)
        out["type"] = sdp.get("type")
        sdp = sdp.get("sdp")
    if isinstance(sdp, str):
        out["type"] = out.get("type") or message.get("type")
        out["media"] = [l for l in sdp.split("\r\n") if l.startswith("m=")]
        out["codecs"] = sorted({l.split(" ", 1)[1].split("/")[0] for l in sdp.split("\r\n") if l.startswith("a=rtpmap:")})
        out["candidates_in_sdp"] = sum(1 for l in sdp.split("\r\n") if l.startswith("a=candidate:"))
    candidate = message.get("candidate")
    if candidate is not None:
        out["candidate_type"] = type(candidate).__name__
    if "start" in message:
        out["start"] = message["start"]
    return out


class Emulator:
    def __init__(self, workdir, config, args):
        self.args = args
        self.work = Path(workdir)
        self.config = json.loads(json.dumps(DEFAULTS))
        deep_update(self.config, config)
        self.display = dict(self.config["display"])
        self.settings = dict(self.config["settings"])
        self.options = self.config["options"]
        self.unit = {"active": "active", "sub": "running", "result": "success", "restarts": 0}
        deep_update(self.unit, config.get("unit", {}))
        self.booted = config.get("booted", True)
        self.grpc_up = config.get("grpc", "up") == "up"
        self.token = None
        self.discovery = None
        self.started = time.time()
        self.record = Record()
        self.participants = {}
        self.touch = None
        self.key = None
        self.frame_number = 0
        self.frame_cache = {}
        self.busy = {"display": False, "settings": False}
        self.boot_task = None
        self.gateway = None
        self.gateway_wanted = True
        self.gateway_restarting = False
        self.gateway_event = asyncio.Event()
        self.closing = False
        self.web_port = args.web_port or free_port()
        for name in ("running", "avd", "host/proc", "host/cgroup", "android", "bin-state"):
            (self.work / name).mkdir(parents=True, exist_ok=True)
        self.write_avd_config()
        self.write_host()
        self.write_unit()
        self.write_android()

    # ---- files the gateway reads ----

    def path(self, name):
        return str(self.work / name)

    def write_avd_config(self):
        d = self.display
        # The emulator rewrites config.ini as "key = value".
        write_atomic(self.path("avd/config.ini"), "".join(f"{k} = {v}\n" for k, v in {
            "AvdId": "cloudphone", "avd.ini.displayname": "cloudphone", "hw.cpu.ncore": self.settings["cores"],
            "hw.lcd.density": d["density"], "hw.lcd.height": d["height"], "hw.lcd.width": d["width"],
            "hw.ramSize": f"{self.settings['memoryMb']}M", "image.sysdir.1": "system-images/android-36/google_apis_playstore/x86_64/",
        }.items()))

    def write_host(self):
        load = self.config["load"]
        write_atomic(self.path("host/proc/loadavg"), f"{load:.2f} {load:.2f} {load:.2f} 2/321 {FAKE_EMULATOR_PID}\n")
        total = self.config["host_memory_mb"] * 1024
        write_atomic(self.path("host/proc/meminfo"),
                     f"MemTotal:       {total} kB\nMemFree:        {total // 4} kB\nMemAvailable:   {total // 2} kB\n"
                     f"SwapTotal:      2097148 kB\nSwapFree:       2097148 kB\n")
        running = self.grpc_up and self.unit["active"] == "active"
        write_atomic(self.path("host/cgroup/cgroup.procs"), f"{FAKE_EMULATOR_PID}\n" if running else "")
        write_atomic(self.path("host/cgroup/memory.current"), f"{(self.settings['memoryMb'] + 512) * 1048576}\n")
        usage = int((time.time() - self.started) * 1.5e6)
        write_atomic(self.path("host/cgroup/cpu.stat"), f"usage_usec {usage}\nuser_usec {usage}\nsystem_usec 0\n")
        # UNVERIFIED (beyond what the gateway parses): qemu's command line.
        s = self.settings
        args = ["/opt/cloudphone/android-sdk/emulator/qemu/linux-x86_64/qemu-system-x86_64-headless",
                "-avd", "cloudphone", "-port", "5558", "-grpc", "8554", "-grpc-use-token", "-no-window",
                "-gpu", s["renderer"], "-memory", str(s["memoryMb"]), "-cores", str(s["cores"])]
        with open(self.path("host/proc/emulator.cmdline"), "wb") as f:
            f.write(b"\0".join(a.encode() for a in args) + b"\0")

    def write_unit(self):
        u = self.unit
        write_atomic(self.path("systemctl-show"),
                     f"ActiveState={u['active']}\nSubState={u['sub']}\nNRestarts={u['restarts']}\nResult={u['result']}\n")

    def write_android(self):
        total = 4 * 1024 * 1024
        write_atomic(self.path("android/meminfo"),
                     f"MemTotal:        {total} kB\nMemFree:          {total // 3} kB\nMemAvailable:     {total // 2} kB\n"
                     f"SwapTotal:        3145724 kB\nSwapFree:         2097148 kB\n")
        # UNVERIFIED: SurfaceFlinger --timestats -dump layout beyond the
        # "layerName = " and "averageFPS = " lines the gateway reads.
        write_atomic(self.path("android/timestats"),
                     "SurfaceFlinger TimeStats:\nlayerName = 42 SurfaceView[com.example.fakegame/"
                     "com.example.fakegame.MainActivity](BLAST)#51\npackageName = \ntotalFrames = 300\n"
                     "droppedFrames = 0\naverageFPS = 29.97\n")
        if self.options["adb_fails"]:
            write_atomic(self.path("bin-state/adb-fail"), "1\n")
        elif os.path.exists(self.path("bin-state/adb-fail")):
            os.remove(self.path("bin-state/adb-fail"))

    def write_discovery(self):
        """A new emulator process: new pid file, new token."""
        self.remove_discovery()
        self.token = secrets.token_urlsafe(24)
        pid = 10000 + len(self.record.gateway) * 7 + int(time.time() * 1000) % 50000
        self.discovery = self.path(f"running/pid_{pid}.ini")
        # UNVERIFIED: the other keys of the real discovery file and their
        # order; the gateway reads grpc.port, grpc.token and avd.dir.
        write_atomic(self.discovery,
                     f"port.serial=5558\nport.adb=5559\navd.name=cloudphone\navd.dir={self.path('avd')}\n"
                     f"avd.id=cloudphone\ncmdline=\"emulator -avd cloudphone\"\n"
                     f"grpc.port={self.grpc_port}\ngrpc.token={self.token}\n")

    def remove_discovery(self):
        if self.discovery and os.path.exists(self.discovery):
            os.remove(self.discovery)
        self.discovery = None

    # ---- the screen ----

    def frame(self, screen):
        """The current frame for a session's screen; one render per tick."""
        number = int((time.time() - self.started) * FPS)
        key = (screen.width, screen.height, number)
        if key not in self.frame_cache:
            self.frame_cache.clear()
            touch = None
            if self.touch:
                touch = (self.touch["x"] * screen.width // max(1, self.display["width"]),
                         self.touch["y"] * screen.height // max(1, self.display["height"]),
                         self.touch["pressure"] > 0)
            self.frame_cache[key] = screen.render(number, booted=self.booted, touch=touch,
                                                  key=self.key)
        return self.frame_cache[key]

    # ---- input ----

    def apply_touch(self, touches, via, display=0):
        for t in touches:
            entry = {"x": t.x, "y": t.y, "identifier": t.identifier, "pressure": t.pressure,
                     "touch_major": t.touch_major, "touch_minor": t.touch_minor, "display": display,
                     "via": via, "time": time.time()}
            self.record.touches.append(entry)
            self.touch = entry

    def channel_message(self, label, data):
        import emulator_controller_pb2 as ec

        raw = data if isinstance(data, bytes) else data.encode()
        entry = {"label": label, "size": len(raw), "binary": isinstance(data, bytes), "hex": raw[:64].hex(),
                 "time": time.time()}
        self.record.channel_messages.append(entry)
        try:
            if label == "touch":
                event = ec.TouchEvent.FromString(raw)
                self.apply_touch(event.touches, "touch", event.display)
            elif label == "keyboard":
                event = ec.KeyboardEvent.FromString(raw)
                self.record.keys.append({"key": event.key, "eventType": event.eventType, "keyCode": event.keyCode,
                                         "via": "keyboard", "time": time.time()})
                self.key = event.key
            elif label == "mouse":
                event = ec.MouseEvent.FromString(raw)
                self.record.mouse.append({"x": event.x, "y": event.y, "buttons": event.buttons, "via": "mouse"})
            elif label == "input":
                # Emulator 36.6.11 never reads this channel (DEVELOPMENT.md):
                # recorded, not applied.
                event = ec.InputEvent.FromString(raw)
                entry["dropped"] = True
                entry["event"] = event.WhichOneof("type")
        except Exception as error:
            entry["error"] = str(error)

    def read_adb_log(self):
        try:
            with open(self.path("bin-state/adb.log")) as f:
                f.seek(self.record.adb_offset)
                text = f.read()
                self.record.adb_offset = f.tell()
        except OSError:
            return
        for line in text.splitlines():
            self.record.adb.append(line)
            words = line.split()
            if "keyevent" in words and words.index("keyevent") + 1 < len(words):
                key = words[words.index("keyevent") + 1]
                self.record.keys.append({"key": key, "via": "adb", "time": time.time()})
                self.key = key

    # ---- lifecycle of the emulator process ----

    def set_unit(self, active, sub, **extra):
        self.unit.update(active=active, sub=sub, **extra)
        self.write_unit()
        self.write_host()

    async def drop_sessions(self, why, bye=False):
        for participant in list(self.participants.values()):
            await participant.close(why, bye=bye)

    async def stop(self, why="stop"):
        self.record.events.append({"event": "android-stop", "why": why, "time": time.time()})
        self.set_unit("deactivating", "stop-sigterm")
        await asyncio.sleep(self.options["stop_seconds"])
        self.grpc_up = False
        self.booted = False
        await self.drop_sessions(why)
        self.remove_discovery()
        self.set_unit("inactive", "dead", result="success")

    async def start(self, why="start"):
        self.record.events.append({"event": "android-start", "why": why, "time": time.time()})
        self.started = time.time()
        self.write_avd_config()
        self.write_discovery()
        self.grpc_up = True
        self.booted = False
        # Type=simple: "active (running)" as soon as the process runs.
        self.set_unit("active", "running", result="success")
        if self.boot_task:
            self.boot_task.cancel()
        self.boot_task = asyncio.create_task(self.boot())

    async def boot(self):
        await asyncio.sleep(self.options["boot_seconds"])
        self.booted = True
        self.record.events.append({"event": "android-booted", "time": time.time()})

    async def wait_booted(self):
        while not self.booted:
            await asyncio.sleep(0.1)

    async def crash(self):
        """The emulator dies; systemd restarts it after RestartSec."""
        self.record.events.append({"event": "android-crash", "time": time.time()})
        self.grpc_up = False
        self.booted = False
        await self.drop_sessions("crash")
        self.remove_discovery()
        self.set_unit("activating", "auto-restart", result="exit-code", restarts=self.unit["restarts"] + 1)
        await asyncio.sleep(self.options["crash_seconds"])
        await self.start("restart after crash")

    # ---- the root services of part 03 ----

    async def watch_requests(self):
        while not self.closing:
            await asyncio.sleep(0.1)
            if self.options["hold_requests"]:
                continue
            for kind in ("display", "settings"):
                path = self.path(f"{kind}-request")
                if not self.busy[kind] and (os.path.exists(path) or os.path.islink(path)):
                    self.busy[kind] = True
                    asyncio.create_task(self.apply_request(kind, path))

    def report(self, kind, line):
        self.record.requests[kind].append({"status": line, "time": time.time()})
        write_atomic(self.path(f"{kind}-status"), line + "\n")

    async def apply_request(self, kind, path):
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                os.remove(path)
                self.report(kind, "failed invalid request")
                return
            with open(path, "rb") as f:
                line = f.read(64).split(b"\n")[0].decode(errors="replace")
            os.remove(path)
            self.record.requests[kind].append({"request": line, "time": time.time()})
            await (self.apply_display(line) if kind == "display" else self.apply_settings(line))
        except Exception:
            log.exception("%s request", kind)
        finally:
            self.busy[kind] = False

    @staticmethod
    def size_ok(width, height, density):
        return (width % 2 == 0 and height % 2 == 0 and 240 <= width <= 1440 and 320 <= height <= 3200
                and 80 <= density <= 640)

    async def apply_display(self, line):
        match = re.fullmatch(r"([0-9]{3,4}) ([0-9]{3,4}) ([0-9]{2,3})", line)
        if not match:
            self.report("display", "failed invalid request")
            return
        width, height, density = (int(v, 10) for v in match.groups())
        if not self.size_ok(width, height, density):
            self.report("display", "failed out of range")
            return
        self.report("display", f"applying {width} {height} {density}")
        await asyncio.sleep(self.options["apply_seconds"])
        failure = self.options["fail_next"].pop("display", None)
        if failure is not None:
            self.report("display", f"failed {failure or 'set-resolution.sh: journalctl -u cloudphone-display'}")
            return
        await self.set_resolution(width, height, density)
        self.report("display", f"done {width} {height} {density}")

    async def set_resolution(self, width, height, density):
        """03-android-emulator/scripts/set-resolution.sh."""
        await self.stop("screen size change")
        self.display = {"width": width, "height": height, "density": density}
        await self.start("screen size change")
        await self.wait_booted()
        await self.restart_gateway("set-resolution.sh")

    async def apply_settings(self, line):
        match = re.fullmatch(r"([a-z_]{1,32}) ([0-9]{1,2}) ([0-9]{4,6})( ([0-9]{3,4}) ([0-9]{3,4}) ([0-9]{2,3}))?", line)
        if not match:
            self.report("settings", "failed invalid request")
            return
        renderer, cores, memory = match.group(1), int(match.group(2), 10), int(match.group(3), 10)
        size = None
        if match.group(4):
            size = tuple(int(match.group(i), 10) for i in (5, 6, 7))
            if not self.size_ok(*size):
                self.report("settings", "failed out of range")
                return
        host = self.config["host_memory_mb"]
        if (renderer not in RENDERERS or not 1 <= cores <= (os.cpu_count() or 1)
                or not 2048 <= memory <= host - 2048 or memory % 512):
            self.report("settings", "failed out of range")
            return
        if self.busy["display"]:
            self.report("settings", "failed a screen size change is in progress")
            return
        words = f"{renderer} {cores} {memory}" + (" %d %d %d" % size if size else "")
        self.report("settings", f"applying {words}")
        await asyncio.sleep(self.options["apply_seconds"])
        failure = self.options["fail_next"].pop("settings", None)
        if failure is not None:
            self.report("settings", f"failed {failure or 'restart: journalctl -u cloudphone-emulator'}")
            return
        self.settings = {"renderer": renderer, "cores": cores, "memoryMb": memory}
        if size:
            await self.set_resolution(*size)
        else:
            # systemctl restart cloudphone-emulator.service: returns once the
            # new process runs, before Android has booted. The gateway
            # follows by itself (new discovery file).
            await self.stop("settings change")
            await self.start("settings change")
        self.report("settings", f"done {words}")

    # ---- systemd for the gateway ----

    def install_plugins(self):
        """PLUGINS_DIR/<id> -> the repository's plugin directories, as an
        install script would copy them."""
        target = self.work / "plugins"
        target.mkdir(exist_ok=True)
        for entry in self.config.get("plugins", []):
            # "dir" (installed under its id) or {"path": "dir", "name": "installed name"}.
            relative = entry["path"] if isinstance(entry, dict) else entry
            source = (HERE.parent.parent / relative).resolve()
            if isinstance(entry, dict) and "name" in entry:
                plugin_id = entry["name"]
            else:
                with open(source / "plugin.json") as f:
                    plugin_id = json.load(f)["id"]
            link = target / plugin_id
            if not link.exists():
                link.symlink_to(source)
        return str(target)

    async def supervise_gateway(self):
        log_file = open(self.path("gateway.log"), "ab")
        gateway_python = self.args.gateway_python
        while not self.closing:
            if not self.gateway_wanted:
                self.gateway_event.clear()
                await self.gateway_event.wait()
                continue
            # files/libexec/cloudphone-gateway waits for a discovery file.
            found = sorted((self.work / "running").glob("pid_*.ini"))
            if not found:
                await asyncio.sleep(0.2)
                continue
            env = dict(os.environ)
            env.update(PATH=f"{HERE / 'bin'}:{env.get('PATH', '')}", FAKE_ROOT=str(self.work),
                       FAKE_GATEWAY_PATH=self.args.gateway_path, FAKE_EMULATOR_UNIT=EMULATOR_UNIT,
                       FAKE_EMULATOR_PID=str(FAKE_EMULATOR_PID), PYTHONDONTWRITEBYTECODE="1")
            command = [gateway_python, str(HERE / "gateway_shim.py"),
                       "--host", "127.0.0.1", "--port", str(self.web_port), "--web_root", self.args.web_root,
                       "--adb", str(HERE / "bin" / "adb"), "--adb_serial", "emulator-5558",
                       "--discovery_file", str(found[0]), "--emulator_unit", EMULATOR_UNIT,
                       "--display_request", self.path("display-request"), "--display_status", self.path("display-status"),
                       "--settings_request", self.path("settings-request"), "--settings_status", self.path("settings-status"),
                       "--plugins_dir", self.install_plugins()]
            self.gateway = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.DEVNULL, stdout=log_file, stderr=log_file, env=env,
                preexec_fn=die_with_parent)
            entry = {"pid": self.gateway.pid, "discovery": found[0].name, "started": time.time(), "exit": None}
            self.record.gateway.append(entry)
            code = await self.gateway.wait()
            entry["exit"] = code
            entry["stopped"] = time.time()
            self.gateway = None
            if self.closing:
                break
            if self.gateway_restarting:
                self.gateway_restarting = False
                continue
            if code == 0:
                # Restart=on-failure: a clean exit stays down.
                self.gateway_wanted = False
                continue
            await asyncio.sleep(self.options["gateway_restart_seconds"])

    async def restart_gateway(self, why):
        self.record.events.append({"event": "gateway-restart", "why": why, "time": time.time()})
        if self.gateway and self.gateway.returncode is None:
            self.gateway_restarting = True
            self.gateway.terminate()
        self.gateway_wanted = True
        self.gateway_event.set()

    async def stop_gateway(self):
        self.gateway_wanted = False
        if self.gateway and self.gateway.returncode is None:
            self.gateway.terminate()

    def start_gateway(self):
        self.gateway_wanted = True
        self.gateway_event.set()

    # ---- control ----

    async def control(self, body):
        """POST /control: settings (kept until changed) and one-shot actions."""
        for key in ("options",):
            if key in body:
                deep_update(self.options, body[key])
        for key in ("data_channels", "offer", "touch_fails", "adb_fails", "hold_requests", "status_lcd",
                    "apply_seconds", "stop_seconds", "boot_seconds", "crash_seconds", "gateway_restart_seconds"):
            if key in body:
                self.options[key] = body[key]
        if "fail_next" in body:
            self.options["fail_next"].update(body["fail_next"])
        if "load" in body:
            self.config["load"] = float(body["load"])
        if "unit" in body:
            self.unit.update(body["unit"])
            self.write_unit()
        if "booted" in body:
            self.booted = bool(body["booted"])
        if "grpc" in body:
            self.grpc_up = body["grpc"] == "up"
        self.write_host()
        self.write_android()
        action = body.get("action")
        if action == "drop_streams":
            await self.drop_sessions("dropped by the test", bye=body.get("bye", True))
        elif action == "crash":
            asyncio.create_task(self.crash())
        elif action == "restart":
            async def restart():
                await self.stop("restart")
                await self.start("restart")
            asyncio.create_task(restart())
        elif action == "replace_discovery":
            # A new emulator process (pid, token) without anything else.
            self.write_discovery()
            await self.drop_sessions("emulator replaced")
        elif action == "stop_gateway":
            await self.stop_gateway()
        elif action == "start_gateway":
            self.start_gateway()
        elif action == "restart_gateway":
            await self.restart_gateway("asked by the test")
        elif action == "reset_record":
            self.read_adb_log()
            self.record.reset()
            try:
                self.record.adb_offset = os.path.getsize(self.path("bin-state/adb.log"))
            except OSError:
                pass
        elif action:
            raise web.HTTPBadRequest(text=f"unknown action {action}")

    def state(self):
        return {
            "display": self.display, "settings": self.settings, "unit": self.unit, "booted": self.booted,
            "grpc": "up" if self.grpc_up else "down", "options": self.options, "load": self.config["load"],
            "discovery": self.discovery and os.path.basename(self.discovery), "token": self.token,
            "gateway": {"running": bool(self.gateway and self.gateway.returncode is None),
                        "pid": self.gateway.pid if self.gateway else None, "starts": len(self.record.gateway)},
            "sessions": [p.info for p in self.participants.values()],
            "web_port": self.web_port, "grpc_port": self.grpc_port, "workdir": str(self.work),
        }

    def record_json(self):
        self.read_adb_log()
        r = self.record
        return {
            "touches": r.touches, "keys": r.keys, "mouse": r.mouse, "channel_messages": r.channel_messages,
            "grpc": r.grpc, "jsep": {"to_browser": r.jsep_to_browser, "from_browser": r.jsep_from_browser},
            "requests": r.requests, "sessions": r.sessions, "gateway": r.gateway, "events": r.events, "adb": r.adb,
        }


def free_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_services(emulator):
    import emulator_controller_pb2 as ec
    import emulator_controller_pb2_grpc as ec_grpc
    import rtc_service_v2_pb2 as rtc
    import rtc_service_v2_pb2_grpc as rtc_grpc
    from google.protobuf import empty_pb2

    async def check(context, method):
        metadata = dict(context.invocation_metadata())
        authorized = bool(emulator.token) and metadata.get("authorization") == f"Bearer {emulator.token}"
        emulator.record.grpc.append({"method": method, "authorized": authorized, "time": time.time()})
        if not emulator.grpc_up:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "emulator not running")
        if not authorized:
            # UNVERIFIED: the status code the emulator gives a wrong token.
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing or invalid token")

    class Controller(ec_grpc.EmulatorControllerServicer):
        async def getStatus(self, request, context):
            await check(context, "getStatus")
            s = emulator.settings
            status = ec.EmulatorStatus(
                version=EMULATOR_VERSION, uptime=int((time.time() - emulator.started) * 1000), booted=emulator.booted,
                vmConfig=ec.VmConfiguration(hypervisorType=ec.VmConfiguration.KVM, numberOfCpuCores=s["cores"],
                                            ramSizeBytes=s["memoryMb"] * 1048576))
            # platformConfig is empty on 36.6.11: the gateway's answer has
            # only the hw.lcd.width and hw.lcd.height it adds itself (checked
            # against a live emulator, 2026-10).
            if emulator.options["status_lcd"]:
                for key in ("width", "height", "density"):
                    status.platformConfig[f"hw.lcd.{key}"] = str(emulator.display[key])
            return status

        async def getScreenshot(self, request, context):
            await check(context, "getScreenshot")
            d = emulator.display
            image = emulator.frame(Screen(d["width"], d["height"]))
            if request.format == ec.ImageFormat.RGBA8888:
                import numpy as np
                image = np.dstack([image, np.full(image.shape[:2], 255, dtype=np.uint8)])
            return ec.Image(format=ec.ImageFormat(format=request.format, width=d["width"], height=d["height"]),
                            image=image.tobytes(), seq=emulator.frame_number, timestampUs=int(time.time() * 1e6))

        async def sendTouch(self, request, context):
            await check(context, "sendTouch")
            if emulator.options["touch_fails"]:
                await context.abort(grpc.StatusCode.INTERNAL, "touch injection failed (fake)")
            emulator.apply_touch(request.touches, "grpc", request.display)
            return empty_pb2.Empty()

        async def sendKey(self, request, context):
            await check(context, "sendKey")
            emulator.record.keys.append({"key": request.key, "eventType": request.eventType, "via": "grpc"})
            emulator.key = request.key
            return empty_pb2.Empty()

        async def setPhysicalModel(self, request, context):
            await check(context, "setPhysicalModel")
            return empty_pb2.Empty()

        async def getLogcat(self, request, context):
            await check(context, "getLogcat")
            text = "10-17 12:00:00.000  1000  1000 I FakeAndroid: hello from the fake emulator\n"
            return ec.LogMessage(contents=text if request.start == 0 else "", start=request.start,
                                 next=request.start + (len(text) if request.start == 0 else 0))

    class Rtc(rtc_grpc.RtcServicer):
        async def RequestRtcStream(self, request, context):
            await check(context, "RequestRtcStream")
            guid = str(uuid.uuid4())
            servers = [{"urls": list(s.urls)} for s in request.ice_server_config.ice_servers]
            participant = Participant(emulator, guid, servers)
            emulator.participants[guid] = participant
            emulator.record.sessions.append(participant.info)
            asyncio.create_task(participant.start())
            return rtc.RtcStreamResponse(id=rtc.Id(guid=guid))

        async def SendJsepMessage(self, request, context):
            await check(context, "SendJsepMessage")
            guid = request.jsep_msg.id.guid
            try:
                message = json.loads(request.jsep_msg.message)
            except ValueError:
                message = {"unparsed": request.jsep_msg.message[:200]}
            emulator.record.jsep_from_browser.append({"guid": guid, "message": summarize(message)})
            participant = emulator.participants.get(guid)
            if participant:
                try:
                    await participant.handle(message)
                except Exception:
                    log.exception("JSEP message from the browser")
            return rtc.SendJsepMessageResponse()

        async def ReceiveJsepMessageStream(self, request, context):
            await check(context, "ReceiveJsepMessageStream")
            participant = emulator.participants.get(request.id.guid)
            if not participant:
                return
            while True:
                text = await participant.outbox.get()
                if text is None:
                    return
                yield rtc.ReceiveJsepMessageResponse(jsep_msg=rtc.JsepMsg(id=rtc.Id(guid=participant.guid), message=text))

    return Controller(), Rtc(), ec_grpc, rtc_grpc


async def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--proto-dir", required=True, help="generated emulator_controller_pb2 etc.")
    parser.add_argument("--gateway-python", required=True, help="Python of the gateway's virtualenv")
    parser.add_argument("--gateway-path", required=True, help="directory holding the videobridge_gateway package")
    parser.add_argument("--web-root", required=True, help="the built page (index.html, assets/)")
    parser.add_argument("--web-port", type=int, default=0)
    parser.add_argument("--config", default="{}", help="JSON: initial display, settings, options, unit, booted, load")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s fake %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aioice").setLevel(logging.WARNING)
    logging.getLogger("aiortc").setLevel(logging.WARNING)
    sys.path.insert(0, args.proto_dir)

    emulator = Emulator(args.workdir, json.loads(args.config), args)
    controller, rtc_servicer, ec_grpc, rtc_grpc = make_services(emulator)
    server = grpc.aio.server()
    ec_grpc.add_EmulatorControllerServicer_to_server(controller, server)
    rtc_grpc.add_RtcServicer_to_server(rtc_servicer, server)
    emulator.grpc_port = server.add_insecure_port("localhost:0")
    await server.start()
    if emulator.grpc_up and emulator.unit["active"] == "active":
        emulator.write_discovery()
        emulator.write_host()

    app = web.Application()

    async def get_record(request):
        return web.json_response(emulator.record_json())

    async def get_state(request):
        return web.json_response(emulator.state())

    async def post_control(request):
        await emulator.control(await request.json())
        return web.json_response(emulator.state())

    app.router.add_get("/record", get_record)
    app.router.add_get("/state", get_state)
    app.router.add_post("/control", post_control)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    control_port = site._server.sockets[0].getsockname()[1]

    tasks = [asyncio.create_task(emulator.supervise_gateway()), asyncio.create_task(emulator.watch_requests())]

    async def metrics():
        while True:
            await asyncio.sleep(1)
            emulator.write_host()
    tasks.append(asyncio.create_task(metrics()))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    # Ready once the gateway answers (it needs a discovery file to start).
    deadline = time.time() + 60
    async with ClientSession(timeout=ClientTimeout(total=2)) as session:
        while time.time() < deadline and not stop.is_set():
            if not emulator.gateway_wanted or not emulator.discovery:
                break
            try:
                async with session.get(f"http://127.0.0.1:{emulator.web_port}/api/v1/ping") as response:
                    if response.status == 204:
                        break
            except Exception:
                pass
            await asyncio.sleep(0.1)
    print("READY " + json.dumps({"web": emulator.web_port, "control": control_port, "grpc": emulator.grpc_port,
                                 "workdir": str(emulator.work)}), flush=True)

    await stop.wait()
    emulator.closing = True
    if emulator.gateway and emulator.gateway.returncode is None:
        emulator.gateway.terminate()
        try:
            await asyncio.wait_for(emulator.gateway.wait(), 5)
        except asyncio.TimeoutError:
            emulator.gateway.kill()
    for task in tasks:
        task.cancel()
    await emulator.drop_sessions("fake stopping")
    await server.stop(0)
    await runner.cleanup()


if __name__ == "__main__":
    die_with_parent()
    asyncio.run(main())
