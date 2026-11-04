import assert from 'node:assert/strict';
import gameFeature from './page_game.js';
import { soulsParts, measureResourceRate } from './page_gold.js';
import { freshnessColour } from './page_freshness.js';
import { shortNumber } from './page_numbers.js';
import { RESOURCE_ICONS } from './page_resources.js';
import { SCREEN_ICONS } from './page_screen_icons.js';
import { RATES } from './page_icons.js';
import { readFile } from 'node:fs/promises';

assert.equal(freshnessColour(0), 'rgb(255, 255, 255)');
assert.equal(freshnessColour(300), 'rgb(215, 238, 255)');
assert.equal(freshnessColour(600), 'rgb(175, 221, 255)');
assert.equal(freshnessColour(900), freshnessColour(600));
assert.equal(freshnessColour(-10), freshnessColour(0));

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
const inventoryCatalogue = JSON.parse(await readFile(new URL('./screen_inventory.json', import.meta.url)));
const snapshots = JSON.parse(await readFile(new URL('./screen_snapshots.json', import.meta.url)));
const world = JSON.parse(await readFile(new URL('./screen_snapshots_world.json', import.meta.url)));
const answer = {
  resources: catalogue.map((row) => ({ ...row, value: null, verified: false })),
  screens: Object.entries(snapshots).map(([screen, details]) => ({ screen, label: screen,
    path: ['A menu path that must not create a group'], fields: [], details,
    inventory: inventoryCatalogue[screen],
    example: { url: `/examples/${screen}`, captured: 1 },
    examples: [{ url: `/examples/${screen}`, captured: 1 }],
  })),
};
answer.screens.push({ screen: 'character_class', fields: [], inventory: inventoryCatalogue.character_class ?? { kind: 'classes', status: 'never_read' } });
answer.screens.push({ screen: 'battle', fields: [
  { field: 'stage', label: 'Stage actuel', value: 970, shown: 'number' },
  { field: 'highest', label: 'Stage le plus haut atteint', value: 990, shown: 'lower_bound', seen: 1 },
  { field: 'progress', label: 'Progression du stage', value: .4, shown: 'percent' },
  { field: 'preset', label: 'Préréglage de combat', value: 'IV', shown: 'text' },
] });
for (const screen of ['dungeon_forest', 'dungeon_training']) answer.screens.push({ screen,
  fields: [], details: world[screen], example: { url: `/examples/${screen}`, captured: 1 },
  examples: [{ url: `/examples/${screen}_scroll_1`, captured: 2 }],
});
answer.screens.find((row) => row.screen === 'soul_weapon').fields = [
  { field: 'soul_weapon_selected', label: 'Arme sélectionnée', value: 'Ambition' },
  { field: 'soul_weapon_equipped', label: 'Soul Weapon équipée', value: 'Ambition' },
  { field: 'soul_weapon_variant', label: 'Variante de gravure', value: 'Gold-maxed' },
];
const options = [];
const game = gameFeature({ get: async () => answer, refresh() {}, tr: (text) => text }, {
  resourceOptions: [{ type: 'status', label: 'Gold par seconde', value: () => '1/s' }],
  displayOptions: [{ type: 'section', key: 'display-rates', label: 'Débits', icon: RATES },
    { type: 'choice', key: 'goldOverlay', label: 'Gold/h' }],
});
game.rows(options, 0);
await new Promise((resolve) => setImmediate(resolve));
const categories = options.filter((row) => row.type === 'section' && row.key?.startsWith('progression-'));
assert.deepEqual(categories.map((row) => row.label), ['Vue d’ensemble', 'Enhance - Growing Knowledge', 'Growth - Latent Power', 'Companions', 'Beasts',
  'Weapons', 'Soul Weapons', 'Accessories', 'Classes', 'Black Orb', 'Spirit', 'Familiars', 'Skills',
  'Constellations', 'Memory Tree', 'Relics', 'Summon']);
