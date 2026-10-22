"""The shared lease on the game's taps, for a holder outside the plugin (a
script or an agent playing for the user): while it holds the lease, the
plugin's own sequences (the launch, the mine, the watchdog's repairs) do
not tap; the watchdog only looks and says its repair is deferred.

GET    /lease   {lease: {holder, reason, since, until} or null}
POST   /lease   {holder, reason, seconds}: takes it, or renews the
                holder's own (seconds: 1 to ports.LEASE_MAX); 409 while
                another holder has it
DELETE /lease   {holder}: releases the holder's own lease only (404 when
                it does not hold it)

POST and DELETE need the page token, as every non-GET route. The plugin's
own holder names are refused here. The lease itself is ports.Lease.
"""

import re

OWN = ("launch", "mine", "watchdog", "mode", "stage_change")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$")


def t(template, **params):
    """A status text (features/texts.py)."""
    return {"template": template, "params": params}


def asked(body, need_seconds=True):
    """((holder, reason, seconds), None), or (None, the error, a status text)."""
    if not isinstance(body, dict):
        return None, t("Attendu : {expected}", expected="{holder, reason, seconds}")
    holder, reason, seconds = body.get("holder"), body.get("reason"), body.get("seconds")
    if not isinstance(holder, str) or not NAME.match(holder) or holder in OWN:
        return None, t("holder : 1 à 40 lettres, chiffres, espaces, '.', '_' ou '-', pas un nom du plugin")
    if not need_seconds:
        return (holder, None, None), None
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 200:
        return None, t("reason : un texte de 1 à 200 caractères")
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds:
        return None, t("seconds : un nombre, au moins 1 (15 minutes au plus sont gardées)")
    return (holder, reason.strip(), float(seconds)), None


def lease(ports):
    async def body_of(request):
        try:
            return await request.json()
        except (ValueError, TypeError, AttributeError):
            return None

    async def handle_get(request):
        return ports.respond({"lease": ports.lease.state()})

    async def handle_post(request):
        wanted, error = asked(await body_of(request))
        if error:
            return ports.respond({"error_t": error}, status=400)
        why = ports.lease.take(*wanted, user=True)
        if why:
            return ports.respond({"error_t": why, "lease": ports.lease.state()}, status=409)
        return ports.respond({"lease": ports.lease.state()})

    async def handle_delete(request):
        wanted, error = asked(await body_of(request), need_seconds=False)
        if error:
            return ports.respond({"error_t": error}, status=400)
        if not ports.lease.release(wanted[0]):
            return ports.respond({"error_t": t("pas ton bail"), "lease": ports.lease.state()}, status=404)
        return ports.respond({"lease": None})

    return {"routes": [("GET", "/lease", handle_get), ("POST", "/lease", handle_post),
                       ("DELETE", "/lease", handle_delete)]}
