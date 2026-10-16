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

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d (%(funcName)s): %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Properties dictionary populated by parsing the discovery file
DISCOVERY_PROPS = {}
EMULATOR_CHANNEL = None
VIDEOBRIDGE_CHANNEL = None
ADB_PATH = "/opt/android-sdk/platform-tools/adb"
ADB_SERIAL = "emulator-5558"
# Android display size in pixels, read from the running AVD's config.ini.
DISPLAY_WIDTH = 540
DISPLAY_HEIGHT = 1170
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
VIEWERS = {"count": 0}
STATE_CACHE = {"time": 0.0, "value": None}
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
LAST_DISPLAY_CHANGE = {"time": None}


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
        logging.error(f"Failed to read discovery file: {e}")
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


def read_load():
    try:
        with open("/proc/loadavg", "r") as f:
            one, five = f.read().split()[:2]
        return {"one": float(one), "five": float(five), "cpus": os.cpu_count() or 1}
    except (OSError, ValueError):
        return None


async def handle_state(request):
    """
    GET /api/v1/state: what the page needs to explain a problem to the user.
    Cached for a couple of seconds, as every open page polls it.
    """
    loop = asyncio.get_running_loop()
    if STATE_CACHE["value"] is None or loop.time() - STATE_CACHE["time"] > STATE_CACHE_SECONDS:
        unit, booted = await asyncio.gather(read_emulator_unit(), read_android_booted())
        STATE_CACHE["value"] = {
            "emulator": unit,
            "android": {"booted": booted},
            "viewers": VIEWERS["count"],
            "load": read_load(),
            "display": read_display_status(),
        }
        STATE_CACHE["time"] = loop.time()
    return web.json_response(STATE_CACHE["value"], headers={"Cache-Control": "no-store"})


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
            logging.warning("The emulator restarted: restarting the gateway to follow it.")
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


