"""The game's state (features/game.py, features/game_rules.py), offline:
the scan's mapping on real fixtures pasted back on an empty screen (each
screen gives the fields expected, and only those), the readers' time on
them (printed), the rules (the highest stage only goes up, a value once
seen is never null again, a relaunch keeps the values unverified), and
the feature on fake ports: the state kept in state.json across a gateway
restart, the highest stage of earlier versions taken over, a relaunch
heard from the ports, the user's changes logged, require() on a screen
that does not show a field.
Run: python3 -m unittest test_game"""

import asyncio
import importlib.util
import json
import os
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_game_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screens = load("screens")
rules = load("features/game_rules")
game = load("features/game")
reader_module = load("features/game_readers")
fact_module = load("features/game_facts")
observation_module = load("features/game_observation")


def create_game(ports, screens, rules, readers, archive=None, examples=None):
    registry = reader_module.ReaderRegistry(screens, rules, readers)
    facts = fact_module.FactStore(ports, rules)
    pipeline = observation_module.ObservationPipeline(ports, registry, facts, archive=archive)
    producer = observation_module.CaptureProducer(ports, pipeline)
    return game.game(ports, rules, facts, pipeline, producer, examples=examples)
ports_module = load("features/ports")
with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    WEAPONS = json.load(f)
READERS = reader_module.reader_table(screens, load("stage"), load("stage_select"), load("gold"), load("soul_counters"),
                            load("soul_weapon"), load("engraving_screen"), load("battle_controls"),
                            load("features/screen_rules"), TABLE, WEAPONS, load("cube_balance"),
                            load("top_currencies"))
W, H = 480, 1040
BATTLE = ("battle_emerald", "battle_menu_labels", "battle_mana_bar")


def screen(*names, background=(20, 16, 14)):
    """An empty 480x1040 screen with the crops pasted back where they were."""
    pixels = bytearray(bytes(background) * (W * H))
    for name in names:
        _, _, x, y, w, h, data = screens.fixture(name)
        for row in range(h):
            start = ((y + row) * W + x) * 3
            pixels[start:start + w * 3] = data[row * w * 3:(row + 1) * w * 3]
    return W, H, bytes(pixels)


# Each screen made of real crops, and the lasting fields its scan gives.
SCREENS = {
    "battle at stage 920": (BATTLE + ("battle_name_920", "bar_partial", "controls_iv"), None,
                            {"stage": 920, "highest": 920, "preset": "IV", "progress": 122 / 214}),
    "parked on the Soul Weapon screen": (
        ("battle_emerald", "sw_tabs", "sw_title", "gold_parked", "souls_row", "sw_name_vision", "sw_tag_unequip",
         "bar_parked_partial"), None,
        {"gold": {"text": "28.9F", "value": 2.89e19}, "soul_weapon_selected": "Vision",
         "soul_weapon_equipped": "Vision", "souls": None, "progress": None,
         "soul_green": None, "soul_blue": None, "soul_red": None, "soul_white": None}),
    "Select Region": (("battle_emerald", "title_select_region", "banner_giants_glass"), None,
                      {"region": "Giant's Glass"}),
    "Battle settings": (("battle_emerald", "settings_title", "settings_presets_iii"), None, {"preset": "III"}),
    "the engraving": (("eg_title", "eg_grid", "eg_cards"), (0, 0, 0), {"engraving": None}),
    "Power Saving Mode without its number": (("saver_mode",), (0, 0, 0), {}),
    "the sign-in screen": (("sign_in_buttons",), (90, 60, 35), {}),
}


