"""The screen model (screens.look, screen_registry.json) on crops of real
captures (fixtures/) pasted back where they were cut on an empty screen:
every registered screen and overlay is recognised from its fixtures with
a margin over every other one, no fixture alone is taken for a screen it
does not belong to, an image of no screen is unknown, and every
navigation.json screen without anchors is pending capture, never
matched, and named in docs/TODO.md's calibration list.
Run: python3 -m unittest test_screen_model"""

import importlib.util
import os
import random
import re
import statistics
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
TODO = os.path.join(HERE, "..", "..", "docs", "TODO.md")


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_model_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


screens = load("screens")
W, H = 480, 1040
FIXTURES = sorted(name[:-4] for name in os.listdir(os.path.join(HERE, "fixtures")) if name.endswith(".txt")
                  and name != "texts.json")
# A screen's margin over another must be at least this.
GAP = 0.3
# look() on one capture, {screen, overlays}, in ms (the pixel font's
# naming of an unknown screen apart).
BUDGET_MS = 20


class ConcurrentScreens(unittest.TestCase):
    def test_direct_anchor_calls_do_not_reuse_the_last_capture(self):
        anchor = screens._anchor({"share": "MANA_BAR", "test": "white", "above": .6, "step": 1})
        self.assertGreater(anchor((4, 4, bytes([255, 255, 255]) * 16)), 0)
        self.assertLess(anchor((4, 4, bytes(48))), 0)

    def test_two_workers_never_share_capture_measurements(self):
        white = (4, 4, bytes([255, 255, 255]) * 16)
        black = (4, 4, bytes(48))
        first_read, second_read, first_done = Event(), Event(), Event()
        white_anchor = screens._anchor({"share": "MANA_BAR", "test": "white", "above": .6, "step": 1})
        black_anchor = screens._anchor({"share": "MANA_BAR", "test": "white", "below": .4, "step": 1})

        def interleaved(shot):
            if shot is white:
                first_read.set()
                self.assertTrue(second_read.wait(3))
            else:
                second_read.set()
                self.assertTrue(first_done.wait(3))
            return black_anchor(shot)

        def classify(shot):
            if shot is black:
                self.assertTrue(first_read.wait(3))
            try:
                return screens.look(shot)["screen"]
            finally:
                if shot is white:
                    first_done.set()

        registry = {name: {"status": "measured"} for name in ("white", "black")}
        with patch.multiple(screens, BASES=["white", "black"], OVERLAYS=[], REGISTRY=registry,
                            ANCHORS={"white": [white_anchor], "black": [interleaved]}, _seen=[]):
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(classify, white)
                second = workers.submit(classify, black)
                self.assertEqual(first.result(timeout=5), "white")
                self.assertEqual(second.result(timeout=5), "black")


def screen(*names, background=(20, 16, 14)):
    """Real crops at their recorded native positions. Mixed-size fixtures
    use the largest canvas, scaling only the smaller historical crops."""
    crops = [screens.fixture(name) for name in names]
    width, height = max(((crop[0], crop[1]) for crop in crops), default=(W, H))
    pixels = bytearray(bytes(background) * (width * height))
    for sw, sh, x, y, w, h, data in crops:
        if (sw, sh) != (width, height):
            sx, sy = width / sw, height / sh
            left, top, right, bottom = round(x * sx), round(y * sy), round((x + w) * sx), round((y + h) * sy)
            target_w, target_h = right - left, bottom - top
            xs = [min(w - 1, int(col / sx)) * 3 for col in range(target_w)]
            data = b"".join(b"".join(data[start + col:start + col + 3] for col in xs)
                            for start in (min(h - 1, int(row / sy)) * w * 3 for row in range(target_h)))
            x, y, w, h = left, top, target_w, target_h
        for row in range(h):
            start = ((y + row) * width + x) * 3
            pixels[start:start + w * 3] = data[row * w * 3:(row + 1) * w * 3]
    return width, height, bytes(pixels)


def made(key):
    """The screen key's fixtures make, on its background."""
    entry = screens.REGISTRY[key]
    return screen(*entry["fixtures"], background=tuple(entry.get("background", (20, 16, 14))))


def scaled(shot, width, height):
    """shot resized to width x height, nearest pixel (the page's other device shapes)."""
    w, h, pixels = shot
    out = bytearray()
    for y in range(height):
        row = int(y * h / height) * w
        for x in range(width):
            i = (row + int(x * w / width)) * 3
            out += pixels[i:i + 3]
    return width, height, bytes(out)


REGISTERED = [key for key, entry in screens.REGISTRY.items() if entry["status"] == "registered"]
MEASURED = [key for key, entry in screens.REGISTRY.items() if entry["status"] == "measured"]


