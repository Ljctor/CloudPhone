import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { inventoryTables } from './page_inventory.js';
const catalogue = JSON.parse(await readFile(new URL('./screen_inventory.json', import.meta.url)));
const weapon = { screen: 'equipment_weapon', inventory: catalogue.equipment_weapon,
  examples: ['equipment_weapon', 'equipment_weapon_scroll_1', 'equipment_weapon_scroll_2']
    .map((name) => ({ url: `/examples/${name}`, captured: 123 })) };
const tables = inventoryTables(weapon);
assert.ok(tables.every((row) => row.type === 'inventory-table'));
const featured = tables.find((table) => table.key.endsWith('-featured')).rows()[0].cells[0];
assert.equal(featured.image.url, '/examples/equipment_weapon_scroll_2');
assert.deepEqual(featured.image.box, [200, 700, 280, 810]);
assert.equal(featured.value, '+200 · 0/5');
const rows = tables.find((table) => table.key.endsWith('-rarities')).rows();
assert.deepEqual(rows.map((row) => row.label), ['Mythic', 'Legendary', 'Epic']);
assert.ok(rows[0].cells.every((cell) => cell.image === null && cell.value === 'never read'));
assert.ok(rows[1].cells.every((cell) => cell.image.url.endsWith('equipment_weapon_scroll_1')));
assert.ok(tables[1].caption().includes('possession actuelle non confirmée'));
weapon.examples = [];
assert.equal(tables[1].rows()[0].cells[0].image, null, 'unavailable private archives do not produce broken invented art');
const spirit = { screen: 'spirit', inventory: { kind: 'spirits', items: [
  { id: 'loar1', name: 'Loar', stars: 2 }, { id: 'loar2', name: 'Loar', stars: 4 },
  { id: 'reserve', name: 'Other', stars: 1, rarity: 'Legendary' },
] } };
const spirits = inventoryTables(spirit);
const partners = spirits.find((table) => table.key.endsWith('-partners')).rows();
assert.deepEqual(partners.map((row) => row.cells.map((cell) => cell.label)), [
  ['Loar', 'Sala', 'Noah'], ['Zappy', 'Mum', 'Todd'], ['Luga', 'Kart', 'Radeon', 'Ark', 'Herb', 'Bo'],
]);
assert.equal(partners[0].cells[0].value, '4 ★');
assert.equal(partners[0].cells[1].value, 'never read');
assert.deepEqual(spirits.find((table) => table.key.endsWith('-reserves')).rows().map((row) => row.label), ['Legendary', 'Epic']);
assert.equal(spirits.find((table) => table.key.endsWith('-reserves')).rows()[0].cells[0].label, 'Other');
const familiars = inventoryTables({ screen: 'familiar', inventory: { kind: 'familiars', items: [
  { name: 'A', stars: 2 }, { name: 'B', stars: 5 }, { name: 'C', stars: null },
  { name: 'D', stars: 3, altar_slot: 1 },
] } });
assert.equal(familiars[0].rows()[0].cells.length, 6);
assert.deepEqual(familiars[1].rows()[0].cells.map((cell) => cell.label), ['B', 'A']);
const relics = inventoryTables({ screen: 'equipment_relic', inventory: { kind: 'relics', items: [
  { name: 'Crit', primary_bonus: { display_text: '+1,234.50%' }, inheritance_bonus: { display_text: '+12.00%' } },
  ...['Other1', 'Other2', 'Other3', 'Other4'].map((name) => ({ name })),
] } });
const relicRows = relics[0].rows();
assert.deepEqual(relicRows[0].cells.map((cell) => cell.label), ['Extra Dmg', 'Crit', 'HP']);
assert.deepEqual(relicRows.map((row) => row.cells.length), [3, 3, 1]);
assert.deepEqual(relicRows[0].cells[1].bonuses, [
  { role: 'primary', display_text: '+1,234.50%' }, { role: 'inheritance', display_text: '+12.00%' },
]);
const orb = { screen: 'black_orb_accessory', inventory: catalogue.black_orb_accessory,
  example: { url: '/examples/black_orb_accessory', captured: 100 } };
const orbCell = inventoryTables(orb)[0].rows()[0].cells[0];
assert.equal(orbCell.label, 'Bracelet of Freedom');
assert.equal(orbCell.image.kind, 'sprite');
assert.equal(orbCell.image.asset, 'BlackAcc_105');
assert.ok(orbCell.image.url.startsWith('data:image/png;base64,'));
assert.equal(orbCell.indicators.element.id, 'wind');
assert.equal(orbCell.indicators.stars, undefined);
assert.equal(orbCell.indicators.awakening, undefined);
assert.equal(orbCell.bonuses[0].display_text, 'Wind Dmg +6,388%');
assert.equal(orbCell.bonuses.length, 5, 'three distinct attribute effects are not summed');
console.log('Inventory order, private capture crops, historical provenance, unknowns and exact bonus roles: OK');

