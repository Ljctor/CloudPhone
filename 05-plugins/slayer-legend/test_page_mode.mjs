import assert from 'node:assert/strict';
import modeFeature from './page_mode.js';
const flush = () => new Promise((resolve) => setImmediate(resolve));
const timers = new Map(); let next = 1;
globalThis.window = { localStorage: { getItem: () => null, removeItem() {} },
  setTimeout(fn) { const id = next++; timers.set(id, fn); return id; }, clearTimeout(id) { timers.delete(id); },
  setInterval() { return 1; }, clearInterval() {} };
const settings = { mode: 'mpw18', defaultMode: 'mpw18' };
const state = { configured: true, mode: 'mpw18', default: 'mpw18', state: 'farming', tone: 'ok', until: null,
  message_t: 'Stage 970 · III', intention: null };
const posts = [];
let setupResponse = null;
let watchdogIntent = null;
const api = { setting: (key) => settings[key] ?? null, addTranslations() {}, refresh() {},
  tr: (value, args = {}) => {
    const params = typeof value === 'object' ? value.params : args;
    const template = typeof value === 'object' ? value.template : value;
    return String(template).replace(/\{(\w+)\}/g, (_, key) => params[key] ?? key);
  }, adopt(key, value) { settings[key] = value; },
  get: async (path) => {
    if (path === '/mode') return structuredClone(state);
    if (path === '/loadout') return { loadouts: { mpw18: { stage: 970, preset: 'III', soul_weapon: null } } };
    if (path === '/engravings') return { weapons: [] };
    if (path === '/stages') return { mpw18: [{ number: 970 }], mpw4: [] };
    if (path === '/farming') return null;
    throw Error(path);
  }, post(path, body) { posts.push({ path, body });
    if (path === '/mode/setup') return setupResponse;
    return Promise.resolve({ ok: true, body: structuredClone(state) }); },
};
const ui = modeFeature(api, { known: () => null, stage: null,
  watchdog: { line: () => '', retry: () => null, intention: () => watchdogIntent } });
await flush();
const intentRow = ui.options.find((option) => option.label === 'Intention');
assert.equal(intentRow.visible(), false);
const overlay = ui.overlay();
assert.equal(overlay.length, 2, 'game overlay remains only mode and timer');
assert.equal(overlay[0].text, 'FARMING MPW18');
assert.equal(overlay[1].text, 'défaut');
state.intention = { kind: 'resource_refresh', destination: 'equipment_weapon',
  purpose_t: { template: 'Actualiser les compteurs de ressources', params: {} }, route: null, route_known: false };
const poll = [...timers.values()].find((fn) => fn.name === 'askMode');
await poll();
assert.equal(intentRow.visible(), true);
assert.match(intentRow.value(), /Equipment: Weapon.*Actualiser les compteurs de ressources/);
assert.deepEqual(ui.overlay(), overlay, 'temporary destination does not replace the requested farming mode');
ui.onSetting('stage18', '971');
assert.equal(posts.length, 0, 'draft editing does not execute a new mode or route');
state.intention = null; await poll();
watchdogIntent = { kind: 'park', destination: 'soul_weapon', purpose_t: 'surveiller les âmes' };
assert.match(intentRow.value(), /Soul Weapon.*surveiller les âmes/);
watchdogIntent = null;
assert.equal(intentRow.visible(), false, 'completed/absent intentions do not leave a permanent extra row');
state.state = 'idle'; state.tone = 'error'; state.message_t = null;
state.setup_blocker_t = { template: 'Gravure automatique désactivée · premier passage soumis à supervision', params: {} };
await poll();
const statusRow = ui.options.find((option) => option.label === 'État');
assert.match(statusRow.value(), /Gravure automatique désactivée.*supervision/);
assert.equal(ui.overlay().length, 2);
assert.ok(ui.overlay().every((line) => line.colour === '#ff4040'), 'idle proven blocker uses existing red tone');
state.setup_result = { mode: 'mpw18', result: 'failed', at: Date.now() / 1000,
  message_t: { template: 'Échec de la configuration courante', params: {} } };
