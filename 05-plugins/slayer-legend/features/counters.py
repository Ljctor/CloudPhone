"""The emerald and diamond counters, for browsers that cannot read the
video's pixels (Firefox on Android): where each counter is, and the pixels
of its digits after the comma, from an emulator screenshot.

GET /emerald-mask[?counter=diamond]

Read-only: it never touches the game. The finder is emerald_mask.py.
"""

import asyncio
import base64
import logging

# A mask this young is given again instead of a new screenshot.
SECONDS = 0.4


def mask_of(emerald, shot, area):
    """The counter's mask in area (page pixels at 360 wide) of shot: {mask,
    reason}; mask has the digits after the comma's pixels (base64 RGB)."""
    width, _, image = shot
    scale = width / 360
    x0, y0 = emerald.js_round(area["x"] * scale), emerald.js_round(area["y"] * scale)
    w, h = emerald.js_round(area["width"] * scale), emerald.js_round(area["height"] * scale)
    pixels = bytearray()
    for y in range(y0, y0 + h):
        start = (y * width + x0) * 3
        pixels += image[start:start + w * 3]
    if len(pixels) != w * h * 3:
        return {"mask": None, "reason": "screenshot"}
    mask, reason = emerald.find_emerald_mask(pixels, w, h, scale, channels=3, area=area)
    if mask:
        # The page redraws the digits after the comma: send their pixels.
        box = mask["decimals"]["pixels"]
        crop = bytearray()
        for y in range(box["y"], box["y"] + box["height"]):
            start = (y * w + box["x"]) * 3
            crop += pixels[start:start + box["width"] * 3]
        box["rgb"] = base64.b64encode(bytes(crop)).decode("ascii")
        # The finder counts from AREA; the crop starts at a whole pixel.
        dx, dy = x0 / scale - area["x"], y0 / scale - area["y"]
        for part in (mask, mask["number"]):
            part["x"] += dx
            part["y"] += dy
        mask["decimals"]["x"] += dx
    return {"mask": mask, "reason": reason}


def counters(ports, emerald):
    caches = {counter: {"time": 0.0, "value": None, "lock": None} for counter in ("emerald", "diamond")}

    async def read_mask(area):
        shot = await ports.capture(max_age=SECONDS)
        if not shot:
            return {"mask": None, "reason": "screenshot"}
        return await ports.analyse(mask_of, emerald, shot, area)

    async def handle_mask(request):
        diamond = request.query.get("counter") == "diamond"
        cache = caches["diamond" if diamond else "emerald"]
        if cache["lock"] is None:
            cache["lock"] = asyncio.Lock()
        async with cache["lock"]:
            if cache["value"] is None or ports.clock.monotonic() - cache["time"] > SECONDS:
                try:
                    cache["value"] = await read_mask(emerald.DIAMOND_AREA if diamond else emerald.AREA)
                except Exception as e:
                    logging.warning(f"Counter mask: no screenshot: {e!r}")
                    cache["value"] = {"mask": None, "reason": "screenshot"}
                cache["time"] = ports.clock.monotonic()
        return ports.respond(cache["value"])

    return {"routes": [("GET", "/emerald-mask", handle_mask)]}
