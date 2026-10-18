# Copyright (C) 2026 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import argparse
import asyncio
import sys
import os
from pathlib import Path

# Add the proto/ directory to sys.path to allow absolute imports between sibling proto stubs
# (e.g., rtc_service_v2_pb2 importing ice_config_pb2).
proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

import aiohttp
from aiohttp import web
import grpc
import hmac
import html
import json
import logging
import secrets
import time

# Add local path to package import context to resolve generated proto modules
proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
sys.path.insert(0, proto_dir)
from .proto import emulator_controller_pb2 as ec
from .proto import emulator_controller_pb2_grpc as ec_grpc
from .proto import rtc_service_v2_pb2 as rtc
from .proto import rtc_service_v2_pb2_grpc as rtc_grpc
from .proto import ice_config_pb2 as ice
from .plugins import load_plugins, run_adb
from . import events as events_log
from . import notify
from . import logs
from .logs import log
from .http import viewers

# Records to journald and to GET /api/v1/logs (see logs.py).
logs.setup()

# Properties dictionary populated by parsing the discovery file
DISCOVERY_PROPS = {}
EMULATOR_CHANNEL = None
VIDEOBRIDGE_CHANNEL = None
ADB_PATH = "/opt/android-sdk/platform-tools/adb"
ADB_SERIAL = "emulator-5558"
# Android display size in pixels, read from the running AVD's config.ini.
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 1040
AVD_DIR = None
# Screen size changes requested from the page: the gateway writes
# "WIDTH HEIGHT DENSITY" to DISPLAY_REQUEST and a root service applies it,
# reporting progress in DISPLAY_STATUS. Empty paths disable the feature.
DISPLAY_REQUEST = ""
DISPLAY_STATUS = ""
DISPLAY_LIMITS = {"width": (240, 1440), "height": (320, 3200), "density": (80, 640)}
# What the page shows the user when something is wrong: the emulator's
# systemd unit (read with "systemctl show", no privilege needed), whether
# Android finished booting, how many viewers are connected and the load.
EMULATOR_UNIT = ""
DISCOVERY_FILE = ""
STATE_CACHE = {"time": 0.0, "value": None}
# Server metrics for the page's server panel, sampled in the background.
# Android's own figures need adb, so they are read only while a page asks
# for them (GET /api/v1/state?details=1 in the last ANDROID_WANTED_SECONDS).
METRICS = {"host": None, "emulator": None, "android": None, "android_wanted": 0.0}
METRICS_SECONDS = 2
ANDROID_METRICS_SECONDS = 5
ANDROID_WANTED_SECONDS = 30
STATE_CACHE_SECONDS = 2.0
# The gateway also serves the page, so page and API share one origin and no
# CORS is needed. Each start draws a random token, written into index.html;
# every POST must carry it, so a web page from another origin (for instance
# one open in the phone's browser while the VPN is up) cannot drive or
# reboot Android.
PAGE_TOKEN = secrets.token_urlsafe(32)
TOKEN_HEADER = "X-CloudPhone-Token"
WEB_ROOT = ""
DISPLAY_CHANGE_INTERVAL = 120.0
# Emulator settings (renderer, cores, memory) work the same way: the gateway
# writes "RENDERER CORES MEMORY_MB" to SETTINGS_REQUEST and a root service
# applies it, reporting in SETTINGS_STATUS. Changes of either kind share the
# rate limit above: each one restarts Android.
SETTINGS_REQUEST = ""
SETTINGS_STATUS = ""
RENDERERS = ("lavapipe", "swiftshader", "swangle", "software")
# Older names of the same renderers, still accepted by the emulator.
LEGACY_RENDERERS = {"swiftshader_indirect": "swiftshader", "swangle_indirect": "swangle"}
LAST_DISPLAY_CHANGE = {"time": None}
GRPC_OPTIONS = [("grpc.max_receive_message_length", 32 * 1024 * 1024)]
# When the page last asked for a change that restarts Android: a restart
# soon after it is expected, not an error.
CHANGE = {"requested": 0.0}
CHANGE_RESTART_SECONDS = 600


def parse_discovery_file(path):
    props = {}
    if not path or not os.path.exists(path):
        logging.warning(f"Discovery file not found or not specified at: {path}")
        return props
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    props[k.strip()] = v.strip()
        logging.info(f"Loaded discovery properties from {path}")
    except Exception as e:
        logging.error(f"Failed to read discovery file: {e}. Restart the emulator (systemctl restart cloudphone-emulator).")
    return props


def read_display_size(avd_dir):
    """Returns (width, height) from AVD_DIR/config.ini, or None.

    The emulator rewrites config.ini as "key = value", avdmanager writes
    "key=value"; both are accepted.
    """
    if not avd_dir:
        return None
    values = {}
    try:
        with open(os.path.join(avd_dir, "config.ini"), "r") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep:
                    values[key.strip()] = value.strip()
        return int(values["hw.lcd.width"]), int(values["hw.lcd.height"])
    except (OSError, KeyError, ValueError) as e:
        logging.warning(f"Could not read the display size from {avd_dir}: {e}")
        return None


def read_avd_config(avd_dir):
    """Returns {width, height, density} from AVD_DIR/config.ini, or {}."""
    if not avd_dir:
        return {}
    values = {}
    try:
        with open(os.path.join(avd_dir, "config.ini"), "r") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep:
                    values[key.strip()] = value.strip()
        return {
            "width": int(values["hw.lcd.width"]),
            "height": int(values["hw.lcd.height"]),
            "density": int(values.get("hw.lcd.density", "0")),
        }
    except (OSError, KeyError, ValueError):
        return {}


def json_int(value):
    """A JSON integer, never a string, float or boolean ("360" is refused)."""
    if type(value) is not int:
        raise TypeError("not an integer")
    return value


def read_settings_status():
    """Returns the state of the last emulator settings request."""
    if SETTINGS_REQUEST and os.path.exists(SETTINGS_REQUEST):
        return {"state": "pending"}
    words = (read_file(SETTINGS_STATUS) or "").split() if SETTINGS_STATUS else []
    if not words or words[0] not in ("applying", "done", "failed"):
        return {"state": "idle"}
    if words[0] == "failed":
        return {"state": "failed", "message": " ".join(words[1:])[:200]}
    result = {"state": words[0]}
    if len(words) in (4, 7):
        result.update(renderer=words[1], cores=words[2], memoryMb=words[3])
    if len(words) == 7:
        result.update(width=words[4], height=words[5], density=words[6])
    return result


