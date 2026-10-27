import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import navigationDebug, { ANNOTATIONS, annotationPoint, zonesFor, recognisedScreen } from './page_navigation_debug.js';

const graph = JSON.parse(readFileSync(new URL('./navigation.json', import.meta.url)));
const registry = JSON.parse(readFileSync(new URL('./screen_registry.json', import.meta.url)));
const battle = zonesFor('battle', graph, registry);
assert.ok(battle.some((zone) => zone.id === 'menu_equipment' && zone.kind === 'tap'));
assert.ok(!battle.some((zone) => zone.id === 'better_weapon_toast'));
const equipment = zonesFor('equipment_weapon', graph, registry);
assert.ok(equipment.some((zone) => zone.id === 'scroll' && zone.kind === 'vertical' && zone.conditional));
assert.ok(!equipment.some((zone) => zone.id === 'batch_combine'));

const centreY = (zone) => (zone.rect[1] + zone.rect[3]) / 2;
const fullBattle = zonesFor('battle', graph, registry, { screen: 'battle', plain: true, overlays: [] });
assert.equal(centreY(fullBattle.find((zone) => zone.id === 'preset_arrow')), .444);
const reducedBattle = zonesFor('soul_weapon', graph, registry, {
  screen: 'battle', plain: false, overlays: ['panel', 'equipment_weapon', 'soul_weapon'],
});
assert.equal(centreY(reducedBattle.find((zone) => zone.id === 'preset_arrow')), .355);
assert.ok(!zonesFor('battle_settings', graph, registry, {
  screen: 'battle', plain: false, overlays: ['battle_settings'],
}).some((zone) => zone.id === 'preset_arrow'));

const returnGraph = structuredClone(graph);
returnGraph.screens.equipment_weapon.moves.push({ id: 'combat_close_test', to: 'battle',
  tap: [.5, .18], combat_return: true });
const reducedScan = { screen: 'battle', plain: false, overlays: ['equipment_weapon'], at: Date.now() / 1000 };
assert.ok(zonesFor('equipment_weapon', returnGraph, registry, reducedScan)
  .some((zone) => zone.id === 'combat_close_test' && zone.kind === 'tap'));
assert.ok(!zonesFor('equipment_weapon', returnGraph, registry, { ...reducedScan, plain: true })
  .some((zone) => zone.id === 'combat_close_test'));
assert.ok(!zonesFor('equipment_weapon', returnGraph, registry, { ...reducedScan, overlays: ['equipment_weapon', 'battle_settings'] })
  .some((zone) => zone.id === 'combat_close_test'));
assert.ok(!zonesFor('equipment_weapon', returnGraph, registry)
  .some((zone) => zone.id === 'combat_close_test'));
const at = Date.now() / 1000;
assert.equal(recognisedScreen({ screen: 'battle', overlays: ['equipment_weapon'], at }), 'equipment_weapon');
assert.equal(recognisedScreen({ screen: 'battle', overlays: ['panel'], at }), null);
assert.equal(recognisedScreen({ screen: 'battle', overlays: [], at: at - 20 }), null);
console.log('Navigation debug zones and screen name: OK');

