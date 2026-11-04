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
let rateHistory = null;
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
    if (path === '/rate-history') return rateHistory;
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
assert.ok(!options.some((option) => option.type === 'action' && /Appliquer/.test(option.label)), 'configuration has no Apply button');
const edit = (key, value) => { settings[key] = value; ui.onSetting(key, value); };
const settle = async () => { await flush(); await flush(); };
const confirm = async (index, extra = {}) => {
  const { mode, if_revision, ...part } = posts[index].body;
  accepted[mode] = { ...part, revision: `revision-${index + 1}`, ...extra };
  posts[index].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } });
  await settle();
};
await settle(); status(); await settle();
assert.equal(posts.length, 0, 'opening the dialog does not write or apply a stored target');
assert.equal(ui.stage('mpw18'), 940);
assert.equal(byLabel('Soul Weapon').value(), '32');
assert.match(status(), /Cible acceptée/);
assert.equal(byLabel('Cible').visible(), false);
assert.equal(byLabel('Placement automatique').visible(), false);
// Changes made in one event turn produce one complete target, never an
// intermediate weapon paired with its previous variant.
edit('stage18', '941'); edit('mpw18Preset', 'IV'); edit('mpw18Weapon', '36');
status(); await settle();
assert.equal(byLabel('Gravure').value(), '');
assert.match(status(), /Choisir une gravure valide/);
assert.equal(posts.length, 0, 'incomplete choices cannot overwrite the accepted target');
assert.match(summary(), /940.*III.*Ambition/);
assert.equal(byLabel('Cible').visible(), true, 'incomplete draft keeps the accepted target visible');
edit('mpw18Variant', 'Balanced'); await settle();
assert.equal(posts.length, 1, 'a complete choice saves without an Apply click');
assert.match(status(), /Enregistrement/);
assert.equal(byLabel('Cible').visible(), true, 'saving keeps accepted target visible');
assert.deepEqual(posts[0].body, { mode: 'mpw18', stage: 941, preset: 'IV', soul_weapon: { id: 36, variant: 'Balanced' } });
posts[0].resolve({ ok: false, status: 400, body: { error_t: { template: 'Cible invalide' } } }); await settle();
assert.match(status(), /Application non confirmée.*Cible invalide/);
assert.equal(byLabel('Cible').visible(), true, 'rejection keeps accepted target visible');
assert.match(summary(), /940.*Ambition/);
assert.equal(posts.length, 1, 'a rejection cannot cause an automatic write loop');
assert.equal(byLabel('État').button().label, 'Réessayer l’enregistrement');
byLabel('État').button().run(); await settle();
await confirm(1, { weapon: 'Vision' });
assert.match(summary(), /941.*IV.*Vision/);
assert.equal(ui.stage('mpw18'), 941);
assert.equal(applied, 1);
assert.equal(byLabel('Cible').visible(), false, 'confirmed matching choices hide summary');
// Edits arriving during a write survive its response and are saved in
// order using the newly accepted revision; intermediate edits coalesce.
edit('mpw18Preset', 'V'); await settle();
assert.equal(posts[2].body.if_revision, 'revision-2');
edit('mpw18Preset', 'II'); edit('mpw18Preset', 'I'); await settle();
assert.equal(posts.length, 3);
await confirm(2, { weapon: 'Vision' });
assert.equal(byLabel('Préréglage de combat').value(), 'I');
assert.equal(posts.length, 4);
assert.equal(posts[3].body.preset, 'I');
assert.equal(posts[3].body.if_revision, 'revision-3');
await confirm(3, { weapon: 'Vision' });
edit('mpw18Preset', 'I'); await settle();
assert.equal(posts.length, 4, 'unchanged complete choices do not reapply a mode');
// Clearing a requested weapon is also a complete automatically saved target.
edit('mpw18Weapon', ''); await settle();
assert.equal(posts[4].body.soul_weapon, null);
await confirm(4, { weapon: null });
assert.match(summary(), /Sans Soul Weapon demandée/);
// A lost response is reconciled through GET, never by repeating the mutation.
edit('mpw18Preset', 'III'); await settle();
accepted.mpw18 = { ...accepted.mpw18, preset: 'III', revision: 'revision-6' };
posts[5].resolve(null); await settle();
assert.match(summary(), /III/);
assert.equal(posts.length, 6);
// Unsupported recipes are saved as preferences while staying visibly blocked.
staticSupport.supported = false;
staticSupport.reason_t = { template: 'Grille 4×4 non prise en charge' };
edit('mpw18Weapon', '36'); status(); await settle(); edit('mpw18Variant', 'Balanced'); await settle();
await confirm(6, { weapon: 'Vision', automation: structuredClone(staticSupport) });
assert.match(status(), /Cible acceptée · exécution bloquée.*4×4/);
// Both a stalled mutation and readback have deadlines. Their late answers
// cannot overwrite a newer snapshot, and no automatic write is repeated.
const deadlines = new Map(); let nextTimer = 1; let farmingPoll;
globalThis.window = { setTimeout(fn) { const id = nextTimer++; deadlines.set(id, fn); return id; },
  clearTimeout(id) { deadlines.delete(id); }, setInterval(fn) { farmingPoll = fn; return 1; }, clearInterval() {} };
