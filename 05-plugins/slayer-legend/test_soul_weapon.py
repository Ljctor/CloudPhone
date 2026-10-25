"""Equipping the loadout's soul weapon: the Soul Weapon screen's readers on
crops of real captures (fixtures/sw_*: never a full screen, nothing with
the account's name), the planning rules on views described here, and the
guarded sequence against a scripted game (fake ports with the real
navigation guard, readers answering from the game's state, virtual
time). Nothing touches Android.
Run: python3 -m unittest test_soul_weapon"""

import asyncio
import contextlib
import copy
import importlib.util
import json
import os
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_sw_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load("soul_weapon")
LOG = load("features/ports").python_log("slayer-legend")
EXCEPTION = load("features/ports").exception_log(LOG)
TEXTS = load("features/ports").text_ports()
french = TEXTS["french"]
rules = load("features/soul_weapon_rules")
feature = load("features/soul_weapon")
stage_change = load("features/stage_change")
stage_rules = load("features/stage_change_rules")
nav = load("nav")
es = load("engraving_screen")
engraving_setup = load("features/engraving_setup")
setup_rules = load("features/engraving_setup_rules")
engraving_rules = load("features/engraving_rules")
screens = load("screens")
fixtures = load("test_fixtures")
with open(os.path.join(HERE, "engravings.json"), encoding="utf-8") as f:
    TABLE = json.load(f)
with open(os.path.join(HERE, "stages.json"), encoding="utf-8") as f:
    STAGES = json.load(f)
NAMES = reader.names_of(TABLE)
ORDER = rules.order_names(TABLE)
AMBITION, GRAND = 32, 45


def screen(*names):
    return fixtures.screen(*names)


class Readers(unittest.TestCase):
    def test_title(self):
        self.assertTrue(reader.title(screen("sw_title")))
        self.assertFalse(reader.title(screen("sw_name_ambition")))
        self.assertFalse(reader.title(screen("sw_tabs")))

    def test_names(self):
        self.assertEqual(reader.name(screen("sw_name_ambition"), NAMES), "Ambition")
        self.assertEqual(reader.name(screen("sw_name_grand"), NAMES), "Grand")
        self.assertEqual(reader.name(screen("sw_name_vision"), NAMES), "Vision")
        # The Soul Weapon screen is not an ordinary weapon's card.
        self.assertFalse(reader.weapon_detail(screen("sw_title", "sw_name_vision")))
        # Against a list without it, the closest is not taken.
        self.assertIsNone(reader.name(screen("sw_name_grand"), [n for n in NAMES if n != "Grand"]))
        self.assertIsNone(reader.name(screen("sw_title"), NAMES))

    def test_owned(self):
        self.assertEqual(reader.owned(screen("sw_owned_1")), 1)
        self.assertEqual(reader.owned(screen("sw_owned_0")), 0)
        self.assertIsNone(reader.owned(screen("sw_name_grand")))

    def test_list(self):
        none = reader.rows(screen("sw_list_none"))
        first = reader.rows(screen("sw_list_first"))
        self.assertEqual(len(none), 5)
        self.assertEqual(len(first), 5)
        self.assertEqual([row["selected"] for row in none], [False] * 5)
        self.assertEqual([row["selected"] for row in first], [True] + [False] * 4)
        # The first cell's tap, where sw_other's was taken (0.087, 0.61):
        # in its upper part.
        x, y = reader.select_point(first[0])
        self.assertAlmostEqual(x, 0.087)
        self.assertTrue(first[0]["top"] < y < (first[0]["top"] + first[0]["bottom"]) / 2)
        self.assertEqual(reader.tags(screen("sw_list_first")), [])

    def test_tab(self):
        self.assertEqual(reader.tab(screen("sw_tabs")), "weapon")
        self.assertIsNone(reader.tab(screen("sw_title")))

    def test_badge(self):
        self.assertIs(reader.equipped_badge(screen("sw_badge_red")), True)
        self.assertIs(reader.equipped_badge(screen("sw_badge_grey")), False)
        # Not told until an owned, unequipped weapon is seen grey.
        self.assertFalse(reader.BADGE_TELLS)

    def test_whole_screen(self):
        shot = screen("sw_title", "sw_name_ambition", "sw_owned_1", "sw_list_none", "sw_badge_red")
        view = reader.view(shot, NAMES)
        self.assertEqual((view["open"], view["selected"], view["owned"], view["tag"]), (True, "Ambition", 1, None))
        self.assertEqual(len(view["rows"]), 5)


def tagged(text, top=0.835, scale=2):
    """A synthetic orange tag in the list with text drawn in the card font
    (white), on an empty screen: until the tag is captured."""
    width, height = 480, 1040
    pixels = bytearray(bytes((20, 16, 14)) * (width * height))
    left, right, y0 = int(0.03 * width), int(0.15 * width), int(top * height)
    marks = reader.font.render(text, scale, reader.CARD_FONT)
    rows = len(marks) + 6
    for y in range(y0, y0 + rows):
        for x in range(left, right):
            pixels[(y * width + x) * 3:(y * width + x) * 3 + 3] = bytes((230, 140, 30))
    for dy, row in enumerate(marks):
        for dx, v in enumerate(row):
            if v and left + 3 + dx < right:
                i = ((y0 + 3 + dy) * width + left + 3 + dx) * 3
                pixels[i:i + 3] = b"\xff\xff\xff"
    return (width, height, bytes(pixels))


class Tag(unittest.TestCase):
    def test_synthetic_tags_read_nothing(self):
        # Text drawn in another font matches no template cut from the game:
        # found as a tag, read as nothing.
        for text in ("Equip", "Unequip", "Grand"):
            found, box = reader.tag(tagged(text))
            self.assertIsNone(found)
            self.assertTrue(box[0] <= 0.09 <= box[2] and box[1] <= 0.845 <= box[3])
        self.assertEqual(reader.tag(screen("sw_list_none")), (None, None))

    @unittest.skipUnless(os.path.exists(os.path.join(FIXTURES, "sw_tag_equip.txt")),
                         "no capture of the Equip tag yet (fixtures/sw_tag_equip.txt)")
    def test_equip_tag_capture(self):
        self.assertEqual(reader.tag(screen("sw_tag_equip"))[0], "Equip")

    def test_unequip_tag_capture(self):
        text, box = reader.tag(screen("sw_tag_unequip"))
        self.assertEqual(text, "Unequip")
        self.assertTrue(box[0] < 0.1 < box[2] and box[1] < 0.623 < box[3])

    def test_the_equip_gate_is_closed_until_both_tags_are_captured(self):
        self.assertEqual(reader.TAG_LEARNED, os.path.exists(os.path.join(FIXTURES, "sw_tag_equip.txt")))


