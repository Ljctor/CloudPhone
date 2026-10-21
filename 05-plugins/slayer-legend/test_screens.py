"""screens.classify on synthetic screenshots drawn from the areas it reads
(no screenshot of the game in the repository), and the reading of
Android's crash dialog (ports.crash_window, ports.close_button) from the
text dumpsys and uiautomator print. Run: python3 -m unittest test_screens
"""

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


screens = load("screens")
ports = load("features/ports")
W, H = 480, 1040


def shot(*areas, background=(0, 0, 0)):
    """A screenshot: background, then each (area, colour) filled."""
    pixels = bytearray(bytes(background) * (W * H))
    for (left, top, right, bottom), colour in areas:
        for y in range(int(top * H), int(bottom * H)):
            for x in range(int(left * W), int(right * W)):
                pixels[(y * W + x) * 3:(y * W + x) * 3 + 3] = bytes(colour)
    return W, H, bytes(pixels)


GREEN, LIGHT, ORANGE, GREY, WHITE = (40, 200, 60), (225, 225, 225), (230, 140, 30), (110, 110, 110), (250, 250, 250)


class Classify(unittest.TestCase):
    def test_the_save_notice_confirm_orange_exit_grey(self):
        self.assertEqual(screens.classify(shot((screens.CONFIRM_BUTTON, ORANGE), (screens.EXIT_BUTTON, GREY))), "save")

    def test_the_title_white_tap_to_start_near_the_bottom(self):
        # The letters cover part of their area, not all of it.
        left, top, right, bottom = screens.START_TEXT
        self.assertEqual(screens.classify(shot(((left, top, left + 0.06, bottom), WHITE))), "title")

    def test_battle_and_a_panel_over_it(self):
        self.assertEqual(screens.classify(shot((screens.TOP_EMERALD, GREEN), (screens.MENU_LABELS, LIGHT))), "battle")
        self.assertEqual(screens.classify(shot((screens.TOP_EMERALD, GREEN))), "menu", "the bottom names covered")

    def test_power_saving_mode(self):
        self.assertEqual(screens.classify(shot((screens.SAVER_BUTTON, (70, 70, 70)), (screens.SAVER_TEXT, ORANGE))),
                         "saver")

    def test_anything_else_is_other(self):
        # TODO: the "connected on another device" screen and the choice of
        # two saves are not mapped (no layout known): they are "other", and
        # the watchdog only alerts on them after a mode's end
        # (watchdog_rules.AFTER_MODE).
        self.assertEqual(screens.classify(shot(background=(30, 30, 60))), "other")
        self.assertEqual(screens.classify(shot(((0.1, 0.4, 0.9, 0.6), WHITE))), "other", "an unknown dialog")


DUMPSYS = """WINDOW MANAGER WINDOWS (dumpsys window windows)
  mCurrentFocus=Window{9f1 u0 Application Error: com.gear2.growslayer}
  mFocusedApp=ActivityRecord{1a2 u0 com.gear2.growslayer/com.google.firebase.MessagingUnityPlayerActivity t12}
"""
HIERARCHY = ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
             "<node index=\"0\" text=\"Slayer Legend s’arrête\" resource-id=\"android:id/alertTitle\" "
             "class=\"android.widget.TextView\" bounds=\"[54,421][426,477]\" />"
             "<node index=\"1\" text=\"Infos sur l’appli\" resource-id=\"android:id/aerr_app_info\" "
             "class=\"android.widget.Button\" bounds=\"[54,540][426,606]\" />"
             "<node index=\"2\" text=\"Fermer l’application\" resource-id=\"android:id/aerr_close\" "
             "class=\"android.widget.Button\" bounds=\"[54,606][426,672]\" /></hierarchy>")


GAME = "Window{1a u0 com.gear2.growslayer/com.google.firebase.MessagingUnityPlayerActivity}"
GAME_APP = ("  mFocusedApp=ActivityRecord{2b u0 com.gear2.growslayer/"
            "com.google.firebase.MessagingUnityPlayerActivity t9}")


class Focus(unittest.TestCase):
    """ports.focus_of: who has the focus, for the watchdog's "away"."""

    def test_the_game_in_front(self):
        self.assertEqual(ports.focus_of(f"  mCurrentFocus={GAME}\n{GAME_APP}\n"),
                         (True, "com.gear2.growslayer/com.google.firebase.MessagingUnityPlayerActivity"))

    def test_a_passing_window_over_the_game_cannot_tell(self):
        for window in ("null", "Window{3 u0 InputMethod}", "Window{4 u0 Toast}", "Window{5 u0 PopupWindow:1f}"):
            self.assertEqual(ports.focus_of(f"  mCurrentFocus={window}\n{GAME_APP}\n")[0], None, window)

    def test_nothing_said_cannot_tell(self):
        self.assertEqual(ports.focus_of(""), (None, None))
        self.assertEqual(ports.focus_of("Can't find service: window"), (None, None))

    def test_another_app_in_front(self):
        launcher = "Window{6 u0 com.android.launcher3/com.android.launcher3.uioverride.QuickstepLauncher}"
        self.assertEqual(ports.focus_of(f"  mCurrentFocus={launcher}\n  mFocusedApp=ActivityRecord{{7 u0 "
                                        "com.android.launcher3/.Launcher t1}\n"),
                         (False, "com.android.launcher3/com.android.launcher3.uioverride.QuickstepLauncher"))
        self.assertEqual(ports.focus_of("  mCurrentFocus=null\n  mFocusedApp=ActivityRecord{7 u0 "
                                        "com.android.settings/.Settings t1}\n"), (False, "com.android.settings/.Settings"))
        # The keyboard over another app is that app's.
        self.assertFalse(ports.focus_of("  mCurrentFocus=Window{3 u0 InputMethod}\n"
                                        "  mFocusedApp=ActivityRecord{7 u0 com.android.settings/.Settings t1}\n")[0])

    def test_another_display_does_not_hide_the_game(self):
        self.assertTrue(ports.focus_of(f"  mCurrentFocus=null\n  mCurrentFocus={GAME}\n")[0])


class CrashDialog(unittest.TestCase):
    def test_its_window_in_front(self):
        self.assertEqual(ports.crash_window(DUMPSYS), "crash")
        self.assertIsNone(ports.crash_window(DUMPSYS.replace("Application Error: ", "")))
        self.assertIsNone(ports.crash_window("  mCurrentFocus=Window{1 u0 Application Error: com.other.app}"))

    def test_not_responding_is_its_own(self):
        self.assertEqual(ports.crash_window(DUMPSYS.replace("Application Error", "Application Not Responding")), "anr")

    def test_wait_is_found_by_its_id(self):
        wait = HIERARCHY.replace("aerr_app_info", "aerr_wait")
        self.assertEqual(ports.close_button(wait, "aerr_wait"), (240, 573))
        self.assertIsNone(ports.close_button(HIERARCHY, "aerr_wait"))

    def test_close_app_is_found_by_its_id_whatever_the_language(self):
        self.assertEqual(ports.close_button(HIERARCHY), (240, 639))
        self.assertIsNone(ports.close_button(HIERARCHY.replace("aerr_close", "aerr_wait")))
        self.assertIsNone(ports.close_button("UI hierchary dumped to: /dev/tty"))


if __name__ == "__main__":
    unittest.main()
