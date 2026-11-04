import { COLOURS, matchGesture, gestureLabel, screenLabel, battlefieldLabel, inside } from './model.js';
import oralFeedback, { freezeOralContext, oralTransport } from '../page_oral_feedback.js';
import { zoneStyle } from '../page_zone_style.js';

const $ = (id) => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const state = { data: { nodes: [], edges: [], feedback: [] }, nodes: new Map(), current: null,
  outgoing: new Map(), incoming: new Map(), history: [], position: -1, overlay: true, map: false,
  includeTraces: false, search: '', selectedEdge: null, gesture: null, load: 0, feedback: [], loading: false, revision: null };
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};
const svg = (tag, attributes = {}, text) => {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text != null) node.textContent = text;
  return node;
};
const current = () => state.nodes.get(state.current);
const oral = oralFeedback({ transport: oralTransport('/api/oral-feedback'), capture: () => {
  const node = current();
  if (!node) throw Error('Aucune capture sélectionnée.');
  return freezeOralContext({ image: $('screen-image'), layer: $('phone'), svgElement: $('overlay'),
    source: 'review', nodeId: node.id, screen: node.screen, displayName: screenLabel(node),
    regions: node.regions ?? [], enabled: state.overlay,
    state: { selectedEdge: state.selectedEdge, representativeNodeId: node.representativeNodeId, review: node.review },
  });
} });
$('feedback-panel').append(oral.element);
const outgoing = () => state.outgoing.get(state.current) ?? [];
const safeImage = (url) => typeof url === 'string' && url.startsWith('/api/image/') && !url.startsWith('//') ? url : null;
const date = (node) => {
  const stamp = node.at ?? node.captured ?? node.time;
  return Number.isFinite(stamp) && stamp > 0 ? new Date(stamp * 1000).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' }) : '';
};
const reviewText = (node) => {
  const status = node.review?.processingStatus ?? node.review?.status ?? node.review_status;
  return ({ processed: 'Analyse automatique effectuée', ambiguous: 'À examiner par l’agent', rejected: 'Capture inexploitable' })[status] ?? 'Capture enregistrée';
};

function notice(message, error = false) {
  $('notice').hidden = !message;
  $('notice').textContent = message;
  $('notice').classList.toggle('error', error);
}