def rows(count=5, selected=None):
    return [{"top": 0.56 + 0.064 * i, "bottom": 0.615 + 0.064 * i, "selected": i == selected} for i in range(count)]


def view(selected=None, row=None, owned=1, tag=None, count=5, opened=True):
    return {"open": opened, "selected": selected, "owned": owned, "tag": tag,
            "tag_box": [0.03, 0.835, 0.15, 0.86] if tag else None, "tags": [[0.03, 0.835, 0.15, 0.86]] if tag else [],
            "rows": rows(count, row), "badge": None}


class Plan(unittest.TestCase):
    def plan(self, v, target="Ambition", direction=None, memory=None):
        memory = memory or rules.fresh_memory(direction)
        return rules.plan(v, target, rules.observe(memory, v, ORDER), ORDER, True)

    def test_done_and_equip(self):
        self.assertEqual(self.plan(view("Ambition", 2, tag="Unequip")), ("done",))
        # Selected, its cell out of view (the list opens so): read another.
        self.assertEqual(self.plan(view("Ambition", None)), ("select", 2))
        self.assertEqual(self.plan(view("Ambition", 2, tag="Equip")), ("equip",))
        self.assertEqual(self.plan(dict(view("Ambition", 2), badge=True)), ("done",))

    def test_no_equip_until_the_tag_is_calibrated(self):
        v = view("Ambition", 2, tag="Equip")
        step = rules.plan(v, "Ambition", rules.observe(rules.fresh_memory(None), v, ORDER), ORDER)
        self.assertEqual(step[0], "fail")
        self.assertIn("étiquette Equip pas calibrée", french(step[1]))
        self.assertIn("équipement non fait", french(step[1]))
        # Done, select and scroll do not need it.
        v = view("Ambition", 2, tag="Unequip")
        self.assertEqual(rules.plan(v, "Ambition", rules.observe(rules.fresh_memory(None), v, ORDER), ORDER),
                         ("done",))

    def test_failures(self):
        self.assertIn("Owned : 0", french(self.plan(view("Ambition", 2, owned=0, tag="Equip"))[1]))
        self.assertIn("illisible", french(self.plan(view("Ambition", 2, owned=None, tag="Equip"))[1]))
        self.assertIn("étiquette", french(self.plan(view("Ambition", 2))[1]))
        self.assertIn("pas reconnu", french(self.plan(view(opened=False))[1]))
        self.assertIn("partagé", french(self.plan(view("Grand", 0), target="Silence")[1]))
        self.assertIn("illisible", french(self.plan(view(None, 1))[1]))
        self.assertIn("liste", french(self.plan(view("Grand", None, count=0))[1]))

    def test_select_and_scroll(self):
        # The selection out of view: the middle cell, to read one.
        self.assertEqual(self.plan(view(None, None)), ("select", 2))
        # The direction unknown: the next cell, to learn it.
        self.assertEqual(self.plan(view("Grand", 0)), ("select", 1))
        self.assertEqual(self.plan(view("Grand", 4)), ("select", 3))
        # Known: counted from the selected cell (Ambition is 13 before Grand).
        self.assertEqual(self.plan(view("Grand", 0), direction=-1), ("scroll", "down"))
        self.assertEqual(self.plan(view("Grand", 0), direction=1), ("scroll", "up"))
        self.assertEqual(self.plan(view("Wild", 1), direction=-1), ("select", 0))
        self.assertEqual(self.plan(view("Solitude", 3), direction=1), ("select", 2))

    def test_learning_the_direction(self):
        memory = rules.observe(rules.fresh_memory(), view("Grand", 0), ORDER)
        memory = rules.observe(memory, view("Honor", 1), ORDER)
        self.assertEqual(memory["direction"], -1)
        memory = rules.observe(rules.fresh_memory(), view("Wild", 0), ORDER)
        self.assertEqual(rules.observe(memory, view("Ambition", 1), ORDER)["direction"], 1)
        # A scroll in between: rows not comparable.
        memory = rules.scrolled(rules.observe(rules.fresh_memory(), view("Grand", 0), ORDER))
        self.assertIsNone(rules.observe(memory, view("Honor", 1), ORDER)["direction"])
        # Not one place per row: the list is not the game's order.
        memory = rules.observe(rules.fresh_memory(), view("Grand", 0), ORDER)
        memory = rules.observe(memory, view("Wild", 1), ORDER)
        self.assertEqual(memory["direction"], "unknown")
        self.assertIn("ordre", french(rules.plan(view("Wild", 1), "Ambition", memory, ORDER)[1]))

    def test_progress(self):
        self.assertFalse(rules.progressed(view("Grand", 0), view("Grand", 0)))
        self.assertTrue(rules.progressed(view("Grand", 0), view("Honor", 1)))
        self.assertTrue(rules.progressed(view("Ambition", 1, tag="Equip"), view("Ambition", 1, tag="Unequip")))

    def test_cache(self):
        self.assertFalse(rules.fresh_cache(None, 10, None, None))
        self.assertTrue(rules.fresh_cache({"id": 1, "at": 5}, 10, 4, None))
        self.assertFalse(rules.fresh_cache({"id": 1, "at": 5}, 10, 6, None))
        self.assertFalse(rules.fresh_cache({"id": 1, "at": 5}, 10, None, 7))