class Mapping(unittest.TestCase):
    def test_real_top_bar_resources_are_scanned(self):
        shot = screen("top_currencies_battle", "battle_menu_labels", "battle_mana_bar")
        _, readings, ran = reader_module.read_all(screens, rules, READERS, shot)
        self.assertIn("currencies", ran)
        self.assertEqual(readings["emerald"], {"text": "276,362", "value": 276362})
        self.assertEqual(readings["diamond"], {"text": "984", "value": 984})

    def test_each_screen_gives_its_fields_and_only_those(self):
        timings = {}
        for case, (names, background, expected) in SCREENS.items():
            shot = screen(*names, background=background or (20, 16, 14))
            took = {}
            look, readings, ran = reader_module.read_all(screens, rules, READERS, shot, timings=took)
            facts, _ = rules.noted({}, readings, 1000.0)
            lasting = {field: fact["value"] for field, fact in rules.persisted(facts).items()}
            self.assertEqual(set(lasting), set(expected), f"{case}: {look['screen']} {look['overlays']} {ran}")
            for field, value in expected.items():
                if value is None:
                    continue
                if isinstance(value, float):
                    self.assertAlmostEqual(lasting[field], value, msg=case)
                else:
                    self.assertEqual(lasting[field], value, case)
            for reader, seconds in took.items():
                timings.setdefault(reader, []).append(seconds)
        print("\nScan readers on the fixtures (ms, worst):",
              ", ".join(f"{reader} {max(seconds) * 1000:.0f}" for reader, seconds in sorted(timings.items())))
        # A reader run on every capture stays cheap: the looks keep their pace.
        for reader, seconds in timings.items():
            if not rules.READERS[reader]["every"]:
                self.assertLess(max(seconds), 0.3, reader)

    def test_the_souls_row_reads_its_four_colours(self):
        names, background, _ = SCREENS["parked on the Soul Weapon screen"]
        _, readings, _ = reader_module.read_all(screens, rules, READERS, screen(*names))
        self.assertEqual({colour: count["text"] for colour, count in readings["souls"].items()},
                         {"green": "94.6C", "blue": "19.4C", "red": "16.1C", "white": "4.64C"})

    def test_the_engraving_grid_reads_its_pieces(self):
        names, background, _ = SCREENS["the engraving"]
        _, readings, _ = reader_module.read_all(screens, rules, READERS, screen(*names, background=background))
        cells = readings["engraving"]["cells"]
        self.assertEqual(readings["engraving"]["weapon"], "Vision")
        self.assertEqual((len(cells), {len(row) for row in cells}), (5, {5}))
        self.assertTrue(readings["engraving"]["pieces"])

    def test_an_engraving_title_alone_reads_no_grid(self):
        _, readings, _ = reader_module.read_all(screens, rules, READERS, screen("eg_title", background=(0, 0, 0)))
        self.assertIsNone(readings["engraving"])

    def test_a_slow_reader_waits_its_turn_unless_forced(self):
        shot = screen(*SCREENS["battle at stage 920"][0])
        _, _, ran = reader_module.read_all(screens, rules, READERS, shot, {"battle_stage": 100.0, "gold": 100.0}, 105.0)
        self.assertNotIn("battle_stage", ran)
        self.assertIn("progress", ran)
        _, readings, ran = reader_module.read_all(screens, rules, READERS, shot, {"battle_stage": 100.0}, 105.0,
                                         force=("battle_stage",))
        self.assertEqual(readings["stage"], 920)

    def test_the_older_classifier_stands_in_for_an_unknown_screen(self):
        unknown = {"screen": "unknown", "overlays": []}
        self.assertIn("battle_stage", rules.readers_for(unknown, "battle"))
        self.assertIn("saver_stage", rules.readers_for(unknown, "saver"))
        self.assertEqual(rules.readers_for(unknown, "other"), [])
        self.assertNotIn("progress", rules.readers_for(unknown, "menu"))

    def test_selectable_region_rows_do_not_raise_the_highest_cleared_stage(self):
        selectable = types.SimpleNamespace(
            regions=lambda _: ["Land of Prophecy"],
            view=lambda *_: {"region": 0, "rows": [{"stage": 973, "move": 0.5}]})
        readers = reader_module.reader_table(screens, load("stage"), selectable, load("gold"),
                                    load("soul_counters"), load("soul_weapon"),
                                    load("engraving_screen"), load("battle_controls"),
                                    load("features/screen_rules"), TABLE, WEAPONS)
        self.assertEqual(readers["region"](None, None, None, None), {"region": "Land of Prophecy"})
        self.assertEqual(rules.READERS["region"]["fields"], ("region",))


