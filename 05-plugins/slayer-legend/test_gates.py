"""The gates on taps conditioned on a reading (05-plugins/AGENTS.md): such a
tap is real only once its reader has a crop of a real capture (fixtures/)
for every state it must tell apart, each with a green test. Until then the
gate stays closed: refused, with an error alert stating the fact.

Every gate is listed here with the fixtures it needs. An open gate missing
one of them fails this test (red, never skipped); a closed gate is fine.
Run: python3 -m unittest test_gates"""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_gates_{name.replace('/', '_')}",
                                                  os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# (module, flag, the fixtures of every state its reading tells apart, the
# test reading them).
GATES = [
    ("soul_weapon", "TAG_LEARNED", ["sw_tag_equip", "sw_tag_unequip"], "test_soul_weapon"),
    ("soul_weapon", "BADGE_TELLS", ["sw_badge_red", "sw_badge_grey", "sw_badge_owned_grey"], "test_soul_weapon"),
    ("stage", "PROGRESS_CALIBRATED", ["bar_empty", "bar_partial", "bar_full", "bar_flash", "bar_parked_empty",
                                      "bar_parked_partial", "bar_parked_full", "bar_parked_flash"], "test_fixtures"),
    # Readings, not taps: full digits are read once a capture of them is a
    # fixture (the game's option on, the counters in full).
    ("gold", "FULL_DIGITS_CALIBRATED", ["gold_full"], "test_souls"),
    ("gold", "HIGH_RES_FULL_DIGITS_CALIBRATED", ["gold_full_mid", "gold_full_hi"], "test_souls"),
    ("soul_counters", "FULL_DIGITS_CALIBRATED", ["souls_full"], "test_souls"),
    ("engraving_screen", "PADLOCK_LEARNED", ["eg_cards_unlocked", "eg_cards_relocked"], "test_engraving_screen"),
    ("engraving_screen", "POPUP_LEARNED", ["eg_popup_locked", "eg_popup_unlocked", "eg_cards_relocked"],
     "test_engraving_screen"),
    ("engraving_screen", "PREVIEW_LEARNED", ["eg_preview_base", "eg_preview_turned", "eg_preview_valid",
                                             "eg_grid_removed"], "test_engraving_screen"),
]


class Gates(unittest.TestCase):
    def test_an_open_gate_has_all_its_fixtures(self):
        for module, flag, fixtures, test in GATES:
            with self.subTest(gate=flag):
                is_open = getattr(load(module), flag)
                missing = [name for name in fixtures if not os.path.exists(os.path.join(FIXTURES, f"{name}.txt"))]
                if is_open:
                    self.assertEqual(missing, [], f"{module}.{flag} is open without fixtures {missing}")
                    with open(os.path.join(HERE, f"{test}.py"), encoding="utf-8") as f:
                        source = f.read()
                    for name in fixtures:
                        self.assertIn(f'"{name}"', source, f"{name} is read by no test of {test}")

    def test_every_gate_is_listed(self):
        # A new *_LEARNED / *_TELLS / *_CALIBRATED flag must be listed above.
        listed = {(module, flag) for module, flag, _, _ in GATES}
        found = set()
        for folder in (HERE, os.path.join(HERE, "features")):
            for name in os.listdir(folder):
                if not name.endswith(".py") or name.startswith("test_"):
                    continue
                module = os.path.relpath(os.path.join(folder, name[:-3]), HERE)
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    for line in f:
                        head = line.split("=")[0].strip()
                        if "=" in line and not line.startswith(" ") and head.isupper() and "_NOT_" not in head and \
                                head.endswith(("_LEARNED", "_TELLS", "_CALIBRATED")):
                            found.add((module, head))
        self.assertEqual(found - listed, set())


if __name__ == "__main__":
    unittest.main()
