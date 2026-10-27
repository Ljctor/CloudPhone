import assert from 'node:assert/strict';
import gameFeature from './page_game.js';
import { soulsParts } from './page_gold.js';
import { shortNumber } from './page_numbers.js';
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
for (const screen of ['quest', 'scroll', 'stage_select', 'weapon', 'black_orb']) {
  const icon = SCREEN_ICONS[screen];
  assert.ok(icon?.startsWith('data:image/png;base64,'), screen);
  const png = Buffer.from(icon.slice(icon.indexOf(',') + 1), 'base64');
  assert.ok(png.length > 1000 && png.subarray(1, 4).toString() === 'PNG', screen);
  assert.ok(png.readUInt32BE(16) >= 24 && png.readUInt32BE(20) >= 24, screen);
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
Object.assign(answer.resources.find((row) => row.field === 'gold'),
  { value: { text: '629,033,368,693,144,910,929', value: 6.290333686931449e20 } });
assert.equal(gold.value(), '629F');
Object.assign(answer.resources.find((row) => row.field === 'cubes'),
  { value: { text: '2,876,335,558', value: 2876335558 } });
assert.equal(options.find((row) => row.label === 'Cubes').value(), '2.88C');
assert.equal(shortNumber('45.9E'), '45.9E');
assert.equal(soulsParts({ green: { rate: 12345.6789 } })[0].text, '12.3A');
answer.screens.push({ screen: 'guild_request', path: ['Combat', 'Adventure: Guild', 'Guild Request'],
  fields: [], observed: true, example: { url: '/api/v1/plugins/slayer-legend/examples/guild_request' } });
game.rows(options, 0);
assert.equal(options.filter((row) => row.key === 'game-guild_request').length, 1);
assert.equal(options.filter((row) => row.label === 'Données').length, 0);
const inventoryAnswer = { resources: [], screens: [
  { screen: 'soul_weapon', path: ['Combat', 'Equipment: Weapon', 'Soul Weapon'], fields: [],
    example: { url: '/examples/soul_weapon' } },
  { screen: 'equipment_accessories', path: ['Combat', 'Equipment: Accessories'], fields: [],
    inventory: { kind: 'accessories', items: [
      { id: 'accessory-grey-4', appearance: 'grey', grade: 4, enhancement: 30,
        displayed_fraction: { numerator: 4, denominator: 5 }, owned: null, equipped: false },
    ] }, details: [{ label: 'Accessoires visibles', value: '+30 à +41' },
      { label: 'Onglet', value: 'Accessories' }] },
  { screen: 'equipment_weapon', path: ['Combat', 'Equipment: Weapon'], fields: [],
    example: { url: '/examples/equipment_weapon', captured: 1 },
    inventory: { kind: 'weapons', items: [
      { id: 'weapon-grey-4', appearance: 'grey', grade: 4, enhancement: 200,
        displayed_fraction: { numerator: 1, denominator: 5 }, owned: null, equipped: false },
      { id: 'weapon-grey-3', appearance: 'grey', grade: 3, enhancement: 200,
        displayed_fraction: { numerator: 0, denominator: 5 }, owned: null, equipped: false },
      { id: 'weapon-gold', appearance: 'gold', grade: null, enhancement: 200,
        displayed_fraction: { numerator: 0, denominator: 5 }, owned: true, equipped: true },
    ] }, details: [{ label: 'Armes visibles', value: 'Grades 4, 3, 2 et 1' },
      { label: 'Niveau affiché sur les armes', value: '+200' }] },
  { screen: 'character_class', path: ['Combat', 'Character: Promotion', 'Class'], fields: [],
    inventory: { kind: 'classes', status: 'never_read' },
    details: [{ label: 'Classes', value: 'never read' }] },
] };
const inventoryOptions = [];
gameFeature({ get: async () => inventoryAnswer, refresh() {}, tr: (value) => value })
  .rows(inventoryOptions, 0);
await new Promise((resolve) => setImmediate(resolve));
const atKey = (key) => inventoryOptions.findIndex((row) => row.key === key);
assert.ok(atKey('game-equipment_weapon') < atKey('game-soul_weapon'));
assert.ok(atKey('game-soul_weapon') < atKey('game-equipment_accessories'));
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_weapon-grey').depth, 4);
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_weapon-weapon-grey-4').value(), '+200 · 1/5');
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_weapon-weapon-grey-3').value(), '+200 · 0/5');
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_weapon-weapon-gold').value(), '+200 · 0/5 · Équipé');
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_accessories-accessory-grey-4').value(), '+30 · 4/5');
assert.equal(inventoryOptions.find((row) => row.key === 'inventory-equipment_weapon-date').value(), new Date(1000).toLocaleString());
assert.equal(inventoryOptions.find((row) => row.label === 'Classes').value(), 'never read');
assert.equal(inventoryOptions.find((row) => row.label === 'Classes').muted(), true);
assert.equal(inventoryOptions.filter((row) => row.label === 'Classes').length, 1);
assert.equal(inventoryOptions.filter((row) => row.label === 'Armes visibles').length, 0);
assert.equal(inventoryOptions.filter((row) => row.label === 'Accessoires visibles').length, 0);
assert.equal(inventoryOptions.filter((row) => row.type === 'section' && row.key?.startsWith('inventory-')).length, 3);
const inventoryCatalogue = JSON.parse(await readFile(new URL('./screen_inventory.json', import.meta.url)));
assert.equal(inventoryCatalogue.equipment_weapon.items.length, 25);
assert.equal(inventoryCatalogue.equipment_accessories.items.length, 25);
const catalogueAnswer = { resources: [], screens: ['equipment_weapon', 'equipment_accessories'].map((screen) => ({
  screen, path: screen === 'equipment_weapon' ? ['Combat', 'Equipment: Weapon'] :
    ['Combat', 'Equipment: Accessories'], fields: [], inventory: inventoryCatalogue[screen],
})) };
catalogueAnswer.screens.push({ screen: 'character_promotion', path: ['Combat', 'Character: Promotion'],
  fields: [], inventory: inventoryCatalogue.character_promotion,
  details: [{ label: 'Promotions observées', value: '18 rangs' },
    { label: 'Infinaut', value: 'Challenge · Recommended Lv.2400' }] });
const catalogueOptions = [];
gameFeature({ get: async () => catalogueAnswer, refresh() {}, tr: (value) => value })
  .rows(catalogueOptions, 0);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(catalogueOptions.filter((row) => row.key?.startsWith('inventory-equipment_') &&
  row.type === 'section').length, 14);
assert.equal(catalogueOptions.filter((row) => row.key?.startsWith('inventory-equipment_') &&
  row.type === 'status').length, 52);
assert.equal(catalogueOptions.find((row) => row.key === 'inventory-equipment_accessories-accessory-red-grade-3').value(), '+47 · 24/5');
assert.equal(catalogueOptions.find((row) => row.key === 'inventory-character_promotion-selected').value(), 'Blue Abyss');
assert.equal(catalogueOptions.find((row) => row.key === 'inventory-character_promotion-Infinaut').value(),
  'Défi · Recommended Lv.2400');
assert.equal(catalogueOptions.filter((row) => row.key?.startsWith('inventory-character_promotion-')).length, 20);
assert.equal(catalogueOptions.filter((row) => row.label === 'Promotions observées').length, 0);
assert.equal(catalogueOptions.filter((row) => row.label === 'Infinaut').length, 1);
const menuAnswer = { resources: [], screens: [
  { screen: 'skill', path: ['Combat', 'Skill panel'], fields: [], example: { url: '/skill' } },
  { screen: 'quest_daily', path: ['Combat', 'Quest panel: Daily'], fields: [], example: { url: '/quest' } },
  { screen: 'stage_select', path: ['Combat', 'Select Region'], fields: [], example: { url: '/region' } },
  { screen: 'equipment_weapon', path: ['Combat', 'Equipment: Weapon'], fields: [], example: { url: '/weapon' } },
  { screen: 'equipment_accessories', path: ['Combat', 'Equipment: Accessories'], fields: [], example: { url: '/accessories' } },
  { screen: 'black_orb', path: ['Combat', 'Equipment: Accessories', 'Black Orb'], fields: [], example: { url: '/orb' } },
  { screen: 'scroll', label: 'Scroll', path: ['Combat', 'Scroll'], fields: [], inventory: { status: 'never_read' } },
] };
const menuOptions = [];
gameFeature({ get: async () => menuAnswer, refresh() {}, tr: (value) => value }).rows(menuOptions, 0);
await new Promise((resolve) => setImmediate(resolve));
for (const [key, label, depth, icon] of [
  ['game-skill', 'Skill', 2, SCREEN_ICONS.skill],
  ['game-path-Quest', 'Quest', 2, SCREEN_ICONS.quest],
  ['game-stage_select', 'Select Region', 2, SCREEN_ICONS.stage_select],
  ['game-equipment_weapon', 'Weapon', 3, SCREEN_ICONS.weapon],
  ['game-black_orb', 'Black Orb', 4, SCREEN_ICONS.black_orb],
  ['game-scroll', 'Scroll', 2, SCREEN_ICONS.scroll],
]) {
  const row = menuOptions.find((item) => item.key === key);
  assert.equal(row?.label, label, key);
  assert.equal(row.depth, depth, key);
  assert.equal(row.icon, icon, key);
}
assert.equal(menuOptions.find((row) => row.key === 'game-equipment_accessories').depth, 3);
assert.equal(menuOptions.find((row) => row.key === 'inventory-scroll-unread').value(), 'never read');
console.log('Resource icons, nested inventory, unknown values and live counter updates: OK');
