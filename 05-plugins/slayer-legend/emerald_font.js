// The game's counter font as it draws it at 480 px wide: 1 px strokes,
// doubled horizontal bars, 9 rows high plus one row for the comma's tail.
// 2, 4, 6, 8, 0 and the comma were read off the game's emerald counter;
// 1, 3, 5, 7 and 9 were drawn in the same style. Each glyph advances its
// width plus one column (its shadow). See shade() for the rest.
const MASKS = {
  0: ['.###.', '#####', '#...#', '#...#', '#...#', '#...#', '#...#', '#####', '.###.', '.....'],
  1: ['..#.', '.##.', '###.', '..#.', '..#.', '..#.', '..#.', '..#.', '..#.', '....'],
  2: ['.###.', '#####', '#...#', '...##', '..##.', '.##..', '##...', '#####', '#####', '.....'],
  3: ['.###.', '#####', '#...#', '..##.', '..###', '....#', '#...#', '#####', '.###.', '.....'],
  4: ['....#.', '...##.', '..###.', '.##.#.', '##..#.', '######', '######', '....#.', '....#.', '......'],
  5: ['#####', '#####', '#....', '####.', '#####', '....#', '#...#', '#####', '.###.', '.....'],
  6: ['..##.', '.###.', '##...', '####.', '#####', '#...#', '#...#', '#####', '.###.', '.....'],
  7: ['#####', '#####', '#...#', '...#.', '..##.', '..#..', '.##..', '.#...', '.#...', '.....'],
  8: ['.###.', '#####', '#...#', '#####', '#####', '#...#', '#...#', '#####', '.###.', '.....'],
  9: ['.###.', '#####', '#...#', '#...#', '#####', '.####', '...##', '.###.', '.##..', '.....'],
  ',': ['..', '..', '..', '..', '..', '..', '..', '.#', '##', '#.'],
};

// Rows of a glyph, rows below the digits' bottom, and 480 px per 360 px.
export const FONT = { height: 10, below: 1, digitRows: 9, scale: 480 / 360 };

// How much ink each pixel of `text` gets, as the game draws it: 1 for a
// stroke, 0.95 for a stroke with nothing under it (its lower edge), 0.6
// for the shadow just right of a stroke. Returns { width, cover } with
// cover[y][x] in 0..1.
export function shade(text) {
  const masks = [...text].map((c) => MASKS[c]).filter(Boolean);
  const width = masks.reduce((sum, mask) => sum + mask[0].length + 1, 0);
  const ink = Array.from({ length: FONT.height }, () => new Array(width).fill(false));
  let left = 0;
  for (const mask of masks) {
    mask.forEach((row, y) => [...row].forEach((c, x) => { if (c === '#') ink[y][left + x] = true; }));
    left += mask[0].length + 1;
  }
  const cover = ink.map((row, y) => row.map((on, x) => {
    if (on) return y + 1 < FONT.height && ink[y + 1][x] ? 1 : 0.95;
    return x > 0 && row[x - 1] ? 0.6 : 0;
  }));
  return { width, cover };
}