// These are transcribed observations from three archived game captures,
// independent of the renderer and never promoted to current possession.
const relicCatalogue = catalogue.equipment_relic;
assert.equal(relicCatalogue.scope, 'captured_snapshot');
assert.equal(relicCatalogue.verified, false);
assert.equal(relicCatalogue.items.length, 12);
const expectedRelics = [
  ["Giant's Right Hand", 100, 'Extra Dmg + 2200%', '(+616%)'],
  ['Demon Eye of Weakness', 100, 'CRIT Dmg + 400%', '(+112%)'],
  ['Oath of Immortality', 100, 'Extra HP + 1400%', '(+294%)'],
  ['Sacred Tree of Rebirth', 100, 'Extra HP Recovery + 420%', '(+88.2%)'],
  ['Ring of Lightning', 50, 'ATK SPD + 35%', '(+5.6%)'],
  ['Golden Star', 100, 'Monster defeat Gold + 500%', '(+90%)'],
  ['Seal of the Legendary Archer', 100, 'Accuracy rate + 1400', '(+294)'],
  ['Veil of the Night', 100, 'Dodge rate + 700', '(+112)'],
  ['Spark of Eternity', 100, 'Fire Dmg + 300%', '(+69%)'],
  ["Mermaid's Tear", 100, 'Water Dmg + 300%', '(+69%)'],
  ['Eye of the Sky', 100, 'Wind Dmg + 300%', '(+69%)'],
  ['Crown of the Great Mountain', 100, 'Earth Dmg + 300%', '(+78%)'],
];
assert.deepEqual(relicCatalogue.items.map((item) => [item.name, item.level,
  item.primary_bonus.display_text, item.inheritance_bonus.display_text]), expectedRelics);
const registry = JSON.parse(await readFile(new URL('./screen_registry.json', import.meta.url)));
const relicNode = registry.tree.equipment_relic;
const allowed = [relicNode.example, ...relicNode.scroll.flatMap((scroll) => scroll.captures)]
  .map((path) => path.split('/').at(-1));
const relicScreen = { screen: 'equipment_relic', inventory: relicCatalogue,
  examples: [...new Set(relicCatalogue.items.map((item) => item.source.capture))]
    .map((capture) => ({ url: `/examples/${capture.replace(/\.png$/, '')}`, captured: 123 })) };
const actualRelics = inventoryTables(relicScreen)[0].rows();
assert.deepEqual(actualRelics.map((row) => row.cells.length), [3, 3, 3, 3]);
assert.deepEqual(actualRelics[0].cells.map((cell) => cell.label), expectedRelics.slice(0, 3).map((row) => row[0]));
for (const [index, item] of relicCatalogue.items.entries()) {
  assert.equal(item.owned, null);
  assert.equal(item.primary_bonus.raw, item.primary_bonus.display_text);
  assert.equal(item.inheritance_bonus.raw, item.inheritance_bonus.display_text);
  assert.equal(item.raw_bonus_line, `${item.primary_bonus.raw} ${item.inheritance_bonus.raw}`);
  assert.ok(allowed.includes(item.source.capture), item.name);
  assert.ok(item.source.captured > 0);
  const [left, top, right, bottom] = item.source.box;
  assert.ok(left >= 0 && top >= 0 && right > left && bottom > top && right <= item.source.width && bottom <= item.source.height);
  const cell = actualRelics.flatMap((row) => row.cells)[index];
  assert.equal(cell.image.url, `/examples/${item.source.capture.replace(/\.png$/, '')}`);
  assert.deepEqual(cell.bonuses.map((bonus) => [bonus.role, bonus.display_text]), [
    ['primary', expectedRelics[index][2]], ['inheritance', expectedRelics[index][3]],
  ]);
}
console.log('Twelve historical relics: exact names, levels, primary/inheritance text, order and private crop references: OK');

// Clean base art is independent from the archived star/element observations.
let observedOrbs = { screen: 'black_orb', inventory: structuredClone(catalogue.black_orb) };
const blackTables = inventoryTables(observedOrbs, () => observedOrbs);
const blackCells = () => blackTables[0].rows()[0].cells;
assert.deepEqual(blackCells().map((cell) => cell.image.asset),
  ['BlackAcc_105', 'BlackAcc_205', 'BlackAcc_305', 'BlackAcc_405']);
assert.deepEqual(blackCells().map((cell) => cell.indicators.element.id), ['wind', 'earth', 'fire', 'water']);
assert.deepEqual(blackCells().map((cell) => cell.indicators.stars), [undefined, undefined, 2, undefined]);
assert.ok(blackCells().every((cell) => cell.indicators.awakening === undefined));
const cleanFireImage = blackCells()[2].image.url;
observedOrbs.inventory.items[2].stars = 0;
observedOrbs.inventory.items[2].element = null;
assert.equal(blackCells()[2].indicators.stars, 0, 'observed zero is distinct from unread');
assert.equal(blackCells()[2].indicators.element, undefined);
assert.equal(blackCells()[2].image.url, cleanFireImage, 'badges do not modify the base sprite');
observedOrbs.inventory.items[2].stars = null;
observedOrbs.inventory.items[2].sprite.asset = 'unknown-art';
assert.equal(blackCells()[2].indicators.stars, undefined);
assert.equal(blackCells()[2].image, null, 'unknown sprite never falls back to a frozen card');
console.log('Black Orb original sprites and independently observed dynamic badges: OK');
