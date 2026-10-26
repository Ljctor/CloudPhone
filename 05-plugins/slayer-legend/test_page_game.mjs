import assert from 'node:assert/strict';
import gameFeature from './page_game.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { readFile } from 'node:fs/promises';

const catalogue = JSON.parse(await readFile(new URL('./resources.json', import.meta.url)));
assert.equal(catalogue.length, 21);
for (const field of ['gold', 'emerald', 'soul_green', 'soul_blue', 'soul_red', 'soul_white']) {
  assert.ok(RESOURCE_ICONS[field]?.startsWith('data:image/'), field);
}
assert.equal(RESOURCE_ICONS.diamond, undefined, 'unverified game icon must not be invented');
const answer = {
  resources: catalogue.map((row) => ({ ...row, value: null, verified: false })),
  screens: [{ screen: 'soul_weapon', path: ['Combat', 'Equipment: Weapon', 'Soul Weapon'],
    fields: [{ field: 'soul_weapon_equipped', label: 'Weapon', value: 'Vision', seen: 1, verified: true }] }],
};
const options = [];
const game = gameFeature({ get: async () => answer, refresh() {}, tr: (text) => text });
game.rows(options, 0);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(options[0].key, 'resources');
assert.equal(options.filter((row) => row.type === 'status').length, 22);
assert.equal(options.find((row) => row.key === 'game-soul_weapon').label, 'Soul Weapon');
assert.equal(options.find((row) => row.key === 'game-state').depth, 1);
assert.equal(options.find((row) => row.key === 'game-path-Equipment').depth, 2);
assert.equal(options.find((row) => row.key === 'game-path-Equipment/Weapon').depth, 3);
assert.equal(options.find((row) => row.key === 'game-soul_weapon').depth, 4);
const gold = options.find((row) => row.label === 'Gold');
assert.equal(gold.muted(), true);
Object.assign(answer.resources.find((row) => row.field === 'gold'), { value: 0, seen: 1, verified: true });
assert.ok(gold.value()[0].text.startsWith('0 · '));
assert.equal(gold.muted(), false);
console.log('Resource icons, navigation paths, unknown values and live counter updates: OK');