def settings_limits():
    """What the page may ask for: renderers, at most every host thread, and
    the host's memory minus 2 GiB."""
    meminfo = read_meminfo(read_file("/proc/meminfo") or "")
    return {
        "renderers": list(RENDERERS),
        "maxCores": os.cpu_count() or 1,
        "maxMemoryMb": (meminfo.get("MemTotal", 0) // 1024 - 2048) // 512 * 512,
    }


async def handle_settings(request):
    """GET /api/v1/emulator-settings: the settings Android runs with, the
    allowed choices and the state of the last change."""
    cgroup = f"/sys/fs/cgroup/system.slice/{EMULATOR_UNIT}" if EMULATOR_UNIT else None
    return web.json_response({
        "canChange": bool(SETTINGS_REQUEST),
        "current": read_emulator_settings(cgroup),
        "display": read_avd_config(AVD_DIR),
        "limits": settings_limits(),
        "request": read_settings_status(),
    }, headers={"Cache-Control": "no-store"})


def change_request(refused):
    """A screen size or settings request the gateway refuses (invalid,
    disabled, one already running, too soon) is a warning record."""
    def wrap(handler):
        async def handle(request):
            response = await handler(request)
            if response.status >= 400:
                try:
                    error = json.loads(response.text).get("error", "")
                except (TypeError, ValueError, AttributeError):
                    error = str(response.status)
                log("warning", "gateway", refused, error=error)
            return response
        return handle
    return wrap


@change_request("Changement des réglages d’Android refusé : {error}")
async def handle_set_settings(request):
    """POST /api/v1/emulator-settings {renderer, cores, memoryMb[, width,
    height, density]}: asks the root service to change them, which restarts
    Android once (data is kept). The screen size is optional and all three
    of its values come together."""
    if not SETTINGS_REQUEST:
        return web.json_response({"error": "Emulator settings changes are disabled"}, status=403)
    try:
        data = await request.json()
        renderer, cores, memory = data["renderer"], json_int(data["cores"]), json_int(data["memoryMb"])
        if not isinstance(renderer, str):
            raise TypeError("renderer is not a string")
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "renderer, cores and memoryMb are required"}, status=400)
    limits = settings_limits()
    if renderer not in RENDERERS:
        return web.json_response({"error": f"renderer must be one of {', '.join(RENDERERS)}"}, status=400)
    if not 1 <= cores <= limits["maxCores"]:
        return web.json_response({"error": f"cores must be between 1 and {limits['maxCores']}"}, status=400)
    if not 2048 <= memory <= limits["maxMemoryMb"] or memory % 512:
        return web.json_response(
            {"error": f"memoryMb must be a multiple of 512 between 2048 and {limits['maxMemoryMb']}"}, status=400)
    size = ""
    given = [key for key in DISPLAY_LIMITS if data.get(key) is not None]
    if given:
        try:
            if len(given) != len(DISPLAY_LIMITS):
                raise ValueError
            wanted = {key: json_int(data[key]) for key in DISPLAY_LIMITS}
        except (ValueError, TypeError):
            return web.json_response({"error": "width, height and density go together"}, status=400)
        for key, (low, high) in DISPLAY_LIMITS.items():
            if not low <= wanted[key] <= high:
                return web.json_response({"error": f"{key} must be between {low} and {high}"}, status=400)
        if wanted["width"] % 2 or wanted["height"] % 2:
            return web.json_response({"error": "width and height must be even"}, status=400)
        size = f" {wanted['width']} {wanted['height']} {wanted['density']}"
    if read_settings_status()["state"] in ("pending", "applying") or read_display_status()["state"] in ("pending", "applying"):
        return web.json_response({"error": "A change is already in progress"}, status=409)
    since = time.time() - last_change()
    if since < DISPLAY_CHANGE_INTERVAL:
        wait = int(DISPLAY_CHANGE_INTERVAL - since) + 1
        return web.json_response({"error": f"Wait {wait} s before the next change"}, status=429)
    LAST_DISPLAY_CHANGE["time"] = time.time()
    temporary = f"{SETTINGS_REQUEST}.tmp"
    with open(temporary, "w") as f:
        f.write(f"{renderer} {cores} {memory}{size}\n")
    os.replace(temporary, SETTINGS_REQUEST)
    CHANGE["requested"] = time.time()
    log("normal", "gateway", "Changement des réglages d’Android demandé ({settings}) : Android va redémarrer",
        notify=True, settings=f"{renderer}, {cores} × CPU, {memory} MiB"
        + (f", {wanted['width']}×{wanted['height']}" if size else ""))
    return web.json_response({"status": "pending"}, status=202)


def read_display_status():
    """Returns the state of the last screen size request."""
    if DISPLAY_REQUEST and os.path.exists(DISPLAY_REQUEST):
        return {"state": "pending"}
    try:
        with open(DISPLAY_STATUS, "r") as f:
            words = f.read(256).split()
    except OSError:
        return {"state": "idle"}
    if not words:
        return {"state": "idle"}
    state = words[0] if words[0] in ("applying", "done", "failed") else "idle"
    result = {"state": state}
    if state in ("applying", "done") and len(words) == 4:
        try:
            result["width"], result["height"], result["density"] = map(int, words[1:])
        except ValueError:
            pass
    if state == "failed":
        result["message"] = " ".join(words[1:])
    return result