def todo_line(prefix):
    """The `names` listed on docs/TODO.md's paragraph starting with prefix."""
    with open(TODO, encoding="utf-8") as f:
        text = f.read()
    start = text.index(prefix)
    paragraph = text[start:text.find("\n", start)]
    return re.findall(r"`([^`]+)`", paragraph)


class Registry(unittest.TestCase):
    def test_every_id_is_a_navigation_screen_or_a_named_overlay(self):
        overlays_only = {"panel", "better_weapon_toast"}
        for key, entry in screens.REGISTRY.items():
            with self.subTest(key=key):
                self.assertTrue(key in screens.NAMES or key in overlays_only and entry["kind"] == "overlay")
                self.assertIn(entry["status"], screens.TIERS)
                self.assertTrue(entry["anchors"])
                for base in entry.get("over", []):
                    self.assertEqual(screens.REGISTRY[base]["kind"], "screen")

    def test_a_registered_screen_has_real_fixtures(self):
        for key in REGISTERED:
            with self.subTest(key=key):
                fixtures = screens.REGISTRY[key].get("fixtures")
                self.assertTrue(fixtures)
                for name in fixtures:
                    self.assertIn(name, FIXTURES)
                for spec in screens.REGISTRY[key]["anchors"]:
                    if "patch" in spec:
                        self.assertIn(spec["patch"], fixtures, "an anchor is cut from the screen's own fixtures")

    def test_a_signature_is_a_downscaled_grey_grid(self):
        for key, signature in screens.SIGNATURES.items():
            for grid in signature:
                self.assertLessEqual(len(grid), 2 * screens.SAMPLES, key)

    def test_pending_screens_are_named_in_the_calibration_list(self):
        self.assertEqual(sorted(todo_line("Screens pending capture:")), sorted(screens.pending()))
        self.assertEqual(sorted(todo_line("Screens recognised without a fixture:")), sorted(MEASURED))


nav = load("nav")


def move_of(ref):
    screen, move_id = ref.split("/")
    return screen, next((m for m in nav.connections(screen) if m["id"] == move_id), None)


def point_of(move, entry=None):
    if entry and entry.get("point"):
        return entry["point"]
    if "tap" in move or "swipe" in move:
        return (move.get("tap") or move["swipe"])[:2]
    left, top, right, bottom = move["area"]
    return (left + right) / 2, (top + bottom) / 2


class Tree(unittest.TestCase):
    """Every screen known so far: a parent, the move that reaches it and
    the one back, each an allowed move the guard lets through; a screen
    the tour skips says why; a scroll area the tour swipes is measured,
    with its swipe in navigation.json."""

    def test_every_parent_is_known(self):
        for key, entry in screens.TREE.items():
            with self.subTest(key=key):
                self.assertTrue(entry["parent"] is None or entry["parent"] == "battle" or entry["parent"] in screens.TREE)
                self.assertTrue(entry["visit"] or entry.get("why"))
                if entry["look"] not in ("panel", "screen"):
                    self.assertIn(entry["look"], screens.REGISTRY)

    def test_the_tour_takes_allowed_moves_only(self):
        for key, entry in screens.TREE.items():
            if not entry["visit"]:
                continue
            with self.subTest(key=key):
                parent = screens.TREE.get(entry["parent"], {"screen": "battle"})["screen"]
                screen, move = move_of(entry["via"])
                self.assertEqual(screen, parent, "the move leaves from the parent's screen")
                self.assertEqual(move["to"], entry["screen"])
                x, y = point_of(move, entry)
                self.assertIsNone(nav.guard(screen, move["id"], x, y, "tap"))
                if "back" in entry:
                    screen, back = move_of(entry["back"])
                    self.assertEqual(screen, entry["screen"])
                    kind = "key" if "key" in back else "tap"
                    # A combat return additionally consumes a fresh reading;
                    # verified alone does not satisfy its visibility guard.
                    seen = ({"look": {"screen": "battle", "plain": False, "overlays": ["panel"]},
                             "combat_visible": True} if back.get("needs", {}).get("reduced_battle") else None)
                    self.assertIsNone(nav.guard(screen, back["id"], *(point_of(back) if kind == "tap" else (None, None)),
                                                kind, verified=True, seen=seen))

    def test_a_skipped_move_is_never_one_the_tour_sends(self):
        forbidden = [key for key, entry in screens.TREE.items() if entry["via"] and move_of(entry["via"])[1].get("forbidden")]
        for key in forbidden:
            self.assertFalse(screens.TREE[key]["visit"], key)
        self.assertIn("promotion_bonus", forbidden)

    def test_scroll_areas(self):
        for key, entry in screens.TREE.items():
            for area in entry.get("scroll", []):
                with self.subTest(key=key, content=area["content"]):
                    left, top, right, bottom = area["rect"]
                    self.assertTrue(0 <= left < right <= 1 and 0 <= top < bottom <= 1)
                    if not area["measured"]:
                        self.assertNotIn("move", area)
                        self.assertTrue(area["why"])
                        continue
                    screen, move = move_of(area["move"])
                    self.assertEqual(screen, entry["screen"])
                    self.assertFalse(move.get("forbidden"))
                    x, y = point_of(move)
                    if area["direction"] != "pages":
                        self.assertIn("swipe", move)
                        self.assertTrue(left <= x <= right and top <= y <= bottom, "the swipe starts in its area")
                        self.assertTrue(left <= move["swipe"][2] <= right and top <= move["swipe"][3] <= bottom)


