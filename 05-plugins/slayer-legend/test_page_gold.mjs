import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import goldFeature, { combatCountersVisible } from './page_gold.js';
import { GOLD_COUNTER_FONT as font, GOLD_COUNTER_SOURCES as sources } from './page_gold_counter_font.js';
import { freshnessColour } from './page_freshness.js';
import { drawText } from './gold_text.js';
import { getScreen } from './page_screen_scan.js';

// Every stroke, including the comma's descender, comes from the real Gold
// counter rather than a resized abbreviated-font template.
assert.equal(font.height, 11);
assert.equal(Object.keys(font.glyphs).length, 11);
for (const [char, source] of Object.entries(sources)) {
  const lines = (await readFile(new URL(`./fixtures/${source.fixture}.txt`, import.meta.url), 'utf8')).trim().split('\n');
  const [, , , , width] = lines[1].split(' ').map(Number);
  const rgb = Buffer.from(lines.slice(2).join(''), 'hex');
  const [left, top, right, bottom] = source.box;
  const expected = [];
  for (let y = top; y < bottom; y++) {
    let row = '';
    for (let x = left; x < right; x++) {
      const pixel = (y * width + x) * 3;
      row += Math.min(...rgb.subarray(pixel, pixel + 3)) > 140 ? '#' : '.';
    }
    expected.push(row);
  }
  assert.deepEqual(font.glyphs[char], expected, char);
}
assert.equal(freshnessColour(0), 'rgb(255, 255, 255)');
assert.equal(freshnessColour(300), 'rgb(215, 238, 255)');
assert.equal(freshnessColour(600), 'rgb(175, 221, 255)');
assert.equal(freshnessColour(3600), freshnessColour(600));

let now = 1000000;
const originalNow = Date.now;
Date.now = () => now;
const intervals = [];
const nodes = [];
globalThis.window = { devicePixelRatio: 1, setInterval(fn) { intervals.push(fn); }, setTimeout() {}, clearTimeout() {} };
globalThis.document = { createElement(tagName) {
  const node = { tagName: tagName.toUpperCase(), style: {}, children: [], isConnected: false,
    append(...children) { this.children.push(...children); for (const child of children) child.isConnected = true; },
    appendChild(child) { this.append(child); }, remove() { this.isConnected = false; },
    getContext() { return this.context ??= { fills: [], fillStyle: '', fillRect(...rect) { this.fills.push({ colour: this.fillStyle, rect }); } }; } };
  nodes.push(node);
  return node;
} };
const layer = document.createElement('div');
layer.offsetHeight = 1560;
layer.offsetWidth = 720;
const answer = { box: [298 / 720, 0.2, 0.6, 0.21], read: 1000, shade: 1, rate: 1, span: 300, window: 300 };
const api = { layer, setting() {}, refresh() {}, tr: (x) => x,
  async get(path) {
    if (path === '/gold-font') return { height: 13, glyphs: { '1': Array(13).fill('##') } };
    if (path === '/gold') return answer;
    return { resources: [{ field: 'cubes', value: 1234567890, seen: 1000, verified: true }] };
  } };
let scan = { screen: 'battle', overlays: [], plain: true, at: 1000 };
const feature = goldFeature(api, { overlay: [() => []], screenScan: () => scan });
await new Promise((resolve) => setImmediate(resolve));
const total = layer.children.find((node) => node.style.cssText?.includes('left:36.1%'));
assert.ok(total, 'Cubes stay aligned with the Gold icon');
const canvas = total.children[1];
assert.equal(canvas.style.height, '15px', '11 native rows and complete two-pixel outline at 720×1560');
assert.ok(canvas.context.fills.some((fill) => fill.colour === '#000'), 'black outline');
assert.ok(canvas.context.fills.some((fill) => fill.colour === freshnessColour(0)), 'fresh white fill');
const inkLeft = Math.min(...canvas.context.fills.filter((fill) => fill.colour === freshnessColour(0))
  .map((fill) => fill.rect[0]));
assert.equal(.361 * layer.offsetWidth + parseFloat(canvas.style.left) + inkLeft, 298,
  'Cube number ink aligns with Gold number ink while the icon stays fixed');
const rateRows = layer.children.filter((node) => node.style.cssText?.includes('right:1%'));
assert.equal(rateRows.length, 7);
assert.equal(new Set(rateRows.map((row) => row.style.width)).size, 1);
assert.ok(parseFloat(rateRows[0].style.width) > 0);
assert.ok(rateRows.every((row) => row.children[0].style.flexShrink === '0'));
assert.ok(rateRows.every((row) => row.children[1].style.marginLeft !== 'auto'));
assert.ok(rateRows.every((row) => row.style.cssText.includes('gap:2px')));
now += 300000;
scan.at = now / 1000;
intervals[0]();
assert.ok(canvas.context.fills.some((fill) => fill.colour === freshnessColour(300)), 'age changes colour without a new reading');
feature.update();
assert.equal(canvas.context.fills.at(-1).colour, freshnessColour(300), 'refreshing does not reset the reading age');