const expire = async () => { const [id, fn] = deadlines.entries().next().value; deadlines.delete(id); fn(); await settle(); };
holdReads = true;
edit('mpw18Preset', 'II'); await settle();
await expire(); await expire();
assert.match(status(), /Délai dépassé.*non confirmé/);
assert.equal(byLabel('Cible').visible(), true, 'ambiguous write keeps accepted target visible');
assert.equal(posts.length, 8);
accepted.mpw18 = { ...accepted.mpw18, preset: 'II', revision: 'revision-8' };
posts[7].resolve({ ok: true, body: { loadouts: structuredClone(accepted) } }); await settle();
assert.match(status(), /Délai dépassé/);
heldReads[0].resolve({ loadouts: { ...accepted, mpw18: { ...accepted.mpw18, preset: 'III' } } }); await settle();
assert.match(status(), /Délai dépassé/);
heldReads[1].resolve({ loadouts: structuredClone(accepted) }); await settle();
assert.doesNotMatch(status(), /Délai dépassé/);
assert.equal(deadlines.size, 0);
// A conflicting revision is refreshed before retry; the saved target and
// user's latest choices remain separate throughout reconciliation.
edit('mpw18Preset', 'IV'); await settle();
assert.equal(posts[8].body.if_revision, 'revision-8');
posts[8].resolve({ ok: false, status: 409, body: { error_t: { template: 'Configuration modifiée ailleurs : recharge la cible avant d’appliquer' } } }); await settle();
accepted.mpw18.preset = 'V'; accepted.mpw18.revision = 'revision-9';
heldReads[2].resolve({ loadouts: structuredClone(accepted) }); await settle();
assert.equal(byLabel('Préréglage de combat').value(), 'IV');
assert.match(summary(), /V/);
assert.match(status(), /Configuration modifiée ailleurs/);
assert.equal(byLabel('Cible').visible(), true, 'revision conflict keeps accepted target visible');
assert.equal(posts.length, 9);
const reloadTarget = byLabel('État').button();
assert.equal(reloadTarget.label, 'Recharger et réessayer');
const reloading = reloadTarget.run();
heldReads[3].resolve({ loadouts: structuredClone(accepted) }); await reloading; await settle();
assert.equal(posts[9].body.if_revision, 'revision-9');
await confirm(9, { weapon: 'Vision', automation: structuredClone(staticSupport) });
holdReads = false;
// An inactive mode's preferences are saved to that mode alone. The page
// never sends a mode selection or an explicit setup request for an edit.
edit('stage4', '500'); edit('mpw4Preset', 'II'); await settle();
assert.equal(posts[10].path, '/loadout');
assert.equal(posts[10].body.mode, 'mpw4');
await confirm(10);
assert.ok(posts.every((post) => post.path === '/loadout'));
edit('mpw18Preset', 'II'); ui.dispose(); await settle();
assert.equal(posts.length, 11, 'disposing cancels a queued autosave');
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
accepted.mpw18.automation = { supported: true, scope: 'static', runtime_verified: false, engraving_required: true };
staticSupport.supported = true; staticSupport.reason_t = null;
farmingSnapshot = { soul_weapon: { switch: 'real', engraving: 'real', recovery: {
  weapon_id: 36, variant: 'Balanced', phase: 'recovered', verified: false,
  locks_verified: true, required: false, at: 1000 } } };