class Game:
    """The scripted game: the Soul Weapon list in the game's order (down:
    ids going down, as direction -1), five whole cells shown, a tag under
    the selected cell of an owned weapon (Unequip on the equipped one)."""

    CELL, FIRST = 0.0644, 0.5615

    def __init__(self, **state):
        self.now = 0.0
        self.state = {"screen": "battle", "panel": None, "tab": "weapon", "offset": 0, "selected": None,
                      "equipped": AMBITION, "owned": {AMBITION, GRAND - 1, 20}, "descending": True,
                      "first_id": GRAND, "focused": True, "busy": None, "tag_unread": False,
                      "equip_fails": False, "name_unread": False, "detail_instead": False}
        self.state.update(state)
        if self.state["selected"] is None:
            self.state["selected"] = self.state["equipped"]
        self.moves, self.alerts, self.leases, self.captures = [], [], [], 0

    def id_at(self, index):
        s = self.state
        return s["first_id"] - index if s["descending"] else s["first_id"] + index

    def index_of(self, weapon):
        s = self.state
        return s["first_id"] - weapon if s["descending"] else weapon - s["first_id"]

    def cells(self):
        s = self.state
        out = []
        for row in range(5):
            weapon = self.id_at(s["offset"] + row)
            if 1 <= weapon <= 89:
                top = self.FIRST + self.CELL * row
                out.append({"top": top, "bottom": top + 0.054, "selected": weapon == s["selected"], "id": weapon})
        return out

    def snapshot(self):
        self.captures += 1
        return (480, 1040, dict(self.state, now=self.now, cells=self.cells()))

    def apply(self, screen, move, point):
        s = self.state
        if move == "menu_equipment":
            s["screen"], s["panel"] = "equipment", "equipment_weapon"
        elif screen == "equipment_accessories" and move == "weapon":
            s["tab"] = "weapon"
        elif move == "soul_weapon" and screen == "equipment_weapon":
            s["screen"] = "detail" if s["detail_instead"] else "soul"
        elif screen == "weapon_detail" and move == "close":
            s["screen"] = "equipment"
        elif screen == "soul_weapon" and move == "select":
            cell = next(c for c in self.cells() if c["top"] <= point[1] <= c["bottom"])
            s["selected"] = cell["id"]
        elif move == "scroll":
            s["offset"] = max(0, min(84, s["offset"] + (4 if point[1] > 0.7 else -4)))
        elif move == "equip":
            if not s["equip_fails"]:
                s["equipped"] = s["selected"]
        elif screen == "soul_weapon" and move == "close":
            s["screen"] = "equipment"
        elif move == "close":
            s["screen"], s["panel"] = "battle", None

    def ports(self):
        game = self

        class Busy(RuntimeError):
            pass

        @contextlib.asynccontextmanager
        async def leased(holder, reason, seconds, user=False):
            if game.state["busy"]:
                raise Busy(game.state["busy"])
            game.leases.append((holder, reason))
            yield

        def guarded(screen, move, point, kind="tap", verified=False, seen=None):
            refusal = nav.guard(screen, move, point[0], point[1], kind, verified, seen)
            if refusal:
                raise RuntimeError(refusal)

        async def capture(max_age=0):
            return game.snapshot()

        async def analyse(fn, *args):
            return fn(*args)

        async def tap(shot, screen, move, point, verified=False, seen=None):
            guarded(screen, move, point, verified=verified, seen=seen)
            game.moves.append((screen, move))
            game.apply(screen, move, point)

        async def swipe(shot, screen, move, start, end, milliseconds, verified=False, seen=None):
            guarded(screen, move, start, "swipe", verified, seen)
            game.moves.append((screen, move))
            game.apply(screen, move, start)

        async def focused():
            return game.state["focused"]

        async def sleep(seconds):
            game.now += seconds

        async def notify(text):
            game.alerts.append(text)

        tasks = []

        def spawn(coroutine):
            tasks.append(coroutine)
            return coroutine

        store = SimpleNamespace(saved={}, sections={}, save=lambda: None)
        store.register = lambda name, snapshot: store.sections.__setitem__(name, snapshot)
        return SimpleNamespace(capture=capture, analyse=analyse, tap=tap, taps=None, swipe=swipe, focused=focused,
                               notify=notify, clock=SimpleNamespace(sleep=sleep, wall=lambda: 1e9 + game.now,
                                                                     monotonic=lambda: game.now),
                               leased=leased, Busy=Busy, store=store, last_input=lambda: None, spawn=spawn,
                               tasks=tasks, respond=lambda value, status=200: (status, value), log=LOG,
                               exception=EXCEPTION, **TEXTS)


def fake_reader(game):
    def tag_of(s):
        cell = next((c for c in s["cells"] if c["id"] == s["selected"]), None)
        if s["screen"] != "soul" or cell is None or s["selected"] not in s["owned"] | {s["equipped"]}:
            return None, None
        box = [0.03, cell["top"] + 0.03, 0.15, cell["top"] + 0.05]
        return (None if s["tag_unread"] else "Unequip" if s["selected"] == s["equipped"] else "Equip"), box

    def view(shot, names):
        s = shot[2]
        if s["screen"] != "soul":
            return {"open": False, "selected": None, "owned": None, "tag": None, "tag_box": None, "tags": [],
                    "rows": [], "badge": None}
        text, box = tag_of(s)
        entry = next(e for e in TABLE["weapons"] if e["id"] == s["selected"])
        return {"open": True, "selected": None if s["name_unread"] else entry["name"],
                "owned": 1 if s["selected"] in s["owned"] | {s["equipped"]} else 0, "tag": text, "tag_box": box,
                "tags": [box] if box else [],
                "rows": [{k: c[k] for k in ("top", "bottom", "selected")} for c in s["cells"]], "badge": None}

    return SimpleNamespace(
        names_of=reader.names_of, select_point=reader.select_point, view=view, CARD_FONT=reader.CARD_FONT,
        TAG_LEARNED=game.state.get("tag_learned", True),
        title=lambda shot: shot[2]["screen"] == "soul",
        weapon_detail=lambda shot: shot[2]["screen"] == "detail",
        tab=lambda shot: shot[2]["tab"] if shot[2]["screen"] == "equipment" else None)


