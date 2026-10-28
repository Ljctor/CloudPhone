import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import trace from './page_trace.js';
import capturePreview, { archivedScreen } from './page_navigation_preview.js';
import navigationDebug, { ANNOTATIONS, annotationPoint, floatingDebugPanel, landmarksFor, zonesFor, recognisedScreen } from './page_navigation_debug.js';

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
assert.equal(centreY(fullBattle.find((zone) => zone.id === 'preset_arrow')), 462.5 / 1040);
const reducedBattle = zonesFor('soul_weapon', graph, registry, {
  screen: 'battle', plain: false, overlays: ['panel', 'equipment_weapon', 'soul_weapon'],
});
assert.ok(Math.abs(centreY(reducedBattle.find((zone) => zone.id === 'preset_arrow')) - 553 / 1560) < 1e-12);
const genericPanelScan = { screen: 'battle', plain: false, overlays: ['panel'] };
assert.ok(zonesFor('battle', graph, registry, genericPanelScan)
  .some((zone) => zone.id === 'preset_arrow'), 'every normal minimised bottom panel keeps the arrow');
for (const [fixture, zones] of [['battle_arrow_full', fullBattle], ['battle_arrow_minimized', reducedBattle]]) {
  const lines = readFileSync(new URL(`./fixtures/${fixture}.txt`, import.meta.url), 'utf8')
    .split('\n').filter((line) => line && !line.startsWith('#'));
  const [width, height, left, top, cropWidth] = lines[0].split(' ').map(Number);
  const pixels = Buffer.from(lines.slice(1).join(''), 'hex');
  const arrow = zones.find((zone) => zone.id === 'preset_arrow');
  const centreX = Math.round((arrow.rect[0] + arrow.rect[2]) * width / 2);
  const centreY = Math.round((arrow.rect[1] + arrow.rect[3]) * height / 2);
  const index = ((centreY - top) * cropWidth + centreX - left) * 3;
  const rgb = [...pixels.subarray(index, index + 3)];
  assert.equal(rgb.length, 3);
  assert.ok(Math.max(...rgb) - Math.min(...rgb) < 10 && Math.min(...rgb) > 65,
    `${fixture}: zone centre falls on the actual grey arrow`);
  assert.ok(arrow.rect[0] > .95 && arrow.rect[2] < 1 && arrow.rect[3] < .5,
    'side arrow stays away from the top menu and other controls');
}
for (const trackedRect of [null, [.1, .1, .2, .2]]) {
  const trackedArrow = zonesFor('battle', graph, registry,
    { screen: 'battle', plain: true, overlays: [] }, new Map([['preset_arrow', trackedRect]]))
    .find((zone) => zone.id === 'preset_arrow');
  assert.deepEqual(trackedArrow.rect, fullBattle.find((zone) => zone.id === 'preset_arrow').rect,
    'battle animation or scrolling never moves or hides this fixed side control');
}
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
globalThis.document = { createElement: (tag) => new Element(tag), createElementNS: (ns, tag) => new Element(tag) };
const realDateNow = Date.now;
let testNow = realDateNow();
Date.now = () => testNow;
let poll;
globalThis.window = { setInterval(fn) {
  poll = async () => { testNow += 251; await fn(); await flush(); };
  return 1;
}, clearInterval() {} };
const all = (node) => [node, ...node.children.flatMap(all)];
const root = new Element('main'); root.root = true;
const status = () => all(root).find((item) => item.attrs.role === 'status')?.textContent;
const buttons = () => all(root).filter((item) => item.tagName === 'button' && !('data-debug-toggle' in item.attrs) && !('data-screen-evidence' in item.attrs));
const event = (clientX = 30, clientY = 70) => ({ clientX, clientY, pointerId: 1,
  preventDefault() { this.prevented = true; }, stopPropagation() { this.stopped = true; } });
// Yield one event-loop turn so shared request/finally chains settle without
// coupling the fixture to the number of microtasks in the scan cache.
const flush = () => new Promise((resolve) => setImmediate(resolve));
let archive = { clicks: [] };
let currentScreen = 'battle';
let currentScanOverrides = {};
let armedReply;
let armResponse;
const tapListeners = new Set();
let traceTaps = 'on';
let traceResponse = { ok: true, status: 202, body: { queued: true } };
let nextId = 0;
let snapshotResponse = { ok: true, body: { id: 'snapshot-1', kind: 'screen', capture_status: 'complete', before_url: '/snapshot', before_scan: { screen: 'battle', overlays: [] } } };
const posts = [];
const api = {
  layer: root, tr: (text) => text, setting: (key) => key === 'traceTaps' ? traceTaps : 'on',
  onTap(fn) { tapListeners.add(fn); return () => tapListeners.delete(fn); },
  async get(path) {
    if (path === '/navigation-debug') return { graph, registry };
    if (path === '/trace') return {};
    if (path === '/trace/manual') return archive;
    if (path === '/screen?quick=1') return { scan: { screen: currentScreen, plain: true, overlays: [], at: Date.now() / 1000, ...currentScanOverrides } };
    throw Error(path);
  },
  post(path, body) {
    posts.push({ path, body });
    if (path === '/trace/arm') return new Promise((resolve) => { armedReply = () => resolve(armResponse ?? { ok: true, status: 200, body: { armed: true, id: `capture-${++nextId}`, seconds: 30 } }); });
    if (path === '/trace') return Promise.resolve(traceResponse);
    if (path === '/trace/capture') return Promise.resolve(snapshotResponse);
    if (path === '/trace/cancel') return Promise.resolve({ ok: true, status: 200, body: { cancelled: true } });
    throw Error(path);
  },
};
assert.deepEqual(ANNOTATIONS.map((action) => action.kind), ['navigation', 'forbidden', 'scannable', 'vertical', 'horizontal']);
assert.deepEqual(annotationPoint(event(200, -20), root.getBoundingClientRect()), { x: 1, y: 0 });
let ui = navigationDebug(api);
await flush();
assert.equal(buttons().length, 5);
currentScanOverrides = { plain: false, overlays: ['panel'] };
await poll();
assert.equal(all(root).filter((item) => item.title?.startsWith('preset_arrow')).length, 1,
  'generic minimised panel renders its fixed side arrow even without a panel identity');
