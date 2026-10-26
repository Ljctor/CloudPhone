import assert from 'node:assert/strict';
import gameFeature from './page_game.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { SCREEN_ICONS } from './page_screen_icons.js';
import { readFile } from 'node:fs/promises';

const catalogue = JSON.parse(await readFile(new URL('./resources.json', import.meta.url)));
assert.equal(catalogue.length, 21);
assert.equal(catalogue.findIndex((row) => row.field === 'soul_white'),
  catalogue.findIndex((row) => row.field === 'soul_red') + 1);
for (const field of ['gold', 'emerald', 'soul_green', 'soul_blue', 'soul_red', 'soul_white',
  'feather_white', 'feather_green', 'feather_purple', 'dragon_power', 'dragon_spark']) {
  assert.ok(RESOURCE_ICONS[field]?.startsWith('data:image/'), field);
}
assert.ok(RESOURCE_ICONS.diamond?.startsWith('data:image/png;base64,'), 'diamond icon comes from battle capture');
for (const screen of ['character', 'skill', 'equipment', 'companion', 'adventure', 'shop']) {
  assert.ok(SCREEN_ICONS[screen]?.startsWith('data:image/png;base64,'), screen);
}
const answer = {
  resources: catalogue.map((row) => ({ ...row, value: null, verified: false })),
  screens: [{ screen: 'soul_weapon', path: ['Combat', 'Equipment: Weapon', 'Soul Weapon'],
    fields: [{ field: 'soul_weapon_equipped', label: 'Weapon', value: 'Vision', seen: 1, verified: true }] },
  { screen: 'dungeon_forest', path: ['Combat', 'Adventure: Dungeon', 'Forest of Circulation'],
    fields: [], observed: true, details: [{ label: 'Étages vus', value: '156–165' }],
    example: { url: '/api/v1/plugins/slayer-legend/examples/dungeon_forest', captured: 1 },
    examples: [{ url: '/api/v1/plugins/slayer-legend/examples/dungeon_forest', captured: 1,
      label: 'Début' }, { url: '/api/v1/plugins/slayer-legend/examples/dungeon_forest_scroll',
      captured: 2, label: 'Après défilement' }] }],
};
const options = [];
const game = gameFeature({ get: async () => answer, refresh() {}, tr: (text) => text }, {
  resourceOptions: [{ type: 'status', label: 'Gold par seconde', value: () => '1/s' }],
});
game.rows(options, 0);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(options[0].key, 'resources');
assert.equal(options.filter((row) => row.type === 'status').length, 25);
assert.equal(options[options.findIndex((row) => row.label === 'Gold par seconde') - 1].label, 'Analyse');
assert.equal(options.find((row) => row.key === 'game-soul_weapon').label, 'Soul Weapon');
assert.equal(options.find((row) => row.key === 'game-state').depth, 1);
assert.equal(options.find((row) => row.key === 'game-path-Equipment').depth, 2);
assert.equal(options.find((row) => row.key === 'game-path-Equipment').icon, SCREEN_ICONS.equipment);
assert.equal(options.find((row) => row.key === 'game-path-Equipment/Weapon').depth, 3);
assert.equal(options.find((row) => row.key === 'game-soul_weapon').depth, 4);
assert.equal(options.find((row) => row.key === 'game-dungeon_forest').label, 'Forest of Circulation');
assert.equal(options.find((row) => row.label === 'Étages vus').value(), '156–165');
assert.equal(options.find((row) => row.label === 'Relevé historique').value(), new Date(1000).toLocaleString());
assert.equal(options.find((row) => row.key === 'capture-dungeon_forest').examples().length, 2);
assert.equal(options.filter((row) => row.label === 'Données').length, 0);
const gold = options.find((row) => row.label === 'Gold');
assert.equal(gold.value(), 'never read');
Object.assign(answer.resources.find((row) => row.field === 'gold'), { value: 0, seen: 1, verified: true });
assert.equal(gold.value(), '0');
Object.assign(answer.resources.find((row) => row.field === 'soul_green'),
  { value: { text: '02.0C' }, seen: 1, verified: true });
Object.assign(answer.resources.find((row) => row.field === 'soul_blue'),
  { value: { text: '0.70C' }, seen: 1, verified: true });
assert.equal(options.find((row) => row.label === 'Âmes vertes').value(), '2.0C');
assert.equal(options.find((row) => row.label === 'Âmes bleues').value(), '0.70C');
answer.screens.push({ screen: 'guild_request', path: ['Combat', 'Adventure: Guild', 'Guild Request'],
  fields: [], observed: true, example: { url: '/api/v1/plugins/slayer-legend/examples/guild_request' } });
game.rows(options, 0);
assert.equal(options.filter((row) => row.key === 'game-guild_request').length, 1);
assert.equal(options.filter((row) => row.label === 'Données').length, 0);
console.log('Resource icons, navigation paths, unknown values and live counter updates: OK');