def fake_screens():
    def plain(shot):
        return shot[2]["screen"] == "battle"

    def open_tab(shot):
        s = shot[2]
        return (0.41, "equipment_weapon") if s["screen"] == "equipment" else None

    return SimpleNamespace(plain_battle=plain, open_tab=open_tab, TAB_TAP_Y=screens.TAB_TAP_Y,
                           classify=lambda shot: shot[2]["screen"])


def build(game, loadout=None, engraving=None):
    ports = game.ports()
    loadouts = loadout or {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": AMBITION, "variant": "Atk"}},
                           "mpw4": {"stage": 915, "preset": None, "soul_weapon": {"id": GRAND - 1, "variant": "Atk"}}}
    soul = {"feature": feature.soul_weapon, "reader": fake_reader(game), "rules": rules, "table": TABLE,
            "loadout": lambda mode: loadouts[mode], "engraving": engraving}
    part = stage_change.stage_change(ports, fake_screens(), SimpleNamespace(regions=lambda table: []),
                                     SimpleNamespace(), stage_rules, STAGES, soul)
    return ports, part["api"]


def outcome(answer):
    """(result, text) of a run (its timings left out)."""
    return answer["result"], french(answer["text_t"])


def equip(game, mode="mpw18", api=None):
    ports, built = build(game) if api is None else (None, api)
    return asyncio.run(built["soul_weapon"](mode)), built


class Sequence(unittest.TestCase):
    def test_already_equipped_and_cached(self):
        game = Game(selected=GRAND)
        answer, api = equip(game)
        self.assertEqual(outcome(answer), ("done", ""))
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        self.assertEqual(game.moves[:2], [("battle", "menu_equipment"), ("equipment_weapon", "soul_weapon")])
        # Parked: the screen stays open, nothing closed.
        self.assertNotIn(("soul_weapon", "close"), game.moves)
        self.assertEqual(game.state["screen"], "soul")
        # The next time: one look (still parked), nothing tapped.
        before, captures = len(game.moves), game.captures
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual((len(game.moves), game.captures), (before, captures + 1))
        # After a relaunch (the game back on the battle) it reads again.
        game.state["screen"] = "battle"
        asyncio.run(api["relaunched"]("mpw18"))
        self.assertGreater(len(game.moves), before)
        self.assertEqual(game.alerts, [])

    def test_equips_another_weapon_fast(self):
        game = Game(selected=AMBITION)
        ports, api = build(game)
        answer = asyncio.run(api["soul_weapon"]("mpw4"))
        self.assertEqual(outcome(answer), ("done", ""))
        self.assertEqual(game.state["equipped"], GRAND - 1)
        self.assertEqual(game.moves.count(("soul_weapon", "equip")), 1)
        self.assertLessEqual(game.now, 20)
        # The direction learnt is kept (state.json).
        self.assertEqual(ports.store.sections["soul_weapon"]()["direction"], -1)

    def test_scrolls_to_a_far_weapon(self):
        game = Game(selected=GRAND, equipped=GRAND, owned={GRAND, 30})
        loadouts = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": 30, "variant": "Atk"}}}
        _, api = build(game, loadouts)
        answer = asyncio.run(api["soul_weapon"]("mpw18"))
        self.assertEqual(answer["result"], "done", answer)
        self.assertEqual(game.state["equipped"], 30)
        self.assertIn(("soul_weapon", "scroll"), game.moves)
        moves = [m for m in game.moves if m[0] == "soul_weapon" and m[1] in ("select", "scroll", "equip")]
        self.assertLessEqual(len(moves), rules.MOST_MOVES)

    def test_ascending_list(self):
        game = Game(selected=GRAND, equipped=GRAND, owned={GRAND, GRAND + 2}, descending=False, first_id=GRAND - 2)
        loadouts = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": GRAND + 2, "variant": "Atk"}}}
        _, api = build(game, loadouts)
        self.assertEqual(asyncio.run(api["soul_weapon"]("mpw18"))["result"], "done")
        self.assertEqual(game.state["equipped"], GRAND + 2)

    def test_a_loadout_change_of_the_active_mode(self):
        # The mode feature's trigger: the new loadout given, applied alone.
        game = Game(selected=GRAND, owned={AMBITION, 36})
        ports, api = build(game)
        new = {"stage": 920, "preset": None, "soul_weapon": {"id": 36, "variant": "Gold-balanced"}}
        self.assertEqual(outcome(asyncio.run(api["ensure_soul_weapon"]("mpw18", new))), ("done", ""))
        self.assertEqual(game.state["equipped"], 36)
        self.assertLessEqual(game.now, 60)
        self.assertEqual(game.leases[-1], ("stage_change", "farm mpw18"))

    def test_a_weapon_card_instead_is_closed_and_alerted(self):
        game = Game(detail_instead=True)
        answer, _ = equip(game, "mpw4")
        self.assertEqual(answer["result"], "failed")
        self.assertIn("fiche d’une arme", french(answer["text_t"]))
        self.assertIn(("weapon_detail", "close"), game.moves)
        self.assertNotIn(("weapon_detail", "equip"), game.moves)

    def test_accessories_tab_first(self):
        game = Game(tab="accessories", selected=AMBITION)
        answer, _ = equip(game)
        self.assertEqual(answer["result"], "done", answer)
        self.assertIn(("equipment_accessories", "weapon"), game.moves)
        self.assertNotIn(("equipment_accessories", "black_orb"), game.moves)

    def test_not_owned_fails_without_equip(self):
        game = Game(owned={AMBITION})
        answer, _ = equip(game, "mpw4")
        self.assertEqual(answer["result"], "failed")
        self.assertIn("Soul Weapon", french(answer["text_t"]))
        self.assertIn("Owned : 0", french(answer["text_t"]))
        self.assertNotIn(("soul_weapon", "equip"), game.moves)

    def test_equip_gate_closed_one_error_alert(self):
        game = Game(selected=AMBITION, tag_learned=False)
        answer, _ = equip(game, "mpw4")
        self.assertEqual(answer["result"], "failed")
        self.assertIn("étiquette Equip pas calibrée, équipement non fait", french(answer["text_t"]))
        self.assertNotIn(("soul_weapon", "equip"), game.moves)
        # Selecting and scrolling still ran.
        self.assertIn(("soul_weapon", "select"), game.moves)

    def test_unread_tag_or_name_taps_no_tag(self):
        for state in ({"tag_unread": True}, {"name_unread": True}):
            game = Game(selected=AMBITION, **state)
            answer, _ = equip(game, "mpw4")
            self.assertEqual(answer["result"], "failed", state)
            self.assertNotIn(("soul_weapon", "equip"), game.moves)
            self.assertEqual(game.state["equipped"], AMBITION)

    def test_equip_without_effect_stops(self):
        game = Game(selected=AMBITION, equip_fails=True)
        answer, _ = equip(game, "mpw4")
        self.assertEqual(answer["result"], "failed")
        self.assertIn("Equip sans effet", french(answer["text_t"]))
        self.assertEqual(game.moves.count(("soul_weapon", "equip")), 1)

    def test_no_weapon_chosen(self):
        # Nothing equipped: only the way to the parking.
        game = Game(selected=GRAND)
        loadouts = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": None}}
        _, api = build(game, loadouts)
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual(game.moves, [("battle", "menu_equipment"), ("equipment_weapon", "soul_weapon")])

    def test_emergency_off(self):
        game = Game(selected=GRAND)
        ports = game.ports()
        soul = {"feature": feature.soul_weapon, "reader": fake_reader(game), "rules": rules, "table": TABLE,
                "loadout": lambda mode: {"soul_weapon": {"id": AMBITION, "variant": "Atk"}}}
        part = stage_change.stage_change(ports, fake_screens(), SimpleNamespace(regions=lambda table: []),
                                         SimpleNamespace(), stage_rules, STAGES, soul)
        post = next(h for m, p, h in part["routes"] if m == "POST")

        class Request:
            def __init__(self, body):
                self.body = body

            async def json(self):
                return self.body

        self.assertEqual(asyncio.run(post(Request({"soul_weapon": "maybe"})))[0], 400)
        status, body = asyncio.run(post(Request({"soul_weapon": "off"})))
        self.assertEqual((status, body["soul_weapon"]["switch"]), (200, "off"))
        self.assertEqual(ports.store.sections["soul_weapon"]()["switch"], "off")
        asyncio.run(part["api"]["soul_weapon"]("mpw18"))
        self.assertEqual(game.moves, [])

    def test_after_a_relaunch_one_alert_on_failure(self):
        game = Game(owned={AMBITION})
        ports, api = build(game)
        task = api["relaunched"]("mpw4")
        asyncio.run(task)
        self.assertEqual(len(game.alerts), 1)
        self.assertIn("After the game's relaunch", game.alerts[0])
        self.assertIsNone(api["relaunched"]("mine"))