// Exercise the UI with a tiny DOM: annotation gestures must never leak to
// Android, and capture feedback must survive polling and a page reload.
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.attrs = {}; }
  get isConnected() { return this.root || Boolean(this.parent?.isConnected); }
  append(child) { child.parent = this; this.children.push(child); }
  replaceChildren() { for (const child of this.children) child.parent = null; this.children = []; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((item) => item !== this); this.parent = null; }
  setAttribute(key, value) { this.attrs[key] = value; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 100, height: 200 }; }
  setPointerCapture() {}
}
globalThis.document = { createElement: (tag) => new Element(tag) };
let poll;
globalThis.window = { setInterval(fn) { poll = fn; return 1; }, clearInterval() {} };
const all = (node) => [node, ...node.children.flatMap(all)];
const root = new Element('main'); root.root = true;
const status = () => all(root).find((item) => item.attrs.role === 'status')?.textContent;
const buttons = () => all(root).filter((item) => item.tagName === 'button');
const event = (clientX = 30, clientY = 70) => ({ clientX, clientY, pointerId: 1,
  preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } });
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
let archive = { clicks: [] };
let currentScreen = 'battle';
let armedReply;
let armResponse;
let taps;
let nextId = 0;
const posts = [];
const api = {
  layer: root, tr: (text) => text, setting: () => 'on',
  onTap(fn) { taps = fn; return () => { taps = null; }; },
  async get(path) {
    if (path === '/navigation-debug') return { graph, registry };
    if (path === '/trace') return {};
    if (path === '/trace/manual') return archive;
    if (path === '/screen?quick=1') return { scan: { screen: currentScreen, overlays: [], at: Date.now() / 1000 } };
    throw Error(path);
  },
  post(path, body) {
    posts.push({ path, body });
    if (path === '/trace/arm') return new Promise((resolve) => { armedReply = () => resolve(armResponse ?? { armed: true, id: `capture-${++nextId}`, until: Date.now() / 1000 + 30 }); });
    if (path === '/trace') return Promise.resolve({});
    throw Error(path);
  },
};
assert.deepEqual(ANNOTATIONS.map((action) => action.kind), ['navigation', 'forbidden', 'scannable', 'vertical', 'horizontal']);
assert.deepEqual(annotationPoint(event(200, -20), root.getBoundingClientRect()), { x: 1, y: 0 });
let ui = navigationDebug(api);
await flush();
assert.equal(buttons().length, 5);
// Every slider is drawn with two chevrons, without the old rectangle.
const chevron = all(root).find((item) => item.textContent === '⌃');
assert.equal(chevron, undefined, 'battle has no calibrated vertical slider');
buttons()[1].onclick(event()); await flush();
assert.match(status(), /Capture avant…/);
assert.ok(buttons().every((button) => button.disabled));
armedReply(); await flush();
assert.match(status(), /Capture avant enregistrée/);
archive.clicks = [{ id: 'capture-1', kind: 'forbidden', capture_status: 'armed', before_url: '/before' }];
await poll();
assert.match(status(), /Clique sur l’élément/, 'persisted armed capture remains ready for input');
let surface = all(root).find((item) => item.onpointermove);
assert.ok(surface, 'forbidden annotation intercepts input');
const down = event(); surface.onpointerdown(down);
const up = event(); surface.onpointerup(up);
assert.ok(down.stopped && down.prevented && up.stopped && up.prevented);
assert.deepEqual(posts.at(-1), { path: '/trace', body: { x: 0.3, y: 0.35, kind: 'tap' } });
assert.match(status(), /Capture après…/);
archive.clicks = [{ id: 'capture-1', kind: 'forbidden', capture_status: 'complete',
  before_url: '/before', after_url: '/after', tap: { x: .3, y: .35 } }];
await poll();
assert.match(status(), /Déclaration enregistrée/);
assert.deepEqual(all(root).filter((item) => item.tagName === 'a').map((item) => item.href), ['/before', '/after']);
await poll();
assert.match(status(), /Déclaration enregistrée/, 'completion remains visible');
// Drawing a slider sends its extent, and ordinary polling preserves the
// pointer surface so a long drag cannot be interrupted by a refresh.
buttons()[3].onclick(event()); await flush(); armedReply(); await flush();
surface = all(root).find((item) => item.onpointermove);
surface.onpointerdown(event(20, 40));
await poll();
assert.ok(all(root).includes(surface));
surface.onpointermove(event(30, 160));
assert.ok(all(surface).some((item) => item.textContent === '⌃'));
surface.onpointerup(event(30, 160));
assert.deepEqual(posts.at(-1).body, { x: .2, y: .2, kind: 'swipe', end: { x: .3, y: .8 } });
archive.clicks.unshift({ id: 'capture-2', kind: 'vertical', capture_status: 'complete',
  before_url: '/before-2', after_url: '/after-2', tap: posts.at(-1).body });
await poll();
ui.dispose();
assert.equal(root.children.length, 0);
ui = navigationDebug(api); await flush();
assert.match(status(), /Déclaration enregistrée/, 'restores archived declaration after reload');
assert.match(status(), /slider vertical/);
currentScreen = 'equipment_weapon'; await poll();
assert.ok(all(root).some((item) => item.textContent === '⌃'));
assert.ok(all(root).some((item) => item.textContent === '⌄'));
armResponse = { armed: false };
buttons()[0].onclick(event()); await flush(); armedReply(); await flush();
assert.match(status(), /Échec/);
await poll();
assert.match(status(), /Échec/, 'old archived capture must not hide an arm failure');
armResponse = { armed: true, id: 'expired-capture', until: 1 };
buttons()[0].onclick(event()); await flush(); armedReply(); await flush();
await poll();
assert.match(status(), /Capture expirée/);
assert.ok(buttons().every((button) => !button.disabled));
ui.dispose();
console.log('Navigation annotations, consumed gestures and persistent capture feedback: OK');