async function load({ quiet = false } = {}) {
  const ticket = ++state.load;
  state.loading = true;
  $('reload').disabled = true;
  try {
    const response = await fetch('/api/graph', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Chargement impossible (${response.status}).`);
    const data = await response.json();
    if (ticket !== state.load) return;
    state.data = data;
    state.nodes = new Map((data.nodes ?? []).map((node) => [node.id, node]));
    state.outgoing.clear(); state.incoming.clear();
    for (const edge of data.edges ?? []) {
      if (!state.nodes.has(edge.from) || !state.nodes.has(edge.to)) continue;
      for (const [map, id] of [[state.outgoing, edge.from], [state.incoming, edge.to]]) {
        if (!map.has(id)) map.set(id, []);
        map.get(id).push(edge);
      }
    }
    state.feedback = Array.isArray(data.feedback) ? data.feedback : data.feedback?.items ?? [];
    const wanted = new URLSearchParams(location.hash.slice(1)).get('node');
    const initial = state.nodes.get(wanted) ?? current()
      ?? data.nodes.find((node) => node.id === 'screen:battle' && node.image)
      ?? data.nodes.find((node) => node.image && node.screen === 'battle' && state.outgoing.has(node.id))
      ?? data.nodes.find((node) => node.image && state.outgoing.has(node.id))
      ?? data.nodes.find((node) => node.image && node.screen === 'battle')
      ?? data.nodes.find((node) => node.image) ?? data.nodes[0];
    if (!initial) { $('screen-title').textContent = 'Aucune capture disponible'; notice('Les captures enregistrées apparaîtront ici.'); return; }
    if (!quiet) notice('');
    const result = $('feedback-result').textContent;
    visit(initial.id, { remember: !state.current, edge: data.edges.find((edge) => edge.id === state.selectedEdge?.id) ?? null });
    if (quiet) $('feedback-result').textContent = result;
  } catch (error) {
    notice(error.message || 'Impossible de charger la carte. Réessayez avec le bouton Actualiser.', true);
    if (!state.current) $('screen-title').textContent = 'Carte indisponible';
  } finally { if (ticket === state.load) { $('reload').disabled = false; state.loading = false; } }
}

function visit(id, { remember = true, edge = null } = {}) {
  if (!state.nodes.has(id)) return;
  if (remember && id !== state.current) {
    state.history = state.history.slice(0, state.position + 1);
    state.history.push(id); state.position = state.history.length - 1;
  }
  state.current = id; state.selectedEdge = edge;
  const hash = `#node=${encodeURIComponent(id)}`;
  if (location.hash !== hash) history.replaceState(null, '', hash);
  $('feedback-result').textContent = '';
  render();
}

function renderList() {
  const scroll = { top: $('screen-list').scrollTop, left: $('screen-list').scrollLeft };
  const groups = new Map();
  for (const node of state.data.nodes) {
    if (!state.includeTraces && !node.image) continue;
    if (state.search && !`${screenLabel(node)} ${node.screen}`.toLowerCase().includes(state.search)) continue;
    if (!groups.has(node.screen)) groups.set(node.screen, []);
    groups.get(node.screen).push(node);
  }
  const list = $('screen-list'); list.replaceChildren();
  for (const [screen, nodes] of [...groups.entries()].sort((a, b) => screenLabel(a[1][0]).localeCompare(screenLabel(b[1][0]), 'fr'))) {
    const active = current()?.screen === screen;
    const button = element('button', `screen-item${active ? ' active' : ''}`, screenLabel(nodes[0]));
    button.setAttribute('role', 'listitem'); button.setAttribute('aria-current', active ? 'true' : 'false');
    button.addEventListener('click', () => { notice(''); visit(nodes.find((node) => node.source === 'configured' && node.image)?.id ?? nodes.find((node) => node.image && state.outgoing.has(node.id))?.id ?? nodes.find((node) => node.image)?.id ?? nodes[0].id); });
    list.append(button);
  }
  if (!groups.size) list.append(element('p', 'muted', 'Aucun écran ne correspond.'));
  list.scrollTop = scroll.top; list.scrollLeft = scroll.left;
}

function renderCapture() {
  const node = current();
  $('screen-title').textContent = screenLabel(node);
  const field = battlefieldLabel(node);
  $('source-label').textContent = field ? `CHAMP DE BATAILLE · ${field.toUpperCase()}` : reviewText(node).toUpperCase();
  $('capture-date').textContent = [date(node), node.source === 'configured' ? 'Graphe configuré · à vérifier' : reviewText(node)].filter(Boolean).join(' · ');
  const select = $('capture-select'); select.replaceChildren();
  const variants = state.data.nodes.filter((item) => item.screen === node.screen && (item.image || state.includeTraces || item.id === node.id));
  for (const [index, item] of variants.entries()) {
    const type = item.source === 'trace' ? 'Trace sans capture' : item.source === 'configured' ? 'Graphe configuré' : item.source === 'example' ? 'Capture archivée'
      : item.id.endsWith(':before') ? 'Avant le geste' : 'Après le geste';
    const option = element('option', '', `${type}${date(item) ? ` · ${date(item)}` : ` · ${index + 1}`}`);
    option.value = item.id; option.selected = item.id === node.id; select.append(option);
  }
  const image = $('screen-image'), url = safeImage(node.image);
  image.hidden = !url; $('image-empty').hidden = Boolean(url);
  if (url) {
    image.alt = `${screenLabel(node)} — ${date(node) || 'capture enregistrée'}`;
    if (image.getAttribute('src') !== url) image.src = url;
  } else {
    image.removeAttribute('src');
    const canvas = $('thumbnail'), context = canvas.getContext('2d'); context.clearRect(0, 0, 12, 26);
    const pixels = node.thumbnail?.pixels;
    canvas.hidden = !(typeof pixels === 'string' && /^[0-9a-f]{312}$/.test(pixels));
    if (!canvas.hidden) for (let i = 0; i < pixels.length; i++) {
      const value = parseInt(pixels[i], 16) * 17; context.fillStyle = `rgb(${value},${value},${value})`; context.fillRect(i % 12, Math.floor(i / 12), 1, 1);
    }
  }
  $('back').disabled = state.position <= 0;
  $('forward').disabled = state.position >= state.history.length - 1;
  renderOverlay();
}

function renderOverlay() {
  const layer = $('overlay'); layer.replaceChildren(); layer.toggleAttribute('hidden', !state.overlay);
  if (!state.overlay || !current()) return;
  const regions = [...(current().regions ?? [])];
  // Recorded points are useful even when no annotation rectangle was made.
  for (const edge of outgoing()) {
    if (!edge.start) continue;
    const proposal = regions.find((region) => region.id === `edge:${edge.id}`);
    if (regions.some((region) => ['navigation', 'tap'].includes(region.kind) && inside(edge.start, region.rect))) continue;
    const isSwipe = Boolean(edge.end) && edge.kind === 'swipe';
    const kind = edge.annotationKind === 'draggable' ? 'draggable' : isSwipe
      ? Math.abs(edge.end.y - edge.start.y) >= Math.abs(edge.end.x - edge.start.x) ? 'vertical' : 'horizontal' : 'navigation';
    const colour = COLOURS[kind];
    if (isSwipe) {
      const x = edge.start.x * 480, y = edge.start.y * 1040, x2 = edge.end.x * 480, y2 = edge.end.y * 1040;
      layer.append(svg('line', { x1: x, y1: y, x2, y2, stroke: colour, 'stroke-width': 3, 'stroke-dasharray': 'none', opacity: .8 }));
      const angle = Math.atan2(y2 - y, x2 - x), arm = 10;
      layer.append(svg('path', { d: `M ${x2 - Math.cos(angle - .6) * arm} ${y2 - Math.sin(angle - .6) * arm} L ${x2} ${y2} L ${x2 - Math.cos(angle + .6) * arm} ${y2 - Math.sin(angle + .6) * arm}`, fill: 'none', stroke: colour, 'stroke-width': 3 }));
    } else {
      const style = zoneStyle(proposal ?? { user: edge.source === 'manual', conditional: edge.conditional });
      layer.append(svg('circle', { cx: edge.start.x * 480, cy: edge.start.y * 1040, r: 10, stroke: colour, fill: '#ffe10018', 'stroke-width': style.width, opacity: style.opacity, 'stroke-dasharray': style.dash, 'stroke-linecap': style.linecap }));
      if (style.double) layer.append(svg('circle', { cx: edge.start.x * 480, cy: edge.start.y * 1040, r: 7, stroke: colour, fill: 'none', 'stroke-width': 1 }));
    }
  }
  regions.sort((a, b) => Number(Boolean(a.forbidden || a.kind === 'forbidden')) - Number(Boolean(b.forbidden || b.kind === 'forbidden')));
  for (const region of regions) {
    if (!Array.isArray(region.rect) || region.rect.length !== 4 || region.rect.some((v) => !Number.isFinite(v))) continue;
    const [l, t, r, b] = region.rect, forbidden = region.forbidden || region.kind === 'forbidden';
    const style = zoneStyle(region);
    const kind = forbidden ? 'forbidden' : region.kind, colour = COLOURS[kind] ?? '#94a3b8';
    const box = svg('rect', { x: l * 480, y: t * 1040, width: (r - l) * 480, height: (b - t) * 1040,
      rx: 0, fill: `${colour}12`, stroke: colour, 'stroke-width': style.width, opacity: style.opacity,
      'stroke-dasharray': style.dash, 'stroke-linecap': style.linecap });
    if (style.double && (r-l)*480 > 8 && (b-t)*1040 > 8) layer.append(svg('rect', { x:l*480+3, y:t*1040+3, width:(r-l)*480-6, height:(b-t)*1040-6, fill:'none', stroke:colour, 'stroke-width':1 }));
    box.append(svg('title', {}, `${region.label ?? region.id ?? kind}${region.source ? ` · ${region.source}` : ''}`)); layer.append(box);
    if (['detection', 'scannable'].includes(kind)) {
      layer.append(svg('text', { x: Math.max(3, l * 480), y: Math.max(13, t * 1040 - 5), fill: colour, class: 'zone-label' }, region.label ?? region.id ?? 'Reconnaissance'));
    }
  }
}

function transitionButton(edge, compact = false) {
  const target = state.nodes.get(edge.to), button = element('button', `transition${state.selectedEdge?.id === edge.id ? ' active' : ''}`);
  const url = safeImage(target.image);
  if (url) { const image = element('img'); image.src = url; image.alt = ''; image.loading = 'lazy'; button.append(image); }
  else button.append(element('span', 'gesture-icon', edge.end ? '↕' : '↗'));
  const label = element('span'); label.append(element('strong', '', screenLabel(target)), element('small', '', `${edge.source === 'configured' ? 'Configuré · ' : ''}${gestureLabel(edge)}`));
  button.append(label, element('span', 'arrow', '→'));
  button.title = `${gestureLabel(edge)} → ${screenLabel(target)}`;
  button.addEventListener('click', () => { notice(''); visit(edge.to, { edge }); });
  return button;
}

function renderTransitions(candidates = null) {
  const list = $('transitions'); list.replaceChildren();
  const all = candidates ?? outgoing();
  const seen = new Set();
  const edges = all.filter((edge) => {
    const key = `${edge.to}:${gestureLabel(edge)}:${edge.source}`; if (seen.has(key)) return false; seen.add(key); return true;
  });
  $('transition-note').textContent = candidates ? 'Plusieurs destinations ont été enregistrées pour ce geste. Choisissez celle à vérifier.'
    : current()?.source === 'configured' ? 'Trajets définis dans le plugin, à confronter aux captures et à vos retours.' : 'Les destinations sont issues des gestes enregistrés.';
  for (const edge of edges.slice(0, 60)) list.append(transitionButton(edge));
  if (!edges.length) list.append(element('div', 'empty-transitions', 'Aucune transition enregistrée depuis cette capture. Choisissez un autre exemple ou signalez le trajet attendu.'));
  if (edges.length > 60) list.append(element('p', 'muted', 'Les premières transitions sont affichées. Le graphe permet de poursuivre écran par écran.'));
}

function renderMap() {
  const map = $('map'); map.replaceChildren();
  const before = [...new Set((state.incoming.get(state.current) ?? []).map((edge) => edge.from))].filter((id) => id !== state.current).slice(0, 12);
  const after = [...new Set(outgoing().map((edge) => edge.to))].filter((id) => id !== state.current).slice(0, 12);
  const rows = Math.max(before.length, after.length, 1), height = Math.max(550, rows * 220 + 60);
  map.setAttribute('width', '800'); map.setAttribute('height', String(height)); map.setAttribute('viewBox', `0 0 800 ${height}`);
  const placements = new Map([[state.current, { x: 320, y: height / 2 - 95 }]]);
  before.forEach((id, i) => placements.set(id, { x: 35, y: 40 + i * 220 }));
  after.forEach((id, i) => { if (!placements.has(id)) placements.set(id, { x: 605, y: 40 + i * 220 }); });
  for (const edge of [...(state.incoming.get(state.current) ?? []), ...outgoing()]) {
    const a = placements.get(edge.from), b = placements.get(edge.to); if (!a || !b || edge.from === edge.to) continue;
    const x = a.x + 140, y = a.y + 85, x2 = b.x, y2 = b.y + 85;
    const path = svg('path', { d: `M ${x} ${y} C ${x + 65} ${y}, ${x2 - 65} ${y2}, ${x2} ${y2}`, fill: 'none', stroke: edge.kind === 'swipe' ? '#748fce' : '#556a88', 'stroke-width': 1.5, 'stroke-dasharray': edge.source === 'configured' ? '6 4' : 'none', opacity: .65 });
    path.append(svg('title', {}, gestureLabel(edge))); map.append(path);
  }
  for (const [id, position] of placements) {
    const node = state.nodes.get(id), group = svg('g', { class: 'map-node', tabindex: 0, role: 'button', 'aria-label': screenLabel(node) });
    group.append(svg('rect', { x: position.x, y: position.y, width: 150, height: 185, rx: 9,
      fill: id === state.current ? '#22344d' : '#151e2c', stroke: id === state.current ? '#a1c7ff' : '#34435c', 'stroke-width': 1.5 }));
    const url = safeImage(node.image);
    if (url) group.append(svg('image', { href: url, x: position.x + 43, y: position.y + 10, width: 64, height: 139, preserveAspectRatio: 'xMidYMin meet' }));
    else group.append(svg('text', { x: position.x + 75, y: position.y + 83, 'text-anchor': 'middle', fill: '#687e9f', 'font-size': 35 }, '◇'));
    const label = screenLabel(node); group.append(svg('text', { x: position.x + 75, y: position.y + 170, 'text-anchor': 'middle', fill: '#cad8eb', 'font-size': 10 }, label.length > 24 ? `${label.slice(0, 22)}…` : label));
    group.append(svg('title', {}, label));
    group.addEventListener('click', () => visit(id)); group.addEventListener('keydown', (event) => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); visit(id); } });
    map.append(group);
  }
}