assert.equal(all(root).filter((item) => item.title?.startsWith('menu_')).length, 0,
  'unidentified panel never borrows Battle menu zones');
assert.deepEqual(zonesFor(null, graph, registry, genericPanelScan).map((zone) => zone.id), ['preset_arrow']);
currentScanOverrides = {};
await poll();
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
const historicalLink = all(root).find((item) => item.attrs['data-capture-open'] === 'before');
const modifiedClick = { ...event(), ctrlKey: true };
historicalLink.onclick(modifiedClick);
assert.equal(modifiedClick.prevented, undefined, 'modified link click keeps access to original image');
historicalLink.onclick(event());
let viewer = all(root).find((item) => 'data-capture-preview' in item.attrs);
assert.ok(viewer);
assert.ok(all(viewer).some((item) => 'data-recorded-tap' in item.attrs));
assert.ok(all(viewer).some((item) => item.textContent?.includes('Écran historique non identifié')));
assert.ok(!all(viewer).some((item) => item.title === 'menu_equipment'), 'unknown historical screens cannot borrow live battle zones');
assert.equal(all(viewer).find((item) => item.attrs['data-capture-raw'] === 'before').href, '/before');
all(viewer).find((item) => item.textContent === 'Fermer').onclick(event());
assert.ok(!all(root).some((item) => 'data-capture-preview' in item.attrs));

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
surface.onpointerdown(event(10, 20)); surface.onpointerup(event(40, 80));
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
// Scannable declarations consume a corner-to-corner drag, never a tap.
archive = { clicks: [] };
traceResponse = { ok: true, status: 202, body: { queued: true } };
ui = navigationDebug(api); await flush();
buttons()[2].onclick(event()); await flush(); armedReply(); await flush();
surface = all(root).find((item) => 'data-annotation-surface' in item.attrs);
const beforeRectangle = posts.length;
surface.onpointerdown(event(80, 160)); surface.onpointerup(event(80, 160));
assert.equal(posts.length, beforeRectangle, 'a click cannot declare a scannable rectangle');
const rectangleDown = event(80, 160); surface.onpointerdown(rectangleDown);
const rectangleMove = event(20, 40); surface.onpointermove(rectangleMove);
assert.ok(all(surface).some((item) => item.style.cssText?.includes('#52e99a')), 'green drag preview');
const rectangleUp = event(20, 40); surface.onpointerup(rectangleUp);
for (const pointer of [rectangleDown, rectangleMove, rectangleUp]) assert.ok(pointer.prevented && pointer.stopped);
assert.deepEqual(posts.at(-1).body, { x: .8, y: .8, kind: 'swipe', end: { x: .2, y: .2 } });
ui.dispose();

