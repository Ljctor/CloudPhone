"""The mode's rules (features/mode_rules.py): a mode is chosen only once
configured; a number a POST leaves out or null keeps its value.
Run: python3 -m unittest test_mode_rules"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = load("features/mode_rules")
texts = load("features/texts")


class Request(unittest.TestCase):
    def test_mpw4_needs_its_stage(self):
        asked, error = rules.request({"mode": "mpw4"})
        self.assertIsNone(asked)
        self.assertEqual(error, rules.t("Farming mpw4 : choisis d’abord son stage"))
        asked, error = rules.request({"mode": "mpw4", "stage4": 31})
        self.assertIsNone(error)
        self.assertEqual((asked[0], asked[2]["stage4"]), ("mpw4", 31))

    def test_the_mine_needs_its_floor_and_area(self):
        for body in ({"mode": "mine"}, {"mode": "mine", "floor": 12}, {"mode": "mine", "area": 3},
                     {"mode": "mine", "floor": 12, "area": 6}, {"mode": "mine", "floor": 10000, "area": 3}):
            asked, error = rules.request(body)
            self.assertIsNone(asked, body)
            self.assertTrue(error["template"].startswith("Mine fermée : choisis d’abord"), (body, error))
        asked, error = rules.request({"mode": "mine", "floor": 12, "area": 3})
        self.assertIsNone(error)
        self.assertEqual(asked[0], "mine")

    def test_the_others_need_nothing(self):
        for mode in ("mpw18", "free"):
            asked, error = rules.request({"mode": mode})
            self.assertIsNone(error, mode)
            self.assertEqual(asked[0], mode)

    def test_the_default_has_no_timer(self):
        asked, _ = rules.request({"mode": "mpw18", "until": 1_800_000_000})
        self.assertIsNone(asked[1])


class DefaultMode(unittest.TestCase):
    NOW = 1_800_000_000.0

    def test_what_it_may_be(self):
        self.assertEqual(rules.default_request({}, {}, "free"), ("free", None))
        self.assertEqual(rules.default_request({"default": "mpw18"}, {}, "free"), ("mpw18", None))
        self.assertEqual(rules.default_request({"default": "free"}, {}, "mpw18"), ("free", None))
        self.assertIsNotNone(rules.default_request({"default": "mine"}, {}, "mpw18")[1])
        self.assertIsNotNone(rules.default_request({"default": "nope"}, {}, "mpw18")[1])

    def test_mpw4_only_once_configured(self):
        self.assertIn("stage", rules.default_request({"default": "mpw4"}, {"stage4": None}, "mpw18")[1]["template"])
        self.assertEqual(rules.default_request({"default": "mpw4"}, {"stage4": 925}, "mpw18"), ("mpw4", None))

    def test_the_default_has_no_timer_the_others_have(self):
        asked, _ = rules.request({"mode": "mpw4", "stage4": 925, "until": self.NOW + 60}, {}, "mpw4")
        self.assertIsNone(asked[1])
        asked, _ = rules.request({"mode": "mpw18", "until": self.NOW + 60, "default": "free"}, {})
        self.assertEqual(asked[1], self.NOW + 60)
        self.assertIsNone(rules.timer_for("free", None, False, "mpw18", None, self.NOW, "free"))
        self.assertEqual(rules.timer_for("mpw18", None, False, "free", None, self.NOW, "free"),
                         self.NOW + rules.TIMED_MINUTES * 60)

    def test_a_restart_after_the_end_is_back_to_the_default(self):
        self.assertEqual(rules.restored("mpw18", self.NOW - 1, False, self.NOW, "mpw4"), ("mpw4", None, True))
        self.assertEqual(rules.restored("mine", None, False, self.NOW, "free"), ("free", None, False))
        self.assertEqual(rules.restored("free", self.NOW + 60, False, self.NOW, "free"), ("free", None, False))

    def test_the_watch_runs_for_a_timed_mode_or_mpw4(self):
        self.assertFalse(rules.watched("mpw18", "mpw18"))
        self.assertFalse(rules.watched("free", "free"))
        self.assertTrue(rules.watched("mpw4", "mpw4"), "its gold scroll looks")
        self.assertTrue(rules.watched("mpw18", "free"))


class MineEnds(unittest.TestCase):
    def test_why_the_mine_ended(self):
        for state, why in (("stopped", "mine done"), ("no_feather", "mine no feather"),
                           ("entry_failed", "mine entry"), ("blocked", "mine stopped")):
            self.assertEqual(rules.due("mine", None, {"enabled": False, "state": state}, 0), why, state)
        self.assertIsNone(rules.due("mine", None, {"enabled": True, "state": "farming"}, 0))

    def test_one_alert_naming_the_default(self):
        self.assertEqual(rules.back_text("mine no feather", "mpw18", 920),
                         "Closed Mine stopped: no feather left, back to farming mpw18 (stage 920)")
        self.assertEqual(rules.back_text("mine no feather", "free"),
                         "Closed Mine stopped: no feather left, back to free play")
        self.assertEqual(rules.back_text("mine entry", "mpw4", 925,
                                         "no way back into the mine (Dungeon screen not seen)"),
                         "Closed Mine stopped: no way back into the mine (Dungeon screen not seen), "
                         "back to farming mpw4 (stage 925)")
        self.assertEqual(rules.back_text("timer", "mpw18", 920), "Timer ended: back to farming mpw18 (stage 920)")


class Timer(unittest.TestCase):
    NOW = 1_800_000_000.0

    def test_an_absent_until_keeps_the_timer(self):
        asked, _ = rules.request({"mode": "free"}, {})
        self.assertFalse(asked[3])
        self.assertEqual(rules.timer_for("free", asked[1], asked[3], "free", self.NOW + 600, self.NOW), self.NOW + 600)
        # A timed mode just chosen starts with its default timer.
        self.assertEqual(rules.timer_for("free", asked[1], asked[3], "mpw18", None, self.NOW),
                         self.NOW + rules.TIMED_MINUTES * 60)

    def test_a_null_until_clears_it(self):
        asked, error = rules.request({"mode": "mine", "floor": 12, "area": 3, "until": None}, {})
        self.assertIsNone(error)
        self.assertTrue(asked[3])
        self.assertIsNone(rules.timer_for("mine", asked[1], asked[3], "mine", self.NOW + 600, self.NOW))
        self.assertIsNone(rules.timer_for("mine", asked[1], asked[3], "mpw18", None, self.NOW))

    def test_a_given_until_and_the_default_mode(self):
        self.assertEqual(rules.timer_for("mpw4", self.NOW + 60, True, "mpw4", self.NOW + 600, self.NOW), self.NOW + 60)
        self.assertIsNone(rules.timer_for("mpw18", None, False, "free", self.NOW + 600, self.NOW))


class Merge(unittest.TestCase):
    STORED = {"stage18": 920, "stage4": 31, "highest": 950, "floor": 161, "area": 2}

    def test_a_post_with_a_null_field_leaves_the_value_in_place(self):
        asked, error = rules.request({"mode": "mpw18", "stage18": None, "stage4": 40}, self.STORED)
        self.assertIsNone(error)
        self.assertEqual(asked[2], {**self.STORED, "stage4": 40})

    def test_an_absent_field_too(self):
        asked, _ = rules.request({"mode": "free"}, self.STORED)
        self.assertEqual(asked[2], self.STORED)

    def test_a_mode_configured_on_the_gateway_is_accepted(self):
        asked, error = rules.request({"mode": "mpw4", "stage4": None}, self.STORED)
        self.assertIsNone(error)
        self.assertEqual(asked[2]["stage4"], 31)
        asked, error = rules.request({"mode": "mine"}, self.STORED)
        self.assertIsNone(error)
        self.assertEqual((asked[2]["floor"], asked[2]["area"]), (161, 2))

    def test_nothing_stored(self):
        asked, _ = rules.request({"mode": "mpw18"}, {})
        self.assertEqual(asked[2], dict.fromkeys(rules.NUMBERS))


class FreePlayWarning(unittest.TestCase):
    def test_once_2_minutes_before_the_end(self):
        until = 10_000
        self.assertFalse(rules.warn_due("free", until, None, until - 121))
        self.assertTrue(rules.warn_due("free", until, None, until - 120))
        self.assertTrue(rules.warn_due("free", until, None, until - 5))
        self.assertFalse(rules.warn_due("free", until, until, until - 5), "said once")
        self.assertFalse(rules.warn_due("free", until, None, until), "ended: no warning")

    def test_again_when_the_timer_was_moved_later(self):
        self.assertTrue(rules.warn_due("free", 10_600, 10_000, 10_500))

    def test_only_free_play_with_a_timer(self):
        for mode in ("mpw18", "mpw4", "mine"):
            self.assertFalse(rules.warn_due(mode, 10_000, None, 9_950), mode)
        self.assertFalse(rules.warn_due("free", None, None, 9_950))

    def test_the_text(self):
        self.assertEqual(rules.WARNING, "The Cloud Phone takes over in 2 min: extend free play if you are still "
                                        "playing")


class Hold(unittest.TestCase):
    """A switch on hold while the user plays: one alert, the user's choice."""

    def test_the_alert_and_the_state_row(self):
        self.assertEqual(rules.hold_alert("mpw18", 59.6),
                         "Switch to farming mpw18 on hold: you are playing. Next try in 60 s.")
        self.assertEqual(rules.hold_alert("mpw4", 12, applied=True),
                         "Loadout mpw4 on hold: you are playing. Next try in 12 s.")
        self.assertEqual(texts.french(rules.hold_message("mpw18", 42)),
                         "Passage au farming mpw18 en attente : tu joues · nouvel essai dans 42 s")
        self.assertEqual(texts.french(rules.hold_message("mpw4", 42, applied=True)),
                         "Configuration mpw4 en attente : tu joues · nouvel essai dans 42 s")
        self.assertEqual(texts.english(rules.hold_message("mpw18", 42)),
                         "Switch to farming mpw18 on hold: you are playing · next try in 42 s")
        self.assertEqual(texts.french(rules.hold_message("mpw18", 0.2)), "Passage au farming mpw18 en attente : "
                         "tu joues · nouvel essai dans 1 s", "never « dans 0 s »")

    def test_the_ready_text_says_the_hold_apart(self):
        self.assertEqual(rules.ready_text("mpw18", 95, held=60.2),
                         "Farming mpw18 ready in 95 s (including 60 s waiting: you were playing)")
        self.assertEqual(rules.ready_text("mpw18", 34, held=0.3), "Farming mpw18 ready in 34 s")
        self.assertEqual(rules.ready_text("mpw4", 80, applied=True, alert="X", held=50),
                         "Loadout mpw4 applied in 80 s (including 50 s waiting: you were playing); X")

    def test_free_or_resume_while_on_hold(self):
        hold = {"id": "a1", "action": None}
        self.assertEqual(rules.hold_request({"action": "free"}, hold, None), ("free", None))
        self.assertEqual(rules.hold_request({"action": "resume", "hold": "a1"}, hold, None), ("resume", None))

    def test_the_same_answer_again_changes_nothing(self):
        self.assertEqual(rules.hold_request({"action": "resume"}, {"id": "a1", "action": "resume"}, None),
                         ("again", None))
        self.assertEqual(rules.hold_request({"action": "free"}, None, {"id": "a1", "action": "free"}),
                         ("again", None))
        self.assertEqual(rules.hold_request({"action": "free", "hold": "a1"}, None, {"id": "a1", "action": "free"}),
                         ("again", None))

    def test_nothing_on_hold_is_a_conflict(self):
        for body, hold, last in (({"action": "resume"}, None, None),
                                 ({"action": "resume"}, None, {"id": "a1", "action": "free"}),
                                 ({"action": "resume"}, None, {"id": "a1", "action": "timeout"}),
                                 ({"action": "free", "hold": "old"}, {"id": "a2", "action": None},
                                  {"id": "a1", "action": "free"})):
            action, error = rules.hold_request(body, hold, last)
            self.assertEqual((action, error[0]), (None, 409), body)

    def test_the_alerts_buttons(self):
        self.assertIsNone(rules.hold_buttons("a1", None), "an older gateway: no buttons")
        buttons = rules.hold_buttons("a1", "tok")
        self.assertEqual([(b["label"], b["body"]) for b in buttons],
                         [("Switch to free play", {"action": "free", "hold": "a1"}),
                          ("Resume now", {"action": "resume", "hold": "a1"})])
        self.assertEqual({(b["path"], b["token"]) for b in buttons}, {("/mode/hold", "tok")})

    def test_a_bad_body(self):
        for body in (None, {}, {"action": "later"}, []):
            self.assertEqual(rules.hold_request(body, {"id": "a1", "action": None}, None)[1][0], 400, body)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def wall(self):
        return 1e9 + self.now

    def monotonic(self):
        return self.now


