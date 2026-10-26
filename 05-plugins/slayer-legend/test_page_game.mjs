import assert from 'node:assert/strict';
import gameFeature from './page_game.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { SCREEN_ICONS } from './page_screen_icons.js';
import { readFile } from 'node:fs/promises';

const catalogue = JSON.parse(await readFile(new URL('./resources.json', import.meta.url)));
assert.equal(catalogue.length, 21);
assert.equal(catalogue.findIndex((row) => row.field === 'soul_white'),
  catalogue.findIndex((row) => row.field === 'soul_red') + 1);
for (const field of ['gold', 'emerald', 'soul_green', 'soul_blue', 'soul_red', 'soul_white']) {
  assert.ok(RESOURCE_ICONS[field]?.startsWith('data:image/'), field);
}
assert.ok(RESOURCE_ICONS.diamond?.startsWith('data:image/png;base64,'), 'diamond icon comes from battle capture');
for (const screen of ['character', 'skill', 'equipment', 'companion', 'adventure', 'shop']) {
  assert.ok(SCREEN_ICONS[screen]?.startsWith('data:image/png;base64,'), screen);
}
const answer = {
  resources: catalogue.map((row) => ({ ...row, value: null, verified: false })),
  screens: [{ screen: 'soul_weapon', path: ['Combat', 'Equipment: Weapon', 'Soul Weapon'],
    fields: [{ field: 'soul_weapon_equipped', label: 'Weapon', value: 'Vision', seen: 1, verified: true }] }],
};
const options = [];
const game = gameFeature({ get: async () => answer, refresh() {}, tr: (text) => text }, {
  resourceOptions: [{ type: 'status', label: 'Gold par seconde', value: () => '1/s' }],
});
game.rows(options, 0);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(options[0].key, 'resources');
assert.equal(options.filter((row) => row.type === 'status').length, 23);
assert.equal(options[options.findIndex((row) => row.label === 'Gold par seconde') - 1].label, 'Analyse');
assert.equal(options.find((row) => row.key === 'game-soul_weapon').label, 'Soul Weapon');
assert.equal(options.find((row) => row.key === 'game-state').depth, 1);
assert.equal(options.find((row) => row.key === 'game-path-Equipment').depth, 2);
assert.equal(options.find((row) => row.key === 'game-path-Equipment').icon, SCREEN_ICONS.equipment);
assert.equal(options.find((row) => row.key === 'game-path-Equipment/Weapon').depth, 3);
assert.equal(options.find((row) => row.key === 'game-soul_weapon').depth, 4);
const gold = options.find((row) => row.label === 'Gold');
assert.equal(gold.value(), 'never read');
Object.assign(answer.resources.find((row) => row.field === 'gold'), { value: 0, seen: 1, verified: true });
assert.equal(gold.value(), '0');
console.log('Resource icons, navigation paths, unknown values and live counter updates: OK');