// Old verified resources and recently read Gold never authorise counters
// over another screen, an unknown modal, or an expired screen observation.
answer.read = now / 1000;
for (const hidden of [null, { ...scan, at: now / 1000 - 3 },
  { ...scan, screen: 'unknown' }, { ...scan, screen: 'quest' },
  ...['quest_panel', 'black_orb', 'weapon_details', 'soul_weapon', 'stage_select', 'battle_settings']
    .map((name) => ({ ...scan, overlays: ['panel', name] }))]) {
  scan = hidden;
  feature.update();
  assert.equal(total.isConnected, false, 'Cube total hidden outside visible combat');
  assert.ok(rateRows.every((row) => !row.isConnected), 'every hourly counter hidden outside visible combat');
}
for (const visible of [
  { screen: 'battle', overlays: [], plain: true, at: now / 1000 },
  { screen: 'battle', overlays: ['panel', 'equipment_weapon'], plain: false, at: now / 1000 },
  { screen: 'battle', overlays: ['panel'], plain: false, at: now / 1000 },
]) {
  scan = visible;
  answer.read = now / 1000;
  feature.update();
  assert.equal(total.isConnected, true, 'Cube total restored on full or minimised combat');
  assert.ok(rateRows.every((row) => row.isConnected), 'hourly counters restored on combat');
}
assert.equal(combatCountersVisible({ screen: 'battle', overlays: [], at: now / 1000 }), false,
  'missing geometry does not authorise counters');
assert.equal(combatCountersVisible({ ...scan, at: now / 1000 + 1 }), false, 'future timestamps are refused');
let calls = 0;
const screenApi = { async get(path) { calls++; assert.equal(path, '/screen?quick=1'); return { scan }; } };
const [firstScan, secondScan] = await Promise.all([getScreen(screenApi), getScreen(screenApi)]);
assert.equal(calls, 1, 'overlay and debug share an in-flight classification');
assert.equal(firstScan, secondScan);
await getScreen(screenApi);
assert.equal(calls, 1, 'classification is reused within 250ms');
now += 251;
await getScreen(screenApi);
assert.equal(calls, 2, 'classification refreshes after 250ms');
Date.now = originalNow;

// Check the final raster, after the fill has covered the outline pass.
// Merely emitting black rectangles did not prove a visible border remained.
for (const ratio of [1, 2]) {
  window.devicePixelRatio = ratio;
  for (const colour of [freshnessColour(0), freshnessColour(600)]) {
    const raster = { style: {}, getContext() { return {
      fillStyle: '',
      fillRect(x, y, width, height) {
        for (let dy = y; dy < y + height; dy++) {
          for (let dx = x; dx < x + width; dx++) {
            raster.pixels[dy * raster.width + dx] = this.fillStyle;
          }
        }
      },
    }; } };
    Object.defineProperty(raster, 'height', { set(height) {
      this.pixelHeight = height;
      this.pixels = Array(this.width * height).fill(null);
    }, get() { return this.pixelHeight; } });
    drawText(raster, font, [{ text: '0123456789,', colour }], 1, { outline: 2 });
    const fill = new Set();
    let pen = 2;
    for (const char of '0123456789,') {
      const glyph = font.glyphs[char];
      glyph.forEach((row, y) => [...row].forEach((ink, x) => {
        if (ink !== '#') return;
        for (let dy = 0; dy < ratio; dy++) {
          for (let dx = 0; dx < ratio; dx++) {
            fill.add(((y + 2) * ratio + dy) * raster.width + (pen + x) * ratio + dx);
          }
        }
      }));
      pen += glyph[0].length + 1;
    }
    const border = new Set();
    for (const pixel of fill) {
      const x = pixel % raster.width, y = Math.floor(pixel / raster.width);
      for (let dy = -2 * ratio; dy <= 2 * ratio; dy++) {
        for (let dx = -2 * ratio; dx <= 2 * ratio; dx++) {
          const other = (y + dy) * raster.width + x + dx;
          if (!fill.has(other)) border.add(other);
        }
      }
    }
    assert.ok(border.size > fill.size, 'Gold-like black border is visibly heavier than the fill');
    for (const pixel of fill) assert.equal(raster.pixels[pixel], colour, 'fill keeps its freshness colour');
    for (const pixel of border) assert.equal(raster.pixels[pixel], '#000', 'two complete black pixels survive around every stroke');
    assert.equal(raster.pixels.filter((pixel) => pixel === '#000').length, border.size);
  }
}
console.log('Gold-shaped cube counter, freshness and icon columns: OK');