function renderFeedback() {
  const list = $('feedback-list'); list.replaceChildren();
  const entries = state.feedback.filter((entry) => entry.nodeId === state.current);
  for (const item of entries) {
    const box = element('div', 'feedback-entry', item.text);
    if (item.correctScreen) box.append(element('small', '', `Écran indiqué : ${item.correctScreen}`));
    box.append(element('small', '', date(item))); list.append(box);
  }
  if (!entries.length) list.textContent = 'Aucun retour enregistré.';
  $('feedback-context').textContent = state.selectedEdge ? `Transition : ${gestureLabel(state.selectedEdge)}` : `Capture : ${screenLabel(current())}`;
}

function render() {
  renderList(); renderCapture(); renderTransitions(); renderFeedback();
  $('explorer').hidden = state.map; $('map-view').hidden = !state.map;
  $('explore-view').setAttribute('aria-pressed', String(!state.map)); $('graph-view').setAttribute('aria-pressed', String(state.map));
  if (state.map) renderMap();
}

function followGesture(gesture) {
  const result = matchGesture(outgoing(), gesture, current()?.regions);
  if (result.forbidden) { notice('Cette zone est déclarée interdite. Vous pouvez signaler une correction si ses limites sont incorrectes.'); return; }
  if (result.matches.length === 1) {
    const edge = result.matches[0];
    if (edge.to === state.current) { state.selectedEdge = edge; notice('Ce geste a été enregistré sans changement de capture.'); renderFeedback(); }
    else { notice(edge.source === 'configured' ? 'Trajet configuré dans le plugin : vérifiez que cette destination correspond au jeu.' : ''); visit(edge.to, { edge }); }
  } else if (result.matches.length > 1) { notice('Plusieurs destinations observées : choisissez la transition à droite.'); renderTransitions(result.matches); }
  else notice('Ce geste ne correspond pas à une transition enregistrée sur cette capture. Signalez la destination attendue ou choisissez un autre exemple.');
}