# The moves that reach the parking: the soul weapon step's own way there.
PARKING_MOVES = {("battle", "menu_equipment"), ("equipment_accessories", "weapon"),
                 ("equipment_weapon", "soul_weapon")}


class Parking(unittest.TestCase):
    """The farming modes' idle place, the Soul Weapon screen: reached by
    the soul weapon step's moves, never a tap inside its panel."""

    def test_the_mode_switch_ends_parked_within_its_budget(self):
        game = Game(selected=AMBITION)
        ports, api = build(game)
        answer = asyncio.run(api["soul_weapon"]("mpw4"))
        self.assertEqual(outcome(answer), ("done", ""))
        self.assertIn("park", answer["timings"])
        self.assertEqual(game.state["screen"], "soul")
        self.assertLessEqual(game.now, 60)

    def test_park_from_the_battle_then_already_parked(self):
        game = Game(tab="accessories")
        _, api = build(game)
        self.assertEqual(outcome(asyncio.run(api["park"]("mpw18"))), ("done", ""))
        self.assertEqual(game.state["screen"], "soul")
        self.assertLessEqual(set(game.moves), PARKING_MOVES)
        moves = list(game.moves)
        self.assertEqual(outcome(asyncio.run(api["park"]("mpw18"))), ("done", ""))
        self.assertEqual(game.moves, moves, "already parked: nothing tapped")
        self.assertEqual(game.leases[-1], ("stage_change", "farm mpw18"))

    def test_never_in_free_play_or_the_mine(self):
        for mode in ("free", "mine"):
            game = Game()
            _, api = build(game)
            asyncio.run(api["park"](mode))
            self.assertEqual((game.moves, game.state["screen"]), ([], "battle"), mode)

    def test_never_with_the_soul_weapon_switch_off(self):
        game = Game()
        ports = game.ports()
        ports.store.saved["soul_weapon"] = {"switch": "off"}
        part = stage_change.stage_change(ports, fake_screens(), SimpleNamespace(regions=lambda table: []),
                                         SimpleNamespace(), stage_rules, STAGES,
                                         {"feature": feature.soul_weapon, "reader": fake_reader(game),
                                          "rules": rules, "table": TABLE, "loadout": lambda mode: None})
        self.assertEqual(part["api"]["soul_weapon_switch"](), "off")
        asyncio.run(part["api"]["park"]("mpw18"))
        self.assertEqual(game.moves, [])

    def test_held_while_the_user_plays(self):
        game = Game(busy="the user plays")
        _, api = build(game)
        with self.assertRaises(RuntimeError):
            asyncio.run(api["park"]("mpw18"))
        self.assertEqual(game.moves, [])

    def test_leaving_it_for_free_play_or_a_repair(self):
        game = Game(screen="soul", panel="equipment_weapon")
        _, api = build(game)
        self.assertTrue(api["parked"](game.snapshot()))
        self.assertEqual(outcome(asyncio.run(api["unpark"]("free"))), ("done", ""))
        self.assertEqual(game.moves, [("soul_weapon", "close"), ("equipment_weapon", "close")])
        self.assertEqual(game.state["screen"], "battle")
        # On the battle already: nothing.
        self.assertEqual(outcome(asyncio.run(api["unpark"]("free"))), ("done", ""))
        self.assertEqual(len(game.moves), 2)

    def test_back_to_the_parking_after_a_relaunch(self):
        game = Game(selected=GRAND)
        _, api = build(game)
        asyncio.run(api["soul_weapon"]("mpw18"))
        game.state.update(screen="battle", panel=None)  # the relaunch
        asyncio.run(api["relaunched"]("mpw18"))
        self.assertEqual(game.state["screen"], "soul")
        self.assertEqual(game.alerts, [])


