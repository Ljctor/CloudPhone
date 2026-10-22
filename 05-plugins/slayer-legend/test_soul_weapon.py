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
rules = load("features/soul_weapon_rules")
feature = load("features/soul_weapon")
stage_change = load("features/stage_change")
stage_rules = load("features/stage_change_rules")
nav = load("nav")
es = load("engraving_screen")
engraving_setup = load("features/engraving_setup")
setup_rules = load("features/engraving_setup_rules")
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
        self.assertIn("tag not calibrated", step[1])
        self.assertIn("not equipped", step[1])
        # Done, select and scroll do not need it.
        v = view("Ambition", 2, tag="Unequip")
        self.assertEqual(rules.plan(v, "Ambition", rules.observe(rules.fresh_memory(None), v, ORDER), ORDER),
                         ("done",))

    def test_failures(self):
        self.assertIn("Owned : 0", self.plan(view("Ambition", 2, owned=0, tag="Equip"))[1])
        self.assertIn("illisible", self.plan(view("Ambition", 2, owned=None, tag="Equip"))[1])
        self.assertIn("étiquette", self.plan(view("Ambition", 2))[1])
        self.assertIn("pas reconnu", self.plan(view(opened=False))[1])
        self.assertIn("name shared", self.plan(view("Grand", 0), target="Silence")[1])
        self.assertIn("illisible", self.plan(view(None, 1))[1])
        self.assertIn("liste", self.plan(view("Grand", None, count=0))[1])

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
        self.assertIn("ordre", rules.plan(view("Wild", 1), "Ambition", memory, ORDER)[1])

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
                               tasks=tasks, respond=lambda value, status=200: (status, value))


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
    return answer["result"], answer["text"]


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
        self.assertEqual(game.moves[-2:], [("soul_weapon", "close"), ("equipment_weapon", "close")])
        self.assertEqual(game.state["screen"], "battle")
        # The next time: nothing read, nothing tapped.
        before, captures = len(game.moves), game.captures
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual((len(game.moves), game.captures), (before, captures))
        # After a relaunch it reads again.
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
        self.assertIn("fiche d’une arme", answer["text"])
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
        self.assertIn("Soul Weapon", answer["text"])
        self.assertIn("Owned : 0", answer["text"])
        self.assertNotIn(("soul_weapon", "equip"), game.moves)

    def test_equip_gate_closed_one_error_alert(self):
        game = Game(selected=AMBITION, tag_learned=False)
        answer, _ = equip(game, "mpw4")
        self.assertEqual(answer["result"], "failed")
        self.assertIn("Equip tag not calibrated, not equipped", answer["text"])
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
        self.assertIn("Equip sans effet", answer["text"])
        self.assertEqual(game.moves.count(("soul_weapon", "equip")), 1)

    def test_no_weapon_chosen(self):
        game = Game(selected=GRAND)
        loadouts = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": None}}
        _, api = build(game, loadouts)
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual(game.moves, [])

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
        self.assertIn("Après la relance", game.alerts[0])
        self.assertIsNone(api["relaunched"]("mine"))


# The engraving: Ambition's pattern, a variant of one vertical bar (no turn)
# on column 1, the rest of the pattern left empty.
BAR = [(0, 1), (1, 1), (2, 1), (3, 1)]
ONE_BAR = {"name": "Bar", "pieces": [{"shape": "I", "rotation": 0, "cells": [list(c) for c in BAR]}]}
TURNED_BAR = {"name": "Turned", "pieces": [{"shape": "I", "rotation": 1, "cells": [[1, 1], [1, 2], [1, 3], [1, 4]]}]}
AMBITION_CELLS = {tuple(c) for c in next(e for e in TABLE["weapons"] if e["id"] == AMBITION)["cells"]}


def card(index, shape, level, locked=True, placed=False):
    return {"index": index, "shape": shape, "rotation": 0, "cells": [], "level": level, "locked": locked,
            "placed": placed, "kind": {"I": "gold", "L": "atk"}[shape]}


