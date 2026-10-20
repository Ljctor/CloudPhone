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

# Add the proto/ directory to sys.path to allow absolute imports between sibling proto stubs
# (e.g., rtc_service_v2_pb2 importing ice_config_pb2).
proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from aiohttp import web
import grpc
import logging
import time

# Add local path to package import context to resolve generated proto modules
proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proto")
sys.path.insert(0, proto_dir)
from .proto import emulator_controller_pb2 as ec
from .proto import emulator_controller_pb2_grpc as ec_grpc
from .plugins import load_plugins, plugin_stats
from . import logs
from .logs import log
from .http import viewers
from .http import display
from .http import settings
from .http import events
from .http import notify
from .http import session
from .core import settings as settings_rules
from .core.session import bearer
from .core import metrics as host_metrics
from .adapters import adb, host_files, systemd
from .adapters.host_files import read_file

# Records to journald and to GET /api/v1/logs (see logs.py).
logs.setup()

# Properties dictionary populated by parsing the discovery file
DISCOVERY_PROPS = {}
EMULATOR_CHANNEL = None
VIDEOBRIDGE_CHANNEL = None
# Android display size in pixels, read from the running AVD's config.ini.
DISPLAY_WIDTH = 480
DISPLAY_HEIGHT = 1040
AVD_DIR = None
# Screen size changes requested from the page: see http/display.py.
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
# The page, served with this start's token: see http/session.py.
WEB_ROOT = ""
# Emulator settings (renderer, cores, memory) work like the screen size:
# see http/settings.py.
GRPC_OPTIONS = [("grpc.max_receive_message_length", 32 * 1024 * 1024)]
# When the page last asked for a change that restarts Android: a restart
# soon after it is expected, not an error.
CHANGE = {"requested": 0.0}
CHANGE_RESTART_SECONDS = 600


def change_requested():
    """A screen size or settings request was just written."""
    CHANGE["requested"] = time.time()


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


async def read_emulator_unit():
    """Returns the emulator unit's systemd state, or None if unknown."""
    if not EMULATOR_UNIT:
        return None
    output = await systemd.show(EMULATOR_UNIT, ("ActiveState", "SubState", "NRestarts", "Result"))
    if output is None:
        return None
    values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
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


def read_load():
    return host_metrics.load(read_file("/proc/loadavg"), os.cpu_count() or 1,
                             host_metrics.physical_cores(read_file("/proc/cpuinfo")))


def read_proc_stat():
    """(busy, total) jiffies of all host CPUs."""
    return host_metrics.cpu_jiffies(host_files.first_line("/proc/stat"))


def host_meminfo():
    """The host's /proc/meminfo, kB values by name."""
    return host_metrics.parse_meminfo(read_file("/proc/meminfo") or "")


def emulator_cgroup():
    return f"/sys/fs/cgroup/system.slice/{EMULATOR_UNIT}" if EMULATOR_UNIT else None


async def read_android_metrics():
    """Android's memory and the frame rate of the top layer since the last
    call (SurfaceFlinger timestats, enabled on first use)."""
    script = (
        "cat /proc/meminfo; echo ==TIMESTATS==;"
        " dumpsys SurfaceFlinger --timestats -enable >/dev/null;"
        " dumpsys SurfaceFlinger --timestats -dump -maxlayers 1;"
        " dumpsys SurfaceFlinger --timestats -clear >/dev/null"
    )
    code, output, _ = await adb.run("shell", script, timeout=10)
    if code is None or code == -1:
        return None
    return host_metrics.android_metrics(output)


def read_emulator_settings(cgroup):
    """Renderer, cores and memory the running emulator was started with,
    from its command line (not the configuration, which may have changed
    since)."""
    procs = read_file(f"{cgroup}/cgroup.procs") if cgroup else None
    for pid in (procs or "").split():
        args = host_files.command_line(pid)
        if args is None:
            continue
        found = settings_rules.from_command_line(args)
        if found is not None:
            return found
    return None