await poll();
assert.equal(statusRow.value(), 'Échec de la configuration courante');
state.setup_result.at -= 121; await poll();
assert.match(statusRow.value(), /Gravure automatique désactivée.*supervision/, 'stale attempt reason cannot mask actual gate');
state.setup_result = null;
state.hold = { id: 'hold', mode: 'mpw18', left: 5 }; state.tone = 'setup'; await poll();
assert.match(statusRow.value(), /en attente.*tu joues/);
// Explicit setup uses the current accepted receipt, not edited loadout
// drafts, and keeps hold controls ahead of the optional apply action.
state.setup_request = { mode: 'mpw18', if_revision: 'accepted-revision' };
await poll();
assert.deepEqual(statusRow.button().map((button) => button.label), ['Jeu libre', 'Reprendre']);
state.hold = null; state.setup_blocker_t = null; state.setup_result = null;
await poll();
const apply = statusRow.button();
assert.equal(apply.label, 'Appliquer la configuration');
assert.equal(apply.disabled(), false);
let resolveSetup;
setupResponse = new Promise((resolve) => { resolveSetup = resolve; });
const beforeSetup = posts.length;
const applying = apply.run();
assert.equal(apply.disabled(), true);
assert.equal(statusRow.value(), 'Application demandée…');
await apply.run();
assert.deepEqual(posts.slice(beforeSetup), [{ path: '/mode/setup', body: { mode: 'mpw18', if_revision: 'accepted-revision' } }],
  'a double click cannot start a second application');
state.state = 'moving'; state.setup = true; state.setup_request = null;
state.message_t = 'Application de la configuration mpw18';
resolveSetup({ ok: true, status: 202, body: structuredClone(state) });
await applying;
assert.equal(statusRow.value(), 'Application de la configuration mpw18');
assert.equal(state.setup_result, null, 'an accepted asynchronous request cannot claim verified success');
assert.equal(statusRow.button(), null, 'the apply action disappears while the backend transaction is active');
state.state = 'failed'; state.setup = false;
state.setup_request = { mode: 'mpw18', if_revision: 'current-revision' };
state.setup_result = { mode: 'mpw18', result: 'failed', at: Date.now() / 1000,
  message_t: { template: 'Soul Weapon non équipée', params: {} } };
await poll();
assert.equal(statusRow.value(), 'Soul Weapon non équipée', 'actual application failure remains visible');
setupResponse = Promise.resolve({ ok: false, status: 409,
  body: { error_t: { template: 'Configuration modifiée ailleurs', params: {} } } });
await statusRow.button().run();
assert.equal(statusRow.value(), 'Configuration modifiée ailleurs', 'server rejection is visible even after reconciliation');
await poll();
assert.equal(statusRow.value(), 'Configuration modifiée ailleurs', 'polling cannot erase a rejected request');
setupResponse = Promise.reject(Error('connection lost'));
await statusRow.button().run();
assert.equal(statusRow.value(), 'Application non confirmée · vérification en cours',
  'a failed connection cannot claim that the request was applied');
assert.equal(statusRow.button().disabled(), false, 'a failed request releases the UI action');
let finishLate;
setupResponse = new Promise((resolve) => { finishLate = resolve; });
const existingTimers = new Set(timers.keys());
const beforeDeadlinePosts = posts.length;
const stalled = statusRow.button().run();
const deadline = [...timers].find(([id]) => !existingTimers.has(id));
assert.ok(deadline, 'an application request has a finite UI deadline');
deadline[1]();
await stalled;
assert.equal(statusRow.value(), 'Application non confirmée · vérification en cours');
assert.equal(statusRow.button().disabled(), false, 'deadline releases the action without claiming server cancellation');
finishLate({ ok: true, status: 202, body: structuredClone(state) });
await flush();
assert.equal(posts.length, beforeDeadlinePosts + 1, 'late reconciliation does not automatically retry a mutation');
ui.dispose();
console.log('Requested mode, compact execution status and temporary destination/purpose: OK');
