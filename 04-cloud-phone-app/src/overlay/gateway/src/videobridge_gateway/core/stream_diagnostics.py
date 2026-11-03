"""Bounded signalling evidence. Never retain JSEP payloads, addresses or tokens."""

from collections import Counter, deque
import copy
import logging
import hashlib
import re
import math
import secrets
import time


def summary(message):
    """Only allowlisted message kinds and ICE properties can leave this function."""
    if not isinstance(message, dict):
        return {"kind": "invalid"}
    if "candidate" in message:
        candidate = message["candidate"]
        value = candidate.get("candidate", "") if isinstance(candidate, dict) else candidate
        result = {"kind": "candidate"}
        if not value:
            result["kind"] = "end_of_candidates"
        elif isinstance(value, str):
            words = value.split()
            if len(words) > 2 and words[2].lower() in ("udp", "tcp"):
                result["protocol"] = words[2].lower()
            if "typ" in words:
                index = words.index("typ") + 1
                if index < len(words) and words[index] in ("host", "srflx", "prflx", "relay"):
                    result["candidate_type"] = words[index]
        return result
    sdp = message.get("sdp")
    kind = sdp.get("type") if isinstance(sdp, dict) else message.get("type")
    if kind in ("offer", "answer"):
        return {"kind": kind}
    for kind in ("start", "bye"):
        if kind in message:
            return {"kind": kind}
    return {"kind": "other"}


class Diagnostics:
    def __init__(self, limit=32, clock=time.monotonic):
        self.limit = limit
        self.clock = clock
        self.sessions = {}
        self.closed = deque(maxlen=limit)
        self.inputs = deque(maxlen=16)
        self.attempts = {}

    def attempt(self, viewer, attempt_id):
        key = (viewer, attempt_id)
        state = self.attempts.get(key)
        if state is None:
            if len(self.attempts) >= self.limit:
                self.attempts.pop(next(iter(self.attempts)))
            state = {"attempt_id": attempt_id, "viewer_hash": hashlib.sha256(viewer.encode()).hexdigest()[:12],
                     "started": self.clock(), "session_ids": [], "browser_events": deque(maxlen=96),
                     "browser_received": deque(), "last_stats_log": None}
            self.attempts[key] = state
        return state

    def begin(self, viewer=None, attempt_id=None):
        sid = secrets.token_hex(6)
        # Active sessions are bounded separately from the recently closed ones.
        if len(self.sessions) >= self.limit:
            self.sessions.pop(next(iter(self.sessions)))
        self.sessions[sid] = {"session_id": sid, "started": self.clock(), "phase": "websocket_open",
                              "counts": Counter(), "events": deque(maxlen=48),
                              "browser_events": deque(maxlen=96), "browser_received": deque(), "last_stats_log": None}
        state = self.sessions[sid]
        if viewer and attempt_id:
            attempt = self.attempt(viewer, attempt_id)
            attempt["session_ids"].append(sid)
            del attempt["session_ids"][:-8]
            state["identity"] = (viewer, attempt_id)
            state["attempt_id"] = attempt_id
            state["viewer_hash"] = attempt["viewer_hash"]
            # Share the bounded browser history: pre-WebSocket events and late
            # final events remain attached to this attempt after the socket ends.
            state["browser_events"] = attempt["browser_events"]
            state["browser_received"] = attempt["browser_received"]
        self.event(sid, "websocket_open")
        return sid

    def event(self, sid, phase, **values):
        state = self.sessions.get(sid)
        if state is None:
            return
        state["phase"] = phase
        elapsed = round(self.clock() - state["started"], 3)
        event = {"phase": phase, "after_seconds": elapsed, **values}
        state["events"].append(event)
        (logging.warning if "error" in phase or phase == "bridge_unavailable" else logging.info)(
            "stream session=%s %s", sid, event)

    def message(self, sid, direction, message):
        detail = summary(message)
        state = self.sessions.get(sid)
        if state is not None:
            state["counts"][direction + ":" + detail["kind"]] += 1
        self.event(sid, "jsep_" + direction, **detail)

    def close(self, sid):
        self.event(sid, "closed")
        state = self.sessions.pop(sid, None)
        if state is not None:
            state["duration_seconds"] = round(self.clock() - state["started"], 3)
            self.closed.append(state)

    def snapshot(self):
        def describe(state, active):
            return {**({"attempt_id": state["attempt_id"], "viewer_hash": state["viewer_hash"]} if "attempt_id" in state else {}), "session_id": state["session_id"], "active": active, "phase": state["phase"],
                    "duration_seconds": round(self.clock() - state["started"], 3) if active else state["duration_seconds"],
                    "counts": dict(state["counts"]), "events": list(state["events"]),
                    "browser_events": list(state["browser_events"])}
        return copy.deepcopy({"active": [describe(s, True) for s in self.sessions.values()],
                              "recent": [describe(s, False) for s in self.closed],
                              "hardware_inputs": list(self.inputs),
                              "attempts": [{"attempt_id": s["attempt_id"], "viewer_hash": s["viewer_hash"],
                                            "session_ids": list(s["session_ids"]),
                                            "browser_events": list(s["browser_events"])}
                                           for s in self.attempts.values()]})

    def browser_events(self, sid, events):
        if isinstance(sid, dict):
            identity = (sid["viewer"], sid["attemptId"])
            session_id = sid.get("sessionId")
            if session_id:
                state = self.sessions.get(session_id)
                if state is None:
                    state = next((s for s in self.closed if s["session_id"] == session_id), None)
                if state is None:
                    # Gateway restart or bounded-history eviction: preserve
                    # restart/token evidence under the browser's attempt.
                    state = self.attempt(*identity)
                elif state.get("identity") != identity:
                    raise KeyError("unknown attempt session")
            else:
                state = self.attempt(*identity)
            label = sid["attemptId"]
        else:
            state = self.sessions.get(sid)
            label = sid
        if state is None:
            state = next((s for s in self.closed if s["session_id"] == sid), None)
        if state is None:
            raise KeyError("unknown session")
        now = self.clock()
        received = state["browser_received"]
        while received and received[0] < now - 60:
            received.popleft()
        if len(received) + len(events) > 240:
            raise OverflowError("event rate exceeded")
        for event in events:
            received.append(now)
            record = {**event, "received_after_seconds": round(now - state["started"], 3)}
            state["browser_events"].append(record)
            # Keep milestones and sampled counters across gateway restarts via the normal log writer.
            last_stats = state["last_stats_log"]
            if event["kind"] != "stats" or last_stats is None or now - last_stats >= 15:
                logging.info("stream identity=%s browser=%s", label, record)
                if event["kind"] == "stats":
                    state["last_stats_log"] = now
        return len(events)

    def hardware_key(self, key):
        if key in ("GoBack", "GoHome", "AppSwitch", "Power", "AudioVolumeUp", "AudioVolumeDown"):
            self.inputs.append({"key": key, "observed_at": time.time()})
            logging.info("stream hardware_key=%s active_sessions=%s", key, list(self.sessions))


