// Hides what follows the last comma of Slayer Legend's emerald counter
// ("282,230" shows as "282"), on this screen only: a rectangle painted in the
// bar's own colour over the video. Nothing is sent to Android.
//
// The counter sits in the game's top bar, right of the emerald icon. Its
// width changes with the number, so the comma is found on each frame: it is
// the only glyph that goes one row below the digits. Coordinates are for a
// 360 px wide Android screen and scale with the actual width.

// Search area, in 360-wide Android pixels.
export const AREA = { x: 148, y: 10, width: 47, height: 20 };

// Thresholds as fractions between the darkest and the brightest pixel of
// the area: the game dims the whole screen under its pop-ups. Glyph edges
// are anti-aliased, hence a softer threshold to find where the text ends.
const BRIGHT = 0.55;
const EDGE = 0.3;
const DARK = 0.2;
// Below this contrast (0-255) there is no text to find.
const MIN_CONTRAST = 40;

function luminance(data, index) {
  return (data[index] * 299 + data[index + 1] * 587 + data[index + 2] * 114) / 1000;
}

// pixels: RGBA bytes of the search area, scaled by `scale` (video width /
// 360), `width` × `height` pixels. Returns the rectangle to paint, in
// 360-wide Android pixels relative to the screen, and its colour; or null
// when the counter is not on screen. On null, `why.reason` (when given) says
// which step failed: 'flat' (no contrast: blank image or no text), 'text',
// 'comma', 'digits' or 'colour'.
export function findEmeraldMask(pixels, width, height, scale, why = {}) {
  const miss = (reason) => {
    why.reason = reason;
    return null;
  };
  let low = 255, high = 0;
  for (let i = 0; i < width * height * 4; i += 4) {
    const value = luminance(pixels, i);
    if (value < low) low = value;
    if (value > high) high = value;
  }
  if (high - low < MIN_CONTRAST) return miss('flat');
  const level = (fraction) => low + (high - low) * fraction;
  const brightLevel = level(BRIGHT), edgeLevel = level(EDGE), darkLevel = level(DARK);
  const bright = (x, y) => luminance(pixels, (y * width + x) * 4) > brightLevel;
  const edge = (x, y) => luminance(pixels, (y * width + x) * 4) > edgeLevel;
  const rowCounts = [];
  for (let y = 0; y < height; y++) {
    let count = 0;
    for (let x = 0; x < width; x++) if (bright(x, y)) count++;
    rowCounts.push(count);
  }
  // The digits: the tallest band of rows with many bright pixels.
  const busy = Math.max(4, Math.round(6 * scale));
  let best = null;
  for (let y = 0; y < height; y++) {
    if (rowCounts[y] < busy) continue;
    let end = y;
    while (end + 1 < height && rowCounts[end + 1] >= busy) end++;
    if (!best || end - y > best.bottom - best.top) best = { top: y, bottom: end };
    y = end;
  }
  if (!best) return miss('text');
  const textHeight = best.bottom - best.top + 1;
  if (textHeight < 4 * scale || textHeight > 10 * scale) return miss('text');

  // The comma's tail: bright pixels just below the digits. Keep the last one.
  let comma = -1;
  const tailRows = Math.max(1, Math.round(scale));
  for (let x = width - 1; x >= 0 && comma < 0; x--) {
    for (let y = best.bottom + 1; y <= Math.min(height - 1, best.bottom + tailRows); y++) {
      if (bright(x, y)) {
        comma = x;
        break;
      }
    }
  }
  if (comma < 0) return miss('comma');
  // Left edge of that tail.
  while (comma > 0 && bright(comma - 1, best.bottom + 1)) comma--;

  // End of the number: last bright column after the comma, stopping at a
  // gap wider than a digit spacing (the next icon).
  const gap = Math.max(3, Math.round(3 * scale));
  let right = comma;
  let empty = 0;
  for (let x = comma + 1; x < width && empty <= gap; x++) {
    let any = false;
    for (let y = best.top; y <= best.bottom; y++) if (edge(x, y)) any = true;
    if (any) {
      right = x;
      empty = 0;
    } else {
      empty++;
    }
  }
  if (right - comma < 3 * scale) return miss('digits');

  // Colour: the bar just right of the number, where there is no glyph
  // edge to lighten it.
  let r = 0, g = 0, b = 0, n = 0;
  // The comma touches the last kept digit: start exactly on it.
  const left = comma;
  for (let y = best.top; y <= best.bottom; y++) {
    for (let x = right + 2; x <= Math.min(width - 1, right + 1 + gap); x++) {
      const i = (y * width + x) * 4;
      if (luminance(pixels, i) < darkLevel) {
        r += pixels[i]; g += pixels[i + 1]; b += pixels[i + 2]; n++;
      }
    }
  }
  if (n === 0) return miss('colour');
  why.reason = null;
  const pad = 1;
  return {
    x: AREA.x + left / scale,
    y: AREA.y + best.top / scale - pad,
    width: (right - left + 1) / scale + pad,
    height: (best.bottom - best.top + 1 + tailRows) / scale + 2 * pad,
    color: `rgb(${Math.round(r / n)}, ${Math.round(g / n)}, ${Math.round(b / n)})`,
  };
}
