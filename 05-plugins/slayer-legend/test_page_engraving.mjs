import assert from 'node:assert/strict';
import loadout from './page_engraving.js';
const flush = () => new Promise((resolve) => setImmediate(resolve));
const deferred = () => { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; };
let accepted = { mpw18: { stage: 940, preset: 'III', soul_weapon: { id: 32, variant: 'Balanced' }, weapon: 'Ambition' },
  mpw4: { stage: null, preset: null, soul_weapon: null } };
const settings = {};
const posts = [];
let detailFailure = false;
let holdReads = false;
const heldReads = [];
let farmingSnapshot = null;
let executionSnapshot = null;
const staticSupport = { supported: true, scope: 'static', runtime_verified: false, reason_t: null };
const details = (id) => ({ id, automation: staticSupport, name: id === 32 ? 'Ambition' : 'Vision', grid: 2, cells: [[0, 0]],
  variants: [{ name: 'Balanced', pieces: [{ cells: [[0, 0]], colour: 'red' }] }] });
const api = { addTranslations() {}, tr: (value) => typeof value === 'object' ? value.template : value,
  setting: (key) => settings[key] ?? null, refresh() {},
  async get(path) {
    if (path === '/loadout' && holdReads) { const request = deferred(); heldReads.push(request); return request.promise; }
    if (path === '/loadout') return { loadouts: structuredClone(accepted) };
    if (path === '/farming') return farmingSnapshot;
    if (path === '/engravings') return { weapons: [details(32), details(36)] };
    if (path.startsWith('/engraving?id=') && detailFailure) return null;
    if (path.startsWith('/engraving?id=')) return details(Number(path.split('=')[1]));
    throw Error(path);
  },
  post(path, body) { const request = deferred(); posts.push({ path, body, ...request }); return request.promise; } };
