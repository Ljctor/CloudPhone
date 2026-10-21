// Small pixel-art icons drawn here, in the spirit of the game's own (gold
// coin, emerald, diamond) and the plugin's (a sword): nothing is copied
// from the game or its store art, and nothing depends on a capture. Each
// is an SVG data URL, one rect per pixel, for a section's or the plugin's
// icon (plugins.ts: icon).

// rows: one string per pixel row, a character per pixel ('.' clear);
// palette: character -> CSS colour.
function sprite(rows, palette) {
  const rects = rows.flatMap((row, y) => [...row].map((c, x) => (palette[c]
    ? `<rect x="${x}" y="${y}" width="1" height="1" fill="${palette[c]}"/>` : ''))).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${rows[0].length} ${rows.length}" `
    + `shape-rendering="crispEdges">${rects}</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export const GOLD = sprite([
  '..ooooo..',
  '.oYYYYYo.',
  'oYWYYYYDo',
  'oYWYYYYDo',
  'oYYYYYYDo',
  'oYYYYYYDo',
  'oYYYYYDDo',
  '.oDDDDDo.',
  '..ooooo..',
], { o: '#8a5a00', Y: '#ffd23a', W: '#fff6b0', D: '#e0a000' });

export const EMERALD = sprite([
  '...ooo...',
  '..oLLGo..',
  '.oLGGGDo.',
  'oLGGGGGDo',
  'oGGGGGGDo',
  'oGGGGGDDo',
  '.oGGGDDo.',
  '..oGDDo..',
  '...ooo...',
], { o: '#0b4a22', L: '#b8ffcf', G: '#2fd16a', D: '#159447' });

export const DIAMOND = sprite([
  '..ooooo..',
  '.oWLLLDo.',
  'oWLLLLLDo',
  'oLLLLLLDo',
  '.oLLLLDo.',
  '..oLLDo..',
  '...oLo...',
  '....o....',
], { o: '#1d4f8a', W: '#ffffff', L: '#8fe3ff', D: '#3ba7e0' });

export const SWORD = sprite([
  '........W',
  '.......WL',
  '......WL.',
  '.....WL..',
  'o...WL...',
  '.o.WL....',
  '..oL.....',
  '.oHo.....',
  'oH..o....',
], { W: '#ffffff', L: '#b8c4d6', o: '#7a4a1a', H: '#c98a3a' });