async def read_emulator_unit():
    """Returns the emulator unit's systemd state, or None if unknown."""
    if not EMULATOR_UNIT:
        return None
    try:
        process = await asyncio.create_subprocess_exec(
            "systemctl", "show", EMULATOR_UNIT,
            "--property=ActiveState,SubState,NRestarts,Result",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
    except (OSError, asyncio.TimeoutError):
        return None
    values = dict(
        line.split("=", 1) for line in output.decode(errors="replace").splitlines() if "=" in line
    )
    return {
        "active": values.get("ActiveState", "unknown"),
        "sub": values.get("SubState", "unknown"),
        "result": values.get("Result", "unknown"),
        "restarts": int(values["NRestarts"]) if values.get("NRestarts", "").isdigit() else None,
    }


async def read_android_booted():
    """True when Android finished booting, False while booting, None if the
    emulator does not answer on gRPC."""
    if not EMULATOR_CHANNEL:
        return None
    try:
        stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
        status = await stub.getStatus(
            ec.google_dot_protobuf_dot_empty__pb2.Empty(),
            metadata=get_emulator_metadata(),
            timeout=2,
        )
        return bool(status.booted)
    except Exception:
        return None


def physical_cores():
    """Physical cores (with Hyper-Threading, two threads share each one)."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            text = f.read()
    except OSError:
        return None
    cores = set()
    for chunk in text.split("\n\n"):
        fields = {}
        for line in chunk.splitlines():
            name, _, value = line.partition(":")
            fields[name.strip()] = value.strip()
        if "core id" in fields:
            cores.add((fields.get("physical id"), fields["core id"]))
    return len(cores) or None


def read_load():
    try:
        with open("/proc/loadavg", "r") as f:
            one, five = f.read().split()[:2]
        return {"one": float(one), "five": float(five), "cpus": os.cpu_count() or 1, "cores": physical_cores()}
    except (OSError, ValueError):
        return None


def read_proc_stat():
    """(busy, total) jiffies of all host CPUs."""
    with open("/proc/stat", "r") as f:
        values = [int(v) for v in f.readline().split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values) - idle, sum(values)


def read_meminfo(text):
    """kB values of a /proc/meminfo text, by name."""
    values = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if rest.split():
            try:
                values[name] = int(rest.split()[0])
            except ValueError:
                pass
    return values


def read_file(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except OSError:
        return None


def memory_summary(values):
    """MiB figures from meminfo values."""
    mib = lambda name: round(values[name] / 1024) if name in values else None
    return {
        "total": mib("MemTotal"), "available": mib("MemAvailable"),
        "swapTotal": mib("SwapTotal"),
        "swapUsed": mib("SwapTotal") - mib("SwapFree") if "SwapTotal" in values and "SwapFree" in values else None,
    }


async def read_android_metrics():
    """Android's memory and the frame rate of the top layer since the last
    call (SurfaceFlinger timestats, enabled on first use)."""
    script = (
        "cat /proc/meminfo; echo ==TIMESTATS==;"
        " dumpsys SurfaceFlinger --timestats -enable >/dev/null;"
        " dumpsys SurfaceFlinger --timestats -dump -maxlayers 1;"
        " dumpsys SurfaceFlinger --timestats -clear >/dev/null"
    )
    process = await asyncio.create_subprocess_exec(
        ADB_PATH, "-s", ADB_SERIAL, "shell", script,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        output, errors = await asyncio.wait_for(process.communicate(), timeout=10)
    except asyncio.TimeoutError:
        process.kill()
        return None
    logs.adb_result(process.returncode, errors.decode(errors="replace"))
    meminfo, _, timestats = output.decode(errors="replace").partition("==TIMESTATS==")
    layer = fps = None
    for line in timestats.splitlines():
        name, _, value = line.strip().partition(" = ")
        if name == "layerName" and layer is None:
            # "<id> SurfaceView[com.example/...Activity](BLAST)#12": the package.
            layer = value.split("[", 1)[-1].split("/", 1)[0].split("]", 1)[0] if "[" in value else value
        elif name == "averageFPS" and layer is not None and fps is None:
            try:
                fps = round(float(value), 1)
            except ValueError:
                pass
    return {"memory": memory_summary(read_meminfo(meminfo)), "app": layer, "fps": fps}


def read_emulator_settings(cgroup):
    """Renderer, cores and memory the running emulator was started with,
    from its command line (not the configuration, which may have changed
    since)."""
    procs = read_file(f"{cgroup}/cgroup.procs") if cgroup else None
    for pid in (procs or "").split():
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                args = f.read().decode(errors="replace").split("\0")
        except OSError:
            continue
        if "qemu-system" not in args[0]:
            continue
        option = lambda name: args[args.index(name) + 1] if name in args[:-1] else None
        renderer = option("-gpu")
        return {"renderer": LEGACY_RENDERERS.get(renderer, renderer), "cores": option("-cores"),
                "memoryMb": option("-memory")}
    return None


async def sample_metrics():
    """Host CPU and memory, the emulator unit's CPU and memory (its cgroup),
    and Android's figures while a page wants them."""
    loop = asyncio.get_running_loop()
    cgroup = f"/sys/fs/cgroup/system.slice/{EMULATOR_UNIT}" if EMULATOR_UNIT else None
    previous = None
    last_android = 0.0
    while True:
        try:
            now = loop.time()
            busy, total = read_proc_stat()
            stat = read_file(f"{cgroup}/cpu.stat") if cgroup else None
            usage = None
            if stat:
                usage = dict(line.split() for line in stat.splitlines() if len(line.split()) == 2).get("usage_usec")
            usage = int(usage) if usage else None
            cpus = os.cpu_count() or 1
            if previous:
                p_now, p_busy, p_total, p_usage = previous
                governor = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
                mhz = [float(line.split(":")[1]) for line in (read_file("/proc/cpuinfo") or "").splitlines()
                       if line.startswith("cpu MHz")]
                METRICS["host"] = {
                    "cpu": round(100 * (busy - p_busy) / max(1, total - p_total)),
                    "cpus": cpus,
                    "governor": governor.strip() if governor else None,
                    "mhz": round(sum(mhz) / len(mhz)) if mhz else None,
                    "memory": memory_summary(read_meminfo(read_file("/proc/meminfo") or "")),
                }
                memory = read_file(f"{cgroup}/memory.current") if cgroup else None
                METRICS["emulator"] = {
                    "settings": read_emulator_settings(cgroup),
                    # Percent of one core, like top: 400 = four cores busy.
                    "cpu": round((usage - p_usage) / 1e4 / (now - p_now)) if usage is not None and p_usage is not None else None,
                    "memory": round(int(memory) / 1048576) if memory and memory.strip().isdigit() else None,
                }
            previous = (now, busy, total, usage)
            if now - METRICS["android_wanted"] < ANDROID_WANTED_SECONDS and now - last_android >= ANDROID_METRICS_SECONDS:
                last_android = now
                METRICS["android"] = await read_android_metrics()
        except Exception as error:
            logging.warning("Metrics sampling failed: %s", error)
        await asyncio.sleep(METRICS_SECONDS)


async def handle_notify(request):
    """GET /api/v1/notify: phone alerts through ntfy.sh, {available,
    enabled, topic, url} (see notify.py)."""
    return web.json_response(notify.describe(), headers={"Cache-Control": "no-store"})


async def handle_set_notify(request):
    """POST /api/v1/notify {enabled[, newTopic]}: turns alerts on or off;
    the first time (or with newTopic) it makes the random topic."""
    if not notify.STATE["file"]:
        return web.json_response({"error": "Alerts are not set up on this server"}, status=409)
    try:
        data = await request.json()
        enabled, new_topic = data["enabled"], data.get("newTopic", False)
        if not isinstance(enabled, bool) or not isinstance(new_topic, bool):
            raise TypeError("not booleans")
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "Expected {enabled: true|false[, newTopic: true]}"}, status=400)
    try:
        state = notify.configure(enabled, new_topic)
    except OSError as e:
        logging.warning(f"Alerts not saved: {e!r}")
        return web.json_response({"error": "Could not save the setting"}, status=500)
    logging.info(f"Phone alerts {'on' if enabled else 'off'} (requested by {request.remote})")
    return web.json_response(state)


async def handle_test_notify(request):
    """POST /api/v1/notify/test: one test alert."""
    if not notify.STATE["topic"]:
        return web.json_response({"error": "No topic yet: turn alerts on first"}, status=409)
    sent = await notify.send("Test : les alertes du Cloud Phone arrivent bien", force=True)
    return web.json_response({"sent": sent}, status=200 if sent else 502)


async def watch_events():
    """Every minute, Android's new events (an app crashed, froze or was
    stopped while in sight; Android restarted) become log records, and
    phone alerts when they are on."""
    seen, alerted = {}, {}
    while True:
        await asyncio.sleep(60)
        try:
            found = await read_events()
        except Exception as e:
            logging.warning(f"Android events not read: {e!r}")
            continue
        if not found["android"]:
            continue
        first = seen.get("time") is None
        fresh = notify.new_events(found["events"], seen, kinds=EVENT_RECORDS)
        if first:
            # Before this gateway started: shown on the page, not journaled again.
            for event in reversed(found["events"]):
                if event["kind"] in EVENT_RECORDS and event["kind"] != "android_boot" and event["time"] < GATEWAY_STARTED:
                    level, text, params = event_record(event)
                    logs.remember(level, "emulator", text, event["time"], **params)
        for event in fresh[:10]:
            level, text, params = event_record(event)
            log(level, "emulator", text, notify=event["kind"] == "android_boot", **params)
        if not notify.STATE["enabled"]:
            alerted.clear()
            continue
        for event in notify.new_events(found["events"], alerted)[:5]:
            await notify.send(notify.sentence(event))