class Recognised(unittest.TestCase):
    def test_equipment_selected_tabs_are_distinct_and_scoped(self):
        for key in ("equipment_weapon", "equipment_accessories"):
            other = "equipment_accessories" if key == "equipment_weapon" else "equipment_weapon"
            for width, height in ((480, 1040), (720, 1560)):
                with self.subTest(tab=key, width=width):
                    seen = screens.look(scaled(made(key), width, height))
                    self.assertIn(key, seen["overlays"])
                    self.assertNotIn(other, seen["overlays"])
        growth = screen("battle_emerald", "growth_at_equipment_tabs_720")
        self.assertNotIn("equipment_weapon", screens.look(growth)["overlays"])
        self.assertNotIn("equipment_accessories", screens.look(growth)["overlays"])

    def test_native_weapon_detail_needs_both_tabs_and_close(self):
        native = made("weapon_detail")
        self.assertEqual(native[:2], (720, 1560), 'reviewed native pixels are not distorted to make an anchor')
        self.assertIn("weapon_detail", screens.look(native)["overlays"])
        for crop in ("weapon_detail_tabs_720", "weapon_detail_close_720"):
            self.assertNotIn("weapon_detail", screens.look(screen("battle_emerald", crop))["overlays"])

    def test_every_registered_screen_from_its_fixtures_with_a_margin(self):
        for key in REGISTERED:
            entry = screens.REGISTRY[key]
            base = key if entry["kind"] == "screen" else entry["over"][0]
            with self.subTest(key=key):
                seen = screens.look(made(key))
                self.assertEqual(seen["screen"], base)
                self.assertGreaterEqual(seen["margin"], GAP)
                for other in screens.BASES:
                    if other != base:
                        self.assertLessEqual(seen["margins"][other], seen["margins"][base] - GAP, other)
                if entry["kind"] == "overlay":
                    self.assertIn(key, seen["overlays"])
                    self.assertGreaterEqual(seen["margins"][key], GAP)

    def test_at_another_screen_size(self):
        for key in ("battle", "saver", "soul_weapon", "soul_weapon_engraving"):
            with self.subTest(key=key):
                seen = screens.look(scaled(made(key), 360, 780))
                self.assertEqual(seen["screen"], key if key != "soul_weapon" else "battle")
                if key == "soul_weapon":
                    self.assertIn("soul_weapon", seen["overlays"])

    def test_the_soul_weapon_screen_over_the_battle(self):
        self.assertTrue(screens.soul_weapon_over_battle(made("soul_weapon")))
        self.assertFalse(screens.soul_weapon_over_battle(made("battle")))
        self.assertFalse(screens.soul_weapon_over_battle(made("equipment_weapon")))
        self.assertFalse(screens.soul_weapon_over_battle(screen("sw_title", "sw_tabs")), "no battle under it")

    def test_the_names_the_features_know(self):
        # The bottom menu's names stay grey (138) on the plain battle: the
        # legacy split by light names calls it "menu" (docs/TODO.md), the
        # skill bar (plain) tells it.
        self.assertIn(screens.classify(made("battle")), ("battle", "menu"))
        self.assertEqual(screens.classify(made("soul_weapon")), "menu")
        self.assertEqual(screens.classify(made("saver")), "saver")
        self.assertEqual(screens.classify(made("sign_in")), "sign_in")
        self.assertEqual(screens.classify(made("soul_weapon_engraving")), "other")
        self.assertEqual(screens.known_name(made("soul_weapon_engraving")), "Soul Weapon Engraving")
        self.assertIsNone(screens.known_name(screen()))
        self.assertTrue(screens.plain_battle(made("battle")))
        self.assertFalse(screens.plain_battle(made("soul_weapon")))


