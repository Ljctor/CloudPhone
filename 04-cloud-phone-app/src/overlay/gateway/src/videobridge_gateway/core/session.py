"""The page's session and the WebRTC signalling, as rules.

The gateway also serves the page, so page and API share one origin and no
CORS is needed. Each start draws a random token, written into index.html;
every POST must carry it, so a web page from another origin (for instance
one open in the phone's browser while the VPN is up) cannot drive or
reboot Android.

Signalling relays JSEP messages (SDP, ICE candidates) between the browser
and the emulator's Video Bridge; {"bye": ...} from the browser ends a
session, and the gateway sends one itself when the browser left without it.

No I/O: headers, texts and messages come in, decisions come out.
"""

import hmac
import html
import json

TOKEN_HEADER = "X-CloudPhone-Token"
# The default ICE server given to the Video Bridge.
STUN = "stun:stun.l.google.com:19302"
BYE = json.dumps({"bye": True})


def same_origin(origin, host):
    """True when the request has no Origin (not sent by a cross-origin page)
    or when its Origin is this server."""
    if origin is None:
        return True
    return origin in (f"http://{host}", f"https://{host}")


def token_needed(method):
    return method not in ("GET", "HEAD")


def token_valid(token, page_token):
    return hmac.compare_digest(token, page_token)


def page_with_token(page, page_token):
    """index.html with this start's token in a meta tag."""
    meta = f'<meta name="cloudphone-token" content="{html.escape(page_token)}">'
    return page.replace("<head>", f"<head>\n    {meta}", 1)


def bearer(token):
    """gRPC metadata for a token, none without one."""
    if token:
        return [("authorization", f"Bearer {token}")]
    return []


def is_bye(message):
    """True for the browser's message that ends the session."""
    return "bye" in message
