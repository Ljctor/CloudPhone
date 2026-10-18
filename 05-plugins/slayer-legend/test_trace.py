"""Tests of trace.py's pure logic, on synthetic screenshots.

    cd 05-plugins/slayer-legend && python3 -m unittest test_trace

Not installed on the server (install.sh skips test_*.py).
"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# The plugin's trace.py, by path: "import trace" finds the standard library's.
_spec = importlib.util.spec_from_file_location("slayer_legend_trace", os.path.join(HERE, "trace.py"))
trace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trace)

WIDTH, HEIGHT = 120, 260


def shot(paint):
    """A WIDTH x HEIGHT RGB screenshot; paint(x, y) gives each pixel's grey."""
    pixels = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            v = paint(x, y)
            i = (y * WIDTH + x) * 3
            pixels[i:i + 3] = bytes((v, v, v))
    return WIDTH, HEIGHT, bytes(pixels)


BLACK = shot(lambda x, y: 0)
WHITE = shot(lambda x, y: 255)
# Top half white, bottom half black: a "menu" over the screen.
HALF = shot(lambda x, y: 255 if y < HEIGHT // 2 else 0)
# The same with a small difference (a moving monster): 4 bright pixels.
HALF_NOISY = shot(lambda x, y: 255 if y < HEIGHT // 2 or (x < 2 and y > 250) else 0)


class Thumbnail(unittest.TestCase):
    def test_size_and_levels(self):
        thumb = trace.thumbnail(HALF)
        self.assertEqual(len(thumb), trace.THUMB_WIDTH * trace.THUMB_HEIGHT)
        rows = [thumb[i:i + trace.THUMB_WIDTH] for i in range(0, len(thumb), trace.THUMB_WIDTH)]
        self.assertEqual(rows[0], "f" * trace.THUMB_WIDTH)
        self.assertEqual(rows[-1], "0" * trace.THUMB_WIDTH)

    def test_distance(self):
        self.assertEqual(trace.distance(trace.thumbnail(BLACK), trace.thumbnail(WHITE)), 1.0)
        self.assertEqual(trace.distance(trace.thumbnail(HALF), trace.thumbnail(HALF)), 0.0)
        self.assertLess(trace.distance(trace.thumbnail(HALF), trace.thumbnail(HALF_NOISY)), trace.MATCH)
        self.assertEqual(trace.distance("00", "000"), 1.0)


class GraphTests(unittest.TestCase):
    def signature(self, screen, image):
        return screen, trace.thumbnail(image)

    def test_nodes_merge_and_split(self):
        graph = trace.Graph()
        a = graph.node_for(*self.signature("menu", HALF), 1)
        b = graph.node_for(*self.signature("menu", HALF_NOISY), 2)
        c = graph.node_for(*self.signature("menu", BLACK), 3)
        # Same thumbnail, another screen name: another node.
        d = graph.node_for(*self.signature("other", HALF), 4)
        self.assertEqual(a, b)
        self.assertEqual(len({a, c, d}), 3)
        self.assertEqual(graph.nodes[0]["count"], 2)

    def test_edges_merge_near_taps(self):
        graph = trace.Graph()
        before, after = self.signature("battle", HALF), self.signature("menu", BLACK)
        self.assertTrue(graph.record(before, after, {"x": 0.50, "y": 0.90, "kind": "tap"}, 1))
        self.assertTrue(graph.record(before, after, {"x": 0.51, "y": 0.91, "kind": "tap"}, 2))
        # Far away, or another kind: other edges.
        graph.record(before, after, {"x": 0.10, "y": 0.90, "kind": "tap"}, 3)
        graph.record(before, after, {"x": 0.50, "y": 0.90, "kind": "long"}, 4)
        self.assertEqual([e["count"] for e in graph.edges], [2, 1, 1])
        self.assertEqual(graph.taps(), 4)
        self.assertEqual(graph.last, {"time": 4, "from": 1, "to": 2, "kind": "long"})

    def test_swipes_compare_their_end(self):
        graph = trace.Graph()
        before = after = self.signature("other", HALF)
        up = {"x": 0.5, "y": 0.6, "kind": "swipe", "end": {"x": 0.5, "y": 0.4}}
        down = {"x": 0.5, "y": 0.6, "kind": "swipe", "end": {"x": 0.5, "y": 0.8}}
        graph.record(before, after, up, 1)
        graph.record(before, after, dict(up), 2)
        graph.record(before, after, down, 3)
        self.assertEqual([(e["count"], e["y2"]) for e in graph.edges], [(2, 0.4), (1, 0.8)])
        self.assertEqual(graph.public()["edges"][0]["x2"], 0.5)

    def test_caps(self):
        graph = trace.Graph()
        tap = {"x": 0.5, "y": 0.5, "kind": "tap"}
        for n in range(trace.MAX_NODES):
            graph.nodes.append({"id": n + 1, "screen": "s", "thumb": f"{n:03x}", "first": 0, "count": 1})
        graph.next_id = trace.MAX_NODES + 1
        self.assertIsNone(graph.node_for("menu", trace.thumbnail(HALF), 1))
        self.assertFalse(graph.record(("menu", "x"), ("menu", "y"), tap, 1))
        graph = trace.Graph()
        graph.edges = [{"from": 9, "to": 9, "x": 0, "y": 0, "kind": "tap", "count": 1}] * trace.MAX_EDGES
        self.assertFalse(graph.record(self.signature("menu", HALF), self.signature("menu", HALF), tap, 1))

    def test_public_has_no_private_fields(self):
        graph = trace.Graph()
        graph.record(self.signature("battle", HALF), self.signature("menu", BLACK),
                     {"x": 0.5, "y": 0.9, "kind": "tap"}, 1)
        public = graph.public()
        self.assertEqual(set(public["nodes"][0]), {"id", "screen", "count", "thumb"})
        self.assertEqual(set(public["edges"][0]), {"from", "to", "x", "y", "kind", "count"})


class ParseTap(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(trace.parse_tap({"x": 0.2, "y": 1, "kind": "long"}), {"x": 0.2, "y": 1.0, "kind": "long"})
        self.assertEqual(trace.parse_tap({"x": 0, "y": 0})["kind"], "tap")
        swipe = trace.parse_tap({"x": 0.5, "y": 0.6, "kind": "swipe", "end": {"x": 0.5, "y": 0.4}})
        self.assertEqual(swipe["end"], {"x": 0.5, "y": 0.4})

    def test_invalid(self):
        for body in (None, [], {}, {"x": "a", "y": 0}, {"x": 1.5, "y": 0}, {"x": 0, "y": 0, "kind": "drag"},
                     {"x": 0, "y": 0, "kind": "swipe", "end": {"x": 2, "y": 0}}):
            self.assertIsNone(trace.parse_tap(body), body)


class Files(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "trace.json")
            self.assertEqual(trace.load(path).nodes, [])
            graph = trace.Graph()
            graph.record(("battle", trace.thumbnail(HALF)), ("menu", trace.thumbnail(BLACK)),
                         {"x": 0.5, "y": 0.9, "kind": "tap"}, 1)
            trace.save(graph, path)
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertFalse(os.path.exists(f"{path}.tmp"))
            again = trace.load(path)
            self.assertEqual(again.public(), graph.public())
            # New nodes go on from the highest id.
            self.assertEqual(again.node_for("title", trace.thumbnail(WHITE), 2), 3)

    def test_unreadable_file_is_kept_aside(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "trace.json")
            with open(path, "w") as f:
                f.write("{not json")
            self.assertEqual(trace.load(path).nodes, [])
            self.assertTrue(os.path.exists(f"{path}.bad"))


if __name__ == "__main__":
    unittest.main()