def change_expected():
    """True while Android may restart because the page asked for it: a
    request in the last minutes, one pending or applying, or one finished
    a moment ago (this gateway may have been restarted by it)."""
    if time.time() - CHANGE["requested"] < CHANGE_RESTART_SECONDS:
        return True
    for status, path in ((read_display_status(), DISPLAY_STATUS), (read_settings_status(), SETTINGS_STATUS)):
        if status["state"] in ("pending", "applying"):
            return True
        if status["state"] in ("done", "failed") and time.time() - status_time(path) < CHANGE_RESTART_SECONDS:
            return True
    return False


# Android's events (read_events) as records: level, text, params. Errors
# say what to do next.
EVENT_RECORDS = ("crash", "anr", "killed", "low_memory", "android_boot")


def event_record(event):
    app = event.get("app") or "?"
    reason = event.get("reason") or ""
    kind = event["kind"]
    if kind == "crash":
        return ("error", "{app} a planté ({reason}). Relancez l’appli ; si elle replante, "
                "regardez la mémoire d’Android (Informations → Serveur).", {"app": app, "reason": reason or "?"})
    if kind == "anr":
        return "warning", "{app} ne répondait plus (ANR)", {"app": app}
    if kind == "killed":
        return "warning", "{app} arrêté par Android ({reason})", {"app": app, "reason": reason or "?"}
    if kind == "low_memory":
        return "warning", "Mémoire d’Android insuffisante", {}
    # android_boot: expected after a change the page asked for.
    if change_expected():
        return "normal", "Android a redémarré", {}
    return ("error", "Android a redémarré sans qu’on le demande. Si cela se répète, regardez la mémoire "
            "d’Android (Informations → Serveur) et journalctl -u cloudphone-emulator sur le serveur.", {})


# What watch_health saw at its last look.
HEALTH = {"unit": None, "booted": "unknown", "booting_since": None, "slow_boot": False, "lost": 0,
          "display": None, "settings": None}
HEALTH_SECONDS = 3
SLOW_BOOT_SECONDS = 180


def unit_record(unit):
    """The record for the emulator unit's new state, or None."""
    active, sub = unit["active"], unit["sub"]
    if active == "failed":
        return ("error", "Android s’est arrêté sur une erreur ({result}). Il ne redémarre pas tout seul : "
                "il faut le relancer sur le serveur.", {"result": unit.get("result", "?")})
    if active == "activating" and sub == "auto-restart":
        return ("error", "Android a planté ({result}) : redémarrage automatique. S’il ne revient pas d’ici "
                "deux minutes, relancez-le sur le serveur.", {"result": unit.get("result", "?")})
    if active in ("inactive", "deactivating"):
        if change_expected():
            return "normal", "Android s’arrête pour appliquer le changement", {}
        return "error", "Android est arrêté. Il faut le démarrer sur le serveur.", {}
    if active == "active":
        return "normal", "Le service Android a démarré", {}
    return None


def change_status_record(kind, status):
    """The record for a screen size or settings request's new status."""
    what = "de résolution" if kind == "display" else "des réglages d’Android"
    state = status.get("state")
    if state == "applying":
        return "normal", f"Changement {what} : Android redémarre…", {}, False
    if state == "done":
        return "normal", f"Changement {what} appliqué", {}, True
    if state == "failed":
        unit = "cloudphone-display" if kind == "display" else "cloudphone-settings"
        return ("error", f"Échec du changement {what} : {{message}}. Réessayez ; si cela échoue encore, "
                f"lisez journalctl -u {unit} sur le serveur.", {"message": status.get("message") or "?"}, True)
    return None


def status_time(path):
    try:
        return os.stat(path).st_mtime
    except (OSError, TypeError):
        return 0.0


def last_change():
    """When the last screen or emulator change was asked for or done (Unix
    time). A change restarts the gateway with the emulator, so this process's
    own memory is not enough: the request and status files keep their time."""
    files = (DISPLAY_REQUEST, DISPLAY_STATUS, SETTINGS_REQUEST, SETTINGS_STATUS)
    return max(LAST_DISPLAY_CHANGE["time"] or 0.0, *(status_time(path) for path in files))


async def watch_health():
    """Every few seconds, the emulator unit, Android's boot and the change
    requests: each change of state that matters is a record."""
    while True:
        try:
            unit, booted = await asyncio.gather(read_emulator_unit(), read_android_booted())
            check_health(unit, booted, read_display_status(), read_settings_status())
        except Exception as e:
            logging.warning(f"Health check failed: {e!r}")
        await asyncio.sleep(HEALTH_SECONDS)


