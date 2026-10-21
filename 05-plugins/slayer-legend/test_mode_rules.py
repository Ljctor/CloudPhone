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


class Request(unittest.TestCase):
    def test_mpw4_needs_its_stage(self):
        asked, error = rules.request({"mode": "mpw4"})
        self.assertIsNone(asked)
        self.assertEqual(error, "Farming mpw4 : choisis d’abord son stage")
        asked, error = rules.request({"mode": "mpw4", "stage4": 31})
        self.assertIsNone(error)
        self.assertEqual((asked[0], asked[2]["stage4"]), ("mpw4", 31))

    def test_the_mine_needs_its_floor_and_area(self):
        for body in ({"mode": "mine"}, {"mode": "mine", "floor": 12}, {"mode": "mine", "area": 3},
                     {"mode": "mine", "floor": 12, "area": 6}, {"mode": "mine", "floor": 10000, "area": 3}):
            asked, error = rules.request(body)
            self.assertIsNone(asked, body)
            self.assertTrue(error.startswith("Mine fermée : choisis d’abord"), (body, error))
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
        self.assertIn("stage", rules.default_request({"default": "mpw4"}, {"stage4": None}, "mpw18")[1])
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
                         "Mine fermée arrêtée : plus de plume, retour au farming mpw18 (stage 920)")
        self.assertEqual(rules.back_text("mine no feather", "free"),
                         "Mine fermée arrêtée : plus de plume, retour au jeu libre")
        self.assertEqual(rules.back_text("mine entry", "mpw4", 925,
                                         "retour dans la mine impossible (écran Dungeon pas vu)"),
                         "Mine fermée arrêtée : retour dans la mine impossible (écran Dungeon pas vu), "
                         "retour au farming mpw4 (stage 925)")
        self.assertEqual(rules.back_text("timer", "mpw18", 920), "Minuteur écoulé : retour au farming mpw18 (stage 920)")


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
        self.assertEqual(rules.WARNING, "Le Cloud Phone reprend la main dans 2 min, "
                                        "prolonge le jeu libre si tu joues encore")


if __name__ == "__main__":
    unittest.main()
