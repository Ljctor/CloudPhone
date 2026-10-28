import assert from 'node:assert/strict';
import { inflateSync } from 'node:zlib';
import trace, { captureBefore } from './page_trace.js';

let rgba = new Uint8ClampedArray([10, 20, 30, 255, 40, 50, 60, 255]);
globalThis.document = { createElement: () => ({
  getContext: () => {
    let copied;
    return { drawImage() { copied = rgba.slice(); }, getImageData: () => ({ data: copied }) };
  },
}) };
const video = { videoWidth: 2, videoHeight: 1, readyState: 2 };
const pending = captureBefore(video);
rgba.fill(99); // Android's response arrives after pointerdown; the copy stays unchanged.
const captured = await pending;
assert.deepEqual([...inflateSync(Buffer.from(captured.rgb, 'base64'))], [10, 20, 30, 40, 50, 60]);
assert.equal(captureBefore({ ...video, readyState: 0 }), null);
assert.equal(captureBefore({ ...video, videoWidth: 2000 }), null);

const listeners = new Map();
const device = {
  addEventListener(name, callback, capture) { assert.equal(capture, true); listeners.set(name, callback); },
  removeEventListener(name, callback, capture) {
    assert.equal(capture, true); assert.equal(listeners.get(name), callback); listeners.delete(name);
  },
};
const posts = [];
let onTap;
let stopped = false;
const api = {
  layer: { closest: () => ({ parentElement: device }) }, video: () => video,
  setting: () => 'on', onTap(callback) { onTap = callback; return () => { stopped = true; }; },
  post: async (url, body) => { posts.push([url, body]); return { ok: true, body: { queued: true } }; },
};
const part = trace(api);
listeners.get('pointerdown')();
onTap({ x: .2, y: .3, kind: 'swipe', end: { x: .2, y: .7 } });
// Wait for the asynchronous compression and serialized send without a timer assumption.
for (let i = 0; i < 100 && posts.filter(([url]) => url === '/trace').length < 1; i++) await new Promise((resolve) => setTimeout(resolve, 5));
assert.equal(posts.length, 2);
assert.equal(posts[0][0], '/trace/start');
assert.equal(posts[1][0], '/trace');
assert.equal(posts[1][1].before_frame.encoding, 'deflate');
assert.deepEqual(posts[1][1].end, { x: .2, y: .7 });
listeners.get('pointerdown')();
listeners.get('pointercancel')();
onTap({ x: .4, y: .5, kind: 'tap' });
for (let i = 0; i < 100 && posts.filter(([url]) => url === '/trace').length < 2; i++) await new Promise((resolve) => setTimeout(resolve, 5));
assert.equal(posts.at(-1)[1].before_frame, undefined);
part.dispose();
assert.equal(listeners.size, 0);
assert.equal(stopped, true);
console.log('passive trace captures before user input, preserves swipes, and cleans up');

const rapidPosts = [];
const rapid = trace({ ...api, post: async (url, body) => {
  rapidPosts.push([url, body]); return { ok: true, body: { accepted: true, queued: true } };
} });
listeners.get('pointerdown')();
onTap({ x: .1, y: .2, kind: 'tap' });
listeners.get('pointerdown')();
onTap({ x: .3, y: .4, kind: 'tap' });
for (let i = 0; i < 100 && !rapidPosts.some(([url]) => url === '/trace'); i++) {
  await new Promise((resolve) => setTimeout(resolve, 5));
}
const sent = rapidPosts.filter(([url]) => url === '/trace');
assert.equal(sent.length, 1, 'a superseded compressed pre-frame must not become a direct edge');
assert.equal(sent[0][1].sequence, 2);
assert.equal(rapidPosts.filter(([url]) => url === '/trace/start').length, 2);
rapid.dispose();
console.log('rapid input markers invalidate superseded frame sends');