class Tone(unittest.TestCase):
    """White at the instruction, blue for input, orange for recovery,
    red when blocked."""

    def test_stable_when_it_runs_and_the_watchdog_sees_nothing(self):
        for mode, state in (("mpw18", "farming"), ("mpw4", "farming"), ("free", "free"),
                            ("agent", "agent"), ("mpw18", "plan")):
            self.assertEqual(rules.tone(mode, state, False, False, {"level": None}), "ok", (mode, state))
        self.assertEqual(rules.tone("mine", "mine", False, False, None, "farming"), "ok")

    def test_blue_while_the_user_plays(self):
        self.assertEqual(rules.tone("mpw18", "farming", False, True), "hold")
        self.assertEqual(rules.tone("mpw4", "waiting", True, True), "hold", "a switch on hold")
        self.assertEqual(rules.tone("mpw4", "waiting", True, False), "setup", "returning after the pause")
        self.assertEqual(rules.tone("free", "free", False, True), "hold", "user input is shown in every mode")
        self.assertEqual(rules.tone("agent", "agent", False, True), "hold")

    def test_red_only_on_confirmed_block(self):
        self.assertEqual(rules.tone("mpw18", "failed", False, False), "error", "a setup step failed")
        self.assertEqual(rules.tone("mpw18", "farming", False, False, {"level": "error"}), "setup")
        self.assertEqual(rules.tone("mpw18", "farming", False, False, None, None, True), "setup", "engraving off")
        self.assertEqual(rules.tone("mine", "mine", False, False, None, "blocked"), "error")
        self.assertEqual(rules.tone("mpw18", "failed", True, True), "hold", "user intervention takes priority")

    def test_orange_while_set_up_or_repaired(self):
        for state in ("moving", "waiting"):
            self.assertEqual(rules.tone("mpw4", state, False, False), "setup", state)
        self.assertEqual(rules.tone("mpw18", "farming", False, False, {"level": "warning"}), "setup")
        self.assertEqual(rules.tone("mine", "mine", False, False, None, "relaunching"), "setup")