class EngravingGame(Game):
    """The scripted game with the engraving screen: the grid's cells and
    pieces, the 8 cards; a padlock tap toggles it, a drag places the card's
    piece (base orientation) centred where it is dropped."""

    def __init__(self, cards, pieces=(), **state):
        super().__init__(**state)
        cells = {(r, c): ("empty" if (r, c) in AMBITION_CELLS else "none") for r in range(5) for c in range(5)}
        for piece in pieces:
            for cell in piece:
                cells[cell] = "piece"
        self.state["engraving"] = {"cells": cells, "pieces": [sorted(p) for p in pieces], "cards": cards}
        self.state["drag_misses"] = False

    def snapshot(self):
        width, height, state = super().snapshot()
        return width, height, copy.deepcopy(state)

    def apply(self, screen, move, point, end=None):
        s, eng = self.state, self.state["engraving"]
        if screen == "soul_weapon" and move == "engraving":
            s["screen"] = "engraving"
        elif screen == "soul_weapon_engraving" and move == "close":
            s["screen"] = "soul"
        elif move == "lock":
            index = next(i for i in range(8) if es.lock_point(i) == point)
            eng["cards"][index]["locked"] = not eng["cards"][index]["locked"]
        elif move == "drag_piece":
            index = next(i for i in range(8) if es.drag_point(i) == point)
            shape = TABLE["shapes"][eng["cards"][index]["shape"]]["cells"]
            height, width = max(r for r, _ in shape) + 1, max(c for _, c in shape) + 1
            row = (end[1] - es.GRID_TOP) / es.CELL_H - 0.5 - (height - 1) / 2 + (1 if s["drag_misses"] else 0)
            col = (end[0] - es.GRID_LEFT) / es.CELL_W - 0.5 - (width - 1) / 2
            cells = sorted((round(row) + r, round(col) + c) for r, c in shape)
            if all(eng["cells"].get(cell) == "empty" for cell in cells):
                for cell in cells:
                    eng["cells"][cell] = "piece"
                eng["pieces"].append(cells)
                eng["cards"][index]["placed"] = True
        else:
            super().apply(screen, move, point)

    def ports(self):
        ports = super().ports()
        game = self

        async def swipe(shot, screen, move, start, end, milliseconds, verified=False, seen=None):
            refusal = nav.guard(screen, move, start[0], start[1], "swipe", verified, seen)
            if refusal:
                raise RuntimeError(refusal)
            game.moves.append((screen, move))
            game.apply(screen, move, start, end)

        ports.swipe = swipe
        return ports


def fake_engraving_screen():
    def on(shot):
        return shot[2]["screen"] == "engraving"

    return SimpleNamespace(
        title=on, weapon=lambda shot, names, font: "Ambition" if on(shot) else None,
        grid=lambda shot, size: ({"cells": shot[2]["engraving"]["cells"], "pieces": shot[2]["engraving"]["pieces"]}
                                 if on(shot) else None),
        cards=lambda shot, shapes: shot[2]["engraving"]["cards"] if on(shot) else [],
        locked=lambda shot, index: shot[2]["engraving"]["cards"][index]["locked"] if on(shot) else None,
        lock_point=es.lock_point, drag_point=es.drag_point, cell_centre=es.cell_centre)


def engraving_part(variant):
    return {"setup": engraving_setup.engraving_setup, "screen": fake_engraving_screen(), "rules": setup_rules,
            "variant": lambda weapon_id, name: variant if name == variant["name"] else None}


def engrave(game, variant):
    loadout = {"mpw18": {"stage": 920, "preset": None, "soul_weapon": {"id": AMBITION, "variant": variant["name"]}},
               "mpw4": {"stage": 915, "preset": None, "soul_weapon": None}}
    ports, api = build(game, loadout, engraving_part(variant))
    return outcome(asyncio.run(api["soul_weapon"]("mpw18"))), api


