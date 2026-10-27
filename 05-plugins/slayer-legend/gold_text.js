// Lines of text drawn in the gold counter's own pixel font (from the
// gateway's GET /gold-font: {height, glyphs: {char: rows of "#" and "."}}),
// outlined in black like the game, orange gold unless a line says its
// colour. Used by page_gold.js.

const ORANGE = '#ffa31a';
// The game font has capitals and digits. These tiny lowercase glyphs are
// only for the overlay's "défaut" / "default" label below the mode.
const SMALL = {
  a: ['.....', '.###.', '....#', '.####', '#...#', '.####', '.....'],
  d: ['....#', '....#', '.####', '#...#', '#...#', '.####', '.....'],
  e: ['.....', '.###.', '#...#', '#####', '#....', '.####', '.....'],
  f: ['..###', '.#...', '####.', '.#...', '.#...', '.#...', '.....'],
  h: ['##....', '##....', '##....', '##....', '##....', '######', '#######',
    '##...##', '##...##', '##...##', '##...##', '##...##', '##...##'],
  l: ['.#...', '.#...', '.#...', '.#...', '.#...', '..##.', '.....'],
  t: ['.#...', '.#...', '####.', '.#...', '.#...', '..###', '.....'],
  u: ['.....', '#...#', '#...#', '#...#', '#..##', '.##.#', '.....'],
};
// The counter font has a period but no thousands separator. Its comma
// shares the period's stroke and sits below the baseline.
const COMMA = ['..', '..', '..', '..', '..', '..', '..', '..', '..', '##', '##', '.#', '#.'];

// Lines of text on a canvas, `cell` CSS pixels per game pixel; a line is
// a text or { text, colour }. Letters without accents: the font has none.
// `outline` is the black border's radius in native font pixels. The compact
// full-digit counter needs two pixels, matching Gold's heavier border.
export function drawText(canvas, font, lines, cell, { outline = 1 } = {}) {
  const plain = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const colours = lines.map((line) => (typeof line === 'string' ? ORANGE : line.colour ?? ORANGE));
  const glyphLines = lines.map((line) => [...plain(typeof line === 'string' ? line : line.text)]
    .map((c) => font.glyphs[c] ?? (c === ',' ? COMMA.slice(-font.height) : SMALL[c])).filter(Boolean));
  const rows = font.height;
  // A game pixel between glyphs; reserve the complete outline on every
  // edge so the last digit and the comma's descender are never clipped.
  const widths = glyphLines.map((glyphs) => glyphs.reduce((sum, glyph) => sum + glyph[0].length + 1, 0) - 1 + 2 * outline);
  const width = Math.max(...widths);
  const height = lines.length * (rows + 2 * outline) + (lines.length - 1) * 2;
  const scale = cell * (window.devicePixelRatio || 1);
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  canvas.style.width = `${width * cell}px`;
  canvas.style.height = `${height * cell}px`;
  const context = canvas.getContext('2d');
  for (const [colour, grow] of [['#000', outline], [null, 0]]) {
    glyphLines.forEach((glyphs, line) => {
      context.fillStyle = colour ?? colours[line];
      const base = outline + line * (rows + 2 * outline + 2);
      let pen = outline;
      for (const glyph of glyphs) {
        glyph.forEach((row, y) => [...row].forEach((ink, x) => {
          if (ink === '#') {
            // Whole device pixels: fractional edges leave seams between cells.
            const left = Math.round((pen + x - grow) * scale);
            const top = Math.round((base + y - grow) * scale);
            context.fillRect(left, top, Math.round((pen + x + 1 + grow) * scale) - left,
              Math.round((base + y + 1 + grow) * scale) - top);
          }
        }));
        pen += glyph[0].length + 1;
      }
    });
  }
}
