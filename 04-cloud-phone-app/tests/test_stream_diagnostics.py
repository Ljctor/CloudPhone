"""Offline signalling evidence: safe summaries, bounded history and correlation."""
import json
import logging
import os
import sys
import unittest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "overlay", "gateway", "src")
sys.path.insert(0, SRC)
from videobridge_gateway.core.stream_diagnostics import Diagnostics, summary, check_browser_events


class StreamDiagnostics(unittest.TestCase):
    def test_payload_secrets_never_reach_snapshot_or_logs(self):
        diagnostics = Diagnostics()
        secrets = ["192.0.2.123", "secret-password", "secret-token", "private-guid"]
        with self.assertLogs(level=logging.INFO) as records:
            sid = diagnostics.begin()
            diagnostics.message(sid, "to_browser", {"start": {"iceServers": [{"credential": secrets[1]}]}, "guid": secrets[3]})
            diagnostics.message(sid, "to_browser", {"sdp": {"type": "offer", "sdp": "a=ice-pwd:" + secrets[1]}})
            diagnostics.message(sid, "to_bridge", {"candidate": {"candidate": "candidate:1 1 UDP 123 192.0.2.123 123 typ srflx raddr 10.1.1.1", "token": secrets[2]}})
            diagnostics.close(sid)
        evidence = json.dumps(diagnostics.snapshot()) + str(records.output)
        for secret in secrets + ["10.1.1.1", "a=ice-pwd", "iceServers"]:
            self.assertNotIn(secret, evidence)
        session = diagnostics.snapshot()["recent"][0]
        self.assertEqual(session["session_id"], sid)
        self.assertEqual(session["counts"], {"to_browser:start": 1, "to_browser:offer": 1, "to_bridge:candidate": 1})
        self.assertEqual(session["events"][-2]["candidate_type"], "srflx")
        self.assertEqual(session["events"][-2]["protocol"], "udp")

    def test_malformed_candidates_cannot_inject_properties(self):
        for candidate in (123, [], {}, "candidate:x 1 secret-token 1 private-address 1 typ secret-token"):
            result = summary({"candidate": candidate})
            self.assertTrue(set(result) <= {"kind", "protocol", "candidate_type"})
            self.assertNotIn("secret-token", json.dumps(result))
        self.assertEqual(summary({"candidate": ""}), {"kind": "end_of_candidates"})
        self.assertEqual(summary([]), {"kind": "invalid"})
        self.assertEqual(summary({"type": "secret-token", "sdp": "secret-token"}), {"kind": "other"})

    def test_storage_is_bounded_and_snapshot_detached(self):
        diagnostics = Diagnostics(limit=2)
        for _ in range(4):
            sid = diagnostics.begin()
            for _ in range(60):
                diagnostics.message(sid, "to_browser", {"start": {}})
            diagnostics.close(sid)
        for _ in range(4):
            diagnostics.begin()
        for _ in range(20):
            diagnostics.hardware_key("AudioVolumeUp")
        diagnostics.hardware_key("arbitrary-secret")
        value = diagnostics.snapshot()
        self.assertEqual(len(value["active"]), 2)
        self.assertEqual(len(value["recent"]), 2)
        self.assertEqual(len(value["recent"][0]["events"]), 48)
        self.assertEqual(len(value["hardware_inputs"]), 16)
        value["active"][0]["events"].clear()
        self.assertTrue(diagnostics.snapshot()["active"][0]["events"])

    def test_browser_events_reject_secrets_and_unknown_fields(self):
        sid = "abcdef123456"
        for event in ({"kind": "stats", "ip": "192.0.2.1"},
                      {"kind": "error", "state": "secret-token"},
                      {"kind": "stats", "bytesReceived": "secret-token"},
                      {"kind": "secret-token"},
                      {"kind": "stats", "framesDecoded": True},
                      {"kind": "stats", "framesDecoded": float("nan")},
                      {"kind": "stats", "framesDecoded": -1},
                      {"kind": "stats", "framesDecoded": 10 ** 1000}):
            with self.assertRaises(ValueError):
                check_browser_events({"sessionId": sid, "events": [event]})
        for payload in ({"sessionId": "secret-token", "events": [{"kind": "stats"}]},
                        {"sessionId": sid, "events": []},
                        {"sessionId": sid, "events": [{"kind": "stats"}] * 21}):
            with self.assertRaises(ValueError):
                check_browser_events(payload)

    def test_browser_events_survive_close_are_bounded_and_rate_limited(self):
        now = [10.0]
        diagnostics = Diagnostics(clock=lambda: now[0])
        sid = diagnostics.begin()
        diagnostics.close(sid)
        event = {"kind": "frame", "state": "first-frame", "elapsedMs": 200}
        self.assertEqual(check_browser_events({"sessionId": sid, "events": [event]}), (sid, [event]))
        for _ in range(12):
            self.assertEqual(diagnostics.browser_events(sid, [event] * 20), 20)
        self.assertEqual(len(diagnostics.snapshot()["recent"][0]["browser_events"]), 96)
        with self.assertRaises(OverflowError):
            diagnostics.browser_events(sid, [event])
        now[0] = 71
        self.assertEqual(diagnostics.browser_events(sid, [event]), 1)
        with self.assertRaises(KeyError):
            diagnostics.browser_events("000000000000", [event])

    def test_stats_logs_are_sampled_and_keep_counters_without_payloads(self):
        now = [10.0]
        diagnostics = Diagnostics(clock=lambda: now[0])
        sid = diagnostics.begin()
        with self.assertLogs(level=logging.INFO) as records:
            diagnostics.browser_events(sid, [{"kind": "stats", "framesDecoded": 12}])
            diagnostics.browser_events(sid, [{"kind": "stats", "framesDecoded": 14}])
            now[0] = 25.0
            diagnostics.browser_events(sid, [{"kind": "stats", "framesDecoded": 22}])
        self.assertEqual(len(records.output), 2)
        self.assertIn("12", records.output[0])
        self.assertIn("22", records.output[1])

    def test_elapsed_time_and_final_duration_are_stable(self):
        now = [10.0]
        diagnostics = Diagnostics(clock=lambda: now[0])
        sid = diagnostics.begin()
        now[0] = 12.5
        diagnostics.event(sid, "bridge_opened")
        diagnostics.close(sid)
        now[0] = 99
        self.assertEqual(diagnostics.snapshot()["recent"][0]["duration_seconds"], 2.5)
        self.assertEqual(diagnostics.snapshot()["recent"][0]["events"][-1]["after_seconds"], 2.5)


if __name__ == "__main__":
    unittest.main()