let applied = 0;
const ui = loadout(api, { onApplied: () => { applied++; } });
const options = ui.options('mpw18', () => [{ value: '940', label: '940' }, { value: '941', label: '941' }]);
const byLabel = (label) => options.find((option) => option.label === label);
const status = () => byLabel('État').value();
const summary = () => byLabel('Cible').value();
const apply = byLabel('Appliquer la configuration');
const edit = (key, value) => { settings[key] = value; ui.onSetting(key, value); };
await flush(); status(); await flush();
assert.equal(ui.stage('mpw18'), 940);
assert.equal(byLabel('Soul Weapon').value(), '32');
assert.match(status(), /Cible acceptée/);
assert.ok(!options.some((option) => ['Compatibilité', 'Cible acceptée', 'Preuve pour la cible acceptée', 'Configuration'].includes(option.label)));
assert.deepEqual(options.filter((option) => option.type === 'status' && (option.visible?.() ?? true)).map((option) => option.label), ['Cible', 'État']);
assert.equal(apply.disabled(), true);
edit('stage18', '941'); edit('mpw18Preset', 'IV');
assert.equal(posts.length, 0, 'editing never mutates the gateway or the running mode');
assert.match(status(), /Modifications non appliquées/);
assert.match(summary(), /940.*III.*Ambition/);
edit('mpw18Weapon', '36'); status(); await flush();
assert.equal(byLabel('Gravure').value(), '', 'a new weapon requires a deliberate variant choice');
assert.match(status(), /Choisir une gravure valide/);
assert.equal(apply.disabled(), true);
await apply.run();
assert.equal(posts.length, 0, 'an incomplete weapon cannot silently retain the old accepted target');
assert.match(summary(), /Ambition/);
edit('mpw18Variant', 'Balanced');
assert.equal(apply.disabled(), false);
const firstApply = apply.run();
assert.match(status(), /Enregistrement/);
assert.equal(apply.disabled(), true);
assert.deepEqual(posts[0].body, { mode: 'mpw18', stage: 941, preset: 'IV', soul_weapon: { id: 36, variant: 'Balanced' } });
posts[0].resolve({ ok: false, status: 400, body: { error_t: { template: 'Cible invalide' } } });
await firstApply;
assert.match(status(), /Application non confirmée.*Cible invalide/);
assert.match(summary(), /940.*Ambition/);
assert.equal(byLabel('Soul Weapon').value(), '36', 'a rejected draft stays editable');
const secondApply = apply.run();
accepted.mpw18 = { ...posts[1].body, weapon: 'Vision' }; delete accepted.mpw18.mode;
posts[1].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await secondApply;
assert.match(status(), /Cible acceptée · équipement en jeu à vérifier/);
assert.match(summary(), /941.*IV.*Vision/);
assert.equal(ui.stage('mpw18'), 941);
assert.equal(applied, 1);
// A response for an older submitted draft cannot erase a subsequent edit.
edit('mpw18Preset', 'V');
const thirdApply = apply.run();
edit('mpw18Preset', 'II');
accepted.mpw18.preset = 'V';
posts[2].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await thirdApply;
assert.equal(byLabel('Préréglage de combat').value(), 'II');
assert.match(summary(), /V/);
assert.match(status(), /Modifications non appliquées/);
assert.equal(apply.disabled(), false);
// Clearing a target is explicit and part of the complete revision.
edit('mpw18Weapon', '');
const clearApply = apply.run();
assert.equal(posts[3].body.soul_weapon, null);
accepted.mpw18 = { ...posts[3].body, weapon: null }; delete accepted.mpw18.mode;
posts[3].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await clearApply;
assert.match(summary(), /Sans Soul Weapon demandée/);
// The gateway can accept a write even when its POST response is lost.
edit('mpw18Preset', 'III');
const lostResponse = apply.run();
accepted.mpw18 = { ...posts[4].body, weapon: null }; delete accepted.mpw18.mode;
posts[4].resolve(null); await lostResponse;
assert.match(status(), /Sans Soul Weapon demandée/);
assert.equal(byLabel('Préréglage de combat').value(), 'III');
assert.match(summary(), /III/);
// Structural support is separate from runtime readiness. Unsupported
// recipes may be saved deliberately, but never presented as runnable.
staticSupport.supported = false;
staticSupport.reason_t = { template: 'Grille 4×4 non prise en charge' };
edit('mpw18Weapon', '36'); status(); await flush(); edit('mpw18Variant', 'Balanced');
assert.match(status(), /Modifications non appliquées.*4×4/);
assert.equal(apply.disabled(), false, 'a known unsupported target can still be saved explicitly');
const unsupported = apply.run();
accepted.mpw18 = { ...posts[5].body, weapon: 'Vision', automation: structuredClone(staticSupport) }; delete accepted.mpw18.mode;
posts[5].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await unsupported;
assert.match(status(), /Cible acceptée · exécution bloquée.*4×4/);
// Bound both a stalled mutation and its readback, then reconcile a late
// mutation through a new read instead of accepting its late response.
const deadlines = new Map(); let nextTimer = 1; let farmingPoll;
globalThis.window = { setTimeout(fn) { const id = nextTimer++; deadlines.set(id, fn); return id; },
  clearTimeout(id) { deadlines.delete(id); }, setInterval(fn) { farmingPoll = fn; return 1; }, clearInterval() {} };
const expire = async () => { const [id, fn] = deadlines.entries().next().value; deadlines.delete(id); fn(); await flush(); };
edit('mpw18Preset', 'II'); holdReads = true;
const timedApply = apply.run();
await expire(); await expire(); await timedApply;
assert.match(status(), /Délai dépassé.*non confirmé/);
assert.equal(apply.disabled(), false, 'a deadline releases Apply without automatically retrying the write');
assert.equal(posts.length, 7);
accepted.mpw18 = { ...posts[6].body, weapon: 'Vision', revision: 'revision-2', automation: structuredClone(staticSupport) }; delete accepted.mpw18.mode;
posts[6].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await flush();
assert.match(status(), /Délai dépassé/, 'late mutation ACK alone is ignored');
heldReads[0].resolve({ loadouts: { ...accepted, mpw18: { ...accepted.mpw18, preset: 'III' } } }); await flush();
assert.match(status(), /Délai dépassé/, 'late expired read is ignored too');
heldReads[1].resolve({ loadouts: structuredClone(accepted) }); await flush();
assert.doesNotMatch(status(), /Délai dépassé/);
assert.match(summary(), /II/);
assert.equal(deadlines.size, 0);
// Compare-and-set conflicts refresh accepted state without discarding edits
// or retrying the rejected write. Only another explicit Apply uses the new revision.
edit('mpw18Preset', 'IV');
const conflict = apply.run();
assert.equal(posts[7].body.if_revision, 'revision-2');
posts[7].resolve({ ok: false, status: 409, body: { error_t: { template: 'Configuration modifiée ailleurs : recharge la cible avant d’appliquer' } } });
await flush();
accepted.mpw18.preset = 'V'; accepted.mpw18.revision = 'revision-3';
heldReads[2].resolve({ loadouts: structuredClone(accepted) }); await conflict;
assert.equal(byLabel('Préréglage de combat').value(), 'IV');
assert.match(summary(), /V/);
assert.match(status(), /Configuration modifiée ailleurs/);
assert.equal(posts.length, 8);
const applyAfterConflict = apply.run();
assert.equal(posts[8].body.if_revision, 'revision-3');
accepted.mpw18.preset = 'IV'; accepted.mpw18.revision = 'revision-4';
posts[8].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await applyAfterConflict;
holdReads = false;
ui.dispose();
// A failed detail read is visible and retryable without reloading the page.
for (const key of Object.keys(settings)) delete settings[key];
detailFailure = true;
const retryUi = loadout(api);
const retryOptions = retryUi.options('mpw18');
const retryStatus = retryOptions.find((option) => option.label === 'État');
await flush(); retryStatus.value(); await flush();
assert.match(retryStatus.value(), /Données de gravure indisponibles/);
assert.equal(retryStatus.button().label, 'Réessayer');
detailFailure = false;
retryStatus.button().run(); await flush(); retryStatus.value(); await flush();
assert.doesNotMatch(retryStatus.value(), /Données de gravure indisponibles/);
retryUi.dispose();
// Recovery lock checks are not evidence that the requested recipe is in
// place. Even a full recorded verification is dated historical evidence.
accepted.mpw18.automation = { supported: true, scope: 'static', runtime_verified: false };
staticSupport.supported = true; staticSupport.reason_t = null;
farmingSnapshot = { soul_weapon: { switch: 'real', engraving: 'real', recovery: {
  weapon_id: 36, variant: 'Balanced', phase: 'recovered', verified: false,
  locks_verified: true, required: false, at: 1000 } } };
