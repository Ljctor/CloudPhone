import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import trace from './page_trace.js';
import navigationDebug, { ANNOTATIONS, annotationPoint, floatingDebugPanel, zonesFor, recognisedScreen } from './page_navigation_debug.js';

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
const buttons = () => all(root).filter((item) => item.tagName === 'button' && !('data-debug-toggle' in item.attrs));
const event = (clientX = 30, clientY = 70) => ({ clientX, clientY, pointerId: 1,
  preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } });
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
let archive = { clicks: [] };
let currentScreen = 'battle';
let armedReply;
let armResponse;
const tapListeners = new Set();
let traceTaps = 'on';
let traceResponse = { ok: true, status: 202, body: { queued: true } };
let nextId = 0;
const posts = [];
const api = {
  layer: root, tr: (text) => text, setting: (key) => key === 'traceTaps' ? traceTaps : 'on',
  onTap(fn) { tapListeners.add(fn); return () => tapListeners.delete(fn); },
  async get(path) {
    if (path === '/navigation-debug') return { graph, registry };
    if (path === '/trace') return {};
    if (path === '/trace/manual') return archive;
    if (path === '/screen?quick=1') return { scan: { screen: currentScreen, overlays: [], at: Date.now() / 1000 } };
    throw Error(path);
  },
  post(path, body) {
    posts.push({ path, body });
    if (path === '/trace/arm') return new Promise((resolve) => { armedReply = () => resolve(armResponse ?? { ok: true, status: 200, body: { armed: true, id: `capture-${++nextId}`, seconds: 30 } }); });
    if (path === '/trace') return Promise.resolve(traceResponse);
    if (path === '/trace/cancel') return Promise.resolve({ ok: true, status: 200, body: { cancelled: true } });
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
assert.equal(buttons().length, 1, 'large declaration panel hides immediately during arming');
assert.equal(buttons()[0].textContent, 'Annuler');
assert.ok(buttons()[0].disabled);
armedReply(); await flush();
assert.match(status(), /Capture avant enregistrée/);
archive.clicks = [{ id: 'capture-1', kind: 'forbidden', capture_status: 'armed', before_url: '/before' }];
await poll();
assert.match(status(), /Clique sur l’élément/, 'persisted armed capture remains ready for input');
let surface = all(root).find((item) => 'data-annotation-surface' in item.attrs);
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
surface = all(root).find((item) => 'data-annotation-surface' in item.attrs);
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
const equipmentSlider = all(root).find((item) => item.textContent === '⌃').parent;
assert.match(equipmentSlider.style.cssText, /#168bff/);
assert.match(equipmentSlider.style.cssText, /border:/);
assert.match(equipmentSlider.style.cssText, /background:/);
armResponse = { ok: false, status: 409, body: { error: 'game not visible' } };
buttons()[0].onclick(event()); await flush(); armedReply(); await flush();
assert.match(status(), /Échec/);
await poll();
assert.match(status(), /Échec/, 'old archived capture must not hide an arm failure');
armResponse = { ok: true, status: 200, body: { armed: true, id: 'expired-capture', until: 1 } };
buttons()[0].onclick(event()); await flush(); armedReply(); await flush();
await poll();
assert.match(status(), /Capture expirée/);
assert.ok(buttons().every((button) => !button.disabled));
ui.dispose();
// Run both real onTap consumers with the gateway API's actual response
// envelope. Navigation must pass through Android's input surface and submit
// exactly once, including when background trace recording is disabled.
archive = { clicks: [] };
armResponse = undefined;
ui = navigationDebug(api);
const traceUi = trace(api);
await flush();
for (const setting of ['on', 'off']) {
  traceTaps = setting;
  buttons()[0].onclick(event()); await flush(); armedReply(); await flush();
  assert.match(status(), /Clique sur l’élément/);
  assert.ok(!all(root).some((item) => 'data-annotation-surface' in item.attrs), 'navigation keeps Android input available');
  const before = posts.length;
  const tap = { x: .4, y: .6, kind: 'tap' };
  for (const listener of tapListeners) listener(tap);
  await flush();
  assert.deepEqual(posts.slice(before), [{ path: '/trace', body: tap }]);
  assert.match(status(), /Capture après…/);
  archive.clicks.unshift({ id: `capture-${nextId}`, kind: 'navigation', capture_status: 'complete',
    before_url: '/before', after_url: '/after', tap });
  await poll();
  assert.match(status(), /Déclaration enregistrée/);
}
// A rejected annotation POST is returned as a resolved HTTP envelope by
// plugins.ts; it must leave saving state and expose the failure.
buttons()[2].onclick(event()); await flush(); armedReply(); await flush();
traceResponse = { ok: false, status: 503, body: { error: 'storage unavailable' } };
surface = all(root).find((item) => 'data-annotation-surface' in item.attrs);
surface.onpointerdown(event()); surface.onpointerup(event());
await flush();
assert.match(status(), /Échec/);
traceUi.dispose();
ui.dispose();
assert.equal(tapListeners.size, 0);
archive = { clicks: [] };
traceResponse = { ok: true, status: 202, body: { queued: true } };
ui = navigationDebug(api); await flush();
for (const kind of ['navigation', 'forbidden', 'vertical']) {
  buttons()[ANNOTATIONS.findIndex((action) => action.kind === kind)].onclick(event());
  await flush(); armedReply(); await flush();
  const compact = all(root).find((item) => item.attrs['data-capture-layout'] === 'compact');
  assert.ok(compact);
  assert.match(compact.style.cssText, /pointer-events:none/);
  assert.equal(buttons().length, 1, 'only the small cancel control remains while armed');
  assert.equal(buttons()[0].textContent, 'Annuler');
  assert.match(buttons()[0].style.cssText, /pointer-events:auto/);
  assert.ok(!all(compact).some((item) => item.tagName === 'a'), 'capture links cannot cover game targets');
  const id = `capture-${nextId}`;
  buttons()[0].onclick(event()); await flush();
  assert.deepEqual(posts.at(-1), { path: '/trace/cancel', body: { id } });
  assert.match(status(), /Capture annulée/);
  assert.equal(buttons().length, 5, 'cancel returns the action panel');
  await poll();
  assert.match(status(), /Capture annulée/, 'polling cannot restore a cancelled declaration');
}
ui.dispose();
archive = { clicks: [{ id: 'cancelled-reload', kind: 'navigation', capture_status: 'cancelled', before_url: '/before' }] };
ui = navigationDebug(api); await flush();
assert.match(status(), /Capture annulée/, 'reloading a cancelled declaration restores its final status');
assert.equal(buttons().length, 5);
await poll();
assert.match(status(), /Capture annulée/);
ui.dispose();
// Drag and fold the actual armed panel without rebuilding the input
// surface or sending a declaration. Polling retains both panel choices.
archive = { clicks: [] };
ui = navigationDebug(api); await flush();
buttons()[1].onclick(event()); await flush(); armedReply(); await flush();
const armedSurface = all(root).find((item) => 'data-annotation-surface' in item.attrs);
const debugPanel = () => all(root).find((item) => 'data-debug-panel' in item.attrs);
const handle = () => all(root).find((item) => 'data-debug-drag-handle' in item.attrs);
const toggle = () => all(root).find((item) => 'data-debug-toggle' in item.attrs);
const postsBeforePanelGesture = posts.length;
const dragDown = event(10, 10); handle().onpointerdown(dragDown);
const dragMove = event(40, 60); handle().onpointermove(dragMove);
await poll();
const dragUp = event(40, 60); handle().onpointerup(dragUp);
for (const gesture of [dragDown, dragMove, dragUp]) assert.ok(gesture.prevented && gesture.stopped);
assert.ok(all(root).includes(armedSurface));
toggle().onclick(event());
assert.equal(debugPanel().attrs['data-debug-minimised'], 'true');
assert.equal(toggle().attrs['aria-expanded'], 'false');
await poll();
assert.equal(debugPanel().attrs['data-debug-minimised'], 'true');
assert.ok(all(root).includes(armedSurface), 'folding keeps the annotation surface intact');
assert.equal(posts.length, postsBeforePanelGesture, 'panel drag and fold never submit an annotation');
toggle().onclick(event());
assert.equal(debugPanel().attrs['data-debug-minimised'], 'false');
buttons()[0].onclick(event()); await flush();
ui.dispose();

// Use measured panel sizes to verify both-axis movement, clamping on
// resize, and retained coordinates across compact/full panel attachment.
let viewportSize = { left: 0, top: 0, width: 720, height: 1000 };
const viewport = new Element('div');
viewport.getBoundingClientRect = () => viewportSize;
const floating = floatingDebugPanel(viewport, (event) => { event.preventDefault(); event.stopPropagation(); });
const attach = (compact = false) => {
  const panel = new Element('div');
  panel.getBoundingClientRect = () => ({ width: panel.style.width === 'auto' ? 100 : 380,
    height: panel.style.width === 'auto' ? 30 : 180 });
  const content = new Element('div');
  floating.attach(panel, content, compact, (value) => value);
  return { panel, content, header: panel.children[0], toggle: panel.children[0].children[1] };
};
let floatingUi = attach();
const originalX = parseFloat(floatingUi.panel.style.left);
const originalY = parseFloat(floatingUi.panel.style.top);
floatingUi.header.onpointerdown(event(20, 20));
floatingUi.header.onpointermove(event(120, -230));
floatingUi.header.onpointerup(event(120, -230));
assert.equal(parseFloat(floatingUi.panel.style.left), originalX + 100);
assert.equal(parseFloat(floatingUi.panel.style.top), originalY - 250);
floatingUi.toggle.onclick(event());
assert.equal(floatingUi.content.style.display, 'none');
const retained = { left: floatingUi.panel.style.left, top: floatingUi.panel.style.top };
floatingUi = attach(true);
assert.equal(floatingUi.panel.attrs['data-debug-minimised'], 'true');
assert.equal(floatingUi.panel.style.left, retained.left);
assert.equal(floatingUi.panel.style.top, retained.top);
floatingUi.header.onpointerdown(event());
floatingUi.header.onpointermove(event(3000, 3000));
floatingUi.header.onpointercancel(event(3000, 3000));
assert.equal(floating.dragging, false);
assert.equal(floatingUi.panel.style.left, '620px');
assert.equal(floatingUi.panel.style.top, '970px');
viewportSize = { ...viewportSize, width: 200, height: 300 };
floating.clamp();
assert.equal(floatingUi.panel.style.left, '100px');
assert.equal(floatingUi.panel.style.top, '270px');
floatingUi.toggle.onclick(event());
assert.equal(floatingUi.panel.style.left, '0px');
assert.equal(floatingUi.panel.style.top, '120px');
console.log('Navigation annotations, floating panel gestures and persistent capture feedback: OK');