async def sample_metrics():
    """Host CPU and memory, the emulator unit's CPU and memory (its cgroup),
    and Android's figures while a page wants them."""
    loop = asyncio.get_running_loop()
    cgroup = emulator_cgroup()
    previous = None
    last_android = 0.0
    while True:
        try:
            now = loop.time()
            busy, total = read_proc_stat()
            usage = host_metrics.cgroup_usage(read_file(f"{cgroup}/cpu.stat") if cgroup else None)
            cpus = os.cpu_count() or 1
            if previous:
                p_now, p_busy, p_total, p_usage = previous
                governor = read_file("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
                METRICS["host"] = {
                    "cpu": host_metrics.cpu_percent(busy, total, (p_busy, p_total)),
                    "cpus": cpus,
                    "governor": governor.strip() if governor else None,
                    "mhz": host_metrics.average_mhz(read_file("/proc/cpuinfo")),
                    "memory": host_metrics.memory_summary(host_meminfo()),
                }
                METRICS["emulator"] = {
                    "settings": read_emulator_settings(cgroup),
                    "cpu": host_metrics.core_percent(usage, p_usage, now - p_now),
                    "memory": host_metrics.cgroup_memory_mb(read_file(f"{cgroup}/memory.current") if cgroup else None),
                }
            previous = (now, busy, total, usage)
            if now - METRICS["android_wanted"] < ANDROID_WANTED_SECONDS and now - last_android >= ANDROID_METRICS_SECONDS:
                last_android = now
                METRICS["android"] = await read_android_metrics()
        except Exception as error:
            logging.warning("Metrics sampling failed: %s", error)
        await asyncio.sleep(METRICS_SECONDS)


def change_expected():
    """True while Android may restart because the page asked for it: a
    request in the last minutes, one pending or applying, or one finished
    a moment ago (this gateway may have been restarted by it)."""
    if time.time() - CHANGE["requested"] < CHANGE_RESTART_SECONDS:
        return True
    for status, path in ((display.status(), display.STATUS), (settings.status(), settings.STATUS)):
        if status["state"] in ("pending", "applying"):
            return True
        if status["state"] in ("done", "failed") and time.time() - host_files.mtime(path) < CHANGE_RESTART_SECONDS:
            return True
    return False


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


async def watch_health():
    """Every few seconds, the emulator unit, Android's boot and the change
    requests: each change of state that matters is a record."""
    while True:
        try:
            unit, booted = await asyncio.gather(read_emulator_unit(), read_android_booted())
            check_health(unit, booted, display.status(), settings.status())
        except Exception as e:
            logging.warning(f"Health check failed: {e!r}")
        await asyncio.sleep(HEALTH_SECONDS)


def check_health(unit, booted, display_status, settings_status):
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
    for kind, status, path in (("display", display_status, display.STATUS), ("settings", settings_status, settings.STATUS)):
        key = (status.get("state"), status.get("message"), status.get("width"))
        before = HEALTH[kind]
        HEALTH[kind] = key
        if before == key or status.get("state") in ("idle", "pending", None):
            continue
        # At the gateway's start, a status written just before it (the
        # change restarted Android, then the gateway) is still news.
        if before is None and now - host_files.mtime(path) > 120:
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
            "display": display.status(),
            "settings": settings.status(),
        }
        STATE_CACHE["time"] = loop.time()
    value = {**STATE_CACHE["value"], "kicked": viewers.kicked(request)}
    if request.query.get("details") == "1":
        METRICS["android_wanted"] = loop.time()
        value["metrics"] = {key: METRICS[key] for key in ("host", "emulator", "android")}
        value["plugins"] = plugin_stats(request.app)
    return web.json_response(value, headers={"Cache-Control": "no-store"})


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


async def adb_output(*args, timeout=10):
    """(exit code, stdout) of an adb command, or (-1, "") on timeout or
    when adb could not start: what the events and the plugins get."""
    code, output, _ = await adb.run(*args, timeout=timeout)
    return (-1 if code is None else code), output


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
            log("warning", "gateway", "L’émulateur a redémarré : le gateway redémarre pour le suivre",
                notify=True)
            logging.shutdown()
            os._exit(75)


def get_emulator_metadata():
    return bearer(DISCOVERY_PROPS.get("grpc.token", ""))


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
        code, _, errors = await adb.run("shell", "input", "keyevent", keycodes[key])
        if code is None:
            raise OSError(errors)
        if code:
            raise RuntimeError(errors.strip())
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
    app = web.Application(middlewares=[session.guard, cache_middleware])
    app["videobridge_token"] = videobridge_token

    # Register routes
    app.router.add_get("/api/v1/ping", handle_ping)
    app.router.add_get("/api/v1/display", display.get_display(
        lambda: {"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT}, lambda: read_avd_config(AVD_DIR)))
    app.router.add_get("/api/v1/state", handle_state)
    app.router.add_get("/api/v1/events", events.get_events(adb_output))
    app.router.add_get("/api/v1/logs", handle_logs)
    app.router.add_get("/api/v1/notify", notify.get_notify)
    app.router.add_post("/api/v1/notify", notify.set_notify)
    app.router.add_post("/api/v1/notify/test", notify.test_notify)
    app.router.add_post("/api/v1/viewers/disconnect-others", viewers.disconnect_others(forget_state))
    app.router.add_post("/api/v1/display", display.set_display(
        settings.status, settings.files, change_requested))
    app.router.add_get("/api/v1/emulator-settings", settings.get_settings(
        lambda: read_emulator_settings(emulator_cgroup()), lambda: read_avd_config(AVD_DIR), host_meminfo))
    app.router.add_post("/api/v1/emulator-settings", settings.set_settings(host_meminfo, change_requested))
    app.router.add_get("/api/v1/emulator/status", handle_status)
    app.router.add_post("/api/v1/emulator/gps", handle_gps)
    app.router.add_get("/api/v1/emulator/logcat", handle_logcat)
    app.router.add_post("/api/v1/emulator/key", handle_key)
    app.router.add_post("/api/v1/emulator/touch", handle_touch)
    app.router.add_get("/api/v1/emulator/ws-jsep", session.signalling(lambda: VIDEOBRIDGE_CHANNEL))
    if WEB_ROOT:
        index = session.index(WEB_ROOT)
        app.router.add_get("/", index)
        app.router.add_get("/index.html", index)
        app.router.add_static("/assets", os.path.join(WEB_ROOT, "assets"))
    load_plugins(app, plugins_dir, read_screenshot, adb_output, notify.send, plugin_data or None)

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
        help="Path to the adb binary (hardware keys, Android metrics and events, plugins).",
    )
    parser.add_argument(
        "--adb_serial",
        type=str,
        default="emulator-5558",
        help="adb serial of the emulator.",
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

    global EMULATOR_UNIT, DISCOVERY_FILE
    EMULATOR_UNIT = args.emulator_unit
    events.UNIT = EMULATOR_UNIT
    global WEB_ROOT
    WEB_ROOT = args.web_root
    DISCOVERY_FILE = args.discovery_file or ""
    adb.configure(args.adb, args.adb_serial)
    display.REQUEST = args.display_request
    display.STATUS = args.display_status
    settings.REQUEST = args.settings_request
    settings.STATUS = args.settings_status
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
    alerts = asyncio.create_task(events.watch(adb_output, change_expected))
    await events.log_start(change_expected)
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
