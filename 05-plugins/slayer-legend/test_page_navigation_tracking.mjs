import assert from 'node:assert/strict';
import { makePatch, locatePatch, scrollViewport } from './page_navigation_tracking.js';
import { zonesFor } from './page_navigation_debug.js';

const width = 96; const height = 160;
const frame = { width, height, pixels: new Uint8Array(width * height) };
let seed = 17;
for (let i = 0; i < frame.pixels.length; i++) {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  frame.pixels[i] = seed >>> 24;
}
const viewport = [.1, .2, .9, .9];
const rect = [.4, .45, .6, .55];
const patch = makePatch(frame, rect, viewport);
const shifted = (dx, dy) => {
  const result = { width, height, pixels: new Uint8Array(width * height) };
  for (let y = Math.ceil(viewport[1] * height); y < viewport[3] * height; y++) {
    for (let x = Math.ceil(viewport[0] * width); x < viewport[2] * width; x++) {
      const sx = x - dx; const sy = y - dy;
      if (sx >= viewport[0] * width && sx < viewport[2] * width && sy >= viewport[1] * height && sy < viewport[3] * height) {
        result.pixels[y * width + x] = frame.pixels[sy * width + sx];
      }
    }
  }
  return result;
};
assert.deepEqual(locatePatch(patch, frame, 'vertical'), rect, 'no-op boundary swipe keeps the measured position');
assert.deepEqual(locatePatch(patch, shifted(0, -24), 'vertical')?.map((v) => +v.toFixed(6)), [.4, .3, .6, .4]);
assert.deepEqual(locatePatch(patch, shifted(12, 0), 'horizontal'), [.525, .45, .725, .55]);
assert.equal(locatePatch(patch, shifted(0, -80), 'vertical'), null, 'offscreen content has no rectangle');
assert.equal(locatePatch(patch, { ...frame, pixels: new Uint8Array(width * height) }, 'vertical'), null);
assert.deepEqual(locatePatch(patch, frame, 'vertical'), rect, 'reverse drag can recover original content');
const duplicate = { ...frame, pixels: frame.pixels.slice() };
for (const [x, y, value] of patch.samples) duplicate.pixels[(patch.cy + y + 30) * width + patch.cx + x] = value;
assert.equal(locatePatch(patch, duplicate, 'vertical'), null, 'repeated rows cannot establish identity');
assert.equal(makePatch({ ...frame, pixels: new Uint8Array(width * height) }, rect, viewport), null, 'flat content is untrackable');
const scrolls = [{ rect: viewport, direction: 'vertical' }];
assert.equal(scrollViewport({ kind: 'vertical', rect }, scrolls), null, 'slider viewport itself stays fixed');
assert.equal(scrollViewport({ kind: 'tap', rect: [0, 0, .1, .1] }, scrolls), null, 'fixed chrome stays fixed');
assert.equal(scrollViewport({ kind: 'tap', rect }, scrolls), scrolls[0]);
const graph = { screens: { test: { moves: [{ id: 'item', tap: [.5, .5] }, { id: 'close', tap: [.95, .05] }] } } };
assert.equal(zonesFor('test', graph, {}, null, new Map([['item', null]])).length, 1);
assert.deepEqual(zonesFor('test', graph, {}, null, new Map([['item', rect]]))[0].rect, rect);
console.log('Visual scroll tracking: actual movement, boundaries, disappearance, ambiguity and fixed chrome: OK');
