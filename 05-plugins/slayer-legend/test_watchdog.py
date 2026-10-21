"""The watchdog's rules (features/watchdog_rules.py), offline: the
looks a scripted game gives, one every rules.EVERY seconds, through
judge() and decide(); and features/watchdog.py's Wait on Android's
ANR dialog, on fake ports. Run: python3 -m unittest test_watchdog
"""

import asyncio
import contextlib
import importlib.util
import logging
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("watchdog_rules", os.path.join(HERE, "features", "watchdog_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
spec = importlib.util.spec_from_file_location("watchdog_ports", os.path.join(HERE, "features", "ports.py"))
ports_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ports_module)
LOG = ports_module.python_log("slayer-legend")
EXCEPTION = ports_module.exception_log(LOG)

EPOCH = 1_800_000_000.0
# Stage 920's name ends with III in this table; 921 with IV.
NUMERALS = {920: 3, 921: 4}
PROFILE = rules.profile(None, 920)
ALL = ("relaunch", "back_to_battle", "stage_change", "select_preset", "loadout", "auto_on")

BATTLE = {"adb": True, "running": True, "focused": True, "screen": "battle", "numeral": 3}
OTHER_STAGE = {**BATTLE, "numeral": 4}
UNREAD = {**BATTLE, "numeral": None}
SAVER = {"adb": True, "running": True, "focused": True, "screen": "saver"}
MENU = {"adb": True, "running": True, "focused": True, "screen": "menu"}
TITLE = {"adb": True, "running": True, "focused": True, "screen": "title"}
OTHER = {"adb": True, "running": True, "focused": True, "screen": "other"}
CRASH = {"adb": True, "running": True, "focused": False, "crash": True, "screen": None}
ANR = {"adb": True, "running": True, "focused": False, "anr": True, "screen": None}
GONE = {"adb": True, "running": False, "focused": False, "screen": None}
AWAY = {"adb": True, "running": True, "focused": False, "screen": None}
NO_ADB = {"adb": False, "running": None, "focused": False, "screen": None}
NO_CAPTURE = {"adb": True, "running": True, "focused": True, "screen": None}
E = rules.EVERY


class Watch:
    """The watchdog's rules on virtual time: one look every rules.EVERY
    seconds; inputs and the lease as the script says."""

    def __init__(self, act=True, available=ALL, kept=None, profile=PROFILE):
        self.memory = rules.fresh(kept)
        self.profile = profile
        self.now = 0.0
        self.input = None
        self.lease = None
        self.mode = "mpw18"
        self.resumed = False
        self.after_mode = False
        self.act = {kind: act for kind in ALL}
        self.available = available
        self.records, self.repairs, self.plans, self.symptoms, self.paused = [], [], [], [], []

    def wall(self):
        return EPOCH + self.now

    def look(self, seen):
        self.now += E
        why = rules.paused(self.mode, self.input, self.now)
        if why:
            if self.mode not in rules.MODE_NAMES:
                self.memory = rules.suspended(self.memory)
            self.paused.append(why)
            return None
        symptom, text, params, self.memory = rules.judge(
            seen, self.profile, NUMERALS.get, self.input, self.resumed, self.memory, self.now, self.after_mode)
        self.resumed = False
        self.symptoms.append(symptom)
        context = {"input_wall": None if self.input is None else EPOCH + self.input, "lease": self.lease,
                   "act": self.act, "available": self.available, "mode": self.profile["mode"]}
        self.memory, actions = rules.decide(self.memory, symptom, text, params, context, self.wall())
        for action in actions:
            if action[0] == "record":
                self.records.append((self.now, *action[1:]))
            elif action[0] == "repair":
                self.repairs.append((self.now, action[1]))
            else:
                self.plans.append((self.now, action[1]))
        return symptom

    def looks(self, seen, count):
        for _ in range(count):
            self.look(seen)

    def tap(self):
        """A user input, half way to the next look."""
        self.input = self.now + E / 2

    def alerts(self):
        """The phone alerts, as their texts read."""
        return [(level, text.format(**params)) for _, level, text, params, notify in self.records if notify]

    def kinds(self):
        return [kind for _, kind in self.repairs]

    def notifications(self):
        return [text.format(**params) for _, level, text, params, notify in self.records if notify]


class Timing(unittest.TestCase):
    def test_a_crash_is_alerted_and_relaunched_within_30_s(self):
        w = Watch()
        w.looks(BATTLE, 4)
        crashed = w.now
        w.looks(CRASH, 2)
        self.assertEqual(w.repairs, [(crashed + 2 * E, "relaunch")])
        alert = [t for t, level, text, params, notify in w.records if notify]
        self.assertEqual(alert, [crashed + 2 * E], "the alert goes out with the repair")

    def test_the_title_screen_is_relaunched(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(TITLE, 2)
        self.assertEqual(w.kinds(), ["relaunch"])


class Alerts(unittest.TestCase):
    def test_one_alert_after_two_looks_then_one_back(self):
        w = Watch(available=())
        w.looks(BATTLE, 4)
        w.look(GONE)
        self.assertEqual(w.alerts(), [])
        w.looks(GONE, 10)
        self.assertEqual(w.alerts(), [("warning", "Farming mpw18 : le jeu ne tourne pas")])
        w.looks(BATTLE, 3)
        self.assertEqual(len(w.alerts()), 1, "well for less than a minute: not back yet")
        w.look(BATTLE)
        self.assertEqual(w.alerts()[1:], [("normal", "Farming mpw18 : rétabli")])
        self.assertEqual(rules.counters(w.memory, w.wall())["alerts"], 1)

    def test_adb_missing_is_an_error_and_never_repaired(self):
        w = Watch()
        w.looks(NO_ADB, 10)
        self.assertEqual(w.alerts(), [("error", "Farming mpw18 : adb ne répond pas : l’émulateur ou adb manque")])
        self.assertEqual(w.repairs, [])


class OtherScreen(unittest.TestCase):
    def test_another_screen_is_never_tapped_and_alerted_after_60_s(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(OTHER, 3)
        self.assertEqual(w.alerts(), [], "a stage transition or a loading screen")
        w.look(OTHER)
        self.assertEqual(w.alerts(), [("warning", "Farming mpw18 : écran inattendu")])
        w.looks(OTHER, 40)
        self.assertEqual((w.repairs, w.plans), ([], []))

    def test_relaunched_once_the_game_is_not_in_front(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(OTHER, 3)
        # The first look with another app in front only says "to confirm".
        w.looks(AWAY, rules.AWAY_AFTER)
        self.assertEqual(w.kinds(), [])
        w.look(AWAY)
        self.assertEqual(w.kinds(), ["relaunch"])


class Pauses(unittest.TestCase):
    def test_an_input_pauses_a_minute(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.tap()
        w.looks(GONE, 4)
        self.assertEqual(w.paused, ["En pause : l’utilisateur joue"] * 4)
        w.look(GONE)
        self.assertEqual(w.symptoms[-1], "not_running", "looks again after 60 s")

    def test_a_menu_is_a_disruption_after_60_s_with_no_input(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(MENU, 4)
        self.assertNotIn("menu", w.symptoms)
        w.look(MENU)
        self.assertEqual(w.symptoms[-1], "menu", "the first look more than 60 s after it was first seen")

    def test_a_user_who_plays_in_the_menus_is_no_disruption(self):
        w = Watch()
        for _ in range(10):
            w.tap()
            w.looks(MENU, 4)
        self.assertNotIn("menu", w.symptoms)
        self.assertEqual(w.repairs, [])

    def test_a_menu_when_a_mode_ends_has_no_grace(self):
        w = Watch()
        w.mode = "mpw4"
        w.looks(MENU, 3)
        w.mode, w.resumed = "mpw18", True
        self.assertEqual(w.look(MENU), "menu")

    def test_a_menu_is_back_to_battle_not_a_relaunch(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(MENU, 6)
        self.assertEqual(w.kinds(), ["back_to_battle"])
        self.assertEqual(w.repairs[0][0], 4 * E + 6 * E, "60 s of grace, then two looks")


class Suspension(unittest.TestCase):
    def test_free_play_suspends_it(self):
        w = Watch()
        w.mode = "free"
        w.looks(GONE, 10)
        self.assertEqual((w.symptoms, w.alerts(), w.repairs), ([], [], []))
        self.assertEqual(w.paused[-1], "Jeu libre : rien n’est surveillé")

    def test_a_modes_entry_suspends_it(self):
        self.assertEqual(rules.paused("mpw4", None, 100, moving=True), "En pause : entrée dans le mode {mode}")
        self.assertIsNone(rules.paused("mpw4", None, 100))
        self.assertIsNone(rules.paused("mine", None, 100))

    def test_a_suspension_starts_over(self):
        w = Watch(available=())
        w.looks(BATTLE, 4)
        w.look(GONE)
        w.mode = "free"
        w.look(GONE)
        w.mode = "mpw18"
        w.look(GONE)
        self.assertEqual(w.alerts(), [], "one bad look, then one: no two in a row")


class Saver(unittest.TestCase):
    def test_power_saving_mode_is_well_with_no_stage(self):
        w = Watch()
        w.looks(SAVER, 10)
        self.assertEqual(set(w.symptoms), {None})
        self.assertEqual((w.alerts(), w.repairs), ([], []))

    def test_only_a_battle_look_says_wrong_stage(self):
        w = Watch()
        w.looks(UNREAD, 5)
        self.assertEqual(set(w.symptoms), {None}, "unread is not wrong")
        w.looks(OTHER_STAGE, 2)
        self.assertEqual(w.symptoms[-1], "wrong_stage")
        self.assertEqual(w.alerts(), [("warning", "Farming mpw18 : mauvais stage, pas le 920")])
        self.assertEqual(w.kinds(), ["stage_change"])


class Repairs(unittest.TestCase):
    def test_the_first_looks_after_a_start_only_observe(self):
        w = Watch()
        w.looks(GONE, 2)
        self.assertEqual(w.repairs, [])
        w.look(GONE)
        self.assertEqual(w.kinds(), ["relaunch"])

    def test_one_repair_then_its_verification(self):
        w = Watch()
        w.looks(GONE, 3)
        w.look(BATTLE)
        self.assertIn("Réparation réussie : {repair}", [r[2] for r in w.records])
        self.assertEqual(w.memory["verifying"], None)

    def test_a_repair_that_did_not_take_is_watched_2_minutes(self):
        w = Watch()
        w.looks(GONE, 3)
        w.look(GONE)
        w.looks(GONE, 7)
        self.assertEqual(len(w.repairs), 1, "no relaunch during the passive watch")
        self.assertEqual(rules.counters(w.memory, w.wall())["bad_in_a_row"], 11, "a repair does not reset it")
        self.assertEqual(len(w.alerts()), 2, "the problem's alert and its first failure's")
        without = [r for r in w.records if r[2].startswith("Réparation sans effet")]
        self.assertEqual([(r[1], r[4]) for r in without], [("warning", True)], "the first failure: a phone alert")
        self.assertEqual(without[0][3], {"repair": "relance du jeu", "minutes": 1})
        w.look(GONE)
        self.assertEqual(len(w.repairs), 2)

    def test_a_restart_never_resumes_a_repair(self):
        w = Watch()
        w.looks(GONE, 3)
        self.assertEqual(w.memory["verifying"], "relaunch")
        again = Watch(kept=rules.persisted(w.memory))
        again.now = w.now
        self.assertEqual(again.memory["verifying"], None)
        again.looks(GONE, 2)
        self.assertEqual(again.repairs, [], "observes its first two looks")

    def test_relaunch_and_back_to_battle_are_never_plan_only(self):
        w = Watch(act=False)
        w.looks(GONE, 3)
        w.looks(BATTLE, 1)
        w.looks(MENU, 6)
        self.assertEqual(w.kinds(), ["relaunch", "back_to_battle"])
        self.assertEqual(w.plans, [])

    def test_a_plan_only_stage_change_says_its_plan_once(self):
        w = Watch(act=False)
        w.looks(BATTLE, 3)
        w.looks(OTHER_STAGE, 20)
        self.assertEqual(w.repairs, [])
        self.assertEqual(w.plans, [(5 * E, "stage_change")])

    def test_a_lease_defers_the_repair_and_says_so_once(self):
        w = Watch()
        w.lease = "fps"
        w.looks(GONE, 10)
        self.assertEqual(w.repairs, [])
        deferred = [r[1:] for r in w.records if r[2].startswith("Réparation différée")]
        self.assertEqual(deferred, [("normal", "Réparation différée : bail tenu par {holder}", {"holder": "fps"},
                                     False)])
        w.lease = None
        w.look(GONE)
        self.assertEqual(len(w.repairs), 1)

    def test_a_repair_not_learned_yet_is_an_alert_only(self):
        w = Watch(available=("relaunch", "back_to_battle"))
        w.looks(BATTLE, 4)
        w.looks(OTHER_STAGE, 10)
        self.assertEqual(w.repairs, [])
        self.assertEqual(len(w.alerts()), 1)


class Backoff(unittest.TestCase):
    """Each kind backs off on its own after real failures: 1, 2, 4, 8, 16,
    then 30 minutes, never for good; few alerts; a durable recovery starts
    it over. On virtual time, a look every rules.EVERY seconds."""

    def gone_for(self, w, seconds):
        end = w.now + seconds
        while w.now < end:
            w.look(GONE)

    def test_the_delays(self):
        self.assertEqual([rules.delay(n) for n in range(9)], [0, 60, 120, 240, 480, 960, 1800, 1800, 1800])
        self.assertEqual((rules.delay(3, 1.0), rules.delay(3, -1.0)), (264.0, 216.0), "±10 %")

    def test_three_hours_gone_tries_on_and_on_further_apart(self):
        w = Watch()
        self.gone_for(w, 3 * 3600)
        times = [t for t, _ in w.repairs]
        gaps = [b - a for a, b in zip(times, times[1:])]
        # After each failure (seen a look later): its delay, the 2-minute
        # passive watch at least.
        for gap, wanted in zip(gaps, [120, 120, 240, 480, 960, 1800, 1800]):
            self.assertGreaterEqual(gap, wanted + E, gaps)
            self.assertLess(gap, wanted + 3 * E, gaps)
        self.assertGreaterEqual(times[-1], 3 * 3600 - 1800 - 3 * E, "it never stops")
        self.assertIn(rules.counters(w.memory, w.wall())["next_attempt"]["relaunch"]["failures"],
                      (len(times) - 1, len(times)))

    def test_the_alerts_first_failure_8_min_30_min_then_silence(self):
        w = Watch()
        self.gone_for(w, 3 * 3600)
        said = [(text, params.get("minutes")) for _, level, text, params, notify in w.records if notify]
        self.assertEqual(said, [
            ("{mode} : le jeu ne tourne pas", None),
            ("Réparation sans effet : {repair}, prochain essai dans {minutes} min", 1),
            ("{mode} : {repair} toujours en échec, prochaine tentative dans {minutes} min", 8),
            ("{mode} : {repair} toujours en échec, prochaine tentative dans {minutes} min", 30)])
        self.assertEqual({params.get("mode") for _, _, text, params, notify in w.records if notify and "{mode}" in text},
                         {"Farming mpw18"})
        self.assertFalse([r for r in w.records if "bloquée" in r[2].lower()])

    def test_the_status_says_when_the_next_try_is(self):
        w = Watch()
        self.gone_for(w, 600)
        self.assertGreater(rules.waiting(w.memory, "not_running", w.wall()), 0)
        self.assertIsNone(rules.waiting(w.memory, "menu", w.wall()))

    def test_a_durable_recovery_starts_over_a_short_one_does_not(self):
        w = Watch()
        self.gone_for(w, 15 * 60)
        failures = w.memory["backoff"]["relaunch"]["failures"]
        last = w.memory["backoff"]["relaunch"]["delay"]
        self.assertGreaterEqual(last, 480)
        # Two minutes of battle: shorter than the last delay.
        w.looks(BATTLE, 8)
        self.assertEqual(w.memory["backoff"]["relaunch"]["failures"], failures)
        # The last delay of battle: durable.
        w.looks(BATTLE, int(last // E) + 1)
        self.assertEqual(w.memory["backoff"], {})
        self.assertEqual(w.notifications()[-1], "Farming mpw18 : rétabli")

    def test_a_short_delay_needs_the_5_minute_floor(self):
        w = Watch()
        self.gone_for(w, 90)
        self.assertEqual(w.memory["backoff"]["relaunch"]["failures"], 1)
        w.looks(BATTLE, rules.RECOVERY_FLOOR // E - 1)
        self.assertIn("relaunch", w.memory["backoff"])
        w.looks(BATTLE, 2)
        self.assertEqual(w.memory["backoff"], {})

    def test_the_backoff_survives_a_gateway_restart(self):
        w = Watch()
        self.gone_for(w, 15 * 60)
        state = w.memory["backoff"]["relaunch"]
        again = Watch(kept=rules.persisted(w.memory))
        again.now = w.now
        self.assertEqual(again.memory["backoff"]["relaunch"], state)
        while again.wall() < state["next"] - E:
            again.look(GONE)
        self.assertEqual(again.repairs, [], "no attempt before its next time")
        again.looks(GONE, 3)
        self.assertEqual(again.kinds(), ["relaunch"])
        self.assertEqual(rules.kept_backoff({"relaunch": {"failures": "x"}, "nope": {}}), {})

    def test_a_deferral_or_a_plan_does_not_count(self):
        w = Watch()
        w.lease = "fps"
        w.looks(GONE, 20)
        self.assertEqual((w.repairs, w.memory["backoff"]), ([], {}))
        w = Watch(act=False)
        w.looks(BATTLE, 3)
        w.looks(OTHER_STAGE, 20)
        self.assertEqual(w.memory["backoff"], {})
        # A repair the feature deferred (Busy): not_run, then the same symptom.
        w = Watch()
        w.looks(GONE, 3)
        w.memory = rules.not_run(w.memory, "relaunch")
        w.look(GONE)
        self.assertEqual(w.memory["backoff"], {})
        self.assertFalse([r for r in w.records if r[2].startswith("Réparation sans effet")])

    def test_a_sequence_that_stopped_counts_once(self):
        w = Watch()
        w.looks({**BATTLE, "stage": 921}, 3)
        self.assertEqual(w.memory["verifying"], "stage_change")
        w.memory, said = rules.stopped(w.memory, "stage_change", w.wall())
        self.assertEqual([a[4] for a in said], [True])
        w.look({**BATTLE, "stage": 921})
        self.assertEqual(w.memory["backoff"]["stage_change"]["failures"], 1)

    def test_a_user_input_keeps_the_delay(self):
        w = Watch()
        self.gone_for(w, 15 * 60)
        before = dict(w.memory["backoff"]["relaunch"])
        w.tap()
        w.looks(GONE, 5)
        self.assertEqual(w.memory["backoff"]["relaunch"], before)

    def test_retry_now_starts_the_kind_over(self):
        w = Watch()
        self.gone_for(w, 15 * 60)
        w.memory = rules.retry(w.memory, "relaunch")
        count = len(w.repairs)
        w.look(GONE)
        self.assertEqual(len(w.repairs), count + 1, "at once")

    def test_each_kind_backs_off_on_its_own(self):
        w = Watch()
        self.gone_for(w, 15 * 60)
        w.looks(BATTLE, 1)
        w.looks(MENU, 6)
        self.assertEqual(w.kinds()[-1], "back_to_battle")
        self.assertNotIn("back_to_battle", w.memory["backoff"])


class Profile(unittest.TestCase):
    LOADOUT = {"preset": "III", "soul_weapon": {"id": 32, "variant": "Gold"}, "weapon": "Ambition"}

    def test_the_stage_and_the_modes_loadout(self):
        self.assertEqual(rules.profile(None, 920),
                         {"mode": "mpw18", "stage": 920, "preset": None, "soul_weapon": None})
        self.assertEqual(rules.profile(self.LOADOUT, 915, "mpw4"),
                         {"mode": "mpw4", "stage": 915, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold"}})
        self.assertIsNone(rules.profile({}, None)["stage"], "no mpw18 stage chosen yet")
        for bad in ({"preset": "VI"}, {"preset": 3}, {"soul_weapon": {"id": "32"}}, {"soul_weapon": 32}, 3):
            profile = rules.profile(bad, 920)
            self.assertEqual((profile["preset"], profile["soul_weapon"]), (None, None), bad)

    def test_a_wrong_preset_read_on_battle_is_its_symptom(self):
        profile = rules.profile(self.LOADOUT, 920)
        seen = {**BATTLE, "battle_settings": "II"}
        symptom, _, params, _ = rules.judge(seen, profile, NUMERALS.get, None, False, rules.fresh(), 60)
        self.assertEqual((symptom, params), ("wrong_battle_settings", {"preset": "III"}))
        unread = rules.judge(BATTLE, profile, NUMERALS.get, None, False, rules.fresh(), 60)[0]
        self.assertIsNone(unread, "not read is not wrong")


class StageAndControls(unittest.TestCase):
    """The stage read whole (region and numeral), and the preset and AUTO
    read on the unfolded controls, with the stage change feature's repairs."""

    def test_another_region_with_the_same_numeral_is_a_wrong_stage(self):
        # 940 ends with the same numeral as 920: read whole, it is wrong.
        seen = {**BATTLE, "stage": 940}
        symptom, _, params, _ = rules.judge(seen, PROFILE, NUMERALS.get, None, False, rules.fresh(), 60)
        self.assertEqual((symptom, params), ("wrong_stage", {"stage": 920}))
        good = rules.judge({**BATTLE, "stage": 920}, PROFILE, NUMERALS.get, None, False, rules.fresh(), 60)
        self.assertEqual((good[0], good[1]), (None, "OK (stage {stage})"))

    def test_wrong_stage_is_farmed_back_with_its_backoff(self):
        w = Watch()
        w.looks({**BATTLE, "stage": 921}, 4)
        self.assertEqual(w.kinds(), ["stage_change"])
        w.looks({**BATTLE, "stage": 921}, 40)
        # 10 minutes: tries at about 1, 3 (the 2-minute watch), 5 and 9 minutes.
        self.assertEqual(w.kinds().count("stage_change"), 4, w.repairs)
        self.assertEqual(w.memory["backoff"]["stage_change"]["failures"], 4)

    def test_auto_off_is_its_symptom_and_repair(self):
        w = Watch()
        w.looks({**BATTLE, "auto": "off"}, 3)
        self.assertEqual(w.symptoms[-1], "auto_off")
        self.assertEqual(w.kinds(), ["auto_on"])
        self.assertIsNone(rules.judge({**BATTLE, "auto": None}, PROFILE, NUMERALS.get, None, False,
                                      rules.fresh(), 60)[0], "unread is not off")

    def test_a_switch_on_plan_plans_once(self):
        w = Watch(act=False)
        w.looks({**BATTLE, "auto": "off"}, 6)
        self.assertEqual(w.kinds(), [])
        self.assertEqual([kind for _, kind in w.plans], ["auto_on"])


class GoldAtZero(unittest.TestCase):
    """gold/s at 0 over a full window, two fresh readings in a row: AUTO is
    read at once. A trigger, never a proof: AUTO is tapped only on an OFF
    reading; read ON, one alert."""

    def zeros(self, readings):
        """rules.gold_zero over (rate, span, age) readings, one new sample
        each (age seconds old; rate "none": no gold reading); the triggers."""
        kept, triggers = rules.gold_fresh(), []
        for i, (rate, span, age) in enumerate(readings):
            wall = EPOCH + E * i
            gold = None if rate == "none" else {"rate": rate, "span": span, "last": wall - age}
            kept, trigger = rules.gold_zero(kept, gold, wall)
            triggers.append(trigger)
        return kept, triggers

    def test_two_fresh_zero_readings_over_a_full_window_trigger_once(self):
        self.assertEqual(self.zeros([(0, 300, 5)] * 4)[1], [False, True, False, False])

    def test_a_short_window_or_no_rate_or_gold_above_0_starts_over(self):
        self.assertEqual(self.zeros([(0, 300, 5), (0, 200, 5), (0, 300, 5)])[1], [False] * 3)
        self.assertEqual(self.zeros([(0, 300, 5), (None, 300, 5), (0, 300, 5)])[1], [False] * 3)
        self.assertEqual(self.zeros([(0, 300, 5), (12.5, 300, 5), (0, 300, 5)])[1], [False] * 3)
        self.assertEqual(self.zeros([(0, 300, 5), (12.5, 300, 5), (0, 300, 5), (0, 300, 5)])[1],
                         [False, False, False, True])

    def test_a_stale_sample_or_none_is_not_a_reading(self):
        # The gold feature off the battle screen: its last sample grows old.
        self.assertEqual(self.zeros([(0, 300, 5), (0, 300, 60), (0, 300, 60)])[1], [False] * 3)
        self.assertEqual(self.zeros([(0, 300, 5), ("none", 0, 0), (0, 300, 5)])[1], [False, False, True])

    def test_the_same_sample_twice_is_one_reading(self):
        kept, trigger = rules.gold_zero(rules.gold_fresh(), {"rate": 0, "span": 300, "last": EPOCH}, EPOCH + 1)
        kept, trigger = rules.gold_zero(kept, {"rate": 0, "span": 300, "last": EPOCH}, EPOCH + 16)
        self.assertEqual((kept["zeros"], trigger), (1, False))

    def test_auto_on_is_one_alert_until_gold_is_back(self):
        kept, _ = self.zeros([(0, 300, 5)] * 2)
        kept, alert = rules.gold_alert(kept, "on")
        self.assertTrue(alert)
        self.assertFalse(rules.gold_alert(kept, "on")[1], "said once")
        self.assertFalse(rules.gold_alert(self.zeros([(0, 300, 5)] * 2)[0], "off")[1])
        self.assertFalse(rules.gold_alert(self.zeros([(0, 300, 5)] * 2)[0], None)[1])
        kept, _ = rules.gold_zero(kept, {"rate": 3.0, "span": 300, "last": EPOCH + 100}, EPOCH + 101)
        self.assertFalse(kept["alerted"], "gold back: the next time is said again")

    def test_gold_alone_is_never_a_symptom(self):
        # judge sees only the AUTO reading: unread (None) is no auto_off.
        self.assertIsNone(rules.judge({**BATTLE, "auto": None}, PROFILE, NUMERALS.get, None, False,
                                      rules.fresh(), 60)[0])


class GoldTrigger(unittest.TestCase):
    """features/watchdog.py on fake ports, the battle screen at each look
    (rules.EVERY apart), gold/s always 0 over a full window: when the
    preset and AUTO are read."""

    def looks(self, count, auto, viewers=lambda look: 0, stage=920, answer=None, mode="mpw18", entering=False,
              game=True, launched=False):
        """count looks, AUTO read as auto, viewers(look) connected; (the
        looks that read the controls, the alerts, the farming calls other
        than reading); self.state: GET /watchdog's at the end."""
        spec = importlib.util.spec_from_file_location("watchdog_feature", os.path.join(HERE, "features", "watchdog.py"))
        feature = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(feature)
        self.every = feature.CONTROLS_EVERY
        coroutines, looked, read, alerts, other = [], [0], [], [], []

        class Ports:
            class Busy(RuntimeError):
                pass

            store = types.SimpleNamespace(saved={}, register=lambda *a: None, save=lambda: None)
            lease = types.SimpleNamespace(state=lambda: None)
            enabled = staticmethod(lambda: True)
            log = staticmethod(LOG)
            exception = staticmethod(EXCEPTION)
            respond = staticmethod(lambda body, status=200: body if status == 200 else (status, body))

            class clock:
                now = 0.0
                monotonic = staticmethod(lambda: Ports.clock.now)
                wall = staticmethod(lambda: EPOCH + Ports.clock.now)

                @staticmethod
                async def sleep(seconds):
                    if looked[0] == count:
                        raise asyncio.CancelledError
                    looked[0] += 1
                    Ports.clock.now += seconds

            @staticmethod
            def spawn(coroutine):
                coroutines.append(coroutine)

            last_input = staticmethod(lambda: None)

            @staticmethod
            async def user_input():
                return None
            viewers = staticmethod(lambda: viewers(looked[0]))

            @staticmethod
            async def running():
                return True

            @staticmethod
            async def dialog():
                return None

            @staticmethod
            async def focus():
                return {"game": game, "window": "game" if game else "com.android.launcher3/.Launcher"}

            @staticmethod
            async def capture(max_age):
                return "shot"

            @staticmethod
            async def analyse(facts, shot):
                return "battle", 3, stage

            @staticmethod
            async def notify(text):
                alerts.append(text)

        async def read_controls():
            read.append(looked[0])
            return {"preset": 1, "auto": auto}

        async def refused(*args):
            other.append(("ensure_auto", *args))
            return {"result": "plan", "text": "plan"}

        self.farmed = farmed = []
        self.confirmed = confirmed = []
        self.launches = launches_made = []
        self.reentered = reentered = []

        async def launch():
            launches_made.append(looked[0])

        def start(*args):
            return launch() if launched else None

        async def reenter():
            reentered.append(looked[0])
            return {"result": "done", "text": ""}

        async def farm(*args):
            farmed.append(args)
            return answer or {"result": "plan", "text": "plan"}

        farming = {"read_controls": read_controls, "battle_stage": lambda shot: stage, "ensure_auto": refused,
                   "farm": farm, "switches": lambda: {"stage_change": "real", "preset": "plan", "auto": "plan"}}
        gold = {"current": lambda: {"rate": 0, "span": 300, "last": Ports.clock.wall() - 1}}
        built = feature.watchdog(
            Ports, None, None, rules, NUMERALS.get,
            {"state": lambda: {"mode": mode, "highest": 925, "state": "moving" if entering else "farming"},
             "confirm": confirmed.append},
            {"state": lambda: {"enabled": mode == "mine"}, "reenter": reenter},
            {"running": lambda: False, "start": start, "state": lambda: {"state": "done", "message": ""}},
            lambda name: {"mpw18": {"stage": 920, "preset": 1}, "mpw4": {"stage": 915, "preset": "II"}}[name],
            farming, gold)

        async def run():
            await built["startup"][0](None)
            with self.assertRaises(asyncio.CancelledError):
                await coroutines[0]

        with self.assertLogs("cloudphone.slayer-legend", "INFO"):
            logging.getLogger("cloudphone.slayer-legend").info("GoldTrigger: %d looks", count)
            asyncio.run(run())
        self.state = asyncio.run(built["routes"][0][2](None))
        self.retry = lambda body: asyncio.run(built["routes"][1][2](types.SimpleNamespace(json=lambda: body())))
        return read, alerts, other

    def test_a_stopped_stage_change_is_one_failure_and_retry_clears_it(self):
        _, alerts, _ = self.looks(8, "on", stage=940, answer={"result": "failed", "text": "écran inattendu"})
        self.assertEqual(len(self.farmed), 1, "then its passive watch and delay")
        self.assertEqual(self.state["counters"]["next_attempt"]["stage_change"]["failures"], 1, "counted once")
        stopped = [a for a in alerts if "Réparation arrêtée" in a]
        self.assertEqual(len(stopped), 1)
        self.assertIn("écran inattendu", stopped[0])

        async def body():
            return {"kind": "stage_change"}
        self.assertEqual(self.retry(body)["counters"]["next_attempt"], {})

        async def wrong():
            return {"kind": "nope"}
        self.assertEqual(self.retry(wrong)[0], 400)

    def test_a_plan_stage_change_is_no_failure(self):
        self.looks(8, "on", stage=940, answer={"result": "plan", "text": "plan"})
        self.assertEqual(self.state["counters"]["next_attempt"], {})

    def test_the_second_zero_reads_auto_at_once_and_auto_on_is_one_alert(self):
        read, alerts, other = self.looks(24, "on")
        # The first look reads (nothing kept), the second zero at once (not
        # CONTROLS_EVERY later), then every CONTROLS_EVERY again.
        self.assertEqual(self.every, 300)
        self.assertEqual(read, [1, 2, 2 + self.every // E])
        self.assertEqual(len(alerts), 1)
        self.assertIn(rules.GOLD_ALERT, alerts[0])
        self.assertEqual(other, [], "AUTO read on: nothing tapped")

    def test_someone_watching_changes_nothing(self):
        # No viewer gate: watched or not (or a gateway that does not say),
        # the same reads and the same alert.
        alone = self.looks(6, "on")
        self.assertNotIn("controls", self.state)
        for viewers in (lambda look: 1, lambda look: None):
            self.assertEqual(self.looks(6, "on", viewers=viewers), alone)
        self.assertEqual(alone[0], [1, 2])

    def test_the_stage_repair_passes_the_highest_seen(self):
        # Another stage read on battle: farm() gets mode's highest, as mode.set_stage does.
        self.looks(8, "on", stage=940)
        stage, _, mode, highest = self.farmed[0]
        self.assertEqual((stage, mode, highest), (920, "mpw18", 925))

    def test_auto_off_after_the_trigger_is_the_usual_repair_on_plan(self):
        read, alerts, other = self.looks(8, "off")
        self.assertEqual(read[:2], [1, 2])
        self.assertFalse([a for a in alerts if rules.GOLD_ALERT in a])
        self.assertEqual(other, [], "the auto switch on plan: never ensure_auto")


class ModesOnTheFeature(GoldTrigger):
    """features/watchdog.py checks the selected mode, one scenario each
    (GoldTrigger's fake ports)."""

    def test_mpw4_repairs_its_own_stage_and_its_line_names_it(self):
        _, alerts, _ = self.looks(8, "on", stage=920, mode="mpw4")
        stage, preset, mode, highest = self.farmed[0]
        self.assertEqual((stage, preset, mode, highest), (915, "II", "mpw4", 925))
        self.assertIn("Farming mpw4 : mauvais stage, pas le 915", alerts)
        self.assertEqual(self.state["mode"], "mpw4")
        self.assertEqual(self.state["profile"]["stage"], 915)

    def test_a_look_that_sees_the_mode_farm_confirms_it(self):
        # The mode row leaves "failed" once the watchdog sees it farm.
        self.looks(4, "on")
        self.assertIn("mpw18", self.confirmed)

    def test_a_wrong_stage_confirms_nothing_until_repaired(self):
        self.looks(4, "on", stage=940)
        self.assertEqual(self.confirmed, [])

    def test_a_repair_done_confirms_the_mode(self):
        self.looks(8, "on", stage=940, answer={"result": "done", "text": ""})
        self.assertTrue(self.farmed)
        self.assertIn("mpw18", self.confirmed)

    def test_the_mine_and_free_play_confirm_nothing(self):
        self.looks(4, "on", mode="free")
        self.assertEqual(self.confirmed, [])

    def test_mpw18_ok_is_its_line(self):
        self.looks(4, "on")
        self.assertEqual(self.state["line"], {"template": "OK", "params": {}})
        self.assertEqual(self.state["waiting"], [])

    def test_a_backoff_waiting_is_in_the_line_and_retry_clears_it(self):
        self.looks(5, "on", stage=940, answer={"result": "failed", "text": "écran inattendu"})
        self.assertEqual(self.state["waiting"], ["stage_change"])
        self.assertEqual(self.state["line"]["template"], "{repair} dans {minutes} min")
        self.assertEqual(self.state["line"]["params"]["repair"], "changement de stage")

        async def body():
            return {"kind": "stage_change"}
        self.assertEqual(self.retry(body)["waiting"], [])

    def test_the_mine_never_reads_the_controls_and_alerts_once_the_game_is_away(self):
        read, alerts, other = self.looks(14, "off", mode="mine", game=False)
        self.assertEqual((read, other, self.farmed), ([], [], []))
        self.assertEqual(alerts, ["Mine fermée : le jeu n’est plus au premier plan"])

    def test_the_mine_relaunches_the_game_then_goes_back_in(self):
        self.looks(14, "off", mode="mine", game=False, launched=True)
        self.assertTrue(self.launches)
        self.assertEqual(self.reentered, self.launches, "each relaunch, then the mine's way back in")
        self.assertEqual(self.farmed, [])

    def test_a_modes_entry_is_waited_for(self):
        read, alerts, other = self.looks(6, "off", stage=940, entering=True)
        self.assertEqual((read, alerts, other, self.farmed), ([], [], [], []))
        self.assertEqual(self.state["status"]["template"], "En pause : entrée dans le mode {mode}")
        self.assertEqual(self.state["line"]["params"], {"mode": "Farming mpw18"})

    def test_free_play_looks_at_nothing(self):
        read, alerts, other = self.looks(6, "off", stage=940, mode="free", game=False)
        self.assertEqual((read, alerts, other, self.farmed), ([], [], [], []))
        self.assertEqual(self.state["line"]["template"], "Jeu libre : rien n’est surveillé")


class Focus(unittest.TestCase):
    """Another app in front counts only AWAY_AFTER looks in a row; a
    passing window or a focus Android does not say is never "away"."""

    def test_one_look_with_another_window_is_not_away(self):
        w = Watch()
        w.looks(BATTLE, 4)
        for _ in range(5):
            w.look(AWAY)
            w.look(BATTLE)
        self.assertNotIn("away", w.symptoms)
        self.assertEqual((w.kinds(), w.alerts()), ([], []))

    def test_two_looks_in_a_row_are_away(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(AWAY, 2)
        self.assertEqual(w.symptoms[-2:], ["unknown", "away"])

    def test_the_away_alert_names_the_window(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks({**AWAY, "window": "com.android.launcher3/.Launcher"}, 3)
        alert = next(r for r in w.records if r[4])
        self.assertEqual(alert[2].format(**alert[3]), "Farming mpw18 : une autre application est au premier plan : "
                                                      "com.android.launcher3/.Launcher")

    def test_googles_window_is_the_sign_in_path(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks({**AWAY, "window": "com.google.android.gms/.games.ui.signin.SignInActivity"}, 3)
        self.assertEqual(w.symptoms[-1], "sign_in")
        self.assertEqual(w.kinds(), ["relaunch"])

    def test_cannot_tell_is_no_symptom(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks({**AWAY, "focused": None}, 10)
        self.assertEqual(set(w.symptoms[4:]), {"unknown"})
        self.assertEqual((w.kinds(), w.alerts()), ([], []))


class SignInScreen(unittest.TestCase):
    def test_the_sign_in_screen_is_relaunched(self):
        # The relaunch signs in with Google (launch_rules), once per relaunch.
        w = Watch()
        w.looks({**BATTLE, "screen": "sign_in"}, 4)
        self.assertEqual(w.symptoms[-1], "sign_in")
        self.assertEqual(w.kinds(), ["relaunch"])
        self.assertIn("Sign in with Google", w.alerts()[0][1])


class NotResponding(unittest.TestCase):
    def test_an_anr_is_one_alert_and_never_a_relaunch(self):
        w = Watch()
        w.looks(BATTLE, 3)
        w.looks(ANR, 6)
        self.assertEqual(w.symptoms[-1], "anr")
        self.assertEqual(w.repairs, [])
        self.assertEqual(len(w.alerts()), 1)
        self.assertIn("ne répond pas", w.alerts()[0][1])


class WaitOnTheDialog(unittest.TestCase):
    """features/watchdog.py's own "Wait" on Android's ANR dialog, on fake
    ports: one look every rules.EVERY seconds, the dialog always there."""

    def looks(self, shots):
        """One look per capture given (None: missing); the looks that
        pressed Wait."""
        spec = importlib.util.spec_from_file_location("watchdog_feature", os.path.join(HERE, "features", "watchdog.py"))
        feature = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(feature)
        shots, pressed, coroutines, looked = list(shots), [], [], [0]

        class Ports:
            class Busy(RuntimeError):
                pass

            store = types.SimpleNamespace(saved={}, register=lambda *a: None, save=lambda: None)
            lease = types.SimpleNamespace(state=lambda: None)
            enabled = staticmethod(lambda: True)
            log = staticmethod(LOG)
            exception = staticmethod(EXCEPTION)
            respond = staticmethod(lambda body: body)

            class clock:
                now = 0.0
                monotonic = staticmethod(lambda: Ports.clock.now)
                wall = staticmethod(lambda: EPOCH + Ports.clock.now)

                @staticmethod
                async def sleep(seconds):
                    if looked[0] == len(shots):
                        raise asyncio.CancelledError
                    looked[0] += 1
                    Ports.clock.now += seconds

            @staticmethod
            def spawn(coroutine):
                coroutines.append(coroutine)

            last_input = staticmethod(lambda: None)

            @staticmethod
            async def user_input():
                return None

            @staticmethod
            async def running():
                return True

            @staticmethod
            async def dialog():
                return "anr"

            @staticmethod
            async def capture(max_age):
                return shots[looked[0] - 1]

            @staticmethod
            @contextlib.asynccontextmanager
            async def leased(holder, reason, seconds):
                yield

            @staticmethod
            async def wait_anr(shot):
                pressed.append(looked[0] - 1)
                return True

            @staticmethod
            async def notify(text):
                pass

        built = feature.watchdog(
            Ports, None, None, rules, NUMERALS.get, {"state": lambda: {"mode": "mpw18"}, "confirm": lambda name: None},
            {"state": lambda: {"enabled": False}},
            {"running": lambda: False, "start": lambda *a: None, "state": lambda: {}}, lambda mode: None)

        async def run():
            await built["startup"][0](None)
            with self.assertRaises(asyncio.CancelledError):
                await coroutines[0]

        with self.assertLogs("cloudphone.slayer-legend", "INFO"):
            asyncio.run(run())
        return pressed

    def test_wait_is_pressed_once_per_dialog(self):
        self.assertEqual(self.looks(["shot", "shot", "shot"]), [0])

    def test_a_missing_capture_tries_wait_again_at_the_next_look(self):
        self.assertEqual(self.looks([None, "shot", "shot"]), [1])


class AfterMode(unittest.TestCase):
    """Free play ended: the game here may show "connected on another
    device" or a choice of saves (not mapped yet)."""

    def test_another_screen_is_an_alert_after_2_looks_and_no_repair(self):
        w = Watch()
        w.looks(BATTLE, 3)
        w.after_mode = True
        w.looks(OTHER, 2)
        self.assertEqual(w.symptoms[-1], "after_mode_screen")
        self.assertEqual(len(w.alerts()), 1)
        self.assertIn("autre appareil", w.alerts()[0][1])
        w.looks(OTHER, 10)
        self.assertEqual(w.repairs, [])
        self.assertEqual(len(w.alerts()), 1, "said once")

    def test_the_save_notice_and_the_title_are_relaunched(self):
        for seen in (TITLE, {**TITLE, "screen": "save"}):
            w = Watch()
            w.looks(BATTLE, 3)
            w.after_mode = True
            w.looks(seen, 2)
            self.assertEqual(w.repairs, [(w.now, "relaunch")], seen)

    def test_later_another_screen_is_the_usual_other(self):
        w = Watch()
        w.looks(BATTLE, 3)
        w.looks(OTHER, 3)
        self.assertEqual(w.symptoms[-1], "unexpected")
        self.assertEqual(w.alerts(), [], "4 looks for another screen")


class Flapping(unittest.TestCase):
    """Critique's scenarios: the state flaps; one disruption is few alerts."""

    def test_b_a_pop_up_that_reopens_after_each_way_back(self):
        w = Watch()
        w.looks(BATTLE, 3)
        for _ in range(12):
            w.looks(MENU, 6)
            w.look(BATTLE)
        self.assertLessEqual(len(w.notifications()), 3, w.notifications())
        # Each way back worked: no failure, no backoff, a way back each time.
        self.assertEqual(w.memory["backoff"], {})
        self.assertEqual(w.kinds(), ["back_to_battle"] * 12)

    def pop_ups(self, every, minutes):
        """A pop-up (a menu over the battle) every `every` seconds for
        `minutes`, each closed by the way back (or by itself: 1 good look
        and it comes back when every is 0); (notifications per hour, ways
        back, pop-ups)."""
        w = Watch()
        w.looks(BATTLE, 4)
        start, shown = w.now, 0
        while w.now - start < minutes * 60:
            shown += 1
            opened = w.now
            while w.look(MENU) != "menu" or not w.repairs or w.repairs[-1][0] < opened:
                pass
            w.look(BATTLE)
            while every and w.now - opened < every:
                w.look(BATTLE)
        hours = (w.now - start) / 3600
        return len(w.notifications()) / max(hours, 1), len(w.repairs), shown

    def test_b1_a_pop_up_back_after_one_good_look_for_22_minutes(self):
        per_hour, repairs, shown = self.pop_ups(0, 22)
        self.assertLessEqual(per_hour, 4)
        self.assertEqual(repairs, shown, "one way back per pop-up, no cap")

    def test_b2_a_pop_up_every_2_minutes_for_85_minutes(self):
        per_hour, repairs, shown = self.pop_ups(120, 85)
        self.assertLessEqual(per_hour, 4)
        self.assertEqual(repairs, shown)

    def test_b3_a_pop_up_every_6_minutes_for_an_hour(self):
        per_hour, repairs, shown = self.pop_ups(360, 60)
        self.assertLessEqual(per_hour, 4)
        self.assertEqual(repairs, shown)

    def test_a_relaunch_then_a_pop_up_on_return(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(AWAY, 3)
        w.looks(MENU, 6)
        w.looks(BATTLE, 4)
        self.assertNotIn("Farming mpw18 : rétabli", w.notifications(), "repaired: 5 minutes of battle first")
        w.looks(BATTLE, rules.RECOVERY_FLOOR // E)
        self.assertEqual(w.kinds(), ["relaunch", "back_to_battle"])
        self.assertLessEqual(len(w.notifications()), 2, w.notifications())
        self.assertEqual(w.notifications()[-1], "Farming mpw18 : rétabli")

    def test_c_a_missed_capture_keeps_the_menu_grace(self):
        w = Watch()
        w.looks(MENU, 3)
        self.assertEqual(w.look(NO_CAPTURE), "unknown")
        self.assertEqual(w.look(MENU), "menu", "60 s after the menu was first seen, the missed capture included")

    def test_a_menu_inside_its_grace_changes_nothing(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(GONE, 2)
        before = dict(w.memory)
        w.look(MENU)
        self.assertEqual(w.symptoms[-1], "pending")
        after = dict(w.memory)
        for key in ("looks", "menu_since"):
            before.pop(key), after.pop(key)
        self.assertEqual(after, before)


class Status(unittest.TestCase):
    def test_the_status_says_the_numeral_never_a_stage_number(self):
        _, text, params, _ = rules.judge(BATTLE, PROFILE, NUMERALS.get, None, False, rules.fresh(), 60)
        self.assertEqual(rules.status(text, params), ("{mode} : OK (numéral {numeral})",
                                                      {"numeral": "III", "mode": "Farming mpw18"}))
        self.assertEqual(rules.status(text, params, "mpw4")[1]["mode"], "Farming mpw4")


class Modes(unittest.TestCase):
    """One scenario per mode: the watchdog checks the selected one."""

    def test_mpw18_farming_a_wrong_stage_is_its_stage_change(self):
        w = Watch()
        w.looks(BATTLE, 3)
        w.looks({**BATTLE, "stage": 921, "numeral": 4}, 2)
        self.assertEqual(w.alerts(), [("warning", "Farming mpw18 : mauvais stage, pas le 920")])
        self.assertEqual(w.kinds(), ["stage_change"])

    def test_mpw4_farming_has_its_own_stage_and_names_itself(self):
        w = Watch(profile=rules.profile({"preset": "II"}, 915, "mpw4"))
        w.looks({**BATTLE, "stage": 915, "numeral": None}, 3)
        self.assertEqual(w.symptoms, [None] * 3, "915 is mpw4's stage")
        w.looks({**BATTLE, "stage": 920}, 2)
        self.assertEqual(w.alerts(), [("warning", "Farming mpw4 : mauvais stage, pas le 915")])
        self.assertEqual(w.kinds(), ["stage_change"])
        w.looks({**BATTLE, "stage": 915, "battle_settings": "I"}, 2)
        self.assertEqual(w.symptoms[-1], "wrong_battle_settings", "its own preset")

    def test_the_mine_owns_no_screen_and_alerts_once_when_the_game_is_away(self):
        w = Watch(profile=rules.profile(None, None, "mine"), available=ALL + ("mine_relaunch",))
        w.looks(OTHER, 6)
        w.looks(MENU, 6)
        self.assertEqual(set(w.symptoms), {None}, "the mine's screens are the mine feature's")
        self.assertEqual(w.repairs, [])
        w.looks(AWAY, rules.MINE_AWAY_LOOKS)
        self.assertEqual(w.kinds()[:1], ["mine_relaunch"], "relaunched, then the mine's way back in")
        self.assertLessEqual(w.repairs[0][0], w.now - (rules.MINE_AWAY_LOOKS - rules.REPAIR_AFTER - 1) * E,
                             "before the alert's 2 minutes")
        w.looks(AWAY, 20)
        self.assertIn(("warning", "Mine fermée : le jeu n’est plus au premier plan"), w.alerts())
        # Each attempt after its backoff, never two in a row.
        times = [t for t, kind in w.repairs if kind == "mine_relaunch"]
        self.assertGreater(len(times), 1)
        self.assertGreaterEqual(times[1] - times[0], rules.DELAYS[1] * (1 - rules.JITTER))
        w.looks(GONE, 5)
        w.looks(CRASH, 5)
        self.assertEqual(len([a for a in w.alerts() if "premier plan" in a[1]]), 1, "one absence, one alert")

    def test_the_mine_relaunches_a_game_back_on_its_title_screen(self):
        w = Watch(profile=rules.profile(None, None, "mine"), available=ALL + ("mine_relaunch",))
        w.looks(OTHER, rules.OBSERVE_FIRST)
        w.looks(TITLE, rules.REPAIR_AFTER)
        self.assertEqual(w.symptoms[-rules.REPAIR_AFTER:], ["mine_away"] * rules.REPAIR_AFTER)
        self.assertEqual(w.kinds(), ["mine_relaunch"])

    def test_free_play_checks_nothing(self):
        w = Watch()
        w.mode = "free"
        for seen in (GONE, CRASH, AWAY, OTHER, OTHER_STAGE):
            w.looks(seen, 10)
        self.assertEqual((w.symptoms, w.alerts(), w.repairs, w.plans), ([], [], [], []))


if __name__ == "__main__":
    unittest.main()