def check_health(unit, booted, display, settings):
    now = time.time()
    first = HEALTH["unit"] is None and HEALTH["booted"] == "unknown"
    if unit:
        before = HEALTH["unit"]
        changed = before is None or (before["active"], before["sub"]) != (unit["active"], unit["sub"])
        missed = (before is not None and unit.get("restarts") is not None and before.get("restarts") is not None
                  and unit["restarts"] > before["restarts"] and not changed)
        if missed:
            # Restarted between two looks.
            log("error", "emulator", "Android a planté et a été relancé automatiquement. S’il ne revient pas "
                "d’ici deux minutes, relancez-le sur le serveur.", notify=True)
        elif changed:
            record = unit_record(unit)
            # At the gateway's start only what is wrong is worth a record.
            if record and not (before is None and record[0] == "normal"):
                level, text, params = record
                log(level, "emulator", text, notify=level == "error", **params)
        HEALTH["unit"] = unit
    if booted != HEALTH["booted"]:
        if booted is True and HEALTH["booted"] in (False, None):
            log("normal", "emulator", "Android a démarré", notify=True)
        elif booted is False:
            HEALTH["booting_since"] = now
        HEALTH["booted"] = booted
        HEALTH["slow_boot"] = False
        HEALTH["lost"] = 0
    if booted is False and not HEALTH["slow_boot"] and HEALTH["booting_since"] \
            and now - HEALTH["booting_since"] > SLOW_BOOT_SECONDS:
        HEALTH["slow_boot"] = True
        log("warning", "emulator", "Android met longtemps à démarrer (plus de {minutes} minutes)",
            minutes=SLOW_BOOT_SECONDS // 60)
    # gRPC silent while the unit runs: after a few looks, an error.
    if booted is None and unit and unit["active"] == "active" and not first:
        HEALTH["lost"] += 1
        if HEALTH["lost"] == 4:
            log("error", "emulator", "Le serveur ne joint plus Android (gRPC). S’il ne revient pas d’ici une "
                "minute, relancez Android sur le serveur.", notify=True)
    for kind, status, path in (("display", display, DISPLAY_STATUS), ("settings", settings, SETTINGS_STATUS)):
        key = (status.get("state"), status.get("message"), status.get("width"))
        before = HEALTH[kind]
        HEALTH[kind] = key
        if before == key or status.get("state") in ("idle", "pending", None):
            continue
        # At the gateway's start, a status written just before it (the
        # change restarted Android, then the gateway) is still news.
        if before is None and now - status_time(path) > 120:
            continue
        record = change_status_record(kind, status)
        if record:
            level, text, params, alert = record
            log(level, "gateway", text, notify=alert, **params)


def forget_state():
    """The next GET /api/v1/state reads everything again."""
    STATE_CACHE["value"] = None


async def handle_state(request):
    """
    GET /api/v1/state: what the page needs to explain a problem to the user.
    Cached for a couple of seconds, as every open page polls it; "kicked"
    is per viewer (?viewer=).
    """
    loop = asyncio.get_running_loop()
    if STATE_CACHE["value"] is None or loop.time() - STATE_CACHE["time"] > STATE_CACHE_SECONDS:
        unit, booted = await asyncio.gather(read_emulator_unit(), read_android_booted())
        STATE_CACHE["value"] = {
            "emulator": unit,
            "android": {"booted": booted},
            "viewers": viewers.VIEWERS.count,
            "load": read_load(),
            "display": read_display_status(),
            "settings": read_settings_status(),
        }
        STATE_CACHE["time"] = loop.time()
    value = {**STATE_CACHE["value"], "kicked": viewers.kicked(request)}
    if request.query.get("details") == "1":
        METRICS["android_wanted"] = loop.time()
        value["metrics"] = {key: METRICS[key] for key in ("host", "emulator", "android")}
    return web.json_response(value, headers={"Cache-Control": "no-store"})


# The Events list (GET /api/v1/events): read on demand, cached a little.
EVENTS_CACHE = {"time": 0.0, "value": None, "lock": None}
EVENTS_CACHE_SECONDS = 10.0
GATEWAY_STARTED = time.time()


async def read_unit_start():
    """The emulator unit's last start as an emulator_start event, or None."""
    if not EMULATOR_UNIT:
        return None
    boot_time = events_log.host_boot_time(read_file("/proc/stat") or "")
    try:
        process = await asyncio.create_subprocess_exec(
            "systemctl", "show", EMULATOR_UNIT,
            "--property=ExecMainStartTimestampMonotonic,NRestarts,Result",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
    except (OSError, asyncio.TimeoutError):
        return None
    return events_log.parse_unit(output.decode(errors="replace"), boot_time, "emulator_start")


async def log_start():
    """The gateway's start, and an emulator restart just before it: the
    gateway restarts to follow the emulator, so the previous gateway's
    records of a crash are only in the journal."""
    log("normal", "gateway", "La passerelle a démarré", notify=True)
    unit = await read_unit_start()
    if unit and time.time() - unit["time"] < 180 and unit.get("reason") and not change_expected():
        log("error", "emulator", "Android a redémarré après un arrêt anormal ({result}, {restarts} redémarrages "
            "automatiques). S’il ne revient pas d’ici deux minutes, relancez-le sur le serveur.",
            notify=True, result=unit["reason"], restarts=unit.get("restarts") or 0)


async def read_events():
    found = [{"time": GATEWAY_STARTED, "kind": "gateway_start", "app": None, "reason": None}]
    unit = await read_unit_start()
    if unit:
        found.append(unit)
    code, uptime = await plugin_adb("shell", "cat", "/proc/uptime", timeout=5)
    if code == 0 and uptime.split():
        try:
            found.append({"time": time.time() - float(uptime.split()[0]), "kind": "android_boot",
                          "app": None, "reason": None})
        except ValueError:
            pass
    code, logcat = await plugin_adb("logcat", "-d", "-v", "epoch", "-b", "events,crash", timeout=10)
    if code == 0:
        found.extend(events_log.parse_logcat(logcat))
    found.sort(key=lambda event: event["time"], reverse=True)
    return {"events": found[:100], "android": code == 0}


async def handle_events(request):
    """
    GET /api/v1/events: what happened to Android and the server, newest
    first (see events.py).
    """
    if EVENTS_CACHE["lock"] is None:
        EVENTS_CACHE["lock"] = asyncio.Lock()
    loop = asyncio.get_running_loop()
    async with EVENTS_CACHE["lock"]:
        if EVENTS_CACHE["value"] is None or loop.time() - EVENTS_CACHE["time"] > EVENTS_CACHE_SECONDS:
            EVENTS_CACHE["value"] = await read_events()
            EVENTS_CACHE["time"] = loop.time()
    return web.json_response(EVENTS_CACHE["value"], headers={"Cache-Control": "no-store"})


async def handle_logs(request):
    """
    GET /api/v1/logs?since=CURSOR: {cursor, records}, the gateway's log
    records after CURSOR, oldest first (see logs.py); all that are kept
    without a cursor or with one from an earlier gateway process.
    """
    return web.json_response(logs.since(request.query.get("since", "")[:64]),
                             headers={"Cache-Control": "no-store"})


async def read_screenshot():
    """Android's screen as (width, height, RGB888 bytes), or None."""
    if not EMULATOR_CHANNEL:
        return None
    stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
    try:
        image = await stub.getScreenshot(
            ec.ImageFormat(format=ec.ImageFormat.RGB888),
            metadata=get_emulator_metadata(),
            timeout=3,
        )
    except grpc.RpcError as e:
        logging.debug(f"No screenshot: {e!r}")
        return None
    width, height = image.format.width, image.format.height
    if not width or not height or len(image.image) < width * height * 3:
        return None
    return width, height, image.image


async def plugin_adb(*args, timeout=10):
    return await run_adb(ADB_PATH, ADB_SERIAL, *args, timeout=timeout)


async def watch_discovery_file():
    """
    The emulator writes a new discovery file (new pid, new gRPC token) each
    time it starts. When ours disappears and another one appears, exit so
    that systemd restarts the gateway on the new emulator instead of
    serving a stale connection.
    """
    if not DISCOVERY_FILE:
        return
    directory = os.path.dirname(DISCOVERY_FILE)
    while True:
        await asyncio.sleep(5)
        if os.path.exists(DISCOVERY_FILE):
            continue
        try:
            others = [name for name in os.listdir(directory) if name.startswith("pid_")]
        except OSError:
            others = []
        if others:
            log("warning", "gateway", "L’émulateur a redémarré : la passerelle redémarre pour le suivre",
                notify=True)
            logging.shutdown()
            os._exit(75)


async def handle_display(request):
    """
    GET /api/v1/display: the Android screen size the gateway works with, the
    one in config.ini (current even before the gateway restarts) and the
    state of the last change request.
    """
    return web.json_response(
        {
            "running": {"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT},
            "configured": read_avd_config(AVD_DIR),
            "request": read_display_status(),
            "canChange": bool(DISPLAY_REQUEST),
            "limits": DISPLAY_LIMITS,
        },
        headers={"Cache-Control": "no-store"},
    )


@change_request("Changement de résolution refusé : {error}")
async def handle_set_display(request):
    """
    POST /api/v1/display {width, height, density}: asks the root service to
    change Android's screen size, which reboots Android (data is kept).
    """
    if not DISPLAY_REQUEST:
        return web.json_response({"error": "Screen size changes are disabled"}, status=403)
    try:
        data = await request.json()
        wanted = {key: json_int(data[key]) for key in DISPLAY_LIMITS}
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "width, height and density are required"}, status=400)
    for key, (low, high) in DISPLAY_LIMITS.items():
        if not low <= wanted[key] <= high:
            return web.json_response({"error": f"{key} must be between {low} and {high}"}, status=400)
    if wanted["width"] % 2 or wanted["height"] % 2:
        return web.json_response({"error": "width and height must be even"}, status=400)
    if read_display_status()["state"] in ("pending", "applying") or read_settings_status()["state"] in ("pending", "applying"):
        return web.json_response({"error": "A change is already in progress"}, status=409)
    since = time.time() - last_change()
    if since < DISPLAY_CHANGE_INTERVAL:
        wait = int(DISPLAY_CHANGE_INTERVAL - since) + 1
        return web.json_response({"error": f"Wait {wait} s before the next change"}, status=429)
    LAST_DISPLAY_CHANGE["time"] = time.time()
    temporary = f"{DISPLAY_REQUEST}.tmp"
    with open(temporary, "w") as f:
        f.write(f"{wanted['width']} {wanted['height']} {wanted['density']}\n")
    os.replace(temporary, DISPLAY_REQUEST)
    CHANGE["requested"] = time.time()
    log("normal", "gateway", "Changement de résolution demandé : Android va redémarrer en {size}",
        notify=True, size=f"{wanted['width']}×{wanted['height']}")
    return web.json_response({"status": "pending"}, status=202)


def get_emulator_metadata():
    token = DISCOVERY_PROPS.get("grpc.token", "")
    if token:
        return [("authorization", f"Bearer {token}")]
    return []


def get_videobridge_metadata(token_arg):
    if token_arg:
        return [("authorization", f"Bearer {token_arg}")]
    return []


async def handle_ping(request):
    """
    GET /api/v1/ping
    Answers immediately, without contacting the emulator, so the page can
    measure the network round-trip time.
    """
    return web.Response(status=204, headers={"Cache-Control": "no-store"})


async def handle_status(request):
    """
    GET /api/v1/emulator/status
    Returns the hardware configurations and status of the emulator.
    """
    if not EMULATOR_CHANNEL:
        return web.json_response({"error": "No channel to emulator"}, status=503)

    try:
        stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
        metadata = get_emulator_metadata()
        # Call getStatus
        status_res = await stub.getStatus(
            ec.google_dot_protobuf_dot_empty__pb2.Empty(), metadata=metadata
        )

        # Convert platformConfig map to a regular python dictionary
        platform_config = dict(status_res.platformConfig)
        # Current emulator builds may omit LCD dimensions from getStatus.
        # The browser needs the real dimensions to scale touch coordinates.
        platform_config.setdefault("hw.lcd.width", str(DISPLAY_WIDTH))
        platform_config.setdefault("hw.lcd.height", str(DISPLAY_HEIGHT))

        # Extract vmConfig details
        vm_config = {
            "hypervisorType": status_res.vmConfig.hypervisorType if status_res.vmConfig else "unknown",
            "numberOfCpuCores": status_res.vmConfig.numberOfCpuCores if status_res.vmConfig else 0,
            "ramSizeBytes": status_res.vmConfig.ramSizeBytes if status_res.vmConfig else 0,
        }

        response_data = {
            "version": status_res.version,
            "uptime": status_res.uptime,
            "booted": status_res.booted,
            "hardwareConfig": platform_config,  # Deprecated, kept for backwards compatibility
            "platformConfig": platform_config,  # New preferred field
            "vmConfig": vm_config,
        }
        return web.json_response(response_data)
    except Exception as e:
        logging.error(f"Error fetching status from emulator: {e}. Wait for Android to start; if it does not, restart it on the server.")
        return web.json_response({"error": str(e)}, status=500)


async def handle_gps(request):
    """
    POST /api/v1/emulator/gps
    Updates the mock geolocation of the emulator.
    """
    if not EMULATOR_CHANNEL:
        return web.json_response({"error": "No channel to emulator"}, status=503)

    try:
        data = await request.json()
        latitude = float(data.get("latitude", 0.0))
        longitude = float(data.get("longitude", 0.0))
        altitude = float(data.get("altitude", 0.0))

        stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
        metadata = get_emulator_metadata()

        # Send POSITION physical model update
        req = ec.PhysicalModelValue(
            target=ec.PhysicalModelValue.PhysicalType.POSITION,
            value=ec.ParameterValue(data=[longitude, latitude, altitude]),
        )
        await stub.setPhysicalModel(req, metadata=metadata)
        return web.json_response({"status": "success"})
    except Exception as e:
        logging.error(f"Error setting GPS on emulator: {e}. Retry once Android has started.")
        return web.json_response({"error": str(e)}, status=500)


async def handle_logcat(request):
    """
    GET /api/v1/emulator/logcat
    Fetches a chunk of logs from logcat using polling-friendly start/next structure.
    """
    if not EMULATOR_CHANNEL:
        return web.json_response({"error": "No channel to emulator"}, status=503)

    try:
        start_offset = int(request.query.get("start", "0"))
        stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
        metadata = get_emulator_metadata()

        req = ec.LogMessage(start=start_offset)
        res = await stub.getLogcat(req, metadata=metadata)
        return web.json_response({"next": res.next, "contents": res.contents})
    except Exception as e:
        logging.error(f"Error fetching logcat from emulator: {e}. Retry once Android has started.")
        return web.json_response({"error": str(e)}, status=500)


async def handle_key(request):
    """POST /api/v1/emulator/key forwards one Android hardware key."""
    try:
        data = await request.json()
        key = data.get("key", "")
        supported_keys = {
            "GoBack", "GoHome", "AppSwitch", "Power",
            "AudioVolumeUp", "AudioVolumeDown",
        }
        if key not in supported_keys:
            return web.json_response({"error": "unsupported key"}, status=400)
        keycodes = {
            "GoBack": "BACK",
            "GoHome": "HOME",
            "AppSwitch": "APP_SWITCH",
            "Power": "POWER",
            "AudioVolumeUp": "VOLUME_UP",
            "AudioVolumeDown": "VOLUME_DOWN",
        }
        process = await asyncio.create_subprocess_exec(
            ADB_PATH,
            "-s", ADB_SERIAL, "shell", "input", "keyevent", keycodes[key],
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        logs.adb_result(process.returncode, stderr.decode(errors="replace"))
        if process.returncode:
            raise RuntimeError(stderr.decode(errors="replace").strip())
        return web.json_response({"status": "success"})
    except Exception as e:
        logging.error(f"Error sending key: {e}. Check Android in Information → Server; if adb stays offline, "
                      "restart Android on the server.")
        return web.json_response({"error": str(e)}, status=500)


async def handle_touch(request):
    """POST /api/v1/emulator/touch forwards one touch contact update."""
    try:
        data = await request.json()
        x = max(0, min(DISPLAY_WIDTH - 1, int(data.get("x", 0))))
        y = max(0, min(DISPLAY_HEIGHT - 1, int(data.get("y", 0))))
        pressed = bool(data.get("pressed", False))
        contact = ec.Touch(
            x=x,
            y=y,
            identifier=0,
            pressure=1024 if pressed else 0,
            touch_major=8 if pressed else 0,
            touch_minor=8 if pressed else 0,
        )
        stub = ec_grpc.EmulatorControllerStub(EMULATOR_CHANNEL)
        await stub.sendTouch(
            ec.TouchEvent(touches=[contact], display=0),
            metadata=get_emulator_metadata(),
        )
        return web.json_response({"status": "success"})
    except Exception as e:
        logging.error(f"Error sending touch: {e}. Reload the video (↻); if touches still fail, restart Android on the server.")
        return web.json_response({"error": str(e)}, status=500)


async def handle_websocket_jsep(request):
    """
    GET /api/v1/emulator/ws-jsep (WebSocket Upgrade)
    Handles WebRTC signaling connection and interfaces with Video Bridge over rtc2.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logging.debug("WebSocket connection opened for JSEP signaling.")
    viewer = viewers.viewer_of(request)
    if await viewers.refuse_if_kicked(ws, viewer):
        return ws

    if not VIDEOBRIDGE_CHANNEL:
        logging.error("No channel to Video Bridge. Restart the gateway (systemctl restart cloudphone-gateway).")
        await ws.close(
            code=web.WSCloseCode.INTERNAL_ERROR, message=b"Video Bridge offline"
        )
        return ws

    rtc_stub = rtc_grpc.RtcStub(VIDEOBRIDGE_CHANNEL)
    bridge_metadata = get_videobridge_metadata(request.app["videobridge_token"])
    guid = None
    stream_task = None
    bye_forwarded = False
    viewers.joined(ws, viewer)

    try:
        # 1. Build default ICE configuration using public STUN server
        ice_config = ice.IceServerConfig()
        stun_server = ice_config.ice_servers.add()
        stun_server.urls.append("stun:stun.l.google.com:19302")

        # 2. Initialize signaling session with Video Bridge
        stream_req = rtc.RtcStreamRequest(ice_server_config=ice_config)
        # Connect to retrieve stream credentials
        response = await rtc_stub.RequestRtcStream(stream_req, metadata=bridge_metadata)
        guid = response.id.guid
        logging.debug(
            f"Initialized WebRTC stream session with Video Bridge. Connection ID: {guid}"
        )

        # The emulator sends the authoritative start message on its JSEP
        # stream. Sending a second synthetic start creates two peer
        # connections and breaks both video input and hardware controls.

        # 3. Spawn background streaming reader to forward gRPC messages -> WebSocket
        async def stream_to_client():
            logging.debug(
                f"Starting stream_to_client background task for connection: {guid}"
            )
            try:
                reader_req = rtc.ReceiveJsepMessageRequest(id=rtc.Id(guid=guid))
                logging.debug(
                    f"Subscribing to JSEP message stream from Video Bridge for connection: {guid}"
                )
                async for response_msg in rtc_stub.ReceiveJsepMessageStream(
                    reader_req, metadata=bridge_metadata
                ):
                    msg_text = response_msg.jsep_msg.message
                    logging.debug(
                        f"Received JSEP message from Video Bridge gRPC stream: '{msg_text}'"
                    )
                    if not msg_text:
                        logging.debug(
                            "Received empty JSEP message from Video Bridge. Stopping stream reader."
                        )
                        break
                    parsed_jsep = json.loads(msg_text)
                    logging.debug(f"Forwarding JSEP message to browser: {parsed_jsep}")

                    # If it's an SDP offer/answer, or an ICE candidate message
                    await ws.send_json(parsed_jsep)
                logging.debug("Video Bridge JSEP stream finished cleanly.")
            except asyncio.CancelledError:
                logging.debug(f"stream_to_client task cancelled for connection: {guid}")
            except Exception as ex:
                logging.exception("Error in stream_to_client reader loop. Reload the video (↻) if it stopped:")

        stream_task = asyncio.create_task(stream_to_client())

        # 4. Handle incoming browser messages and route -> Video Bridge
        async for ws_msg in ws:
            if ws_msg.type == web.WSMsgType.TEXT:
                client_data = ws_msg.json()
                logging.debug(
                    f"Received message from Client -> Video Bridge: {client_data}"
                )

                send_req = rtc.SendJsepMessageRequest()
                send_req.jsep_msg.id.guid = guid
                send_req.jsep_msg.message = json.dumps(client_data)

                await rtc_stub.SendJsepMessage(send_req, metadata=bridge_metadata)
                logging.debug(
                    f"Successfully forwarded JSEP message to Video Bridge for connection: {guid}"
                )

                if "bye" in client_data:
                    bye_forwarded = True
                    logging.debug(
                        f"Received 'bye' signal from client. Tearing down connection: {guid}"
                    )
                    break
            elif ws_msg.type == web.WSMsgType.ERROR:
                logging.error(f"WebSocket encountered error: {ws.exception()}. Reload the video (↻) if it stopped.")

    except Exception as e:
        logging.exception("Error in WebSocket session handler. Reload the video (↻) if it stopped:")
    finally:
        viewers.left(ws, viewer)
        logging.debug(f"Closing signaling WebSocket session for ID: {guid}")
        # Browsers do not always get a chance to send a final WebSocket frame
        # when a tab is suspended or killed. Explicitly tear down the emulator
        # participant so that the next viewer does not compete with an orphaned
        # WebRTC session.
        if guid and not bye_forwarded:
            try:
                bye_req = rtc.SendJsepMessageRequest()
                bye_req.jsep_msg.id.guid = guid
                bye_req.jsep_msg.message = json.dumps({"bye": True})
                await rtc_stub.SendJsepMessage(bye_req, metadata=bridge_metadata)
                logging.debug(
                    f"Forwarded teardown for abandoned connection: {guid}"
                )
            except Exception as e:
                logging.warning(f"Failed to tear down abandoned connection {guid}: {e!r}")
        if stream_task:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
        await ws.close()
    return ws


def same_origin(request):
    """True when the request has no Origin (not sent by a cross-origin page)
    or when its Origin is this server."""
    origin = request.headers.get("Origin")
    if origin is None:
        return True
    return origin in (f"http://{request.host}", f"https://{request.host}")


@web.middleware
async def guard_middleware(request, handler):
    if not same_origin(request):
        logging.warning(f"Refused {request.method} {request.path} from origin {request.headers.get('Origin')!r}")
        return web.json_response({"error": "Cross-origin requests are not accepted"}, status=403)
    if request.method not in ("GET", "HEAD"):
        token = request.headers.get(TOKEN_HEADER, "")
        if not hmac.compare_digest(token, PAGE_TOKEN):
            return web.json_response({"error": "Missing or invalid page token: reload the page"}, status=403)
    return await handler(request)


async def handle_index(request):
    """GET /: the page, with this start's token. Never cached, so a reload
    always gets the current token and the current bundle names."""
    try:
        with open(os.path.join(WEB_ROOT, "index.html"), "r", encoding="utf-8") as f:
            page = f.read()
    except OSError:
        return web.Response(status=503, text="The web page is not installed.")
    meta = f'<meta name="cloudphone-token" content="{html.escape(PAGE_TOKEN)}">'
    page = page.replace("<head>", f"<head>\n    {meta}", 1)
    return web.Response(
        text=page, content_type="text/html",
        headers={"Cache-Control": "no-cache", "Referrer-Policy": "no-referrer"},
    )


@web.middleware
async def cache_middleware(request, handler):
    response = await handler(request)
    # Bundles under /assets have content hashes in their names.
    if request.path.startswith("/assets/") and response.status == 200:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    # API answers are live state: never cached, including the upstream
    # helpers that set nothing themselves.
    elif (request.path.startswith("/api/") and not response.prepared
          and "Cache-Control" not in response.headers):
        response.headers["Cache-Control"] = "no-store"
    return response


def init_app(videobridge_token, plugins_dir="", plugin_data=""):
    app = web.Application(middlewares=[guard_middleware, cache_middleware])
    app["videobridge_token"] = videobridge_token

    # Register routes
    app.router.add_get("/api/v1/ping", handle_ping)
    app.router.add_get("/api/v1/display", handle_display)
    app.router.add_get("/api/v1/state", handle_state)
    app.router.add_get("/api/v1/events", handle_events)
    app.router.add_get("/api/v1/logs", handle_logs)
    app.router.add_get("/api/v1/notify", handle_notify)
    app.router.add_post("/api/v1/notify", handle_set_notify)
    app.router.add_post("/api/v1/notify/test", handle_test_notify)
    app.router.add_post("/api/v1/viewers/disconnect-others", viewers.disconnect_others(forget_state))
    app.router.add_post("/api/v1/display", handle_set_display)
    app.router.add_get("/api/v1/emulator-settings", handle_settings)
    app.router.add_post("/api/v1/emulator-settings", handle_set_settings)
    app.router.add_get("/api/v1/emulator/status", handle_status)
    app.router.add_post("/api/v1/emulator/gps", handle_gps)
    app.router.add_get("/api/v1/emulator/logcat", handle_logcat)
    app.router.add_post("/api/v1/emulator/key", handle_key)
    app.router.add_post("/api/v1/emulator/touch", handle_touch)
    app.router.add_get("/api/v1/emulator/ws-jsep", handle_websocket_jsep)
    if WEB_ROOT:
        app.router.add_get("/", handle_index)
        app.router.add_get("/index.html", handle_index)
        app.router.add_static("/assets", os.path.join(WEB_ROOT, "assets"))
    load_plugins(app, plugins_dir, read_screenshot, plugin_adb, notify.send, plugin_data or None)

    return app


async def main():
    parser = argparse.ArgumentParser(
        description="Python Web Gateway for WebRTC Android Emulator"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run the gateway webserver on."
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Address to bind the gateway webserver to.",
    )
    parser.add_argument(
        "--adb",
        type=str,
        default="/opt/android-sdk/platform-tools/adb",
        help="Path to the adb binary used for hardware key events.",
    )
    parser.add_argument(
        "--adb_serial",
        type=str,
        default="emulator-5558",
        help="adb serial of the emulator receiving hardware key events.",
    )
    parser.add_argument(
        "--videobridge",
        type=str,
        default="",
        help="Address of the running videobridge gRPC service. If empty, connects directly to the emulator gRPC service.",
    )
    parser.add_argument(
        "--videobridge_token",
        type=str,
        default="",
        help="Auth token for the videobridge.",
    )
    parser.add_argument(
        "--discovery_file",
        type=str,
        required=True,
        help="Path to the active emulator discovery config (.ini) file.",
    )
    parser.add_argument(
        "--web_root",
        type=str,
        default="",
        help="Directory of the built web page (index.html, assets/), served on the same port.",
    )
    parser.add_argument(
        "--emulator_unit",
        type=str,
        default="",
        help="systemd unit running the emulator, reported to the page. Empty disables it.",
    )
    parser.add_argument(
        "--display_request",
        type=str,
        default="",
        help="File where screen size requests from the page are written for a privileged service. Empty disables them.",
    )
    parser.add_argument(
        "--display_status",
        type=str,
        default="",
        help="File where that privileged service reports progress.",
    )
    parser.add_argument(
        "--settings_request",
        type=str,
        default="",
        help="File the gateway writes emulator settings requests to (empty: disabled).",
    )
    parser.add_argument(
        "--settings_status",
        type=str,
        default="",
        help="File where the privileged settings service reports progress.",
    )
    parser.add_argument(
        "--notify_file",
        type=str,
        default="",
        help="Where the phone alerts' setting is kept (empty: no alerts).",
    )
    parser.add_argument(
        "--plugins_dir",
        type=str,
        default="",
        help="Directory of installed plugins, one subdirectory each (empty: none).",
    )
    parser.add_argument(
        "--plugin_data",
        type=str,
        default="",
        help="Where plugins keep their files, one subdirectory each, created as needed (empty: nowhere).",
    )
    args = parser.parse_args()

    global ADB_PATH, ADB_SERIAL, DISPLAY_REQUEST, DISPLAY_STATUS, EMULATOR_UNIT, DISCOVERY_FILE
    global SETTINGS_REQUEST, SETTINGS_STATUS
    EMULATOR_UNIT = args.emulator_unit
    global WEB_ROOT
    WEB_ROOT = args.web_root
    DISCOVERY_FILE = args.discovery_file or ""
    ADB_PATH = args.adb
    ADB_SERIAL = args.adb_serial
    DISPLAY_REQUEST = args.display_request
    DISPLAY_STATUS = args.display_status
    SETTINGS_REQUEST = args.settings_request
    SETTINGS_STATUS = args.settings_status
    notify.load(args.notify_file)

    # Parse discovery configuration properties
    global DISCOVERY_PROPS
    DISCOVERY_PROPS = parse_discovery_file(args.discovery_file)

    global DISPLAY_WIDTH, DISPLAY_HEIGHT, AVD_DIR
    AVD_DIR = DISCOVERY_PROPS.get("avd.dir")
    size = read_display_size(AVD_DIR)
    if size:
        DISPLAY_WIDTH, DISPLAY_HEIGHT = size
    logging.info(f"Android display: {DISPLAY_WIDTH}x{DISPLAY_HEIGHT}")

    emulator_port = DISCOVERY_PROPS.get("grpc.port")
    if not emulator_port:
        logging.error("Failed to discover emulator gRPC port from discovery file. Restart the emulator (systemctl restart cloudphone-emulator).")
        sys.exit(1)

    emulator_address = f"localhost:{emulator_port}"
    logging.info(f"Connecting to Emulator gRPC service at: {emulator_address}")

    global EMULATOR_CHANNEL, VIDEOBRIDGE_CHANNEL
    # A 1080p RGB888 screenshot is about 6 MB, over gRPC's default 4 MB.
    EMULATOR_CHANNEL = grpc.aio.insecure_channel(emulator_address, options=GRPC_OPTIONS)

    if args.videobridge:
        logging.info(f"Connecting to Video Bridge gRPC service at: {args.videobridge}")
        VIDEOBRIDGE_CHANNEL = grpc.aio.insecure_channel(args.videobridge, options=GRPC_OPTIONS)
    else:
        logging.info("No separate Video Bridge specified; using Emulator gRPC channel directly for Rtc service.")
        VIDEOBRIDGE_CHANNEL = EMULATOR_CHANNEL

    # Start Aiohttp server
    # When the emulator itself provides the RTC bridge, reuse its discovery
    # token. Passing the token on the command line would expose it via /proc.
    bridge_token = args.videobridge_token or DISCOVERY_PROPS.get("grpc.token", "")
    app = init_app(bridge_token, args.plugins_dir, args.plugin_data)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()

    logging.info(f"Gateway Webserver listening on http://{args.host}:{args.port}")

    watcher = asyncio.create_task(watch_discovery_file())
    sampler = asyncio.create_task(sample_metrics())
    alerts = asyncio.create_task(watch_events())
    await log_start()
    health = asyncio.create_task(watch_health())

    # Run forever
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        pass
    finally:
        logging.info("Shutting down Gateway channels.")
        await EMULATOR_CHANNEL.close()
        if VIDEOBRIDGE_CHANNEL and VIDEOBRIDGE_CHANNEL != EMULATOR_CHANNEL:
            await VIDEOBRIDGE_CHANNEL.close()
        await runner.cleanup()


def run_main():
    asyncio.run(main())


if __name__ == "__main__":
    run_main()
