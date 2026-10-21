"""One-time action tokens: what lets a phone alert's button (an ntfy http
action) make one POST without the page token.

The page token never leaves the page: an alert goes through the public
ntfy.sh service, where anyone who knows the topic reads it. So a plugin
that puts buttons in an alert gets a token for one path instead: random,
short-lived (at most MAX_SECONDS), taken once (the first POST with it
spends it, whichever button sent it) and revoked by the plugin once the
alert is out of date. The request carries it in ACTION_HEADER; the page's
origin check still applies.

No I/O: the tokens ({token: {path, until}}) and the time come in.
"""

import hmac
import secrets

ACTION_HEADER = "X-CloudPhone-Action"
MAX_SECONDS = 15 * 60


def issue(tokens, path, now, seconds):
    """A new token for one POST to path within seconds (at most
    MAX_SECONDS); the expired ones are dropped."""
    purge(tokens, now)
    token = secrets.token_urlsafe(24)
    tokens[token] = {"path": path, "until": now + min(float(seconds), MAX_SECONDS)}
    return token


def redeem(tokens, token, method, path, now):
    """True once: a POST to the token's path before it expires; the token
    is spent then (or dropped when expired)."""
    purge(tokens, now)
    if method != "POST" or not token:
        return False
    for known, entry in list(tokens.items()):
        if hmac.compare_digest(known, token):
            if entry["path"] != path:
                return False
            del tokens[known]
            return True
    return False


def revoke(tokens, token):
    """The plugin's alert is out of date: its token no longer works."""
    tokens.pop(token, None)


def purge(tokens, now):
    for token in [token for token, entry in tokens.items() if entry["until"] <= now]:
        del tokens[token]