class RecoveryTone(unittest.TestCase):
    def test_a_repairable_error_stays_orange_until_confirmed_blocked(self):
        self.assertEqual(rules.tone("mpw18", "farming", False, False,
                                    {"level": "error", "blocked": False}), "setup")
        self.assertEqual(rules.tone("mpw18", "failed", False, False,
                                    {"level": "error", "repairing": "relaunch"}), "setup")
        self.assertEqual(rules.tone("mpw18", "farming", False, False,
                                    {"level": "error", "blocked": True}), "error")


class Pause(unittest.TestCase):
    """ports.Lease: the user's 5 s, and a switch resumed within them."""

    def setUp(self):
        self.clock, self.last = Clock(), {"monotonic": 996.0, "wall": 0}
        self.lease = load("features/ports").Lease(self.clock, lambda: self.last)

    def test_the_time_left(self):
        self.assertEqual(self.lease.pause_left(), 1)
        self.clock.now = 1001
        self.assertEqual(self.lease.pause_left(), 0)

    def test_each_input_starts_the_5_s_over(self):
        self.clock.now = 1000
        self.assertEqual(self.lease.pause_left(), 1)
        self.last = {"monotonic": 1000.0, "wall": 0}
        self.assertEqual(self.lease.pause_left(), 5)
        self.clock.now = 1005
        self.assertEqual(self.lease.pause_left(), 0)
        self.assertIsNone(self.lease.take("stage_change", "farm mpw18", 60))

    def test_resumed_now_it_is_taken_within_the_5_s(self):
        self.assertEqual(self.lease.take("stage_change", "farm mpw18", 60)["template"], rules.USER_PLAYING)
        self.assertIsNone(self.lease.take("stage_change", "farm mpw18", 60, pause=False))
        self.lease.check("stage_change")

    def test_the_game_seen_away_is_no_pause(self):
        self.lease.saw_focus(False)
        self.assertEqual(self.lease.pause_left(), 0)
        self.assertIsNone(self.lease.take("stage_change", "farm mpw18", 60))
        self.lease.release("stage_change")
        self.lease.saw_focus(True)
        self.assertEqual(self.lease.take("stage_change", "farm mpw18", 60)["template"], rules.USER_PLAYING)

    def test_an_input_after_it_still_stops_the_sequence(self):
        self.lease.take("stage_change", "farm mpw18", 60, pause=False)
        self.clock.now += 1
        self.last = {"monotonic": self.clock.now, "wall": 0}
        with self.assertRaises(RuntimeError):
            self.lease.check("stage_change")


if __name__ == "__main__":
    unittest.main()