# The engraving, as the captures of 2026-10-22 show it (Vision filled as
# Atk, four L placed in slots 2, 5, 6 and 8, all locked): a tap on a
# card's padlock corner toggles it (or nothing, corner_works False); a tap
# on its middle opens its popup, whose padlock toggles it; a piece dragged
# out of the grid comes out unlocked; a card dragged onto the grid shows
# its preview in its card orientation, HOLD_ROWS above the finger, turned
# a quarter clockwise by rotate, moved by a drag of a cube, placed by
# confirm only where it fits (valid).
VISION_ID = 36
VISION = next(e for e in TABLE["weapons"] if e["id"] == VISION_ID)
VISION_VARIANTS = engraving_rules.variants(VISION, engraving_rules.any_orientation(TABLE))
VISION_CELLS = {tuple(c) for c in VISION["cells"]}
ATK_PIECES = {1: [(0, 1), (0, 2), (0, 3), (1, 1)], 4: [(0, 4), (1, 2), (1, 3), (1, 4)],
              5: [(2, 2), (2, 3), (2, 4), (3, 2)], 7: [(3, 3), (4, 1), (4, 2), (4, 3)]}
CARDS_22 = [("I", 39, "gold"), ("L", 39, "atk"), ("I", 35, "gold"), ("I", 36, "gold"),
            ("L", 39, "atk"), ("L", 39, "atk"), ("I", 40, "gold"), ("L", 38, "atk")]


def cell_at(point):
    col = (point[0] - es.GRID_LEFT) / es.CELL_W - 0.5
    row = (point[1] - es.GRID_TOP) / es.CELL_H - 0.5
    return row, col


class EngravingGame(Game):
    def __init__(self, pieces=None, **state):
        super().__init__(**state)
        pieces = ATK_PIECES if pieces is None else pieces
        self.state["engraving"] = {
            "pieces": {index: sorted(cells) for index, cells in pieces.items()},
            "cards": [{"index": i, "shape": s, "level": lv, "kind": k, "locked": True, "placed": i in pieces}
                      for i, (s, lv, k) in enumerate(CARDS_22)],
            "popup": None, "preview": None}
        self.state.setdefault("corner_works", True)
        self.state.setdefault("popup_lock_works", True)

    def snapshot(self):
        width, height, state = super().snapshot()
        return width, height, copy.deepcopy(state)

    def occupied(self):
        return {cell for cells in self.state["engraving"]["pieces"].values() for cell in cells}

    def apply(self, screen, move, point, end=None):
        s, eng = self.state, self.state["engraving"]
        if screen == "soul_weapon" and move == "engraving":
            s["screen"] = "engraving"
        elif screen == "soul_weapon_engraving" and move == "close":
            s["screen"] = "soul"
        elif move == "lock":
            index = next(i for i in range(8) if es.lock_point(i) == point)
            if s["corner_works"]:
                eng["cards"][index]["locked"] = not eng["cards"][index]["locked"]
        elif move == "piece":
            eng["popup"] = next(i for i in range(8) if es.drag_point(i) == point)
        elif screen == "soul_weapon_engraving_piece" and move == "padlock":
            if s["popup_lock_works"]:
                card = eng["cards"][eng["popup"]]
                card["locked"] = not card["locked"]
        elif screen == "soul_weapon_engraving_piece" and move == "close":
            eng["popup"] = None
        elif move == "remove_piece":
            row, col = cell_at(point)
            cell = (round(row), round(col))
            index = next(i for i, cells in eng["pieces"].items() if cell in cells)
            del eng["pieces"][index]
            eng["cards"][index].update(placed=False, locked=False)
        elif move == "drag_piece":
            index = next(i for i in range(8) if es.drag_point(i) == point)
            base = setup_rules.normalised([tuple(c) for c in TABLE["shapes"][eng["cards"][index]["shape"]]["cells"]])
            row, col = cell_at(end)
            eng["preview"] = {"card": index, "turns": 0, "centre": (row - es.HOLD_ROWS, col), "base": base}
            self.lay()
        elif move == "rotate":
            eng["preview"]["turns"] += 1
            self.lay()
        elif move == "move":
            a, b = cell_at(point), cell_at(end)
            dr, dc = round(b[0] - a[0]), round(b[1] - a[1])
            eng["preview"]["cells"] = [(r + dr, c + dc) for r, c in eng["preview"]["cells"]]
            r0, c0 = eng["preview"]["centre"]
            eng["preview"]["centre"] = (r0 + dr, c0 + dc)
        elif move == "confirm":
            preview = eng["preview"]
            if self.valid():
                eng["pieces"][preview["card"]] = sorted(preview["cells"])
                eng["cards"][preview["card"]]["placed"] = True
                eng["preview"] = None
        elif move == "cancel":
            eng["preview"] = None
        else:
            super().apply(screen, move, point)

    def lay(self):
        """The preview's cells: its shape turned, centred where it is held."""
        preview = self.state["engraving"]["preview"]
        shape = setup_rules.turned(preview["base"], preview["turns"])
        height, width = max(r for r, _ in shape) + 1, max(c for _, c in shape) + 1
        top = round(preview["centre"][0] - (height - 1) / 2)
        left = round(preview["centre"][1] - (width - 1) / 2)
        preview["cells"] = [(r + top, c + left) for r, c in shape]

    def valid(self):
        cells = self.state["engraving"]["preview"]["cells"]
        return all(cell in VISION_CELLS and cell not in self.occupied() for cell in cells)

    def ports(self):
        ports = super().ports()
        game = self
        # The engraving switch: "real" (the supervised run done) unless said.
        ports.store.saved = {"engraving": game.state.get("engraving_switch", "real")}

        async def swipe(shot, screen, move, start, end, milliseconds, verified=False, seen=None):
            refusal = nav.guard(screen, move, start[0], start[1], "swipe", verified, seen)
            if refusal:
                raise RuntimeError(refusal)
            game.moves.append((screen, move))
            game.apply(screen, move, start, end)

        ports.swipe = swipe
        return ports


