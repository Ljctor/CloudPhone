"""Cuts the pixel font's glyphs out of the fixtures (real 480x1040
captures) whose text is known (fixtures/texts.json), averages each
character over its occurrences and writes the result into pixel_font.py
(between its CUT FONT markers). Offline tool, stdlib only; it takes a few
minutes.

    python3 font_cut.py           # prints the shapes and their sources
    python3 font_cut.py --write   # also rewrites pixel_font.py's block

How: each text line is cut into glyphs (its column runs, aligned to the
known characters; runs of touching letters are cut where the characters'
shapes read best). Each glyph's ink coverage is sampled on a grid of
ROWS rows and its width in font pixels. A character seen at least LEAST
times becomes a shape: the average coverage of its occurrences (weighted
by their cap height), as digits 0-9 (tenths of ink, 9 full). The game
renders its font at several sizes, each with its own rounding: when a
character's occurrences fall in two clearly different groups (2-means,
centres further apart than VARIANT_GAP, each group at least LEAST
occurrences), each group is a shape of its own ("a", "a~1", ...).
A character seen fewer than LEAST times is not cut: it stays drawn
(pixel_font.DRAWN) or missing, and reads as None or as a near letter.
"""

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
LEAST = 2
VARIANT_GAP = 0.015
PASSES = 3
CHANNELS = {"max": max, "min": min, "inv": lambda r, g, b: 255 - min(r, g, b)}
BEGIN, END = "# BEGIN CUT FONT (font_cut.py --write)", "# END CUT FONT"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"slayer_legend_cut_{name}", os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


font = _load("pixel_font")


def texts():
    with open(os.path.join(FIXTURES, "texts.json"), encoding="utf-8") as f:
        return json.load(f)["texts"]


def crop(name):
    """(screen width, height, left, top, width, height, rgb bytes)."""
    with open(os.path.join(FIXTURES, f"{name}.txt"), encoding="ascii") as f:
        lines = [line.strip() for line in f if not line.startswith("#")]
    sw, sh, x, y, w, h = map(int, lines[0].split())
    return sw, sh, x, y, w, h, b"".join(bytes.fromhex(row) for row in lines[1:1 + h])


def ink_of(entry):
    """The ink of a texts.json entry's area, and its text lines [(top,
    bottom)] (lines under 4 px are specks)."""
    _, _, _, _, w, h, data = crop(entry["fixture"])
    x0, y0, x1, y1 = entry.get("area") or (0, 0, w, h)
    channel = CHANNELS[entry.get("channel", "max")]
    rows = [[channel(*data[(r * w + c) * 3:(r * w + c) * 3 + 3]) for c in range(x0, min(x1, w))]
            for r in range(y0, min(y1, h))]
    marks = font.ink(rows, entry.get("level"))
    if not marks:
        return None, []
    return marks, [(t, b) for t, b in font.lines(marks) if font.metrics(marks, t, b)[1] >= 4]


def segment(marks, top, bottom, chars, shapes):
    """[(char, (left, right))]: the line's column runs aligned to chars (a
    run may hold several touching characters, several runs one character),
    the cut that reads best with shapes (a width prior for a character with
    no shape yet); None when no alignment exists."""
    runs, cap = font.metrics(marks, top, bottom)
    box_bottom = top + round(cap * font.ROWS / font.CAP) - 1
    if len(runs) == len(chars):
        # One run per character: nothing touches, nothing to choose.
        return list(zip(chars, runs)), cap, box_bottom

    def cost(c, left, right):
        if any(key[0] == c for key in shapes):
            return font.match(marks, (left, right, top, box_bottom), cap, shapes, [c])[1]
        return 0.02 * ((right - left + 1) * font.CAP / cap - 4.5) ** 2

    def split(run, cs):
        left, right = run
        best = {left: (0.0, [])}
        for i, c in enumerate(cs):
            following = {}
            for start, (score, path) in best.items():
                ends = [right] if i == len(cs) - 1 else range(start, right)
                for end in ends:
                    if not 0.6 <= (end - start + 1) * font.CAP / cap <= 8.5:
                        continue
                    total = score + cost(c, start, end)
                    if end + 1 not in following or total < following[end + 1][0]:
                        following[end + 1] = (total, path + [(c, (start, end))])
            best = following
        return best.get(right + 1)

    done = {(0, 0): (0.0, [])}
    for a in range(len(runs) + 1):
        for b in range(len(chars) + 1):
            if (a, b) not in done:
                continue
            score, path = done[(a, b)]
            options = []
            for k in range(1, 9):
                if a < len(runs) and b + k <= len(chars):
                    found = ((cost(chars[b], *runs[a]), [(chars[b], runs[a])]) if k == 1
                             else split(runs[a], chars[b:b + k]))
                    if found:
                        # A cut of touching letters costs a little more than
                        # runs that part them by themselves.
                        options.append(((a + 1, b + k), (found[0] + 0.03 * (k - 1), found[1])))
            for j in range(2, 4):
                if a + j <= len(runs) and b < len(chars):
                    left, right = runs[a][0], runs[a + j - 1][1]
                    options.append(((a + j, b + 1), (cost(chars[b], left, right) + 0.05 * (j - 1),
                                                     [(chars[b], (left, right))])))
            for key, (more, cut) in options:
                if key not in done or score + more < done[key][0]:
                    done[key] = (score + more, path + cut)
    found = done.get((len(runs), len(chars)))
    return (found[1] if found else None), cap, box_bottom


