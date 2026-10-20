"""The gold scroll check shared by the mine and mpw4 farming
(gold_scroll.py): the icon read off a screenshot, the 2-look debounce, one
alert per absence, back once seen again, unknown off a fight screen.
Run: python3 -m unittest test_gold_scroll"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 480, 1040


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scroll = load("gold_scroll")
mode_rules = load("features/mode_rules")


def shot(gold):
    """A dark screen, with a gold (#ffbb33) icon in the buffs' row or not."""
    pixels = bytearray(b"\x20\x20\x30" * (W * H))
    if gold:
        for y in range(62, 78):
            for x in range(20, 36):
                pixels[(y * W + x) * 3:(y * W + x) * 3 + 3] = b"\xff\xbb\x33"
    return (W, H, bytes(pixels))


def looks(seen_list, looks=scroll.LOOKS):
    record, news = scroll.fresh(), []
    for seen in seen_list:
        record, said = scroll.look(record, seen, looks)
        news.append(said)
    return record, news


class Detector(unittest.TestCase):
    def test_the_icon(self):
        self.assertTrue(scroll.shown(shot(True)))
        self.assertFalse(scroll.shown(shot(False)))

    def test_unknown_off_a_fight_screen(self):
        self.assertIs(scroll.seen(True, shot(True)), True)
        self.assertIs(scroll.seen(True, shot(False)), False)
        self.assertIsNone(scroll.seen(False, shot(True)))
        self.assertIsNone(scroll.seen(False, shot(False)))


class Record(unittest.TestCase):
    def test_missing_after_two_looks(self):
        record, news = looks([True, False])
        self.assertEqual((record["gold"], news), (True, [None, None]), "one miss keeps it as told")
        record, news = looks([True, False, False])
        self.assertEqual((record["gold"], news[-1]), (False, "gone"))
        record, news = looks([None, False, False])
        self.assertEqual((record["gold"], news), (False, [None, None, "gone"]), "also never seen before")

    def test_the_debounce_is_a_parameter(self):
        record, news = looks([False, False], looks=3)
        self.assertEqual((record["gold"], news), (None, [None, None]))
        record, news = looks([False], looks=1)
        self.assertEqual((record["gold"], news), (False, ["gone"]))

    def test_one_alert_per_absence(self):
        _, news = looks([False, False, False, None, False, None, None, False])
        self.assertEqual(news.count("gone"), 1, news)

    def test_back_once_seen_again_then_a_new_absence_alerts(self):
        record, news = looks([False, False, True, False, False])
        self.assertEqual(news, [None, "gone", "back", None, "gone"])
        self.assertEqual(record["gold"], False)
        _, news = looks([True, True, False, True])
        self.assertEqual(news, [None, None, None, None], "nothing to say back without a warning")

    def test_a_miss_then_the_scroll_starts_the_count_again(self):
        _, news = looks([False, True, False, True, False])
        self.assertEqual(news, [None] * 5)

    def test_unknown_on_other_screens(self):
        record, news = looks([True, None])
        self.assertEqual((record["gold"], news), (None, [None, None]))
        record, _ = looks([False, False, None])
        self.assertIsNone(record["gold"])
        self.assertTrue(record["warned"], "the warning holds until it is seen again")
        # An unknown look between two misses does not break the run.
        record, news = looks([False, None, False])
        self.assertEqual((record["gold"], news[-1]), (False, "gone"))


class Mpw4Looks(unittest.TestCase):
    def test_every_30_seconds(self):
        self.assertTrue(mode_rules.gold_due(None, 5.0))
        self.assertFalse(mode_rules.gold_due(100.0, 129.0))
        self.assertTrue(mode_rules.gold_due(100.0, 130.0))


if __name__ == "__main__":
    unittest.main()
