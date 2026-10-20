"""The mpw18 watchdog's rules (features/watchdog_rules.py), offline: the
looks a scripted game gives, one every rules.EVERY seconds, through
judge() and decide(); and features/watchdog.py's Wait on Android's
ANR dialog, on fake ports. Run: python3 -m unittest test_watchdog
"""

import asyncio
import contextlib
import importlib.util
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("watchdog_rules", os.path.join(HERE, "features", "watchdog_rules.py"))
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)

EPOCH = 1_800_000_000.0
# Stage 920's name ends with III in this table; 921 with IV.
NUMERALS = {920: 3, 921: 4}
PROFILE = rules.profile(None, 920)
ALL = ("relaunch", "back_to_battle", "stage_change", "select_preset", "loadout")

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

    def __init__(self, act=True, available=ALL, kept=None):
        self.memory = rules.fresh(kept)
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
            if self.mode != "mpw18":
                self.memory = rules.suspended(self.memory)
            self.paused.append(why)
            return None
        symptom, text, params, self.memory = rules.judge(
            seen, PROFILE, NUMERALS.get, self.input, self.resumed, self.memory, self.now, self.after_mode)
        self.resumed = False
        self.symptoms.append(symptom)
        context = {"input_wall": None if self.input is None else EPOCH + self.input, "lease": self.lease,
                   "act": self.act, "available": self.available}
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
        return [(level, text) for _, level, text, params, notify in self.records if notify]

    def kinds(self):
        return [kind for _, kind in self.repairs]

    def notifications(self):
        return [text for _, level, text, params, notify in self.records if notify]


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
        w.looks(AWAY, 2)
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
    def test_every_other_mode_suspends_it(self):
        for mode in ("mpw4", "free", "mine"):
            w = Watch()
            w.mode = mode
            w.looks(GONE, 10)
            self.assertEqual((w.symptoms, w.alerts(), w.repairs), ([], [], []), mode)
            self.assertEqual(w.paused[-1], "En pause : mode {mode}")

    def test_a_suspension_starts_over(self):
        w = Watch(available=())
        w.looks(BATTLE, 4)
        w.look(GONE)
        w.mode = "mine"
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
        self.assertEqual(w.alerts(), [("warning", "Farming mpw18 : mauvais stage : pas le stage {stage}")])
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
        self.assertEqual(len(w.alerts()), 1, "one alert for the whole problem")
        without = [r for r in w.records if r[2].startswith("Réparation sans effet")]
        self.assertEqual([(r[1], r[4]) for r in without], [("warning", False)], "a warning, not a phone alert")
        w.look(GONE)
        self.assertEqual(len(w.repairs), 2)

    def test_three_relaunches_an_hour_then_blocked_with_one_alert(self):
        w = Watch()
        w.looks(GONE, 200)
        self.assertEqual(len(w.repairs), 3, w.repairs)
        blocked = [text for level, text in w.alerts() if text.startswith("Réparation bloquée")]
        self.assertEqual(len(blocked), 1)
        self.assertIn("relaunch", rules.counters(w.memory, w.wall())["blocked_since"])

    def test_back_to_battle_is_capped_at_10_an_hour(self):
        w = Watch()
        # A menu that comes back after each way back to battle.
        for _ in range(11):
            w.looks(BATTLE, 1)
            w.looks(MENU, 6)
        self.assertEqual(w.kinds(), ["back_to_battle"] * 10)
        self.assertEqual(len([t for _, t in w.alerts() if t.startswith("Réparation bloquée")]), 1)

    def test_blocked_clears_on_an_input(self):
        w = Watch()
        w.looks(GONE, 200)
        w.tap()
        w.looks(GONE, 5)
        self.assertEqual(w.paused, ["En pause : l’utilisateur joue"] * 4)
        self.assertEqual(w.memory["blocked"], {})
        self.assertEqual(len(w.repairs), 4, "the user took over: a new hourly count")
        self.assertEqual(len(w.alerts()), 2, "the problem's alert and one blocked alert")

    def test_a_good_look_does_not_clear_blocked(self):
        w = Watch()
        w.looks(GONE, 200)
        w.looks(BATTLE, 5)
        self.assertIn("relaunch", w.memory["blocked"])

    def test_blocked_clears_once_the_hour_frees_a_slot(self):
        w = Watch()
        w.looks(GONE, 200)
        first = w.repairs[0][0]
        while w.now < first + rules.HOUR:
            w.look(GONE)
        self.assertEqual(w.memory["blocked"], {})
        self.assertEqual(len(w.repairs), 4)

    def test_blocked_again_within_the_hour_is_not_said_again(self):
        w = Watch()
        w.looks(GONE, 200)
        w.tap()
        w.looks(GONE, 4)
        w.looks(GONE, 60)
        blocked = [t for t in w.notifications() if t.startswith("Réparation bloquée")]
        self.assertEqual(len(blocked), 1, w.notifications())

    def test_the_cap_survives_a_gateway_restart(self):
        w = Watch()
        w.looks(GONE, 130)
        self.assertEqual(len(w.repairs), 3)
        again = Watch(kept=rules.persisted(w.memory))
        again.now = w.now
        again.looks(GONE, 40)
        self.assertEqual(again.repairs, [], "the hour's three relaunches are kept")
        self.assertEqual(rules.counters(again.memory, again.wall())["repairs_this_hour"],
                         {"relaunch": 3, "back_to_battle": 0, "stage_change": 0, "select_preset": 0, "loadout": 0})

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


class Profile(unittest.TestCase):
    LOADOUT = {"preset": "III", "soul_weapon": {"id": 32, "variant": "Gold"}, "weapon": "Ambition"}

    def test_the_stage_and_mpw18s_loadout(self):
        self.assertEqual(rules.profile(None, 920), {"stage": 920, "preset": None, "soul_weapon": None})
        self.assertEqual(rules.profile(self.LOADOUT, 920),
                         {"stage": 920, "preset": "III", "soul_weapon": {"id": 32, "variant": "Gold"}})
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
            Ports, None, None, rules, NUMERALS.get, {"state": lambda: {"mode": "mpw18"}},
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
        self.assertLessEqual(len(w.repairs), 10)

    def test_a_relaunch_then_a_pop_up_on_return(self):
        w = Watch()
        w.looks(BATTLE, 4)
        w.looks(AWAY, 2)
        w.looks(MENU, 6)
        w.looks(BATTLE, 4)
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
        self.assertEqual(rules.status(text, params), ("Farming mpw18 : OK (numéral {numeral})", {"numeral": "III"}))


if __name__ == "__main__":
    unittest.main()
