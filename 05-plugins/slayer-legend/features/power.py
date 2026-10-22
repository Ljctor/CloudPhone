"""The plugin's on/off switch (ports.enabled, kept in state.json, on by
default). While off the plugin taps nothing: the lease is refused to its
own holders, the watchdog does not look, the mine and the mode switch wait;
the page draws nothing over the game.

GET  /enabled   {enabled}
POST /enabled   {enabled: true or false} (needs the page token)
"""


def power(ports):
    async def handle_get(request):
        return ports.respond({"enabled": ports.enabled()})

    async def handle_post(request):
        try:
            body = await request.json()
        except (ValueError, TypeError, AttributeError):
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("enabled"), bool):
            return ports.respond({"error_t": ports.t("Attendu : {expected}", expected="{enabled: true | false}")},
                                 status=400)
        ports.set_enabled(body["enabled"])
        return ports.respond({"enabled": ports.enabled()})

    return {"routes": [("GET", "/enabled", handle_get), ("POST", "/enabled", handle_post)]}