const executions = [];
const executionWait = deferred();
const evidenceUi = loadout(api, { execution: () => executionSnapshot,
  onExecute: (request) => { executions.push(request); return executionWait.promise; } });
const evidenceOptions = evidenceUi.options('mpw18');
const proof = () => evidenceOptions.find((option) => option.label === 'État').value();
await flush(); proof(); await flush();
assert.match(proof(), /Huit cartes revérifiées verrouillées.*gravure demandée non vérifiée/);
assert.doesNotMatch(proof(), /Gravure et verrouillage des huit cartes vérifiés/);
farmingSnapshot.soul_weapon.recovery = { ...farmingSnapshot.soul_weapon.recovery, phase: 'verified', verified: true, completion_verified: true };
await farmingPoll();
assert.match(proof(), /Gravure et verrouillage des huit cartes vérifiés.*contrôle actuel à refaire/);
farmingSnapshot.soul_weapon.recovery.phase = 'recovered';
await farmingPoll();
assert.match(proof(), /Gravure et verrouillage des huit cartes vérifiés.*contrôle actuel à refaire/);
assert.doesNotMatch(proof(), /gravure demandée non vérifiée/);
farmingSnapshot.soul_weapon.recovery.weapon_id = 32;
await farmingPoll();
assert.match(proof(), /autre arme ou gravure.*à vérifier/);
farmingSnapshot.soul_weapon.recovery.required = true;
await farmingPoll();
assert.match(proof(), /Réparation d’une autre configuration en attente.*cette cible reste à vérifier/);
farmingSnapshot.soul_weapon.recovery.weapon_id = accepted.mpw18.soul_weapon.id;
farmingSnapshot.soul_weapon.recovery.variant = 'different-variant';
await farmingPoll();
assert.match(proof(), /Réparation d’une autre configuration en attente.*cette cible reste à vérifier/);
farmingSnapshot.soul_weapon.recovery.variant = accepted.mpw18.soul_weapon.variant;
await farmingPoll();
assert.match(proof(), /Gravure à reprendre.*configuration demandée non vérifiée/);
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
// The same accepted target can be retried from its own dialog. The
// receipt is validated again at click time, with duplicate clicks ignored.
executionSnapshot.setup_result.target.soul_weapon = accepted.mpw18.soul_weapon;
executionSnapshot.setup_request = { mode: 'mpw18', if_revision: accepted.mpw18.revision };
const proofRow = evidenceOptions.find((option) => option.label === 'État');
const retrySetup = proofRow.button();
assert.equal(retrySetup.label, 'Réessayer cette configuration');
const executing = retrySetup.run();
await retrySetup.run();
assert.deepEqual(executions, [executionSnapshot.setup_request]);
assert.match(proof(), /Application demandée/);
executionWait.resolve(); await executing;
executionSnapshot.setup_request.if_revision = 'obsolete';
await retrySetup.run();
assert.equal(executions.length, 1, 'an obsolete captured retry button cannot execute');
assert.equal(proofRow.button(), null);
// Only the current server result for the full accepted revision proves
// readiness; recorded recovery alone remains historical.
executionSnapshot.setup_result.result = 'done';
executionSnapshot.setup_result.at = Date.now() / 1000;
assert.match(proof(), /Soul Weapon et gravure vérifiées.*huit cartes verrouillées/);
assert.equal(evidenceOptions.find((row) => row.label === 'Placement automatique').visible(), false,
  'a verified receipt is not contradicted by a repeated static support row');
