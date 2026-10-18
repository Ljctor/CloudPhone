"""Viewers: one id per page load, each with its signalling sessions.

A viewer may disconnect the others: their sessions are closed and their ids
refused for KICK_SECONDS, so that their page does not simply reconnect. A
reconnect of the same page (↻, back from background) within BACK_SECONDS
is not news for the others; a viewer that leaves is said GONE_SECONDS later,
once its page did not come back.

No I/O: times are passed in (monotonic seconds), sessions are opaque keys
(the WebSocket answers), and what is worth a record comes back as (level,
text, params, notify) for the caller to log.
"""

KICK_SECONDS = 600.0
GONE_SECONDS = 5.0
BACK_SECONDS = 60.0


class Viewers:
    def __init__(self):
        # Signalling sessions -> viewer id.
        self.sessions = {}
        # Viewer ids another viewer disconnected -> when.
        self.kicked = {}
        # Viewer ids seen lately -> when they last connected.
        self.seen = {}

    @property
    def count(self):
        return len(self.sessions)

    def is_kicked(self, viewer, now):
        for key in [key for key, since in self.kicked.items() if now - since > KICK_SECONDS]:
            del self.kicked[key]
        return bool(viewer) and viewer in self.kicked

    def connected(self, session, viewer, now):
        """A new session of this viewer: its record, or None for a page
        that is coming back."""
        self.sessions[session] = viewer
        last = self.seen.get(viewer)
        self.seen[viewer] = now
        for key in [key for key, seen in self.seen.items() if now - seen > KICK_SECONDS]:
            del self.seen[key]
        if last is not None and now - last < BACK_SECONDS:
            return None
        others = len({other for other in self.sessions.values() if other != viewer})
        if others:
            return "normal", "Un autre appareil s’est connecté ({n} en tout)", {"n": others + 1, "viewer": viewer}, True
        return "normal", "Un appareil s’est connecté", {}, False

    def closed(self, session):
        self.sessions.pop(session, None)

    def gone(self, viewer, now):
        """GONE_SECONDS after a session closed: the record if the viewer did
        not come back, else None."""
        if viewer in self.sessions.values():
            return None
        self.seen[viewer] = now - BACK_SECONDS
        remaining = len(set(self.sessions.values()))
        if remaining:
            return ("normal", "Un autre appareil s’est déconnecté ({n} encore connectés)",
                    {"n": remaining, "viewer": viewer}, True)
        return "normal", "Plus aucun appareil connecté", {}, False

    def kick_others(self, viewer, now):
        """The sessions to close so that only this viewer stays (their
        viewers are refused from now on), and the record to log once they
        are closed."""
        others = [session for session, other in self.sessions.items() if other != viewer]
        for session in others:
            if self.sessions[session]:
                self.kicked[self.sessions[session]] = now
        return others, ("warning", "Un appareil a déconnecté les autres ({n})",
                        {"n": len(others), "viewer": viewer}, True)
