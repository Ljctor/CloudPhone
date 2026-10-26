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
ports_module = load("features/ports")
with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    WEAPONS = json.load(f)
READERS = game.reader_table(screens, load("stage"), load("stage_select"), load("gold"), load("soul_counters"),
                            load("soul_weapon"), load("engraving_screen"), load("battle_controls"),
                            load("features/screen_rules"), TABLE, WEAPONS)
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
    "the engraving": (("eg_title", "eg_grid"), (0, 0, 0), {"engraving": None}),
    "Power Saving Mode without its number": (("saver_mode",), (0, 0, 0), {}),
    "the sign-in screen": (("sign_in_buttons",), (90, 60, 35), {}),
}


class Mapping(unittest.TestCase):
    def test_each_screen_gives_its_fields_and_only_those(self):
        timings = {}
        for case, (names, background, expected) in SCREENS.items():
            shot = screen(*names, background=background or (20, 16, 14))
            took = {}
            look, readings, ran = game.read_all(screens, rules, READERS, shot, timings=took)
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
        _, readings, _ = game.read_all(screens, rules, READERS, screen(*names))
        self.assertEqual({colour: count["text"] for colour, count in readings["souls"].items()},
                         {"green": "94.6C", "blue": "19.4C", "red": "16.1C", "white": "4.64C"})

    def test_the_engraving_grid_reads_its_pieces(self):
        names, background, _ = SCREENS["the engraving"]
        _, readings, _ = game.read_all(screens, rules, READERS, screen(*names, background=background))
        cells = readings["engraving"]["cells"]
        self.assertEqual((len(cells), {len(row) for row in cells}), (5, {5}))
        self.assertTrue(readings["engraving"]["pieces"])

    def test_an_engraving_title_alone_reads_no_grid(self):
        _, readings, _ = game.read_all(screens, rules, READERS, screen("eg_title", background=(0, 0, 0)))
        self.assertIsNone(readings["engraving"])

    def test_a_slow_reader_waits_its_turn_unless_forced(self):
        shot = screen(*SCREENS["battle at stage 920"][0])
        _, _, ran = game.read_all(screens, rules, READERS, shot, {"battle_stage": 100.0, "gold": 100.0}, 105.0)
        self.assertNotIn("battle_stage", ran)
        self.assertIn("progress", ran)
        _, readings, ran = game.read_all(screens, rules, READERS, shot, {"battle_stage": 100.0}, 105.0,
                                         force=("battle_stage",))
        self.assertEqual(readings["stage"], 920)

    def test_the_older_classifier_stands_in_for_an_unknown_screen(self):
        unknown = {"screen": "unknown", "overlays": []}
        self.assertIn("battle_stage", rules.readers_for(unknown, "battle"))
        self.assertIn("saver_stage", rules.readers_for(unknown, "saver"))
        self.assertEqual(rules.readers_for(unknown, "other"), [])
        self.assertNotIn("progress", rules.readers_for(unknown, "menu"))


class Rules(unittest.TestCase):
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
                                 "preset": {"value": "II", "seen": 9.0, "verified": False, "source": "scan"}})

    def test_the_answer_groups_the_fields_by_screen(self):
        facts, _ = rules.noted({}, {"stage": 920}, 1.0)
        answer = rules.answer(facts)
        battle = next(group for group in answer["screens"] if group["screen"] == "battle")
        rows = {row["field"]: row for row in battle["fields"]}
        resources = {row['field']: row for row in answer['resources']}
        self.assertEqual((rows["stage"]["value"], rows["highest"]["value"], resources["emerald"]["pending"]),
                         (920, 920, True))
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
    built = game.game(ports, screens, rules, READERS)
    ports.store.flush()
    return built


class Feature(unittest.TestCase):
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