accepted.mpw18.automation.engraving_required = false;
await farmingPoll();
// Reload current accepted applicability, preserving the draft.
// A separate UI with no engraving requirement cannot claim card locks.
const noEngravingUi = loadout(api, { execution: () => executionSnapshot });
const noEngravingProof = () => noEngravingUi.options('mpw18').find((option) => option.label === 'État').value();
await flush(); noEngravingProof(); await flush();
assert.equal(noEngravingProof(), 'Configuration vérifiée');
noEngravingUi.dispose();
executionSnapshot.setup_result.revision = 'old-revision';
assert.doesNotMatch(proof(), /Soul Weapon et gravure vérifiées/);
executionSnapshot.setup_result.revision = accepted.mpw18.revision;
executionSnapshot.setup_result.at -= 121;
assert.doesNotMatch(proof(), /Soul Weapon et gravure vérifiées/);
executionSnapshot.setup_result.at = Date.now() / 1000;
executionSnapshot.setup_result.target = { ...executionSnapshot.setup_result.target, preset: 'I' };
assert.doesNotMatch(proof(), /Soul Weapon et gravure vérifiées/);
evidenceUi.dispose();
// History belongs to the exact accepted revision, never a draft or a
// different target. Missing fields retain their places, including true zero.
settings.stage18 = String(accepted.mpw18.stage);
settings.mpw18Preset = accepted.mpw18.preset;
settings.mpw18Weapon = String(accepted.mpw18.soul_weapon.id);
settings.mpw18Variant = accepted.mpw18.soul_weapon.variant;
rateHistory = { configs: { mpw18: { revision: accepted.mpw18.revision, fields: [
  { field: 'gold', rate_per_hour: 1234567, measured_at: 1700000000, source: 'observed_window' },
  { field: 'cubes', rate_per_hour: 2345678, measured_at: 1700000000, source: 'observed_window' },
  { field: 'weapon_l3', rate_per_hour: 0, measured_at: 1700000000, source: 'observed_window' },
] } } };
const historicalUi = loadout(api);
await settle();
historicalUi.options('mpw18').find((row) => row.label === 'État').value();
await settle();
const metrics = () => historicalUi.rateOptions('mpw18')[0].items();
assert.deepEqual(metrics().map((row) => row.key), ['gold', 'cubes', 'weapon_l3', 'soul_green', 'soul_blue', 'soul_red']);
assert.equal(metrics()[0].value, '1.23B');
assert.equal(metrics()[1].value, '2.35B', 'cube hourly rate is abbreviated');
assert.equal(metrics()[2].value, '0', 'a measured zero is different from no measurement');
assert.ok(metrics()[0].detail.includes('2023'));
assert.equal(metrics()[3].value, '—');
assert.equal(metrics()[3].detail, 'Jamais mesuré');
for (const mode of ['free', 'mine', 'mpw4']) {
  assert.equal(historicalUi.rateOptions(mode)[0].items().length, 6);
  assert.ok(historicalUi.rateOptions(mode)[0].items().every((row) => row.value === '—'));
}
settings.stage18 = String(accepted.mpw18.stage + 1);
assert.ok(metrics().every((row) => row.value === '—'), 'a visible unsaved draft cannot borrow accepted target rates');
settings.stage18 = String(accepted.mpw18.stage);
assert.equal(metrics()[0].value, '1.23B');
rateHistory.configs.mpw18.revision = 'different-configuration';
assert.ok(metrics().every((row) => row.value === '—'), 'another revision cannot supply rates');
historicalUi.dispose();
assert.equal(deadlines.size, 0);
console.log('Automatic complete loadout saving, ordered revisions, rejected/ambiguous writes and current evidence: OK');
