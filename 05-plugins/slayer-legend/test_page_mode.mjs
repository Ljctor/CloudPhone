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
  }, post(path, body) { posts.push({ path, body }); return Promise.resolve({ ok: true, body: structuredClone(state) }); },
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
ui.dispose();
console.log('Requested mode, compact execution status and temporary destination/purpose: OK');