assert.ok(categories.every((row) => row.depth === 2));
assert.ok(!options.some((row) => row.type === 'section' && (row.depth > 2 && row.key !== 'display-rates' || /Equipment|Adventure|A menu path/.test(row.label))));
assert.equal(options.filter((row) => row.key === 'game-state').length, 1);
assert.equal(options.filter((row) => row.key === 'overlay').length, 1);
assert.equal(options.find((row) => row.key === 'display-rates').depth, 2);
assert.ok(!options.some((row) => row.type === 'capture'), 'progression never offers full-screen capture previews');
const row = (key) => options.find((option) => option.key === key);
assert.equal(row('progression-level').value(), '1941');
assert.equal(row('progression-highest').value(), '> 989');
assert.equal(row('progression-foc').value(), '> 161');
assert.equal(row('progression-cave').value(), '> 844');
assert.equal(row('progression-foc').timestamp(), new Date(2000).toLocaleString([], { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }));
assert.equal(row('progression-cave').timestamp(), new Date(1000).toLocaleString([], { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }));
assert.equal(row('progression-promotion').value(), '≥ Blue Abyss');
answer.screens.find((screen) => screen.screen === 'character_promotion').inventory.selected = 'Infinaut';
assert.equal(row('progression-promotion').value(), '≥ Blue Abyss', 'a selected promotion never proves completion');
for (const label of ['Arme sélectionnée', 'Soul Weapon équipée', 'Variante de gravure', 'Stage actuel',
  'Progression du stage', 'Préréglage de combat', 'Preset sélectionné', 'Onglet', 'Promotion sélectionnée', 'Promotion affichée'])
  assert.ok(!options.some((option) => option.label === label || option.label?.startsWith(label + ' ·')), label);
assert.ok(!options.some((option) => option.key?.endsWith('-featured')), 'equipped-item presentation is not account progression');
assert.equal(row('inventory-equipment_weapon-observed').rows()[0].cells[0].value, '+200 · 0/5', 'observed item data survives without claiming it is currently equipped');
const weapons = row('inventory-equipment_weapon-rarities');
assert.deepEqual(weapons.rows().map((entry) => entry.label), ['Mythic', 'Legendary', 'Epic']);
assert.ok(weapons.caption().includes('historique'));
assert.equal(row('inventory-character_class-rarities').rows().length, 3);
assert.equal(row('inventory-character_promotion-Infinaut').value(), 'Défi · Recommended Lv.2400');
assert.ok(options.some((option) => option.label === 'Collection'), 'dated account collection measurements survive');
assert.ok(options.some((option) => option.label === 'Relax · Owned'), 'historical weapon details keep their object identity');
assert.ok(options.find((option) => option.label === 'Relax · Owned').title().includes('historique'));
assert.ok(!options.some((option) => option.label?.includes('Capture d’exemple')), 'history provenance is in tooltips and dated timestamps');
const relics = row('inventory-equipment_relic-relics');
assert.equal(relics.rows().flatMap((entry) => entry.cells).length, 12);
assert.ok(relics.rows()[0].cells[0].image, 'real item crops remain available after full captures are hidden');
const gold = options.find((option) => option.label === 'Gold');
assert.equal(gold.value(), 'never read'); assert.equal(gold.timestamp(), ''); assert.equal(gold.color(), '#8a919c');
Object.assign(answer.resources.find((entry) => entry.field === 'gold'), { value: 0, seen: 1 });
assert.equal(gold.value(), '0');
assert.equal(gold.timestamp(), new Date(1000).toLocaleString([], { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }));
assert.equal(gold.color(), freshnessColour(600));
const originalNow = Date.now; Date.now = () => 301000;
assert.equal(gold.color(), freshnessColour(300)); Date.now = originalNow;
Object.assign(answer.resources.find((entry) => entry.field === 'cubes'), { value: { text: '2,876,335,558', value: 2876335558 } });
assert.equal(options.find((option) => option.label === 'Cubes').value(), '2,876,335,558');
const forest = answer.screens.find((screen) => screen.screen === 'dungeon_forest');
forest.details = [{ label: 'Previous Entry History', value: '999' }, { label: 'Niveaux visibles', value: '990 à 999' }];
assert.equal(row('progression-foc').value(), 'never read', 'visible choices and previous entry never prove CLEAR');
answer.screens.find((screen) => screen.screen === 'character_promotion').inventory.ranks = [];
assert.equal(row('progression-promotion').value(), 'never read');
assert.equal(shortNumber('45.9E'), '45.9E');
assert.equal(soulsParts({ green: { rate: 12345.6789 } })[0].text, '44.4B/h');
assert.equal(soulsParts({ white: { rate: 1 } }).length, 0);
const first = measureResourceRate(null, { value: { value: 100 }, seen: 1000, verified: true });
assert.equal(measureResourceRate(first, { value: { value: 112 }, seen: 1060, verified: true }).hourly, 720);
assert.equal(measureResourceRate(first, { value: { value: 95 }, seen: 1060, verified: true }).hourly, null);
console.log('Flat account progression, dated CLEAR bounds, no selection/full captures, preserved inventories and resources: OK');