class QuestAndBattle(unittest.TestCase):
    def test_each_quest_tab_on_real_crops_at_multiple_sizes(self):
        for tab in ("daily", "repeat", "achievement"):
            shot = screen("battle_emerald", "quest_title", f"quest_tabs_{tab}")
            for width, height in ((480, 1040), (360, 780), (720, 1560)):
                with self.subTest(tab=tab, size=(width, height)):
                    image = shot if width == 480 else scaled(shot, width, height)
                    seen = screens.look(image)
                    self.assertEqual(seen["screen"], "battle")
                    self.assertIn("quest_panel", seen["overlays"])
                    self.assertEqual(seen["quest_tab"], tab)

    def test_title_and_unambiguous_active_tab_required(self):
        for names in (("battle_emerald", "quest_title"), ("battle_emerald", "quest_tabs_daily"),
                      ("battle_emerald", "settings_title")):
            with self.subTest(crops=names):
                shot = screen(*names)
                self.assertIsNone(screens.quest_tab(shot))
                self.assertNotIn("quest_panel", screens.look(shot)["overlays"])
        width, height, data = screen("battle_emerald", "quest_title", "quest_tabs_daily")
        pixels = bytearray(data)
        for y in range(224, 242):
            for x in range(191, 300):
                i = (y * width + x) * 3
                pixels[i:i + 3] = b"\xff\xff\xff"
        ambiguous = width, height, bytes(pixels)
        self.assertIsNone(screens.quest_tab(ambiguous), "two bright tabs are ambiguous")
        self.assertNotIn("quest_panel", screens.look(ambiguous)["overlays"])

    def test_full_battle_with_dark_menu_labels_is_not_a_panel(self):
        for width, height in ((480, 1040), (360, 780), (720, 1560)):
            seen = screens.look(scaled(made("battle"), width, height))
            self.assertTrue(seen["plain"])
            self.assertNotIn("panel", seen["overlays"])
        self.assertIn("panel", screens.look(made("soul_weapon"))["overlays"])


class Confusion(unittest.TestCase):
    """Each fixture alone, and each screen's fixtures together, on three
    backgrounds: a registered screen found is one a fixture belongs to; a
    registered overlay found too."""

    def owners(self, names):
        """The registered screens and overlays any of names belongs to."""
        return {key for key in REGISTERED if set(screens.REGISTRY[key]["fixtures"]) & set(names)}

    def test_no_screen_taken_for_another(self):
        cases = [[name] for name in FIXTURES] + [screens.REGISTRY[key]["fixtures"] for key in REGISTERED]
        confused = []
        for names in cases:
            for background in ((20, 16, 14), (0, 0, 0), (230, 230, 230)):
                seen = screens.look(screen(*names, background=background))
                owners = self.owners(names)
                bases = {key if screens.REGISTRY[key]["kind"] == "screen" else screens.REGISTRY[key]["over"][0]
                         for key in owners}
                # A measured screen (no fixture yet, e.g. title from a share
                # of white) may take a stray crop: only registered ones are held.
                if seen["screen"] in REGISTERED and seen["screen"] not in bases:
                    confused.append((names, background, seen["screen"]))
                for overlay in seen["overlays"]:
                    if overlay in REGISTERED and overlay not in owners:
                        confused.append((names, background, overlay))
        self.assertEqual(confused, [])


class Unknown(unittest.TestCase):
    def test_no_registered_screen_on_stripes(self):
        # title is recognised from a share of white only (measured, no
        # fixture yet): stripes pass it. A registered screen never does.
        stripes = (W, H, bytes((x * 7) % 256 for x in range(W * H * 3)))
        self.assertNotIn(screens.look(stripes)["screen"], REGISTERED)

    def test_no_screen_on_an_empty_noisy_or_foreign_image(self):
        rng = random.Random(7)
        noise = bytes(rng.randrange(256) for _ in range(W * H * 3))
        for name, shot in (("black", screen(background=(0, 0, 0))), ("grey", screen(background=(128, 128, 128))),
                           ("white", screen(background=(255, 255, 255))), ("noise", (W, H, noise)),
                           ("a dialog", screen("row_913", "banner_giants_glass", background=(60, 40, 30)))):
            with self.subTest(image=name):
                seen = screens.look(shot)
                self.assertEqual(seen["screen"], "unknown")
                self.assertEqual(seen["overlays"], [])
                self.assertEqual(screens.classify(shot), "other")

    def test_a_pending_screen_is_never_matched(self):
        names = set(screens.BASES) | set(screens.OVERLAYS)
        for key in screens.pending():
            self.assertNotIn(key, names)


class OnePass(unittest.TestCase):
    def test_one_look_per_capture(self):
        shot = made("soul_weapon")
        self.assertIs(screens.look(shot), screens.look(shot))
        other = made("battle")
        self.assertIsNot(screens.look(other), screens.look(shot))

    def test_under_the_budget(self):
        shots = [made(key) for key in REGISTERED] + [screen()]
        times = []
        for shot in shots * 3:
            del screens._seen[:]
            start = time.perf_counter()
            screens.look(shot)
            times.append((time.perf_counter() - start) * 1000)
        self.assertLess(statistics.median(times), BUDGET_MS)


if __name__ == "__main__":
    unittest.main()
