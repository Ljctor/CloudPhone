import assert from 'node:assert/strict';
import visualTracker, { makePatch, locatePatch, scrollViewport } from './page_navigation_tracking.js';
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
const clippedRect = [.4, .15, .6, .3];
assert.deepEqual(locatePatch(makePatch(frame, clippedRect, viewport), frame, 'vertical'), [.4, .2, .6, .3], 'rectangle clips at viewport edge');
const scrolls = [{ rect: viewport, direction: 'vertical' }];
assert.equal(scrollViewport({ kind: 'vertical', rect }, scrolls), null, 'slider viewport itself stays fixed');
assert.equal(scrollViewport({ kind: 'tap', rect: [0, 0, .1, .1] }, scrolls), null, 'fixed chrome stays fixed');
assert.equal(scrollViewport({ kind: 'tap', rect }, scrolls), scrolls[0]);
const graph = { screens: { test: { moves: [{ id: 'item', tap: [.5, .5] }, { id: 'close', tap: [.95, .05] }] } } };
assert.equal(zonesFor('test', graph, {}, null, new Map([['item', null]])).length, 1);
assert.deepEqual(zonesFor('test', graph, {}, null, new Map([['item', rect]]))[0].rect, rect);
// Exercise decoded-frame caching and canvas failure: a blocked/unreadable
// video must remove tracked rectangles instead of freezing stale positions.
let draws = 0;
let failed = false;
const rgba = new Uint8Array(192 * 320 * 4);
for (let i = 0; i < rgba.length / 4; i++) {
  const value = frame.pixels[Math.floor(i / 192 / 2) * width + Math.floor(i % 192 / 2)];
  rgba[i * 4] = value; rgba[i * 4 + 1] = value; rgba[i * 4 + 2] = value;
}
globalThis.document = { createElement: () => ({ getContext: () => ({
  drawImage() { draws++; if (failed) throw Error('unreadable frame'); },
  getImageData: () => ({ data: rgba }),
}) }) };
const video = { videoWidth: 192, videoHeight: 320, readyState: 2, currentTime: 1 };
const tracker = visualTracker(() => video);
const trackedZone = [{ id: 'item', kind: 'tap', rect }];
assert.deepEqual(tracker.update('test', trackedZone, scrolls).get('item'), rect);
tracker.update('test', trackedZone, scrolls);
assert.equal(draws, 1, 'one read per decoded video frame');
video.currentTime++;
failed = true;
assert.equal(tracker.update('test', trackedZone, scrolls).get('item'), null);
failed = false; video.currentTime++;
assert.deepEqual(tracker.update('test', trackedZone, scrolls).get('item'), rect);
tracker.reset();
assert.equal(tracker.update('other', [], []).size, 0, 'screen changes discard old identities');
console.log('Visual scroll tracking: actual movement, boundaries, disappearance, ambiguity and fixed chrome: OK');