def fake_engraving_screen(game):
    def eng(shot):
        return shot[2]["engraving"]

    def on(shot):
        return shot[2]["screen"] == "engraving"

    def plain(shot):
        return on(shot) and eng(shot)["popup"] is None and eng(shot)["preview"] is None

    def grid(shot, size):
        if not plain(shot):
            return None
        e = eng(shot)
        taken = {cell for cells in e["pieces"].values() for cell in cells}
        cells = {(r, c): "piece" if (r, c) in taken else "empty" if (r, c) in VISION_CELLS else "none"
                 for r in range(5) for c in range(5)}
        return {"cells": cells, "pieces": sorted(sorted(cells) for cells in e["pieces"].values())}

    def cards(shot, shapes):
        out = []
        for card in eng(shot)["cards"] if on(shot) else []:
            if not plain(shot):
                out.append({"index": card["index"], "shape": None, "level": None, "kind": None, "locked": None,
                            "placed": None, "bright": None})
                continue
            lit = not card["locked"]
            out.append({"index": card["index"], "shape": None if lit else card["shape"],
                        "level": None if lit else card["level"], "kind": None if lit else card["kind"],
                        "locked": None if card["index"] in game.state.get("padlock_unread", ()) else card["locked"],
                        "placed": card["placed"], "bright": lit})
        return out

    def popup_padlock(shot):
        e = eng(shot)
        if not on(shot) or e["popup"] is None:
            return None
        return "closed" if e["cards"][e["popup"]]["locked"] else "open"

    def bar(shot):
        if not on(shot) or eng(shot)["preview"] is None:
            return None
        cells = eng(shot)["preview"]["cells"]
        valid = all(c in VISION_CELLS for c in cells) and not set(cells) & {
            cell for cs in eng(shot)["pieces"].values() for cell in cs}
        return {"cancel": (0.35, 0.35), "rotate": (0.44, 0.35), "confirm": (0.53, 0.35), "valid": valid}

    def cubes(shot):
        e = eng(shot)
        out = {cell: "cube" for cells in e["pieces"].values() for cell in cells}
        if e["preview"]:
            for cell in e["preview"]["cells"]:
                if -1 <= cell[0] <= 5 and -1 <= cell[1] <= 5:
                    out.setdefault(cell, "cube" if cell in VISION_CELLS else "red")
        return out

    return SimpleNamespace(
        title=on, weapon=lambda shot, names, font: "Vision" if on(shot) else None, grid=grid, cards=cards,
        locked=lambda shot, index: cards(shot, None)[index]["locked"] if on(shot) else None,
        popup=lambda shot: on(shot) and eng(shot)["popup"] is not None, popup_padlock=popup_padlock,
        bar=bar, cubes=cubes, lock_point=es.lock_point, drag_point=es.drag_point, cell_centre=es.cell_centre,
        hold_point=es.hold_point, INVENTORY_DROP=es.INVENTORY_DROP, POPUP_LOCK_TAP=es.POPUP_LOCK_TAP,
        POPUP_CLOSE_TAP=es.POPUP_CLOSE_TAP, PADLOCK_LEARNED=True, POPUP_LEARNED=True, PREVIEW_LEARNED=True)


def engrave(game, variant_name):
    loadout = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": VISION_ID, "variant": variant_name}},
               "mpw4": {"stage": 915, "preset": None, "soul_weapon": None}}
    part = {"setup": engraving_setup.engraving_setup, "screen": fake_engraving_screen(game), "rules": setup_rules,
            "variant": lambda weapon_id, name: VISION_VARIANTS.get(name)}
    ports, api = build(game, loadout, part)
    return outcome(asyncio.run(api["soul_weapon"]("mpw18"))), api


def vision_game(**state):
    return EngravingGame(equipped=VISION_ID, selected=VISION_ID, first_id=38, owned={VISION_ID}, **state)


def engraving_moves(game):
    return [m[1] for m in game.moves if m[0].startswith("soul_weapon_engraving")]


