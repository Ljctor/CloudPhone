import assert from 'node:assert/strict';
import fs from 'node:fs';
import loadout from './page_engraving.js';
const table = JSON.parse(fs.readFileSync(new URL('./engravings.json', import.meta.url)));
const entry = table.weapons.find((w) => w.id === 32);
const maxed = { name: 'Gold-maxed', needed: { I: 4 }, pieces: entry.gold.with_rotation.balanced.pieces };
const blocked = (shape) => ({ supported: false, scope: 'static', reason_t: {
  template: 'Gravure de {name} : placement non calibré pour {shapes}', params: { name: 'Ambition', shapes: shape } } });
const variants = [
  { ...entry.variants[0], needed: { J: 1, L: 3 }, automation: blocked('J') },
  { ...entry.variants[1], needed: { I: 1, L: 2, O: 1 }, automation: blocked('O') },
  { ...maxed, automation: { supported: true } },
  { ...maxed, name: 'Gold-balanced', pieces: [...maxed.pieces].reverse().map((p) => ({ ...p, colour: 'blue' })),
    automation: { supported: true } },
];
for (const variant of variants) for (const history of [null, { recovery: { weapon_id: 99, cards: [] } }]) {
  let writes = 0;
  const api = {
    addTranslations() {}, setting: () => null, refresh() {},
    tr: (value, params = {}) => {
      if (typeof value === 'object') return api.tr(value.template, value.params);
      return value.replace(/\{([^}]+)\}/g, (_, key) => params[key] ?? `{${key}}`);
    },
    get: async (path) => path === '/loadout' ? { loadouts: { mpw18: {
      stage: 970, preset: 'IV', soul_weapon: { id: 32, variant: variant.name }, weapon: 'Ambition', revision: 'test',
    } } } : path === '/engravings' ? { weapons: [entry] }
      : path.startsWith('/engraving?') ? { ...entry, variants }
        : path === '/farming' ? { soul_weapon: history } : null,
    post: () => { writes++; throw Error('opening options must not mutate configuration'); },
  };
  const ui = loadout(api);
  const options = ui.options('mpw18');
  const row = (name) => options.find((o) => o.label === name);
  await new Promise(setImmediate); row('Gravure').choices(); await new Promise(setImmediate);
  const requirements = row('Pièces nécessaires').value();
  assert.match(requirements, /Disponibilité à vérifier en jeu/);
  for (const [shape, count] of Object.entries(variant.needed)) assert.ok(requirements.includes(`${count} × ${shape}`));
  const capability = row('Placement automatique').value();
  if (variant.automation.supported) assert.match(capability, /inventaire et équipement non vérifiés/);
  else assert.match(capability, /placement non calibré pour [JO]/);
  const equivalent = options.filter((o) => o.label === 'Attention').find((o) => o.visible());
  assert.equal(Boolean(equivalent), variant.name === 'Gold-balanced');
  if (equivalent) assert.equal(equivalent.value(), 'Même disposition que Gold-maxed');
  assert.equal(writes, 0);
  ui.dispose();
}
console.log('Engraving requirements, static placement limits and equivalent layouts: OK');