// Manual screenshots and classification corrections never synthesize a tap.
archive = { clicks: [] };
currentScreen = 'battle';
const previousBattleRegistry = registry.tree.battle;
registry.tree.battle = { ...previousBattleRegistry, landmarks: [{ id: 'battle_title', rect: [.2, .1, .8, .3] }] };
ui = navigationDebug(api); await flush();
const evidenceButton = (kind) => all(root).find((item) => item.attrs['data-screen-evidence'] === kind);
await poll();
const landmarkBox = all(root).find((item) => item.attrs['data-zone-kind'] === 'detection');
assert.ok(landmarkBox.title.includes('battle_title'));
assert.match(landmarkBox.style.cssText, /#52e99a/);
const beforeSnapshot = posts.length;
await evidenceButton('capture').onclick(event());
assert.deepEqual(posts.slice(beforeSnapshot), [{ path: '/trace/capture', body: {} }]);
assert.ok(all(root).some((item) => item.textContent === 'Écran enregistré'));
assert.ok(all(root).some((item) => item.href === '/snapshot'));
assert.ok(!all(root).some((item) => 'data-annotation-surface' in item.attrs));
await evidenceButton('correction').onclick(event());
const expectedSelect = all(root).find((item) => 'data-expected-screen' in item.attrs);
assert.ok(expectedSelect.children.some((item) => item.value === 'title'));
assert.ok(evidenceButton('submit').disabled, 'a correction requires an explicit expected screen');
expectedSelect.value = 'title'; expectedSelect.onchange();
snapshotResponse = { ok: true, body: { ...snapshotResponse.body, kind: 'screen_correction', expected_screen: 'title' } };
await evidenceButton('submit').onclick(event());
assert.deepEqual(posts.at(-1), { path: '/trace/capture', body: { expected_screen: 'title' } });
assert.ok(all(root).some((item) => item.textContent === 'Erreur de détection enregistrée avec la capture'));
assert.ok(all(root).some((item) => 'data-screen-correction' in item.attrs));
snapshotResponse = { ok: false, body: { error: 'capture unavailable' } };
await evidenceButton('capture').onclick(event());
assert.ok(all(root).some((item) => item.attrs['data-screen-evidence-status'] === '' && item.textContent === 'Échec de l’enregistrement'));
ui.dispose();
if (previousBattleRegistry) registry.tree.battle = previousBattleRegistry;
else delete registry.tree.battle;
const detectionRegistry = { tree: { title: { landmarks: [{ id: 'game_title', rect: [.2, .1, .8, .3] }] } } };
assert.deepEqual(landmarksFor('title', detectionRegistry), [{ id: 'game_title', rect: [.2, .1, .8, .3], kind: 'scannable', detection: true }]);
assert.deepEqual(landmarksFor('unknown', detectionRegistry), []);
assert.ok(!zonesFor('title', graph, detectionRegistry).some((zone) => zone.id === 'game_title'),
  'detection landmarks never become clickable navigation zones');

// The viewer resolves each archived side independently and shares the
// image wrapper with its marker, zones, and swipe arrow.
assert.equal(archivedScreen({ before_scan: { screen: 'battle', overlays: ['panel', 'equipment_weapon'] } }, 'before'), 'equipment_weapon');
assert.equal(archivedScreen({ before_scan: { screen: 'battle', overlays: ['panel'] } }, 'before'), null);
assert.equal(archivedScreen({ before: 'battle' }, 'before'), null, 'legacy identity cannot prove historical overlay geometry');
const previewRecord = { before_url: '/historical-before', after_url: '/historical-after',
  before_scan: { screen: 'battle', overlays: ['equipment_weapon'], plain: false },
  after_scan: { screen: 'battle', overlays: [], plain: true },
  tap: { x: .2, y: .3, kind: 'swipe', end: { x: .7, y: .8 } } };
assert.equal(archivedScreen(previewRecord, 'after'), 'battle');
const drawn = [];
const closeViewer = capturePreview({ layer: root, record: previewRecord, side: 'before',
  zones: [{ id: 'historical-scroll', rect: [.1, .2, .5, .8] }], drawZone: (zone, parent) => drawn.push({ zone, parent }) });
viewer = all(root).find((item) => 'data-capture-preview' in item.attrs);
assert.equal(viewer.attrs.role, 'dialog');
const archivedImage = all(viewer).find((item) => item.tagName === 'img');
assert.equal(archivedImage.src, '/historical-before');
assert.equal(drawn[0].parent, archivedImage.parent);
const recordedMarker = all(viewer).find((item) => 'data-recorded-tap' in item.attrs);
assert.equal(recordedMarker.parent, archivedImage.parent);
assert.match(recordedMarker.style.cssText, /left:20%;top:30%/);
assert.equal(recordedMarker.children.length, 2, 'ring has a horizontal and vertical crosshair');
const swipeLine = all(viewer).find((item) => item.tagName === 'line');
assert.equal(swipeLine.attrs.x1, 20);
assert.equal(swipeLine.attrs.y2, 80);
assert.ok(all(viewer).some((item) => 'data-recorded-swipe-end' in item.attrs));
const viewerPointer = event(); viewer.onpointerdown(viewerPointer);
assert.ok(viewerPointer.stopped, 'viewer gestures never reach Android');
closeViewer();
assert.ok(!all(root).some((item) => 'data-capture-preview' in item.attrs));
const closeRectanglePreview = capturePreview({ layer: root, side: 'after', record: {
  ...previewRecord, kind: 'scannable', tap: { x: .8, y: .8, kind: 'swipe', end: { x: .2, y: .2 } }, rect: [.2, .2, .8, .8] } });
viewer = all(root).find((item) => 'data-capture-preview' in item.attrs);
const rectangleOverlay = all(viewer).find((item) => 'data-recorded-rect' in item.attrs);
assert.ok(rectangleOverlay);
assert.match(rectangleOverlay.style.cssText, /left:20%;top:20%/);
assert.ok(!all(viewer).some((item) => 'data-recorded-swipe' in item.attrs), 'a scannable rectangle is not presented as a game swipe');
closeRectanglePreview();

Date.now = realDateNow;
console.log('Navigation annotations, floating panel gestures and archived previews: OK');