class Engraving(unittest.TestCase):
    def assert_gold_balanced(self, game):
        eng = game.state["engraving"]
        want = sorted(sorted(map(tuple, p["cells"])) for p in VISION_VARIANTS["Gold-balanced"]["pieces"])
        self.assertEqual(sorted(eng["pieces"].values()), want)
        # The bars hold the I Lv40 and Lv39; the L the three Lv39 but one.
        self.assertEqual(sorted(i for i in eng["pieces"] if CARDS_22[i][0] == "I"), [0, 6])
        self.assertNotIn(7, eng["pieces"])
        self.assertTrue(all(c["locked"] for c in eng["cards"]))
        self.assertIsNone(eng["popup"])
        self.assertIsNone(eng["preview"])
        self.assertEqual(game.state["screen"], "soul")  # parked

    def test_ready_as_it_is_nothing_touched(self):
        game = vision_game()
        answer, api = engrave(game, "Atk")
        self.assertEqual(answer, ("done", ""))
        self.assertEqual(engraving_moves(game), ["close"])
        self.assertEqual(game.alerts, [])
        captures = game.captures
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual(game.captures, captures + 1, "one look: still parked")

    def test_atk_to_gold_balanced_swaps_relocks_and_places(self):
        game = vision_game()
        answer, _ = engrave(game, "Gold-balanced")
        self.assertEqual(answer, ("done", ""), game.alerts)
        self.assert_gold_balanced(game)
        moves = engraving_moves(game)
        self.assertIn("remove_piece", moves)
        self.assertIn("rotate", moves)
        self.assertIn("confirm", moves)
        # Each removal is followed by its lock, before anything else.
        for i, move in enumerate(moves):
            if move == "remove_piece":
                self.assertEqual(moves[i + 1], "lock")
        self.assertNotIn("change", moves)
        self.assertEqual(len(game.alerts), 1)
        self.assertIn("ready", game.alerts[0])

    def test_a_corner_tap_without_effect_goes_through_the_popup_with_an_error(self):
        game = vision_game(corner_works=False)
        answer, _ = engrave(game, "Gold-balanced")
        self.assertEqual(answer, ("done", ""), game.alerts)
        self.assert_gold_balanced(game)
        self.assertIn("padlock", engraving_moves(game))
        self.assertTrue(any("corner tap" in alert and "did nothing" in alert for alert in game.alerts))

    def test_a_piece_that_stays_unlocked_is_an_error_never_silent(self):
        game = vision_game(corner_works=False, popup_lock_works=False)
        answer, _ = engrave(game, "Gold-balanced")
        self.assertEqual(answer[0], "failed")
        self.assertIn("déverrouillée", answer[1])
        self.assertTrue(any("unlocked" in alert for alert in game.alerts))
        self.assertIsNone(game.state["engraving"]["popup"])
        self.assertEqual(game.state["screen"], "soul")

    def test_an_unreadable_padlock_at_the_end_is_an_error_never_ready(self):
        game = vision_game(padlock_unread={2})
        answer, _ = engrave(game, "Atk")
        self.assertEqual(answer[0], "failed")
        self.assertIn("Engraving: #3 left unlocked (padlock unreadable)", game.alerts)
        # Never tapped: a tap on a closed padlock opens it.
        self.assertNotIn("lock", engraving_moves(game))
        self.assertTrue(game.state["engraving"]["cards"][2]["locked"])

    def test_the_engraving_step_is_timed_on_its_own(self):
        game = vision_game()
        with self.assertLogs(level="INFO") as logs:
            answer, _ = engrave(game, "Gold-balanced")
        self.assertEqual(answer, ("done", ""), game.alerts)
        self.assertTrue(any("engraving step took" in line and "gestures)" in line for line in logs.output))
        self.assertRegex(game.alerts[0], r"\(engraving [\d.]+ s, [1-9]\d* gestures\)")

    def test_a_variant_change_of_the_running_mode_is_applied_not_cached(self):
        game = vision_game()
        answer, api = engrave(game, "Atk")
        self.assertEqual(answer, ("done", ""))
        loadout = {"stage": 920, "preset": None, "soul_weapon": {"id": VISION_ID, "variant": "Gold-balanced"}}
        answer = asyncio.run(api["ensure_soul_weapon"]("mpw18", loadout))
        self.assertEqual(outcome(answer), ("done", ""), game.alerts)
        self.assert_gold_balanced(game)

    def test_engraving_off_by_default_no_gesture_and_an_error(self):
        game = vision_game(engraving_switch=None)
        with self.assertLogs(level="INFO") as logs:
            answer, api = engrave(game, "Gold-balanced")
        self.assertEqual(answer, ("failed", "Soul Weapon : gravure pas mise en place : premier passage supervisé "
                                            "en attente"))
        self.assertEqual(engraving_moves(game), [])
        self.assertNotIn(("soul_weapon", "engraving"), game.moves)
        self.assertTrue(any("ERROR" in line and "engraving not set up: first supervised run pending" in line
                            for line in logs.output))
        # Not ready: read again next time, never cached.
        self.assertEqual(asyncio.run(api["soul_weapon"]("mpw18"))["result"], "failed")
        self.assertEqual(engraving_moves(game), [])
        self.assertNotIn("ready", " ".join(game.alerts))
        # The watchdog's relaunch: one alert, in English.
        asyncio.run(api["relaunched"]("mpw18"))
        self.assertEqual(len(game.alerts), 1)
        self.assertIn("engraving not set up: first supervised run pending", game.alerts[0])
        self.assertEqual(engraving_moves(game), [])

    def test_engraving_off_the_setup_itself_makes_no_gesture(self):
        game = vision_game()
        ports = game.ports()
        helpers = SimpleNamespace(look=None, tap=None, front=None, Stop=RuntimeError)
        setup = engraving_setup.engraving_setup(ports, fake_engraving_screen(game), setup_rules, helpers,
                                                None, None)
        entry = next(e for e in TABLE["weapons"] if e["id"] == VISION_ID)
        shot, done = asyncio.run(setup("shot", entry, "Atk", VISION_VARIANTS["Atk"], [], None, {}))
        self.assertFalse(done["ok"])
        self.assertEqual(game.moves, [])

    def test_engraving_switch_through_post_farming(self):
        game = vision_game(engraving_switch=None)
        loadout = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": VISION_ID, "variant": "Atk"}}}
        part = {"setup": engraving_setup.engraving_setup, "screen": fake_engraving_screen(game), "rules": setup_rules,
                "variant": lambda weapon_id, name: VISION_VARIANTS.get(name)}
        ports = game.ports()
        soul = {"feature": feature.soul_weapon, "reader": fake_reader(game), "rules": rules, "table": TABLE,
                "loadout": lambda mode: loadout[mode], "engraving": part}
        built = stage_change.stage_change(ports, fake_screens(), SimpleNamespace(regions=lambda table: []),
                                          SimpleNamespace(), stage_rules, STAGES, soul)
        post = next(h for m, p, h in built["routes"] if m == "POST")

        class Request:
            async def json(self):
                return self.body

        request = Request()
        request.body = {"engraving": "on"}
        self.assertEqual(asyncio.run(post(request))[0], 400)
        self.assertEqual(ports.store.sections["engraving"](), "off")
        request.body = {"engraving": "real"}
        status, body = asyncio.run(post(request))
        self.assertEqual((status, body["soul_weapon"]["engraving"]), (200, "real"))
        self.assertEqual(ports.store.sections["engraving"](), "real")
        self.assertEqual(outcome(asyncio.run(built["api"]["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual(engraving_moves(game), ["close"])

    def test_the_lower_l_of_2026_10_21_is_swapped(self):
        pieces = {0: [(0, 1), (0, 2), (0, 3), (0, 4)], 6: [(1, 1), (1, 2), (1, 3), (1, 4)],
                  4: [(2, 2), (2, 3), (2, 4), (3, 2)], 7: [(3, 3), (4, 1), (4, 2), (4, 3)]}
        game = vision_game(pieces=pieces)
        answer, _ = engrave(game, "Gold-balanced")
        self.assertEqual(answer, ("done", ""), game.alerts)
        self.assert_gold_balanced(game)


if __name__ == "__main__":
    unittest.main()
