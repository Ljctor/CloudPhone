import assert from 'node:assert/strict';
import navigationDebug, { visibleDebugZones } from './page_navigation_debug.js';

const roles = [{ kind: 'screen_identifier' }, { kind: 'detection' }, { kind: 'scannable' },
  { kind: 'progression_value', detection: true }, { kind: 'resource_value' }, { kind: 'action' }];
assert.deepEqual(visibleDebugZones(roles, true, false), roles.slice(0, 3));
assert.deepEqual(visibleDebugZones(roles, false, true), roles.slice(3));

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.attrs = {}; }
  get isConnected() { return this.root || Boolean(this.parent?.isConnected); }
  append(child) { child.parent = this; this.children.push(child); }
  replaceChildren() { for (const child of this.children) child.parent = null; this.children = []; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((item) => item !== this); this.parent = null; }
  setAttribute(key, value) { this.attrs[key] = value; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 480, height: 1040 }; }
}
globalThis.document = { createElement: (tag) => new Element(tag), createElementNS: (_, tag) => new Element(tag) };
globalThis.window = { setInterval() { return 1; }, clearInterval() {} };
const all = (node) => [node, ...node.children.flatMap(all)];
const flush = () => new Promise((resolve) => setImmediate(resolve));
const root = new Element('main'); root.root = true;
const settings = {};
const posts = [];
let resolveArm;
const api = {
  layer: root, tr: (value) => value, setting: (key) => settings[key] ?? 'off',
  get: async (path) => {
    if (path === '/navigation-debug') return {
      graph: { screens: { battle: { name: 'Combat Interface', moves: [{ id: 'menu', tap: [.2, .2] }] } } },
      registry: { tree: { battle: { name: 'Combat Interface', landmarks: [{ id: 'identity', rect: [.1, .1, .2, .2] }] } } },
    };
    if (path === '/screen?quick=1') return { scan: { screen: 'battle', plain: true, overlays: [], at: Date.now() / 1000 } };
    return {};
  },
  post: (path, body) => {
    posts.push({ path, body });
    if (path === '/trace/arm') return new Promise((resolve) => { resolveArm = resolve; });
    return Promise.resolve({ ok: true });
  },
};
const ui = navigationDebug(api);
await flush();
for (let mask = 0; mask < 8; mask++) {
  const identification = Boolean(mask & 1), navigation = Boolean(mask & 2), tools = Boolean(mask & 4);
  Object.assign(settings, { screenIdentification: identification ? 'on' : 'off', navigationDebug: navigation ? 'on' : 'off', navigationFeedback: tools ? 'on' : 'off' });
  ui.onSetting('navigationFeedback'); await ui.update(); await flush();
  const nodes = all(root);
  assert.equal(nodes.some((node) => node.textContent === 'Écran : {screen}'), identification, `name mask ${mask}`);
  assert.equal(nodes.some((node) => node.attrs['data-zone-kind'] === 'detection'), identification, `identifier mask ${mask}`);
  assert.equal(nodes.some((node) => node.attrs['data-zone-kind'] === 'navigation'), navigation, `navigation mask ${mask}`);
  assert.equal(nodes.some((node) => node.tagName === 'button' && node.textContent === 'Ajouter un bouton de navigation'), tools, `tools mask ${mask}`);
}
// Turning tools off while the before-capture request is pending must cancel
// its eventual arm, rather than leaving an invisible recording active.
const button = all(root).find((node) => node.tagName === 'button' && node.textContent === 'Ajouter un bouton de navigation');
const arming = button.onclick({ preventDefault() {}, stopPropagation() {} });
settings.navigationFeedback = 'off'; ui.onSetting('navigationFeedback');
resolveArm({ ok: true, body: { id: 'pending-arm', armed: true, seconds: 30 } });
await arming; await flush();
assert.ok(posts.some((item) => item.path === '/trace/cancel' && item.body.id === 'pending-arm'));
assert.equal(posts.some((item) => item.path === '/trace'), false);
ui.dispose();
console.log('Independent identification/navigation/reporting toggles and pending-arm cancellation: OK');
