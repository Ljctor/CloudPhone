// The game's counter font as it draws it at 480 px wide, in its two sizes:
// digits 9 rows high (6 digits or more), with 1 px strokes and a shadow
// column, and 10 rows high (5 digits or fewer), with 2 px strokes and no
// shadow. One more row holds the comma's tail. Glyphs were read off the
// game's emerald and diamond counters; the few not seen there yet (9 rows:
// 1 and 3; 10 rows: 8) are drawn in the same style. Each glyph
// advances its width plus one column. See shade() for the rest.
export const MASKS = {
  9: {
    0: ['.###.', '#####', '#...#', '#...#', '#...#', '#...#', '#...#', '#####', '.###.', '.....'],
    1: ['..#.', '.##.', '###.', '..#.', '..#.', '..#.', '..#.', '..#.', '..#.', '....'],
    2: ['.###.', '#####', '#...#', '...##', '..##.', '.##..', '##...', '#####', '#####', '.....'],
    3: ['.###.', '#####', '#...#', '..##.', '..###', '....#', '#...#', '#####', '.###.', '.....'],
    4: ['....#.', '...##.', '..###.', '.##.#.', '##..#.', '######', '######', '....#.', '....#.', '......'],
    5: ['#####', '#####', '#....', '####.', '#####', '....#', '#...#', '#####', '.###.', '.....'],
    6: ['..##.', '.###.', '##...', '####.', '#####', '#...#', '#...#', '#####', '.###.', '.....'],
    7: ['#####', '#####', '....#', '...##', '...#.', '..##.', '..#..', '..#..', '..#..', '.....'],
    8: ['.###.', '#####', '#...#', '#####', '#####', '#...#', '#...#', '#####', '.###.', '.....'],
    9: ['.###.', '#####', '#...#', '#...#', '#####', '.####', '...##', '.###.', '.##..', '.....'],
    ',': ['..', '..', '..', '..', '..', '..', '..', '.#', '##', '#.'],
  },
  10: {
    0: ['.####.', '######', '##..##', '##..##', '##..##', '##..##', '##..##', '##..##', '######', '.####.', '......'],
    1: ['.##.', '###.', '###.', '.##.', '.##.', '.##.', '.##.', '.##.', '####', '####', '....'],
    2: ['.####.', '######', '##..##', '....##', '...###', '..###.', '.###..', '###...', '######', '######', '......'],
    3: ['.####.', '######', '##..##', '....##', '..####', '..####', '....##', '##..##', '######', '.####.', '......'],
    4: ['....##.', '...###.', '...###.', '..####.', '.#####.', '###.##.', '#######', '#######', '....##.', '....##.', '.......'],
    5: ['######', '######', '##....', '##....', '#####.', '######', '....##', '##..##', '######', '.####.', '......'],
    6: ['..###.', '.####.', '.##...', '##....', '#####.', '######', '##..##', '##..##', '######', '.####.', '......'],
    7: ['######', '######', '....##', '....##', '...###', '...##.', '..###.', '..##..', '..##..', '..##..', '......'],
    8: ['.####.', '######', '##..##', '##..##', '.####.', '######', '##..##', '##..##', '######', '.####.', '......'],
    9: ['.####.', '######', '##..##', '##..##', '##..##', '######', '.#####', '...###', '.####.', '.###..', '......'],
    // Copied pixel for pixel, with its soft edges: h about 0.45, s 0.6.
    ',': ['....', '....', '....', '....', '....', '....', '....', '....', '.h#s', 'h##s', 'h#s.'],
  },
};

// How far each glyph moves the pen, in pixels. The 9-row font sits on
// whole pixels: width plus one (its shadow column). The 10-row font does
// not: width plus half a pixel, the comma 3.5, so that every other glyph
// lands on a half pixel and comes out softened on both sides, as the game
// draws it ("2,266" at 480 px: digits at x 280, 290, 296.5 and 303).
const ADVANCE = {
  9: (c, width) => width + 1,
  10: (c, width) => (c === ',' ? 3.5 : width + 0.5),
};
const SOFT = { h: 0.45, s: 0.6 };

// Rows below the digits' bottom, and 480 px per 360 px.
export const FONT = { below: 1, scale: 480 / 360 };

// How much ink each pixel of `text` gets, as the game draws it with digits
// `rows` high (9 or 10): 1 for a stroke, 0.95 for a stroke with nothing
// under it (its lower edge), at 9 rows 0.6 for the shadow just right of a
// stroke; at 10 rows a glyph on a half pixel is spread over two columns.
// The comma is copied as the game draws it, on the whole pixel before.
// Returns { width, height, cover } with cover[y][x] in 0..1.
export function shade(text, rows = 9) {
  const size = rows >= 10 ? 10 : 9;
  const set = MASKS[size];
  const height = set[0].length;
  const glyphs = [...text].filter((c) => set[c]);
  let pen = 0;
  const placed = glyphs.map((c) => {
    const at = c === ',' ? Math.floor(pen) : pen;
    pen += ADVANCE[size](c, set[c][0].length);
    return { c, at };
  });
  const width = Math.max(1, Math.ceil(Math.max(pen, ...placed.map((g) => g.at + set[g.c][0].length))));
  const cover = Array.from({ length: height }, () => new Array(width).fill(0));
  if (size === 9) {
    // Whole pixels: lay the ink out, then shade it as a whole (a shadow
    // column under the next glyph's ink stays ink).
    const ink = cover.map((row) => row.map(() => false));
    for (const { c, at } of placed) {
      set[c].forEach((row, y) => [...row].forEach((p, x) => { if (p === '#') ink[y][at + x] = true; }));
    }
    return {
      width, height,
      cover: ink.map((row, y) => row.map((on, x) => {
        if (on) return y + 1 < height && ink[y + 1][x] ? 1 : 0.95;
        return x > 0 && row[x - 1] ? 0.6 : 0;
      })),
    };
  }
  for (const { c, at } of placed) {
    const mask = set[c];
    const left = Math.floor(at);
    const frac = at - left;
    mask.forEach((row, y) => [...row].forEach((p, x) => {
      let v = 0;
      if (p === '#') v = y + 1 < height && mask[y + 1][x] === '#' ? 1 : 0.95;
      else if (SOFT[p]) v = SOFT[p];
      if (!v) return;
      cover[y][left + x] = Math.min(1, cover[y][left + x] + v * (1 - frac));
      if (frac && left + x + 1 < width) cover[y][left + x + 1] = Math.min(1, cover[y][left + x + 1] + v * frac);
    }));
  }
  return { width, height, cover };
}
