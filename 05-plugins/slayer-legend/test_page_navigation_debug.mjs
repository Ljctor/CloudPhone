import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { zonesFor, recognisedScreen } from './page_navigation_debug.js';

const graph = JSON.parse(readFileSync(new URL('./navigation.json', import.meta.url)));
const registry = JSON.parse(readFileSync(new URL('./screen_registry.json', import.meta.url)));
const battle = zonesFor('battle', graph, registry);
assert.ok(battle.some((zone) => zone.id === 'menu_equipment' && zone.kind === 'tap'));
assert.ok(!battle.some((zone) => zone.id === 'better_weapon_toast'));
const equipment = zonesFor('equipment_weapon', graph, registry);
assert.ok(equipment.some((zone) => zone.id === 'scroll' && zone.kind === 'vertical' && zone.conditional));
assert.ok(!equipment.some((zone) => zone.id === 'batch_combine'));
const at = Date.now() / 1000;
assert.equal(recognisedScreen({ screen: 'battle', overlays: ['equipment_weapon'], at }), 'equipment_weapon');
assert.equal(recognisedScreen({ screen: 'battle', overlays: ['panel'], at }), null);
assert.equal(recognisedScreen({ screen: 'battle', overlays: [], at: at - 20 }), null);
console.log('Navigation debug zones and screen name: OK');