class Rules(unittest.TestCase):
    def test_unverified_and_future_facts_are_history_not_action_evidence(self):
        facts, _ = rules.noted({}, {"preset": "III"}, 10)
        self.assertIsNotNone(rules.fact_now(facts, "preset", 5, 12))
        self.assertIsNone(rules.fact_now(facts, "preset", None, 9))
        historical = rules.unverified(facts)
        self.assertIsNone(rules.fact_now(historical, "preset", None, 12))
        self.assertEqual(historical["preset"]["value"], "III")

    def test_slow_old_scan_cannot_replace_newer_setup_evidence(self):
        facts, _ = rules.noted({}, {"preset": "IV"}, 20, "setup")
        for value in ("II", None):
            after, changes = rules.noted(facts, {"preset": value}, 10)
            self.assertEqual(after, facts)
            self.assertEqual(changes, [])

    def test_lower_stage_does_not_refresh_or_reverify_historical_highest(self):
        facts, _ = rules.noted({}, {"stage": 920}, 10)
        facts = rules.unverified(facts)
        facts, _ = rules.noted(facts, {"stage": 900}, 20)
        self.assertEqual((facts["highest"]["value"], facts["highest"]["seen"], facts["highest"]["verified"]),
                         (920, 10, False))

    def test_the_highest_stage_only_goes_up_and_a_stage_raises_it(self):
        facts, _ = rules.noted({}, {"stage": 920}, 1.0)
        self.assertEqual(facts["highest"]["value"], 920)
        facts, changes = rules.noted(facts, {"stage": 915}, 2.0)
        self.assertEqual((facts["stage"]["value"], facts["highest"]["value"]), (915, 920))
        self.assertEqual(changes, [("stage", 920, 915)])
        facts, _ = rules.noted(facts, {"highest": 900}, 3.0, "page")
        self.assertEqual(facts["highest"]["value"], 920)

    def test_a_value_once_seen_is_never_null_again(self):
        facts, _ = rules.noted({}, {"preset": "III"}, 1.0)
        facts, changes = rules.noted(facts, {"preset": None}, 2.0)
        self.assertEqual((facts["preset"]["value"], facts["preset"]["seen"], changes), ("III", 1.0, []))

    def test_a_relaunch_keeps_the_values_unverified(self):
        facts, _ = rules.noted({}, {"stage": 920, "preset": "III"}, 1.0)
        facts = rules.unverified(facts)
        self.assertEqual({f: (fact["value"], fact["verified"]) for f, fact in facts.items()},
                         {"stage": (920, False), "highest": (920, False), "preset": ("III", False)})
        facts, _ = rules.noted(facts, {"stage": 920}, 2.0)
        self.assertTrue(facts["stage"]["verified"])

    def test_the_state_read_back_is_checked_and_unverified(self):
        saved = {"stage": {"value": 920, "seen": 5.0, "verified": True, "source": "scan"},
                 "unknown": {"value": 1}, "emerald": {"value": "12"}, "progress": {"value": None},
                 "preset": {"value": "II", "seen": "late", "source": "?"}}
        facts = rules.fresh(saved, 9.0)
        self.assertEqual(facts, {"stage": {"value": 920, "seen": 5.0, "verified": False, "source": "scan"},
                                 "emerald": {"value": "12", "seen": 9.0, "verified": False, "source": "scan"},
                                 "preset": {"value": "II", "seen": 9.0, "verified": False, "source": "scan"}})

    def test_the_answer_groups_the_fields_by_screen(self):
        facts, _ = rules.noted({}, {"stage": 920}, 1.0)
        answer = rules.answer(facts)
        battle = next(group for group in answer["screens"] if group["screen"] == "battle")
        rows = {row["field"]: row for row in battle["fields"]}
        resources = {row['field']: row for row in answer['resources']}
        self.assertEqual((rows["stage"]["value"], rows["highest"]["value"], resources["emerald"]["pending"]),
                         (920, 920, False))
        self.assertNotIn('gold', rows)
        engraving = next(group for group in answer['screens'] if group['screen'] == 'soul_weapon_engraving')
        self.assertEqual(battle['path'], [])
        self.assertEqual(engraving['path'], ['Equipment: Weapon', 'Soul Weapon', 'Soul Weapon Engraving'])
        self.assertFalse({row['screen'] for row in answer['screens']} &
                         {'top_menu', 'top_ranking', 'top_settings', 'top_mail'})
        self.assertNotIn("gold_place", rows)
        json.dumps(answer)

    def test_partial_soul_read_preserves_each_counters_age(self):
        facts, _ = rules.noted({}, {'souls': {'green': {'text': '12', 'value': 12},
                                             'blue': {'text': '0', 'value': 0}}}, 1.0)
        facts, _ = rules.noted(facts, {'souls': {'green': {'text': '13', 'value': 13}}}, 2.0)
        self.assertEqual(facts['soul_blue']['seen'], 1.0)
        self.assertEqual(facts['soul_blue']['value']['value'], 0)
        self.assertEqual(facts['soul_green']['seen'], 2.0)
        restored = rules.fresh(rules.persisted(facts), 3.0)
        self.assertEqual(restored['soul_blue']['value']['value'], 0)
        self.assertFalse(restored['soul_blue']['verified'])

    def test_legacy_souls_migrate_without_becoming_fresh(self):
        facts = rules.fresh({'souls': {'value': {'red': {'text': '8', 'value': 8}},
                                       'seen': 1.0, 'source': 'scan'}}, 10.0)
        self.assertEqual(facts['soul_red']['seen'], 1.0)
        self.assertFalse(facts['soul_red']['verified'])

    def test_every_requested_resource_has_one_counter_and_unknown_is_not_zero(self):
        rows = rules.answer({})['resources']
        expected = {'diamond', 'gold', 'emerald', 'cubes', 'crystals', 'dice',
                    'soul_green', 'soul_blue', 'soul_red', 'soul_white',
                    'stone_green', 'stone_blue', 'stone_red', 'stone_yellow',
                    'feather_white', 'feather_green', 'feather_purple', 'feather_black',
                    'dragon_power', 'dragon_spark', 'black_mana'}
        self.assertEqual({row['field'] for row in rows}, expected)
        self.assertEqual(len(rows), len(expected))
        self.assertTrue(all(row['value'] is None for row in rows))

    def test_character_exp_remains_unread_until_both_numbers_are_calibrated(self):
        answer = rules.answer({})
        character = next(screen for screen in answer["screens"] if screen["screen"] == "character_enhance")
        exp = next(field for field in character["fields"] if field["field"] == "exp")
        self.assertEqual((exp["label"], exp["value"], exp["pending"]), ("EXP", None, True))
        self.assertEqual(character["path"], ["Character: Enhance"])
        self.assertTrue(rules.FIELDS["feather_black"]["pending"])
        self.assertFalse(rules.TREE["black_orb_obtain"]["visit"])
        self.assertEqual(rules.TREE["black_orb_obtain"]["resource"], "feather_black")


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def wall(self):
        return self.now

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def fake_ports(data_dir, shot=None, holder=None):
    logged = []
    clock = Clock()
    capture_listeners, relaunch_listeners = [], []

    async def analyse(fn, *args):
        return fn(*args)

    async def capture(max_age=0):
        for listener in capture_listeners:
            listener(shot)
        return shot

    ports = types.SimpleNamespace(
        clock=clock, analyse=analyse, capture=capture, spawn=lambda coroutine: coroutine.close(),
        log=lambda level, text, notify=False: logged.append((level, text)),
        store=ports_module.State(data_dir, lambda *a, **k: None),
        lease=types.SimpleNamespace(state=lambda: {"holder": holder} if holder else None),
        respond=lambda value, status=200: value, on_capture=capture_listeners.append,
        on_relaunch=relaunch_listeners.append,
        relaunched=lambda why: [listener(why) for listener in relaunch_listeners])
    return ports, logged