def harvest(shapes):
    """{char: [(fixture, marks, box, cap)]} over every text that is read."""
    found = {}
    for entry in texts():
        if entry.get("read") is False:
            continue
        marks, lines = ink_of(entry)
        if len(lines) != len(entry["text"]):
            raise ValueError(f"{entry['fixture']}: {len(lines)} lines for {entry['text']}")
        for (top, bottom), truth in zip(lines, entry["text"]):
            cut, cap, box_bottom = segment(marks, top, bottom, truth.replace(" ", ""), shapes)
            if cut is None:
                raise ValueError(f"{entry['fixture']}: no cut of {truth!r}")
            for char, (left, right) in cut:
                found.setdefault(char, []).append((entry["fixture"], marks, (left, right, top, box_bottom), cap))
    return found


def _columns(occurrences):
    weight = sum(cap for *_, cap in occurrences)
    return max(1, round(sum((box[1] - box[0] + 1) * font.CAP for _, _, box, _ in occurrences) / weight))


def _grids(occurrences, cols):
    return [font._grid(marks, box, cols, font.ROWS) for _, marks, box, _ in occurrences]


def _mean(grids, weights):
    total = sum(weights)
    return [[sum(g[y][x] * w for g, w in zip(grids, weights)) / total for x in range(len(grids[0][0]))]
            for y in range(len(grids[0]))]


def _gap(a, b):
    return sum((x - y) ** 2 for ra, rb in zip(a, b) for x, y in zip(ra, rb)) / sum(len(r) for r in a)


def average(occurrences):
    """The shape (rows of digits 0-9) of a character's occurrences."""
    cols = _columns(occurrences)
    mean = _mean(_grids(occurrences, cols), [cap for *_, cap in occurrences])
    return ["".join(str(min(9, round(v * 9))) for v in row) for row in mean]


def groups(occurrences, depth=0):
    """The occurrences in groups of one rendering each (see VARIANT_GAP)."""
    if depth >= 2 or len(occurrences) < 2 * LEAST:
        return [occurrences]
    grids = _grids(occurrences, _columns(occurrences))
    weights = [cap for *_, cap in occurrences]
    n = len(occurrences)
    i, j = max(((i, j) for i in range(n) for j in range(i + 1, n)), key=lambda p: _gap(grids[p[0]], grids[p[1]]))
    one, two = grids[i], grids[j]
    for _ in range(10):
        a = [k for k in range(n) if _gap(grids[k], one) <= _gap(grids[k], two)]
        b = [k for k in range(n) if k not in a]
        if not a or not b:
            return [occurrences]
        one, two = _mean([grids[k] for k in a], [weights[k] for k in a]), _mean([grids[k] for k in b],
                                                                                [weights[k] for k in b])
    if len(a) < LEAST or len(b) < LEAST or _gap(one, two) < VARIANT_GAP:
        return [occurrences]
    return groups([occurrences[k] for k in a], depth + 1) + groups([occurrences[k] for k in b], depth + 1)


def cut(passes=PASSES):
    """({key: shape}, {key: (occurrences, [fixtures])}): the font cut from
    the fixtures, segmenting again with each pass's shapes."""
    shapes = {key: shape for key, shape in font.FONT.items() if key[0] not in font.DRAWN}
    for _ in range(passes):
        found = harvest(shapes)
        shapes, sources = {}, {}
        for char in sorted(found):
            occurrences = found[char]
            if len(occurrences) < LEAST:
                continue
            for n, part in enumerate(sorted(groups(occurrences), key=lambda p: -len(p))):
                key = char if n == 0 else f"{char}~{n}"
                shapes[key] = average(part)
                sources[key] = (len(part), sorted({fixture for fixture, *_ in part}))
    seen = {char: len(found[char]) for char in found}
    return shapes, sources, seen


def block(shapes, sources):
    lines = [BEGIN, "# Cut from the fixtures by font_cut.py: each shape the average ink coverage",
             "# (digits: tenths of ink, 9 full) of its occurrences; key: the character, or",
             "# the character, ~ and a variant (another size's rendering).", "FONT = {"]
    for key in sorted(shapes):
        lines.append(f"    {key!r}: {shapes[key]!r},")
    lines.append("}")
    lines.append("# Where each shape was cut: (occurrences, fixtures).")
    lines.append("SOURCES = {")
    for key in sorted(sources):
        lines.append(f"    {key!r}: {sources[key]!r},")
    lines.append("}")
    lines.append(END)
    return "\n".join(lines)


def main():
    shapes, sources, seen = cut()
    text = block(shapes, sources)
    print(text)
    print("seen once (not cut):", "".join(sorted(c for c, n in seen.items() if n < LEAST)))
    if "--write" in sys.argv:
        path = os.path.join(HERE, "pixel_font.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        start, end = source.index(BEGIN), source.index(END) + len(END)
        with open(path, "w", encoding="utf-8") as f:
            f.write(source[:start] + text + source[end:])


if __name__ == "__main__":
    main()