const evidenceUi = loadout(api, { execution: () => executionSnapshot });
const evidenceOptions = evidenceUi.options('mpw18');
const proof = () => evidenceOptions.find((option) => option.label === 'État').value();
await flush(); proof(); await flush();
assert.match(proof(), /Huit cartes revérifiées verrouillées.*gravure demandée non vérifiée/);
assert.doesNotMatch(proof(), /Gravure et verrouillage des huit cartes vérifiés/);
farmingSnapshot.soul_weapon.recovery = { ...farmingSnapshot.soul_weapon.recovery, phase: 'verified', verified: true };
await farmingPoll();
assert.match(proof(), /Gravure et verrouillage des huit cartes vérifiés.*contrôle actuel à refaire/);
farmingSnapshot.soul_weapon.recovery.weapon_id = 32;
await farmingPoll();
assert.match(proof(), /autre arme ou gravure.*à vérifier/);
farmingSnapshot.soul_weapon.recovery.required = true;
await farmingPoll();
assert.match(proof(), /Remise en sécurité nécessaire.*huit cartes/);
farmingSnapshot.soul_weapon.engraving = 'off';
farmingSnapshot.soul_weapon.recovery = {};
farmingSnapshot.soul_weapon.last = { weapon: 'Ambition', result: 'failed', engraving_t: 'Unrelated legacy failure' };
await farmingPoll();
assert.match(proof(), /Gravure automatique désactivée.*supervision/);
assert.doesNotMatch(proof(), /Unrelated legacy failure|premier passage.*en attente/);
executionSnapshot = { mode: 'mpw18', setup_result: { mode: 'mpw18', revision: accepted.mpw18.revision,
  result: 'failed', at: Date.now() / 1000, target: { stage: accepted.mpw18.stage, preset: accepted.mpw18.preset,
    soul_weapon: accepted.mpw18.soul_weapon }, message_t: 'Current matching target failed' } };
assert.equal(proof(), 'Current matching target failed');
executionSnapshot.setup_result.revision = 'old-revision';
assert.doesNotMatch(proof(), /Current matching target failed/);
executionSnapshot.setup_result.revision = accepted.mpw18.revision;
executionSnapshot.setup_result.at -= 121;
assert.doesNotMatch(proof(), /Current matching target failed/);
executionSnapshot.setup_result.at = Date.now() / 1000;
executionSnapshot.setup_result.target = { ...executionSnapshot.setup_result.target, soul_weapon: { id: 32, variant: 'Gold-maxed' } };
assert.doesNotMatch(proof(), /Current matching target failed/);
evidenceUi.dispose();
assert.equal(deadlines.size, 0);
console.log('Draft loadout, complete explicit apply, rejected save and accepted-target separation: OK');