async def handle_set_display(request):
    """
    POST /api/v1/display {width, height, density}: asks the root service to
    change Android's screen size, which reboots Android (data is kept).
    """
    if not DISPLAY_REQUEST:
        return web.json_response({"error": "Screen size changes are disabled"}, status=403)
    try:
        data = await request.json()
        wanted = {key: int(data[key]) for key in DISPLAY_LIMITS}
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "width, height and density are required"}, status=400)
    for key, (low, high) in DISPLAY_LIMITS.items():
        if not low <= wanted[key] <= high:
            return web.json_response({"error": f"{key} must be between {low} and {high}"}, status=400)
    if wanted["width"] % 2 or wanted["height"] % 2:
        return web.json_response({"error": "width and height must be even"}, status=400)
    if read_display_status()["state"] in ("pending", "applying"):
        return web.json_response({"error": "A screen size change is already in progress"}, status=409)
    last = LAST_DISPLAY_CHANGE["time"]
    if last is not None and time.monotonic() - last < DISPLAY_CHANGE_INTERVAL:
        wait = int(DISPLAY_CHANGE_INTERVAL - (time.monotonic() - last)) + 1
        return web.json_response({"error": f"Wait {wait} s before the next change"}, status=429)
    LAST_DISPLAY_CHANGE["time"] = time.monotonic()
    temporary = f"{DISPLAY_REQUEST}.tmp"
    with open(temporary, "w") as f:
        f.write(f"{wanted['width']} {wanted['height']} {wanted['density']}\n")
    os.replace(temporary, DISPLAY_REQUEST)
    logging.info(f"Screen size requested: {wanted}")
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
        logging.error(f"Error fetching status from emulator: {e}")
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
        logging.error(f"Error setting GPS on emulator: {e}")
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
        logging.error(f"Error fetching logcat from emulator: {e}")
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
        if process.returncode:
            raise RuntimeError(stderr.decode(errors="replace").strip())
        return web.json_response({"status": "success"})
    except Exception as e:
        logging.error(f"Error sending key: {e}")
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
        logging.error(f"Error sending touch: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_websocket_jsep(request):
    """
    GET /api/v1/emulator/ws-jsep (WebSocket Upgrade)
    Handles WebRTC signaling connection and interfaces with Video Bridge over rtc2.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    logging.info("WebSocket connection opened for JSEP signaling.")

    if not VIDEOBRIDGE_CHANNEL:
        logging.error("No channel to Video Bridge.")
        await ws.close(
            code=web.WSCloseCode.INTERNAL_ERROR, message=b"Video Bridge offline"
        )
        return ws

    rtc_stub = rtc_grpc.RtcStub(VIDEOBRIDGE_CHANNEL)
    bridge_metadata = get_videobridge_metadata(request.app["videobridge_token"])
    guid = None
    stream_task = None
    bye_forwarded = False
    VIEWERS["count"] += 1

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
        logging.info(
            f"Initialized WebRTC stream session with Video Bridge. Connection ID: {guid}"
        )

        # The emulator sends the authoritative start message on its JSEP
        # stream. Sending a second synthetic start creates two peer
        # connections and breaks both video input and hardware controls.

        # 3. Spawn background streaming reader to forward gRPC messages -> WebSocket
        async def stream_to_client():
            logging.info(
                f"Starting stream_to_client background task for connection: {guid}"
            )
            try:
                reader_req = rtc.ReceiveJsepMessageRequest(id=rtc.Id(guid=guid))
                logging.info(
                    f"Subscribing to JSEP message stream from Video Bridge for connection: {guid}"
                )
                async for response_msg in rtc_stub.ReceiveJsepMessageStream(
                    reader_req, metadata=bridge_metadata
                ):
                    msg_text = response_msg.jsep_msg.message
                    logging.info(
                        f"Received JSEP message from Video Bridge gRPC stream: '{msg_text}'"
                    )
                    if not msg_text:
                        logging.info(
                            "Received empty JSEP message from Video Bridge. Stopping stream reader."
                        )
                        break
                    parsed_jsep = json.loads(msg_text)
                    logging.info(f"Forwarding JSEP message to browser: {parsed_jsep}")

                    # If it's an SDP offer/answer, or an ICE candidate message
                    await ws.send_json(parsed_jsep)
                logging.info("Video Bridge JSEP stream finished cleanly.")
            except asyncio.CancelledError:
                logging.info(f"stream_to_client task cancelled for connection: {guid}")
            except Exception as ex:
                logging.exception("Error in stream_to_client reader loop:")

        stream_task = asyncio.create_task(stream_to_client())

        # 4. Handle incoming browser messages and route -> Video Bridge
        async for ws_msg in ws:
            if ws_msg.type == web.WSMsgType.TEXT:
                client_data = ws_msg.json()
                logging.info(
                    f"Received message from Client -> Video Bridge: {client_data}"
                )

                send_req = rtc.SendJsepMessageRequest()
                send_req.jsep_msg.id.guid = guid
                send_req.jsep_msg.message = json.dumps(client_data)

                await rtc_stub.SendJsepMessage(send_req, metadata=bridge_metadata)
                logging.info(
                    f"Successfully forwarded JSEP message to Video Bridge for connection: {guid}"
                )

                if "bye" in client_data:
                    bye_forwarded = True
                    logging.info(
                        f"Received 'bye' signal from client. Tearing down connection: {guid}"
                    )
                    break
            elif ws_msg.type == web.WSMsgType.ERROR:
                logging.error(f"WebSocket encountered error: {ws.exception()}")

    except Exception as e:
        logging.exception("Error in WebSocket session handler:")
    finally:
        VIEWERS["count"] -= 1
        logging.info(f"Closing signaling WebSocket session for ID: {guid}")
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
                logging.info(
                    f"Forwarded teardown for abandoned connection: {guid}"
                )
            except Exception:
                logging.exception(
                    f"Failed to tear down abandoned connection: {guid}"
                )
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
    return response


def init_app(videobridge_token):
    app = web.Application(middlewares=[guard_middleware, cache_middleware])
    app["videobridge_token"] = videobridge_token

    # Register routes
    app.router.add_get("/api/v1/ping", handle_ping)
    app.router.add_get("/api/v1/display", handle_display)
    app.router.add_get("/api/v1/state", handle_state)
    app.router.add_post("/api/v1/display", handle_set_display)
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
    args = parser.parse_args()

    global ADB_PATH, ADB_SERIAL, DISPLAY_REQUEST, DISPLAY_STATUS, EMULATOR_UNIT, DISCOVERY_FILE
    EMULATOR_UNIT = args.emulator_unit
    global WEB_ROOT
    WEB_ROOT = args.web_root
    DISCOVERY_FILE = args.discovery_file or ""
    ADB_PATH = args.adb
    ADB_SERIAL = args.adb_serial
    DISPLAY_REQUEST = args.display_request
    DISPLAY_STATUS = args.display_status

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
        logging.error("Failed to discover emulator gRPC port from discovery file.")
        sys.exit(1)

    emulator_address = f"localhost:{emulator_port}"
    logging.info(f"Connecting to Emulator gRPC service at: {emulator_address}")

    global EMULATOR_CHANNEL, VIDEOBRIDGE_CHANNEL
    EMULATOR_CHANNEL = grpc.aio.insecure_channel(emulator_address)

    if args.videobridge:
        logging.info(f"Connecting to Video Bridge gRPC service at: {args.videobridge}")
        VIDEOBRIDGE_CHANNEL = grpc.aio.insecure_channel(args.videobridge)
    else:
        logging.info("No separate Video Bridge specified; using Emulator gRPC channel directly for Rtc service.")
        VIDEOBRIDGE_CHANNEL = EMULATOR_CHANNEL

    # Start Aiohttp server
    # When the emulator itself provides the RTC bridge, reuse its discovery
    # token. Passing the token on the command line would expose it via /proc.
    bridge_token = args.videobridge_token or DISCOVERY_PROPS.get("grpc.token", "")
    app = init_app(bridge_token)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, args.host, args.port)
    await site.start()

    logging.info(f"Gateway Webserver listening on http://{args.host}:{args.port}")

    watcher = asyncio.create_task(watch_discovery_file())

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
