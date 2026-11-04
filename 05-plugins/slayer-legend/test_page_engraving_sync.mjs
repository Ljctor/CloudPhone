import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import loadout from './page_engraving.js';

const catalogue = JSON.parse(readFileSync(new URL('./engravings.json', import.meta.url))).weapons;
const detail = (id) => structuredClone(catalogue.find((entry) => entry.id === id));
const settle = async () => { await new Promise(setImmediate); await new Promise(setImmediate); };
let poll;
globalThis.window = { setInterval(callback) { poll = callback; return 1; }, clearInterval() {} };
const settings = { stage4: '974', mpw4Weapon: '32', mpw4Variant: 'Gold-maxed' };
let accepted = { stage: 974, preset: 'IV', soul_weapon: { id: 40, variant: 'Atk' }, revision: 'relax-r1', weapon: 'Relax' };
let reads = 0;
const posts = [];
const api = {
  addTranslations() {}, tr: (text) => typeof text === 'object' ? text.template : text,
  setting: (key) => settings[key] ?? null, refresh() {},
  async get(path) {
    if (path === '/loadout') { reads++; return { loadouts: { mpw4: structuredClone(accepted) } }; }
    if (path === '/engravings') return { weapons: catalogue };
    if (path.startsWith('/engraving?id=')) return detail(Number(path.split('=')[1]));
    return null;
  },
  post(path, body) { return new Promise((resolve) => posts.push({ path, body, resolve })); },
};
let ui, rows;
function open() { ui = loadout(api); rows = ui.options('mpw4'); }
const row = (label) => rows.find((item) => item.label === label);
const displayedWeapon = () => row('Soul Weapon').value();
async function warm() { await settle(); row('Grille').rows(); await settle(); }
function assertPattern(id) {
  const entry = detail(id), cells = new Set(entry.cells.map(([r, c]) => `${r},${c}`));
  const grid = row('Grille').rows();
  assert.equal(grid.length, entry.grid);
  assert.deepEqual(grid.flatMap((line, r) => line.flatMap((cell, c) => cell === null ? [] : [`${r},${c}`])).sort(), [...cells].sort());
  assert.ok(grid.flat().every((cell) => cell !== 'empty'), 'current complete recipe covers the correct weapon mask');
}
open(); await warm();
assert.equal(displayedWeapon(), '40', 'persisted Ambition preference cannot override accepted Relax');
assert.equal(row('Gravure').value(), 'Atk');
assertPattern(40);
assert.notDeepEqual(detail(40).cells, detail(43).cells, 'Relax and Ecstasy really have different masks');
assert.equal(posts.length, 0, 'opening with stale preferences must not overwrite accepted configuration');

// Another client changes the accepted weapon: the existing popup refreshes
// without reload, applying the new catalogue rather than retaining Relax.
accepted = { ...accepted, soul_weapon: { id: 43, variant: 'Atk' }, weapon: 'Ecstasy', revision: 'ecstasy-r2' };
poll(); await warm();
assert.equal(displayedWeapon(), '43'); assertPattern(43);
assert.equal(posts.length, 0);

// Explicit incomplete edits are preserved during passive refresh. Their CAS
// remains bound to the last accepted revision, not a silently updated one.
settings.mpw4Weapon = '40'; ui.onSetting('mpw4Weapon', '40');
const beforeDraftPoll = reads;
accepted = { ...accepted, preset: 'III', revision: 'external-r3' };
poll(); await warm();
assert.equal(reads, beforeDraftPoll);
assert.equal(displayedWeapon(), '40');
assert.equal(row('Gravure').value(), '');
settings.mpw4Variant = 'Atk'; ui.onSetting('mpw4Variant', 'Atk'); await warm();
assert.equal(posts.length, 1); assert.equal(posts[0].body.if_revision, 'ecstasy-r2');
poll(); await settle();
assert.equal(displayedWeapon(), '40');
posts[0].resolve({ ok: false, status: 409, body: { error_t: { template: 'Configuration modifiée ailleurs' } } });
await warm();
assert.equal(displayedWeapon(), '40', 'CAS conflict preserves the explicit draft');
assert.match(row('État').value(), /Configuration modifiée ailleurs/);
const readsAtConflict = reads; poll(); await settle(); assert.equal(reads, readsAtConflict);
assert.equal(posts.length, 1, 'passive refresh never retries a rejected write');
ui.dispose();

// After an exact acknowledgement, released edits follow later external
// targets; old global preferences do not pin the popup to the saved draft.
accepted = { stage: 974, preset: 'IV', soul_weapon: { id: 40, variant: 'Atk' }, revision: 'relax-r4', weapon: 'Relax' };
open(); await warm();
settings.mpw4Preset = 'V'; ui.onSetting('mpw4Preset', 'V'); await settle();
assert.equal(posts.length, 2);
accepted = { ...accepted, preset: 'V', revision: 'ack-r5' };
posts[1].resolve({ ok: true, body: { loadouts: { mpw4: structuredClone(accepted) } } }); await settle();
accepted = { ...accepted, preset: 'I', soul_weapon: { id: 43, variant: 'Atk' }, weapon: 'Ecstasy', revision: 'external-r6' };
poll(); await warm();
assert.equal(row('Préréglage de combat').value(), 'I');
assert.equal(displayedWeapon(), '43'); assertPattern(43);
assert.equal(posts.length, 2);
ui.dispose();
console.log('Accepted weapon patterns supersede stale preferences; passive refresh preserves drafts/CAS/conflicts: OK');