const phone = $('phone');
function hitZone(position) {
  const zones = [...(current()?.regions ?? [])];
  for (const edge of outgoing()) {
    if (!edge.start) continue;
    zones.push({ id: `edge:${edge.id}`, kind: edge.end ? 'vertical' : 'navigation',
      rect: [Math.max(0, edge.start.x-.025), Math.max(0, edge.start.y-.012), Math.min(1, edge.start.x+.025), Math.min(1, edge.start.y+.012)], label: gestureLabel(edge) });
  }
  return zones.filter((zone) => inside(position, zone.rect)).sort((a,b) =>
    (a.rect[2]-a.rect[0])*(a.rect[3]-a.rect[1]) - (b.rect[2]-b.rect[0])*(b.rect[3]-b.rect[1]))[0];
}

async function proposeZone(operation, zone, nodeId = state.current) {
  const node = state.nodes.get(nodeId); if (!node) return;
  const body = { nodeId, zoneId: zone.id, screen: node.screen, operation, kind: zone.kind, rect: zone.rect, label: zone.label ?? zone.kind };
  if (operation === 'add') delete body.zoneId;
  try {
    const response = await fetch('/api/zone-feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`Retour non enregistré (${response.status}). Réessayez.`);
    const entry = await response.json();
    if (operation === 'remove') {
      const existing = node.regions.find((region) => region.id === zone.id);
      if (existing) Object.assign(existing, { proposal: 'remove', user: true });
      else node.regions.push({ ...zone, proposal: 'remove', user: true });
    } else node.regions.push({ ...zone, id: entry.zoneId || entry.id, user: true, source: 'user_feedback', proposal: 'add' });
    if (state.current === nodeId) renderOverlay();
    notice(operation === 'remove' ? 'Suppression proposée. La zone reste active dans le plugin jusqu’à examen par le développeur.' : 'Annotation enregistrée. Elle sera visible dans les deux overlays et reste à examiner par le développeur.');
  } catch (error) { notice(error.message, true); }
}

function point(event) {
  const rect = phone.getBoundingClientRect();
  return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) };
}
phone.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || !current()) return;
  const position = point(event), zone = state.overlay && !$('annotation-kind').value ? hitZone(position) : null;
  state.gesture = { start: position, at: performance.now(), pointerId: event.pointerId, node: state.current, annotation: $('annotation-kind').value };
  if (zone) {
    const gesture = state.gesture;
    gesture.timer = setTimeout(() => {
      if (state.gesture !== gesture || gesture.moved) return;
      gesture.handled = true; $('gesture-hint').hidden = true;
      proposeZone('remove', zone, gesture.node);
    }, 600);
  }
  phone.setPointerCapture(event.pointerId);
});
phone.addEventListener('pointermove', (event) => {
  const gesture = state.gesture; if (!gesture || gesture.pointerId !== event.pointerId) return;
  const end = point(event), dx = end.x - gesture.start.x, dy = end.y - gesture.start.y;
  if (Math.hypot(dx, dy) > .012) { gesture.moved = true; clearTimeout(gesture.timer); }
  if (gesture.handled) return;
  if (gesture.annotation) {
    renderOverlay();
    $('overlay').removeAttribute('hidden');
    $('overlay').append(svg('rect', { x: Math.min(end.x,gesture.start.x)*480, y:Math.min(end.y,gesture.start.y)*1040,
      width:Math.abs(dx)*480, height:Math.abs(dy)*1040, fill:'none', stroke:COLOURS[gesture.annotation], 'stroke-width':2, 'stroke-dasharray':'1 5', 'stroke-linecap':'round' }));
  }
  if (Math.hypot(dx, dy) > .035) {
    $('gesture-hint').hidden = false;
    $('gesture-hint').textContent = Math.abs(dx) > Math.abs(dy) ? 'Slide horizontal · relâchez pour suivre le geste' : 'Glissement · relâchez pour suivre le geste';
  }
});
phone.addEventListener('pointerup', (event) => {
  const gesture = state.gesture; state.gesture = null; $('gesture-hint').hidden = true;
  if (!gesture || gesture.pointerId !== event.pointerId || gesture.node !== state.current) return;
  clearTimeout(gesture.timer);
  if (gesture.handled) return;
  if (gesture.annotation) {
    const end = point(event), start = gesture.start;
    $('annotation-kind').value = ''; renderOverlay();
    if (Math.abs(end.x-start.x)<.01 || Math.abs(end.y-start.y)<.01) { notice('Dessinez un rectangle couvrant toute la zone à annoter.'); return; }
    proposeZone('add', { kind:gesture.annotation, rect:[Math.min(start.x,end.x),Math.min(start.y,end.y),Math.max(start.x,end.x),Math.max(start.y,end.y)] }, gesture.node);
    return;
  }
  followGesture({ start: gesture.start, end: point(event), duration: performance.now() - gesture.at });
});
phone.addEventListener('pointercancel', () => { clearTimeout(state.gesture?.timer); state.gesture = null; $('gesture-hint').hidden = true; renderOverlay(); });
phone.addEventListener('contextmenu', (event) => event.preventDefault());
let lastWheel = 0;
phone.addEventListener('wheel', (event) => {
  event.preventDefault();
  if (performance.now() - lastWheel < 700 || !current()) return;
  lastWheel = performance.now(); const start = point(event);
  const horizontal = event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY);
  const amount = (horizontal ? event.deltaX || event.deltaY : event.deltaY) > 0 ? -.25 : .25;
  const end = { ...start, [horizontal ? 'x' : 'y']: Math.max(0, Math.min(1, start[horizontal ? 'x' : 'y'] + amount)) };
  followGesture({ start, end, duration: 500 });
}, { passive: false });

