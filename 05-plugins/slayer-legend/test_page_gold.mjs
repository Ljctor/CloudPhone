import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import goldFeature from './page_gold.js';
import { GOLD_COUNTER_FONT as font, GOLD_COUNTER_SOURCES as sources } from './page_gold_counter_font.js';
import { freshnessColour } from './page_freshness.js';

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
const answer = { box: [0.4, 0.2, 0.6, 0.21], read: 1000, shade: 1, rate: 1, span: 300, window: 300 };
const api = { layer, setting() {}, refresh() {}, tr: (x) => x,
  async get(path) {
    if (path === '/gold-font') return { height: 13, glyphs: { '1': Array(13).fill('##') } };
    if (path === '/gold') return answer;
    return { resources: [{ field: 'cubes', value: 1234567890, seen: 1000, verified: true }] };
  } };
const feature = goldFeature(api, { overlay: [() => []] });
await new Promise((resolve) => setImmediate(resolve));
const total = layer.children.find((node) => node.style.cssText?.includes('left:36.1%'));
assert.ok(total, 'Cubes stay aligned with the Gold icon');
const canvas = total.children[1];
assert.equal(canvas.style.height, '13px', '11 native rows and black outline at 720×1560');
assert.ok(canvas.context.fills.some((fill) => fill.colour === '#000'), 'black outline');
assert.ok(canvas.context.fills.some((fill) => fill.colour === freshnessColour(0)), 'fresh white fill');
const rateRows = layer.children.filter((node) => node.style.cssText?.includes('right:1%'));
assert.equal(rateRows.length, 7);
assert.ok(rateRows.every((row) => row.style.cssText.includes('width:20%')));
assert.ok(rateRows.every((row) => row.children[0].style.flexShrink === '0'));
assert.ok(rateRows.every((row) => row.children[1].style.marginLeft === 'auto'));
now += 300000;
intervals[0]();
assert.ok(canvas.context.fills.some((fill) => fill.colour === freshnessColour(300)), 'age changes colour without a new reading');
feature.update();
assert.equal(canvas.context.fills.at(-1).colour, freshnessColour(300), 'refreshing does not reset the reading age');
Date.now = originalNow;
console.log('Gold-shaped cube counter, freshness and icon columns: OK');
