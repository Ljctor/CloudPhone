"""Test plugin for the e2e suite, gateway side: one route per thing the
plugin host offers (GET, POST behind the token, screenshot, adb, analysis)."""

import time

COUNT = {"value": 0}


def setup(context):
    async def handle_hello(request):
        return context.json({"plugin": context.id, "prefix": context.prefix})

    async def handle_count(request):
        return context.json({"count": COUNT["value"]})

    async def handle_increment(request):
        body = await request.json()
        COUNT["value"] += int(body.get("by", 1))
        return context.json({"count": COUNT["value"]})

    async def handle_screen(request):
        # ?max_age=S: a capture that young will do (shared screenshot).
        shot = await context.screenshot(max_age=float(request.query.get("max_age", 0)))
        if not shot:
            return context.json({"screen": None})
        width, height, pixels = shot
        return context.json({"screen": [width, height], "bytes": len(pixels)})

    async def handle_home(request):
        code, out = await context.adb("shell", "input", "keyevent", "HOME")
        return context.json({"code": code})

    async def handle_analyse(request):
        # An analysis that takes ?seconds=S (at most 5), in context.analyse.
        seconds = min(float(request.query.get("seconds", 1)), 5.0)
        await context.analyse(time.sleep, seconds)
        return context.json({"slept": seconds})

    context.add_get("/hello", handle_hello)
    context.add_get("/count", handle_count)
    context.add_post("/count", handle_increment)
    context.add_get("/screen", handle_screen)
    context.add_post("/home", handle_home)
    context.add_get("/analyse", handle_analyse)
