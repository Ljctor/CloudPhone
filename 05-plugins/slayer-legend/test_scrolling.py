"""scrolling.scroll_until on a scripted list: found when the item shows,
the end told by two frames alike, back to the start, every swipe through
the guard with the move's own points.
Run: python3 -m unittest test_scrolling"""

import asyncio
import importlib.util
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_scrolling_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scrolling = load("scrolling")
nav = load("nav")
W, H = 480, 1040
MOVE = next(m for m in nav.connections("stage_select") if m["id"] == "scroll")
RECT = (0.1, 0.42, 0.9, 0.8)


class Shot(tuple):
    """(width, height, pixels), and the list's first row shown (top)."""


class List:
    """A list of items, ROWS shown at a time, STEP more per swipe."""
    ROWS, STEP = 5, 3

    def __init__(self, items):
        self.items, self.top, self.swipes = items, 0, []

    def shot(self):
        pixels = bytearray(W * H * 3)
        top, bottom = int(RECT[1] * H), int(RECT[3] * H)
        row_height = (bottom - top) // self.ROWS
        for row in range(self.ROWS):
            shade = (self.top + row) * 37 % 200 + 40
            for y in range(top + row * row_height, top + (row + 1) * row_height - 4):
                pixels[(y * W) * 3:(y * W + W) * 3] = bytes((shade, shade, shade)) * W
        shot = Shot((W, H, bytes(pixels)))
        shot.top = self.top
        return shot

    def visible(self, shot):
        return self.items[shot.top:shot.top + self.ROWS]

    def ports(self):
        async def swipe(shot, screen, move, start, end, ms, verified=False, seen=None):
            self.assertion = nav.guard(screen, move, start[0], start[1], "swipe", verified, seen)
            if self.assertion:
                raise AssertionError(self.assertion)
            self.swipes.append((start, end, ms))
            forward = end[1] < start[1]
            last = max(0, len(self.items) - self.ROWS)
            self.top = min(last, self.top + self.STEP) if forward else max(0, self.top - self.STEP)

        async def capture(max_age=0):
            return self.shot()

        async def sleep(seconds):
            return None

        return types.SimpleNamespace(swipe=swipe, capture=capture, clock=types.SimpleNamespace(sleep=sleep))


def run(coroutine):
    return asyncio.run(coroutine)


class ScrollUntil(unittest.TestCase):
    def test_found_when_the_item_shows(self):
        items = [f"item {n}" for n in range(30)]
        game = List(items)
        shot, found = run(scrolling.scroll_until(game.ports(), game.shot(), "stage_select", MOVE, RECT,
                                                 lambda shot: "item 17" in game.visible(shot) and "item 17"))
        self.assertEqual(found, "item 17")
        self.assertIn("item 17", game.visible(shot))
        self.assertEqual(len(game.swipes), 5)
        for start, end, ms in game.swipes:
            self.assertEqual((start, end), scrolling.swipe_of(MOVE))
            self.assertGreaterEqual(ms, 600, "a slow drag, never a tap")

    def test_the_end_when_nothing_moves(self):
        game = List([f"item {n}" for n in range(12)])
        shot, found = run(scrolling.scroll_until(game.ports(), game.shot(), "stage_select", MOVE, RECT,
                                                 lambda shot: None))
        self.assertIsNone(found)
        self.assertEqual(shot.top, 7, "the last items show")
        self.assertEqual(len(game.swipes), 4, "three that moved, one that did not")

    def test_back_to_the_start(self):
        game = List([f"item {n}" for n in range(20)])
        game.top = 15
        shot = run(scrolling.to_start(game.ports(), game.shot(), "stage_select", MOVE, RECT))
        self.assertEqual(shot.top, 0)
        self.assertTrue(all(start == scrolling.swipe_of(MOVE, back=True)[0] for start, _, _ in game.swipes))

    def test_at_most_so_many_swipes(self):
        game = List([f"item {n}" for n in range(300)])
        _, found = run(scrolling.scroll_until(game.ports(), game.shot(), "stage_select", MOVE, RECT,
                                              lambda shot: None, most=3))
        self.assertIsNone(found)
        self.assertEqual(len(game.swipes), 4)

    def test_moved_compares_the_area_only(self):
        game = List([f"item {n}" for n in range(20)])
        a = game.shot()
        self.assertEqual(scrolling.moved(a, a, RECT), 0)
        game.top = 3
        self.assertGreater(scrolling.moved(a, game.shot(), RECT), scrolling.MOVED)
        self.assertEqual(scrolling.moved(a, game.shot(), (0.0, 0.0, 1.0, 0.3)), 0)


if __name__ == "__main__":
    unittest.main()
