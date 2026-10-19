// Lines of text drawn in the gold counter's own pixel font (from the
// gateway's GET /gold-font: {height, glyphs: {char: rows of "#" and "."}}),
// orange outlined in black like the game. Used by page_gold.js.

// Lines of text on a canvas, `cell` CSS pixels per game pixel. Letters
// without accents: the font has none.
export function drawText(canvas, font, lines, cell) {
  const plain = (text) => text.normalize('NFD').replace(/[̀-ͯ]/g, '');
  const glyphLines = lines.map((text) => [...plain(text)].map((c) => font.glyphs[c]).filter(Boolean));
  const rows = font.height;
  // A game pixel of space between glyphs, one round the text for the
  // outline, two between lines.
  const widths = glyphLines.map((glyphs) => glyphs.reduce((sum, glyph) => sum + glyph[0].length + 1, 0) + 1);
  const width = Math.max(...widths);
  const height = lines.length * (rows + 2) + (lines.length - 1) * 2;
  const scale = cell * (window.devicePixelRatio || 1);
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  canvas.style.width = `${width * cell}px`;
  canvas.style.height = `${height * cell}px`;
  const context = canvas.getContext('2d');
  for (const [colour, grow] of [['#000', 1], ['#ffa31a', 0]]) {
    context.fillStyle = colour;
    glyphLines.forEach((glyphs, line) => {
      const base = 1 + line * (rows + 4);
      let pen = 1;
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
