"""Test plugin for the e2e suite, gateway side: one route per thing the
plugin host offers (GET, POST behind the token, screenshot, adb, analysis,
the user's activity, the log, an alert)."""

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

    async def handle_activity(request):
        # The user's activity as the plugin API gives it.
        return context.json({"last_input": context.last_input(), "viewers": context.viewers()})

    async def handle_log(request):
        # One record of the gateway's log, through the plugin API.
        body = await request.json()
        context.log(body.get("level", "normal"), body["text"], bool(body.get("notify")), **body.get("params", {}))
        return context.json({"logged": True})

    async def handle_alert(request):
        # An alert as the plugins send them: a record with notify, and the
        # same text to the user's phone (ntfy, when alerts are on).
        body = await request.json()
        context.log(body.get("level", "warning"), body["text"], True)
        return context.json({"sent": bool(await context.notify(body["text"]))})

    context.add_get("/hello", handle_hello)
    context.add_post("/log", handle_log)
    context.add_post("/alert", handle_alert)
    context.add_get("/activity", handle_activity)
    context.add_get("/count", handle_count)
    context.add_post("/count", handle_increment)
    context.add_get("/screen", handle_screen)
    context.add_post("/home", handle_home)
    context.add_get("/analyse", handle_analyse)
