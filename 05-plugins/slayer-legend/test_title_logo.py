"""Static title artwork from reviewed real crops; no gameplay inputs."""

import unittest

from test_screen_model import screen, screens, scaled


class TitleLogo(unittest.TestCase):
    def test_real_logo_at_native_and_supported_display_sizes(self):
        native = screen("title_logo_720")
        for size in ((720, 1560), (480, 1040), (360, 780)):
            with self.subTest(size=size):
                self.assertTrue(screens.title_logo(scaled(native, *size)))

    def test_prompt_area_does_not_participate_in_landmark(self):
        # Perturbing the prompt demonstrates independence; it is not a
        # claim that these synthetic canvases are real title blink states.
        width, height, data = screen("title_logo_720")
        for colour in (bytes((0, 0, 0)), bytes((255, 255, 255))):
            pixels = bytearray(data)
            for y in range(int(height * .80), int(height * .87)):
                left, right = int(width * .30), int(width * .70)
                start = (y * width + left) * 3
                pixels[start:start + (right - left) * 3] = colour * (right - left)
            self.assertTrue(screens.title_logo((width, height, bytes(pixels))))

    def test_reviewed_real_negatives(self):
        for fixture in ("not_title_logo_beast_mount", "not_title_beast_mount",
                        "quest_title", "eg_title", "battle_emerald", "sign_in_buttons"):
            with self.subTest(fixture=fixture):
                self.assertFalse(screens.title_logo(screen(fixture)))

    def test_shared_logo_does_not_grant_start_permission(self):
        self.assertTrue(screens.title_logo(screen("title_logo_save_dimmed_720")))
        self.assertEqual(screens.classify(screen("title_logo_save_dimmed_720")), "other")
        notice = screen("title_logo_save_dimmed_720", "title_save_buttons_720")
        self.assertEqual(screens.classify(notice), "save")
        shared = screen("title_logo_720", "sign_in_buttons", background=(90, 60, 35))
        self.assertTrue(screens.title_logo(shared))
        self.assertEqual(screens.classify(shared), "sign_in")
        for footer in ("loading_footer_480", "loading_progress_480",
                       "logging_progress_480", "title_version_status_480"):
            native = screen("title_logo_480", footer)
            for size in ((480, 1040), (720, 1560), (360, 780)):
                with self.subTest(footer=footer, size=size):
                    self.assertNotEqual(screens.classify(scaled(native, *size)), "title")

    def test_real_ready_title_blink_phases(self):
        for prompt in ("title_prompt_visible_480", "title_prompt_hidden_480"):
            native = screen("title_logo_480", prompt)
            for size in ((480, 1040), (720, 1560), (360, 780)):
                with self.subTest(prompt=prompt, size=size):
                    self.assertEqual(screens.classify(scaled(native, *size)), "title")


class LoadingScene(unittest.TestCase):
    def test_real_centered_loading_needs_both_text_and_dragon_gate(self):
        parts = ("loading_center_text_480", "loading_dragon_gate_480")
        native = screen(*parts, background=(0, 0, 0))
        for size in ((480, 1040), (720, 1560), (360, 780)):
            with self.subTest(size=size):
                self.assertEqual(screens.classify(scaled(native, *size)), "loading")
        for part in parts:
            self.assertNotEqual(screens.classify(screen(part, background=(0, 0, 0))), "loading")

    def test_title_signin_save_and_unknown_popup_are_not_loading(self):
        for native in (screen("title_logo_480", "title_prompt_hidden_480"),
                       screen("title_logo_720", "sign_in_buttons", background=(90, 60, 35)),
                       screen("title_logo_save_dimmed_720", "title_save_buttons_720"),
                       screen("quest_title"), screen("not_title_logo_beast_mount")):
            self.assertNotEqual(screens.classify(native), "loading")


if __name__ == "__main__":
    unittest.main()