CARDS_FREE = [card(0, "I", 39), card(1, "L", 39), card(2, "I", 35), card(3, "I", 40),
              card(4, "L", 38), card(5, "L", 37), card(6, "I", 36), card(7, "L", 30)]


class Engraving(unittest.TestCase):
    def test_ready_as_it_is_nothing_touched(self):
        cards = copy.deepcopy(CARDS_FREE)
        cards[3]["placed"] = True
        game = EngravingGame(cards, [BAR])
        answer, api = engrave(game, ONE_BAR)
        self.assertEqual(answer, ("done", ""))
        self.assertIn(("soul_weapon", "engraving"), game.moves)
        self.assertIn(("soul_weapon_engraving", "close"), game.moves)
        self.assertFalse([m for m in game.moves if m[1] in ("lock", "drag_piece")])
        self.assertEqual(game.alerts, [])
        self.assertEqual(game.state["screen"], "battle")
        # Ready: cached, the next time nothing is read.
        captures = game.captures
        self.assertEqual(outcome(asyncio.run(api["soul_weapon"]("mpw18"))), ("done", ""))
        self.assertEqual(game.captures, captures)

    def test_locks_first_then_the_highest_level_bar_dragged(self):
        cards = copy.deepcopy(CARDS_FREE)
        cards[5]["locked"] = False
        game = EngravingGame(cards)
        answer, api = engrave(game, ONE_BAR)
        self.assertEqual(answer, ("done", ""))
        engraving_moves = [m[1] for m in game.moves if m[0] == "soul_weapon_engraving"]
        self.assertEqual(engraving_moves, ["lock", "drag_piece", "close"])
        eng = game.state["engraving"]
        self.assertEqual(eng["pieces"], [BAR])
        self.assertTrue(eng["cards"][3]["placed"])  # I Lv40, not the Lv39
        self.assertTrue(all(c["locked"] for c in eng["cards"]))
        self.assertEqual(len(game.alerts), 1)
        self.assertIn("Soul Weapon Ambition (Bar) prête : 1 pièce(s) posée(s), 1 verrouillée(s)", game.alerts[0])

    def test_a_padlock_not_read_stops_before_any_drag(self):
        cards = copy.deepcopy(CARDS_FREE)
        cards[2]["locked"] = None
        game = EngravingGame(cards)
        answer, api = engrave(game, ONE_BAR)
        self.assertEqual(answer[0], "failed")
        self.assertIn("cadenas pas lu fermé : n°3", answer[1])
        self.assertFalse([m for m in game.moves if m[1] in ("lock", "drag_piece")])
        # Not ready: not cached, read again the next time.
        captures = game.captures
        asyncio.run(api["soul_weapon"]("mpw18"))
        self.assertGreater(game.captures, captures)

    def test_a_turned_piece_is_alerted_not_guessed(self):
        game = EngravingGame(copy.deepcopy(CARDS_FREE))
        answer, _ = engrave(game, TURNED_BAR)
        self.assertEqual(answer[0], "failed")
        self.assertIn("Gravure de Ambition (Turned) pas prête", answer[1])
        self.assertIn("rotation pas apprise", answer[1])
        self.assertNotIn(("soul_weapon_engraving", "drag_piece"), game.moves)

    def test_a_drag_landing_elsewhere_stops(self):
        game = EngravingGame(copy.deepcopy(CARDS_FREE))
        game.state["drag_misses"] = True
        answer, _ = engrave(game, ONE_BAR)
        self.assertEqual(answer[0], "failed")
        self.assertIn("n’a pas donné les cases attendues", answer[1])
        self.assertEqual(game.moves.count(("soul_weapon_engraving", "drag_piece")), 1)
        self.assertEqual(game.state["screen"], "battle")


if __name__ == "__main__":
    unittest.main()
