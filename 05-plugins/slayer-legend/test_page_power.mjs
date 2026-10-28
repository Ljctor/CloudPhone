import assert from 'node:assert/strict';
import power from './page_power.js';
const flush = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
const events = new Map();
let poll;
globalThis.window = { setInterval(fn) { poll = fn; return 1; }, clearInterval() {},
  addEventListener(key, fn) { events.set(key, fn); }, removeEventListener(key) { events.delete(key); } };
const gets = [], posts = [], adopted = [];
const api = { setting: () => 'off', tr: (value) => value, refresh() {}, adopt: (...args) => adopted.push(args),
  get() { const request = deferred(); gets.push(request); return request.promise; },
  post(path, body) { const request = deferred(); posts.push({ ...request, path, body }); return request.promise; } };
let redraws = 0;
const ui = power(api, { changed: () => { redraws++; } });
const choice = ui.options[0], status = ui.options[1];
assert.equal(choice.value(), '');
assert.equal(choice.disabled(), false, "an unknown state must still allow a stop request");
gets.shift().resolve({ enabled: true }); await flush();
assert.equal(choice.value(), 'on', 'server state overrides stale local off preference');
assert.equal(ui.on(), true);
assert.equal(status.visible(), false, 'normal confirmed status does not duplicate the switch');
ui.onSetting('power', 'off');
assert.equal(choice.value(), 'on', 'requesting stop does not confirm it');
assert.equal(ui.on(), true);
assert.match(status.value(), /Arrêt demandé/);
assert.equal(status.visible(), true);
posts[0].resolve({ ok: false, status: 503 }); await flush();
gets.shift().resolve({ enabled: true }); await flush();
assert.match(status.value(), /Arrêt non confirmé/);
assert.equal(choice.value(), 'on');
assert.equal(ui.on(), true);
const periodicRead = poll();
gets.shift().resolve({ enabled: true }); await periodicRead;
assert.match(status.value(), /Arrêt non confirmé/, 'periodic reads do not erase a rejected command');
// An old read begun before a successful mutation cannot undo its result.
const staleRead = poll();
const old = gets.shift();
ui.onSetting('power', 'off');
posts[1].resolve({ ok: true, body: { enabled: false } }); await flush();
old.resolve({ enabled: true }); await staleRead;
assert.equal(choice.value(), 'off');
assert.equal(ui.on(), false);
// Changes are serialized; a later intent wins even if an earlier response
// arrives after it was chosen. No overlapping POST can reorder server state.
ui.onSetting('power', 'on');
ui.onSetting('power', 'off');
assert.equal(posts.length, 3);
posts[2].resolve({ ok: true, body: { enabled: true } }); await flush();
assert.equal(posts.length, 4);
assert.deepEqual(posts[3].body, { enabled: false });
posts[3].resolve({ ok: true, body: { enabled: false } }); await flush();
assert.equal(choice.value(), 'off');
assert.match(status.value(), /Serveur : plugin désactivé/);
// Reconnection/focus rechecks the authoritative server, including changes
// from another viewer; a lost response is recoverable by readback.
const reconnect = events.get('online')();
gets.shift().resolve({ enabled: true }); await reconnect;
assert.equal(choice.value(), 'on');
ui.onSetting('power', 'off');
posts[4].resolve({ ok: false, status: 502 }); await flush();
gets.shift().resolve({ enabled: false }); await flush();
assert.equal(choice.value(), 'off');
assert.doesNotMatch(status.value(), /non confirm/);
// A stalled POST and its stalled reconciliation both expire. The switch
// becomes usable with an explicitly unknown outcome; a late ACK cannot
// mutate displayed state without a fresh read.
const deadlines = new Map(); let nextTimer = 1;
window.setTimeout = (fn) => { const id = nextTimer++; deadlines.set(id, fn); return id; };
window.clearTimeout = (id) => deadlines.delete(id);
const expire = async () => { const [id, fn] = deadlines.entries().next().value; deadlines.delete(id); fn(); await flush(); };
ui.onSetting('power', 'on');
await expire(); // POST deadline -> readback begins.
await expire(); // Readback deadline -> busy state ends.
assert.equal(choice.disabled(), false);
assert.equal(choice.value(), '');
assert.match(status.value(), /Délai dépassé.*non confirmé/);
posts[5].resolve({ ok: true, body: { enabled: true } }); await flush();
assert.equal(choice.value(), '', 'late ACK alone does not confirm state');
gets.shift().resolve({ enabled: false }); await flush(); // stale, already timed out.
assert.equal(choice.value(), '');
gets.shift().resolve({ enabled: true }); await flush(); // fresh read after late ACK.
assert.equal(choice.value(), 'on');
assert.doesNotMatch(status.value(), /Délai dépassé/);
assert.equal(deadlines.size, 0);
assert.ok(redraws > 0);
ui.dispose();
assert.equal(events.size, 0);
console.log('Server-confirmed power, rejected stops, reconnect and request ordering: OK');