$('overlay-toggle').addEventListener('change', (event) => { state.overlay = event.target.checked; renderOverlay(); });
$('annotation-kind').addEventListener('change', (event) => {
  notice(event.target.value ? 'Dessinez un rectangle sur la capture. Cette annotation est un retour, pas une autorisation d’action du plugin.' : '');
});
$('include-traces').addEventListener('change', (event) => { state.includeTraces = event.target.checked; renderList(); renderCapture(); });
$('search').addEventListener('input', (event) => { state.search = event.target.value.trim().toLowerCase(); renderList(); });
$('capture-select').addEventListener('change', (event) => { notice(''); visit(event.target.value); });
$('reload').addEventListener('click', load);
$('back').addEventListener('click', () => { if (state.position > 0) visit(state.history[--state.position], { remember: false }); });
$('forward').addEventListener('click', () => { if (state.position < state.history.length - 1) visit(state.history[++state.position], { remember: false }); });
$('explore-view').addEventListener('click', () => { state.map = false; render(); });
$('graph-view').addEventListener('click', () => { state.map = true; render(); });
$('screen-image').addEventListener('error', () => { $('screen-image').hidden = true; $('image-empty').hidden = false; notice('Cette capture n’est plus disponible. Choisissez un autre exemple.', true); });
$('feedback-open').addEventListener('click', () => { $('feedback-panel').hidden = false; $('feedback-text').focus(); });
$('feedback-close').addEventListener('click', () => { $('feedback-panel').hidden = true; });
$('feedback-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const text = $('feedback-text').value.trim(); if (!text || !current()) return;
  const button = event.submitter; button.disabled = true;
  const body = { nodeId: state.current, text };
  if (state.selectedEdge) body.edgeId = state.selectedEdge.id;
  if ($('correct-screen').value.trim()) body.correctScreen = $('correct-screen').value.trim();
  try {
    const response = await fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`Enregistrement impossible (${response.status}). Votre texte est conservé.`);
    const entry = await response.json(); state.feedback.push(entry);
    $('feedback-result').textContent = 'Retour enregistré et associé à cette capture.';
    $('feedback-text').value = ''; $('correct-screen').value = ''; renderFeedback();
  } catch (error) { $('feedback-result').textContent = error.message; }
  finally { button.disabled = false; }
});
window.addEventListener('hashchange', () => {
  const id = new URLSearchParams(location.hash.slice(1)).get('node'); if (id && id !== state.current) visit(id);
});
load();
setInterval(async () => {
  if (document.hidden || state.loading || state.gesture) return;
  try {
    const response = await fetch('/api/revision', { cache: 'no-store' });
    if (!response.ok) return;
    const value = await response.json(), revision = value.revision;
    if (revision == null) return;
    const changed = state.revision !== revision;
    state.revision = revision;
    if (changed) await load({ quiet: true });
  } catch { /* An unavailable review server does not erase the current capture. */ }
}, 3000);