STREAMS = Diagnostics()


BROWSER_KINDS = frozenset(("connection", "ice", "gathering", "signalling", "track", "frame",
                           "playback", "error", "stats", "wake", "websocket", "client", "token", "reset"))
BROWSER_STATES = frozenset(("new", "connecting", "connected", "disconnected", "failed", "closed",
    "checking", "completed", "gathering", "complete", "stable", "have-local-offer", "have-remote-offer",
    "have-local-pranswer", "have-remote-pranswer", "video", "audio", "mute", "unmute", "ended", "first-frame",
    "resolved", "rejected", "first-frame-timeout", "volume-up", "volume-down", "volume-mute", "power", "wake",
    "visible", "hidden", "focus", "blur", "presentation-stalled", "presentation-resumed",
    "open", "error", "constructor-error", "started", "manual-reconnect", "reconnect-queued",
    "signaling-error", "signaling-invalid-json", "remote-description-error", "remote-candidate-error", "peer-created", "page-shown",
    "refused", "refreshed", "refresh-failed", "requested"))
BROWSER_NUMBERS = frozenset(("elapsedMs", "framesDecoded", "bytesReceived", "packetsLost", "framesReceived",
                              "framesDropped", "framesPerSecond", "presented", "keyFramesDecoded", "freezeCount", "totalFreezesDuration",
                              "code", "attempt", "localStorageKeys", "sessionStorageKeys", "readyState", "width", "height"))
BROWSER_FLAGS = frozenset(("storageAvailable", "tokenPresent", "secureContext", "online", "persisted", "clean", "paused", "muted", "hidden", "hadFrame"))


def valid_identity(value, minimum=1):
    return isinstance(value, str) and minimum <= len(value) <= 64 and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None


def check_browser_events(payload):
    """Reject all unknown fields and arbitrary text before storing any browser input."""
    if not isinstance(payload, dict):
        raise ValueError("invalid payload")
    modern = "attemptId" in payload
    required = {"viewer", "attemptId", "events"} if modern else {"sessionId", "events"}
    if not required <= set(payload) or set(payload) - (required | {"sessionId"}):
        raise ValueError("invalid payload")
    sid, events = payload.get("sessionId"), payload["events"]
    if (not modern or sid is not None) and (not isinstance(sid, str) or len(sid) != 12 or any(c not in "0123456789abcdef" for c in sid)):
        raise ValueError("invalid session id")
    if modern:
        if not valid_identity(payload["viewer"]) or not valid_identity(payload["attemptId"], 12):
            raise ValueError("invalid attempt identity")
        sid = {key: value for key, value in payload.items() if key != "events"}
    if not isinstance(events, list) or not 1 <= len(events) <= 20:
        raise ValueError("expected 1 to 20 events")
    for event in events:
        if not isinstance(event, dict) or set(event) - (BROWSER_NUMBERS | BROWSER_FLAGS | {"kind", "state"}):
            raise ValueError("invalid event fields")
        if not isinstance(event.get("kind"), str) or event["kind"] not in BROWSER_KINDS:
            raise ValueError("invalid event kind")
        if "state" in event and (not isinstance(event["state"], str) or event["state"] not in BROWSER_STATES):
            raise ValueError("invalid event state")
        for key in set(event) & BROWSER_FLAGS:
            if type(event[key]) is not bool:
                raise ValueError("invalid event flag")
        for key in set(event) & BROWSER_NUMBERS:
            value = event[key]
            if type(value) not in (int, float) or abs(value) > 1e16 or not math.isfinite(value):
                raise ValueError("invalid event number")
            if key != "packetsLost" and value < 0:
                raise ValueError("negative event number")
    return sid, events