def build(ports):
    built = create_game(ports, screens, rules, READERS)
    ports.store.flush()
    return built


class PassiveNavigation(unittest.TestCase):
    """The scanner observes navigation without any gesture ports."""

    def setup_scan(self, directory):
        ports, _ = fake_ports(directory)
        self.input = None
        ports.last_input = lambda: self.input
        model = types.SimpleNamespace(
            look=lambda shot: {"screen": "battle", "plain": False,
                               "overlays": ["equipment_weapon" if shot[2][0] == 1 else "equipment_accessories"]},
            classify=lambda shot: "battle")
        readers = {name: (lambda *args: {}) for name in rules.READERS}
        calls = []

        def equipment(shot, base, overlays, plain):
            calls.append(shot[2][0])
            return {"weapon_l3" if "equipment_weapon" in overlays else "accessory_l3": shot[2][1]}

        readers["equipment_l3"] = equipment
        api = create_game(ports, model, rules, readers)["api"]
        return ports, api, calls

    def test_fast_weapon_accessory_visits_read_each_panel_and_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, api, calls = self.setup_scan(directory)
            asyncio.run(api["scan"]((1, 1, bytes((1, 7, 0)))))
            ports.clock.now += .2
            asyncio.run(api["scan"]((1, 1, bytes((2, 9, 0)))))
            self.assertEqual(calls, [1, 2])
            self.assertEqual(api["value"]("weapon_l3"), 7)
            self.assertEqual(api["value"]("accessory_l3"), 9)
            with open(os.path.join(directory, "state.json"), encoding="utf-8") as file:
                self.assertEqual(json.load(file)["game"]["accessory_l3"]["value"], 9)
            # Identical panels still respect the normal reader interval.
            ports.clock.now += .2
            asyncio.run(api["scan"]((1, 1, bytes((2, 10, 0)))))
            self.assertEqual(calls, [1, 2])

    def test_user_scroll_refreshes_same_panel_once_and_preserves_capture_time(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, api, calls = self.setup_scan(directory)
            asyncio.run(api["scan"]((1, 1, bytes((1, 7, 0)))))
            ports.clock.now += .2
            self.input = {"monotonic": ports.clock.now, "wall": ports.clock.now}
            ports.clock.now += .1
            acquired = ports.clock.wall()
            asyncio.run(api["scan"]((1, 1, bytes((1, 8, 0)))))
            self.assertEqual(calls, [1, 1])
            self.assertEqual(api["facts"]()["weapon_l3"]["seen"], acquired)
            ports.clock.now += .1
            asyncio.run(api["scan"]((1, 1, bytes((1, 9, 0)))))
            self.assertEqual(calls, [1, 1])

    def test_capture_before_user_input_cannot_consume_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, api, calls = self.setup_scan(directory)
            asyncio.run(api["scan"]((1, 1, bytes((1, 7, 0)))))
            ports.clock.now += .2
            before = ports.clock.wall()
            ports.clock.now += .1
            self.input = {"monotonic": ports.clock.now, "wall": ports.clock.now}
            ports.capture_time = lambda shot: before
            asyncio.run(api["scan"]((1, 1, bytes((1, 8, 0)))))
            self.assertEqual(calls, [1])
            ports.clock.now += .1
            ports.capture_time = lambda shot: ports.clock.wall()
            asyncio.run(api["scan"]((1, 1, bytes((1, 9, 0)))))
            self.assertEqual(calls, [1, 1])
            self.assertEqual(api["value"]("weapon_l3"), 9)

    def test_settled_gesture_frame_reads_after_intermediate_animation(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, api, calls = self.setup_scan(directory)
            asyncio.run(api["scan"]((1, 1, bytes((1, 7, 0)))))
            ports.clock.now += .2
            self.input = {"monotonic": ports.clock.now, "wall": ports.clock.now}
            asyncio.run(api["scan"]((1, 1, bytes((1, 8, 0)))))
            ports.clock.now += .2
            settled = (1, 1, bytes((1, 9, 0)))
            asyncio.run(api["scan"](settled))
            self.assertEqual(api["value"]("weapon_l3"), 8)
            asyncio.run(api["scan_visible"](settled))
            self.assertEqual(api["value"]("weapon_l3"), 9)
            self.assertEqual(calls, [1, 1, 1])


class Feature(unittest.TestCase):
    def test_seen_is_capture_time_not_slow_ocr_completion(self):
        shot = screen(*SCREENS["Battle settings"][0])
        for metadata in (False, True):
            with self.subTest(capture_metadata=metadata), tempfile.TemporaryDirectory() as data_dir:
                ports, _ = fake_ports(data_dir, shot)
                entered = ports.clock.wall()
                captured = entered - 5 if metadata else entered
                if metadata:
                    ports.capture_time = lambda shot: captured
                async def slow(fn, *args):
                    ports.clock.now += 20
                    return fn(*args)
                ports.analyse = slow
                built = build(ports)
                asyncio.run(built["api"]["scan"](shot))
                fact = built["api"]["facts"]()["preset"]
                self.assertEqual(fact["seen"], captured)
                self.assertIsNone(rules.fact_now(built["api"]["facts"](), "preset", 1, ports.clock.wall()))
                answer = asyncio.run(built["routes"][0][2](None))
                self.assertEqual(answer["scan"]["at"], captured)
                self.assertEqual(built["api"]["value"]("preset"), "III", 'old value remains in history')

    def test_fresh_unread_never_returns_a_recent_historical_value(self):
        with tempfile.TemporaryDirectory() as data_dir:
            shot = screen(*SCREENS["Battle settings"][0])
            ports, _ = fake_ports(data_dir, shot)
            readers = dict(READERS, battle_settings=lambda *args: {"preset": None})
            built = create_game(ports, screens, rules, readers)
            built["api"]["note"]({"preset": "II"})
            seen = ports.clock.wall()
            ports.clock.now += .2
            result = asyncio.run(built["api"]["require"](["preset"], 0))
            self.assertEqual(result["preset"], {"value": None, "why": "unread"})
            fact = built["api"]["facts"]()["preset"]
            self.assertEqual((fact["value"], fact["seen"], fact["verified"]), ("II", seen, False))
            self.assertIsNone(asyncio.run(built["api"]["get"]("preset", 100))["value"])

    def test_relaunch_denies_cached_pixels_but_new_capture_can_reverify(self):
        with tempfile.TemporaryDirectory() as data_dir:
            shot = screen(*SCREENS["Battle settings"][0])
            ports, _ = fake_ports(data_dir, shot)
            built = build(ports)
            asyncio.run(built["api"]["scan"](shot))
            ports.relaunched("restarted")
            self.assertIsNone(asyncio.run(built["api"]["get"]("preset", 100))["value"])
            self.assertEqual(built["api"]["value"]("preset"), "III")
            self.assertFalse(built["api"]["facts"]()["preset"]["verified"])
            ports.clock.now += 1
            new_shot = shot[0], shot[1], bytes(bytearray(shot[2]))
            asyncio.run(built["api"]["scan"](new_shot))
            self.assertTrue(built["api"]["facts"]()["preset"]["verified"])

    def test_relaunch_during_ocr_invalidates_inflight_and_cached_answers(self):
        with tempfile.TemporaryDirectory() as data_dir:
            shot = screen(*SCREENS["Battle settings"][0])
            ports, _ = fake_ports(data_dir, shot)
            built = build(ports)
            built["api"]["note"]({"preset": "II"})
            async def restarted(fn, *args):
                ports.relaunched("restarted during OCR")
                return fn(*args)
            ports.analyse = restarted
            result = asyncio.run(built["api"]["require"](["preset", "region"], 5))
            self.assertIsNone(result["preset"]["value"], 'even the initially cached answer lost its verification')
            fact = built["api"]["facts"]()["preset"]
            self.assertEqual((fact["value"], fact["verified"]), ("II", False))

    def test_the_highest_stage_survives_a_restart_and_a_reload(self):
        with tempfile.TemporaryDirectory() as data_dir:
            ports, _ = fake_ports(data_dir)
            first = build(ports)
            first["api"]["note"]({"stage": 925})
            # The gateway restarts: a new feature on the same data directory.
            again = build(fake_ports(data_dir)[0])
            self.assertEqual(again["api"]["value"]("highest"), 925)
            # A page reloaded asks GET /game.
            answer = asyncio.run(again["routes"][0][2](None))
            battle = {row["field"]: row for row in answer["screens"][0]["fields"]}
            self.assertEqual((battle["highest"]["value"], battle["highest"]["verified"]), (925, False))
            with open(os.path.join(data_dir, "state.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["game"]["highest"]["value"], 925)

    def test_the_highest_stage_of_earlier_versions_is_taken_over(self):
        with tempfile.TemporaryDirectory() as data_dir:
            with open(os.path.join(data_dir, "state.json"), "w", encoding="utf-8") as f:
                json.dump({"highest": 910, "mode": {"highest": 950}}, f)
            built = build(fake_ports(data_dir)[0])
            self.assertEqual(built["api"]["value"]("highest"), 950)

    def test_a_relaunch_heard_from_the_ports_leaves_every_value_unverified(self):
        with tempfile.TemporaryDirectory() as data_dir:
            ports, logged = fake_ports(data_dir)
            built = build(ports)
            built["api"]["note"]({"stage": 920, "preset": "II"})
            ports.relaunched("stopped (process gone)")
            facts = built["api"]["facts"]()
            self.assertEqual({fact["verified"] for fact in facts.values()}, {False})
            self.assertEqual(facts["preset"]["value"], "II")
            self.assertIn(("normal", "Game stopped (process gone): every game value unverified until read again"),
                          logged)

    def test_a_change_the_user_makes_is_logged_and_the_plugins_own_is_not(self):
        with tempfile.TemporaryDirectory() as data_dir:
            ports, logged = fake_ports(data_dir)
            built = build(ports)
            built["api"]["note"]({"preset": "II"})
            built["api"]["note"]({"preset": "III"})
            self.assertIn(("normal", "User changed preset from II to III"), logged)
            ports, logged = fake_ports(data_dir, holder="stage_change")
            built = build(ports)
            built["api"]["note"]({"preset": "IV"})
            self.assertFalse([text for _, text in logged if text.startswith("User changed")])

    def test_require_reads_a_fresh_capture_and_says_what_this_screen_does_not_show(self):
        with tempfile.TemporaryDirectory() as data_dir:
            shot = screen(*SCREENS["Battle settings"][0])
            built = build(fake_ports(data_dir, shot)[0])
            answer = asyncio.run(built["api"]["require"](["preset", "region"], 5))
            self.assertEqual(answer["preset"]["value"], "III")
            self.assertEqual(answer["region"], {"value": None, "why": "not readable on this screen"})

    def test_every_capture_is_scanned_once(self):
        with tempfile.TemporaryDirectory() as data_dir:
            shot = screen(*SCREENS["Battle settings"][0])
            ports, _ = fake_ports(data_dir, shot)
            built = build(ports)

            async def run():
                await built["api"]["fresh"](0)
                await built["api"]["scan"](shot)
            asyncio.run(run())
            answer = asyncio.run(built["routes"][0][2](None))
            self.assertEqual(answer["scans"], 1)
            self.assertEqual(answer["scan"]["size"], [shot[0], shot[1]])
            self.assertIn("battle_settings", answer["scan"]["ran"])


class ObservationPipeline(unittest.IsolatedAsyncioTestCase):
    def setup_pipeline(self, directory, reader, archive=None):
        ports, _ = fake_ports(directory)
        ports.spawn = asyncio.create_task
        ports.capture_hooks = []
        ports.on_capture = ports.capture_hooks.append
        model = types.SimpleNamespace(look=lambda shot: {"screen": "battle", "overlays": ["battle_settings"]},
                                      classify=lambda shot: "battle")
        readers = {"battle_settings": reader}
        built = create_game(ports, model, rules, readers, archive=archive)
        return ports, built

    async def turns(self, count=20):
        for _ in range(count):
            await asyncio.sleep(0)

    async def test_detection_publishes_while_ocr_and_archive_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            def read(shot, *args):
                return {"preset": "III"}
            def archive(*args):
                pass
            ports, built = self.setup_pipeline(directory, read, archive)
            async def analyse(fn, *args):
                await gate.wait()
                return fn(*args)
            async def detect(fn, *args):
                return fn(*args)
            ports.analyse, ports.detect = analyse, detect
            shot = (1, 1, b'one')
            demand = asyncio.create_task(built['api']['scan'](shot, ('battle_settings',)))
            await self.turns()
            response = await built['routes'][0][2](None)
            self.assertEqual(response['scan']['screen'], 'battle')
            self.assertEqual(response['scan']['ran'], [])
            self.assertFalse(demand.done(), 'fresh demand must await its reader')
            gate.set()
            self.assertEqual((await demand)['preset'], 'III')
            await self.turns()

    async def test_late_old_read_cannot_reverify_newer_unread(self):
        with tempfile.TemporaryDirectory() as directory:
            old_gate = asyncio.Event()
            def read(shot, *args):
                return {'preset': 'II' if shot[2] == b'old' else None}
            ports, built = self.setup_pipeline(directory, read)
            async def analyse(fn, *args):
                if args[0] == 'battle_settings' and args[1][2] == b'old':
                    await old_gate.wait()
                return fn(*args)
            ports.analyse = analyse
            built['api']['note']({'preset': 'IV'})
            ports.clock.now += 1
            old = (1, 1, b'old')
            new = (1, 1, b'new')
            # Exercise the background hook; explicit scans intentionally serialize demands.
            hooks = ports.capture_hooks
            hooks[0](old)
            await self.turns()
            ports.clock.now += 1
            await built['api']['scan'](new, ('battle_settings',))
            self.assertFalse(built['api']['facts']()['preset']['verified'])
            old_gate.set()
            await self.turns()
            fact = built['api']['facts']()['preset']
            self.assertEqual((fact['value'], fact['verified']), ('IV', False))

    async def test_capture_burst_keeps_only_latest_pending_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda *args: {'preset': 'III'})
            hooks = ports.capture_hooks
            async def detector(fn, *args):
                await gate.wait()
                return fn(*args)
            ports.detect = detector
            hooks[0]((1, 1, b'first'))
            await self.turns()
            for n in range(30):
                ports.clock.now += .1
                hooks[0]((1, 1, bytes([n])))
            response = await built['routes'][0][2](None)
            self.assertEqual(response['observation']['detection_queued'], 1)
            self.assertGreaterEqual(response['observation']['discarded'], 29)
            gate.set()
            await self.turns(50)
            response = await built['routes'][0][2](None)
            self.assertEqual(response['scans'], 2)
            self.assertEqual(response['observation']['detection_queued'], 0)

    async def test_server_observes_without_recent_input_and_start_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, built = self.setup_pipeline(directory, lambda *args: {})
            sleep_gate, capture_gate = asyncio.Event(), asyncio.Event()
            captures, sleeps = [], []
            async def capture(max_age=0):
                captures.append(max_age)
                await capture_gate.wait()
                return (1, 1, b'continuous')
            async def yes():
                return True
            async def sleep(seconds):
                sleeps.append(seconds)
                await sleep_gate.wait()
            ports.capture = capture
            ports.running = ports.focused = yes
            ports.last_input = lambda: None
            ports.clock.sleep = sleep
            await built['startup'][0](None)
            await built['startup'][0](None)
            await self.turns()
            self.assertEqual(captures, [0], 'a second startup must not create another producer')
            capture_gate.set()
            await self.turns()
            self.assertEqual(sleeps, [observation_module.OBSERVE_STABLE])
            response = await built['routes'][0][2](None)
            self.assertEqual(response['observation']['producer']['captures'], 1)
            self.assertTrue(response['observation']['producer']['foreground'])

    async def test_disabled_plugin_does_not_capture_or_probe(self):
        with tempfile.TemporaryDirectory() as directory:
            ports, built = self.setup_pipeline(directory, lambda *args: {})
            sleep_gate = asyncio.Event()
            sleeps = []
            ports.enabled = lambda: False
            async def unexpected(*args, **kwargs):
                self.fail('disabled observer must not capture or probe')
            async def sleep(seconds):
                sleeps.append(seconds)
                await sleep_gate.wait()
            ports.capture = ports.running = ports.focused = unexpected
            ports.clock.sleep = sleep
            await built['startup'][0](None)
            await self.turns()
            self.assertEqual(sleeps, [rules.PROCESS_EVERY])

    async def test_cancelled_explicit_scans_keep_admission_until_exact_frame_drains(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda shot, *args: {
                'preset': 'II' if shot[2] == b'old' else 'III'})
            tracked, analysed = [], []
            def track(task):
                tracked.append(task)
                return task
            ports.track_task = track
            async def analyse(fn, *args):
                analysed.append(args[1][2])
                if args[1][2] == b'old':
                    await gate.wait()
                return fn(*args)
            ports.analyse = analyse
            # Keep screen recognition independent of the blocked resource reader.
            async def detect(fn, *args):
                return fn(*args)
            ports.detect = detect
            first = asyncio.create_task(built['api']['scan']((1, 1, b'old')))
            await self.turns()
            first.cancel()
            await self.turns()
            self.assertFalse(first.done(), 'cancellation must drain its existing batch')
            next_frame = asyncio.create_task(built['api']['scan']((1, 1, b'new')))
            for index in range(20):
                abandoned = asyncio.create_task(built['api']['scan']((1, 1, bytes([index]))))
                await self.turns(2)
                abandoned.cancel()
                await asyncio.gather(abandoned, return_exceptions=True)
                first.cancel()  # Repeated cancellation cannot surrender admission.
            response = await built['routes'][0][2](None)
            self.assertEqual(len(tracked), 1, 'request cancellation cannot accumulate reader jobs')
            self.assertEqual(analysed, [b'old'])
            self.assertEqual(response['observation']['reader_running'], 1)
            self.assertEqual(response['observation']['reader_waiting'], 0)
            self.assertFalse(next_frame.done())
            gate.set()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual(await next_frame, {'preset': 'III'})
            self.assertEqual(analysed, [b'old', b'new'])

    async def test_shutdown_cancellation_drains_shared_background_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda *args: {'preset': 'III'})
            jobs = []
            ports.track_task = lambda task: jobs.append(task) or task
            async def analyse(fn, *args):
                await gate.wait()
                return fn(*args)
            async def detect(fn, *args):
                return fn(*args)
            ports.analyse, ports.detect = analyse, detect
            shot = (1, 1, b'shared')
            ports.capture_hooks[0](shot)
            await self.turns()
            explicit = asyncio.create_task(built['api']['scan'](shot))
            await self.turns()
            explicit.cancel()
            await self.turns()
            explicit.cancel()
            self.assertEqual(len(jobs), 1, 'explicit and background scans share the same frame job')
            jobs[0].cancel()  # The ports lifecycle cancels owned readers at shutdown.
            with self.assertRaises(asyncio.CancelledError):
                await explicit
            self.assertFalse(built['api']['scan'].__self__.explicit_lock.locked())
            self.assertNotIn('preset', built['api']['facts'](), 'cancelled OCR is never fresh evidence')

    def evict_capture_provenance(self, pipeline, ports, metadata):
        for index in range(20):
            ports.clock.now += .001
            shot = (1, 1, bytes([index]))
            metadata[id(shot)] = ports.clock.wall()
            pipeline.observed(shot)
        metadata.clear()  # The ports metadata ring has evicted the requested image too.

    async def test_queued_frame_keeps_stamp_when_capture_metadata_is_evicted(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda shot, *args: {
                'preset': 'II' if shot[2] == b'blocker' else 'III'})
            pipeline = built['api']['scan'].__self__
            metadata = {}
            ports.capture_time = lambda shot: metadata.get(id(shot))
            async def detect(fn, *args):
                return fn(*args)
            async def analyse(fn, *args):
                if args[1][2] == b'blocker':
                    await gate.wait()
                return fn(*args)
            ports.detect, ports.analyse = detect, analyse
            blocker = (1, 1, b'blocker')
            metadata[id(blocker)] = ports.clock.wall()
            first = asyncio.create_task(built['api']['scan'](blocker))
            await self.turns()
            ports.clock.now += .1
            queued = (1, 1, b'queued')
            captured_at = metadata[id(queued)] = ports.clock.wall()
            second = asyncio.create_task(built['api']['scan'](queued, ('battle_settings',)))
            await self.turns()
            self.evict_capture_provenance(pipeline, ports, metadata)
            gate.set()
            await first
            self.assertEqual(await second, {'preset': 'III'})
            self.assertEqual(built['api']['facts']()['preset']['seen'], captured_at)

    async def test_evicted_pre_relaunch_queued_frame_cannot_enter_new_epoch(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda *args: {'preset': 'III'})
            pipeline = built['api']['scan'].__self__
            metadata = {}
            ports.capture_time = lambda shot: metadata.get(id(shot))
            async def detect(fn, *args):
                return fn(*args)
            async def analyse(fn, *args):
                await gate.wait()
                return fn(*args)
            ports.detect, ports.analyse = detect, analyse
            blocker, queued = (1, 1, b'blocker'), (1, 1, b'queued')
            metadata[id(blocker)] = ports.clock.wall()
            first = asyncio.create_task(built['api']['scan'](blocker))
            await self.turns()
            metadata[id(queued)] = ports.clock.wall()
            second = asyncio.create_task(built['api']['scan'](queued))
            await self.turns()
            ports.clock.now += 1
            built['api']['relaunched']('test restart')
            self.evict_capture_provenance(pipeline, ports, metadata)
            gate.set()
            self.assertEqual(await first, {})
            self.assertEqual(await second, {})
            self.assertNotIn('preset', built['api']['facts']())
            self.assertIsNone(built['api']['view']())
            # Even when only ports retains metadata, its acquisition cutoff
            # rejects an unseen reference captured before the restart.
            old = (1, 1, b'old-but-timestamped')
            metadata[id(old)] = ports.clock.wall() - 2
            self.assertEqual(await built['api']['scan'](old), {})

    async def test_require_proof_keeps_stamp_after_slow_ocr_metadata_eviction(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = asyncio.Event()
            ports, built = self.setup_pipeline(directory, lambda *args: {'preset': 'III'})
            pipeline = built['api']['scan'].__self__
            shot = (1, 1, b'required')
            captured_at = ports.clock.wall()
            metadata = {id(shot): captured_at}
            ports.capture_time = lambda shot: metadata.get(id(shot))
            async def capture(max_age=0):
                return shot
            async def detect(fn, *args):
                return fn(*args)
            async def analyse(fn, *args):
                await gate.wait()
                return fn(*args)
            ports.capture, ports.detect, ports.analyse = capture, detect, analyse
            request = asyncio.create_task(built['api']['require'](['preset'], 0))
            await self.turns()
            self.evict_capture_provenance(pipeline, ports, metadata)
            gate.set()
            answer = await request
            self.assertEqual((answer['preset']['value'], answer['preset']['seen']),
                             ('III', captured_at))

    async def test_timestamp_capable_ports_with_missing_metadata_fail_closed(self):
        for missing in (None, True, float('nan'), float('inf')):
            with self.subTest(metadata=missing), tempfile.TemporaryDirectory() as directory:
                ports, built = self.setup_pipeline(directory, lambda *args: {'preset': 'III'})
                shot = (1, 1, b'unknown-time')
                ports.capture_time = lambda shot: missing
                async def capture(max_age=0):
                    return shot
                ports.capture = capture
                self.assertEqual(await built['api']['scan'](shot), {})
                self.assertIsNone(built['api']['view']())
                answer = await built['api']['require'](['preset'], 0)
                self.assertIsNone(answer['preset']['value'])
                self.assertNotIn('preset', built['api']['facts']())
