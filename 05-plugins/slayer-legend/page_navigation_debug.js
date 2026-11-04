// Navigation map and explicit, user-initiated annotations on the live image.
// Draw the recognised screen's navigation, blocked actions and calibrated
// draggable elements. Visual annotations never grant gesture permission.
import visualTracker from './page_navigation_tracking.js';
import { getScreen } from './page_screen_scan.js';
import capturePreview, { archivedScreen } from './page_navigation_preview.js';
import { zoneStyle, addZoneHatching, addSliderChevrons } from './page_zone_style.js';
export { ZONE_COLOURS as COLOURS } from './page_zone_style.js';
import { ZONE_COLOURS as COLOURS } from './page_zone_style.js';
const VALUE_ROLES = ['progression_value', 'resource_value'];
const RECTANGLE_ROLES = [...VALUE_ROLES, 'screen_identifier'];
const recognition = (zone) => !VALUE_ROLES.includes(zone.kind)
  && (zone.kind === 'screen_identifier' || zone.detection || ['scannable', 'detection'].includes(zone.kind));
export const visibleDebugZones = (zones, identification, navigation) => zones.filter((zone) =>
  recognition(zone) ? identification : navigation);
const ROLE_LABELS = { progression_value: 'Valeur de progression', resource_value: 'Valeur de ressource', screen_identifier: 'Identifiant d’écran' };
const RECTANGLE_ANNOTATIONS = ['scannable', ...RECTANGLE_ROLES, 'action', 'draggable'];
let trajectorySerial = 0;

function covers(move, x, y, tolerance) {
  if (move.area) {
    const [left, top, right, bottom] = move.area;
    return left <= x && x <= right && top <= y && y <= bottom;
  }
  const point = move.tap ?? move.hold;
  return Boolean(point) && Math.abs(point[0] - x) <= tolerance && Math.abs(point[1] - y) <= tolerance;
}

function eligible(move, moves, tolerance) {
  if (move.forbidden || move.needs || move.assumed) return false;
  const point = move.tap ?? move.hold ?? (move.area
    ? [(move.area[0] + move.area[2]) / 2, (move.area[1] + move.area[3]) / 2]
    : move.swipe?.slice(0, 2));
  return Boolean(point) && !moves.some((other) => other.forbidden && covers(other, ...point, tolerance));
}

export function zonesFor(screen, graph, registry, scan = null, tracked = null, dynamic = null) {
  const moves = graph?.screens?.[screen]?.moves ?? [];
  const tolerance = graph?.tolerance ?? 0.03;
  const safe = moves.filter((move) => !move.debug_dynamic && !['action', 'draggable'].includes(move.semantic_kind)
    && eligible(move, moves, tolerance)
    && !(screen === 'quest_panel' && move.id === 'scroll_repeat' && scan?.quest_tab !== 'repeat')
    && (!move.combat_return || (scan?.screen === 'battle' && scan.plain === false
      && recognisedScreen(scan, registry) === screen)));
  const zones = safe.filter((move) => move.tap || move.hold || (move.area && move.kind !== 'swipe'))
    .map((move) => ({ id: move.id, kind: 'tap', conditional: Boolean(move.precondition), rect: move.visual_rect ?? move.area ?? [
      (move.tap ?? move.hold)[0] - 0.025, (move.tap ?? move.hold)[1] - 0.012,
      (move.tap ?? move.hold)[0] + 0.025, (move.tap ?? move.hold)[1] + 0.012,
    ] }));
  // Rendering a measured viewport is not permission to use its guarded
  // scroll. In particular Soul Weapon still requires fresh off-tag checks.
  const scrollKey = screen === 'quest_panel' && ['daily', 'repeat', 'achievement'].includes(scan?.quest_tab)
    ? `quest_${scan.quest_tab}` : screen;
  const scrolls = registry?.tree?.[scrollKey]?.scroll ?? [];
  for (const known of scrolls.filter((item) => item.measured && item.visual_source?.role === 'display_bounds_only')) {
    const move = moves.find((item) => known.move === `${screen}/${item.id}`);
    if (!move || move.forbidden || move.assumed) continue;
    zones.push({ id: move.id, kind: known.direction === 'horizontal' ? 'horizontal' : 'vertical',
      conditional: true, rect: known.rect, visual_source: known.visual_source });
  }
  for (const move of safe.filter((item) => item.area && item.kind === 'swipe')) {
    if (zones.some((zone) => zone.id === move.id)) continue;
    const known = scrolls.find((item) => item.move === `${screen}/${move.id}` && item.measured);
    if (!known) continue;
    zones.push({ id: move.id, kind: known.direction === 'horizontal' ? 'horizontal' : 'vertical',
      conditional: Boolean(move.precondition),
      rect: known.rect });
  }
  for (const move of safe.filter((item) => item.swipe)) {
    if (zones.some((zone) => zone.id === move.id)) continue;
    const known = scrolls.find((item) => item.move === `${screen}/${move.id}` && item.measured);
    const [x1, y1, x2, y2] = move.swipe;
    const vertical = Math.abs(y2 - y1) >= Math.abs(x2 - x1);
    zones.push({ id: move.id, kind: vertical ? 'vertical' : 'horizontal',
      conditional: Boolean(move.precondition),
      rect: known?.rect ?? [Math.min(x1, x2) - 0.025, Math.min(y1, y2) - 0.015,
        Math.max(x1, x2) + 0.025, Math.max(y1, y2) + 0.015] });
  }
  for (const move of moves.filter((item) => item.forbidden || ['action', 'draggable'].includes(item.semantic_kind))) {
    if (move.id === 'better_weapon_toast' && !scan?.overlays?.includes('better_weapon_toast')) continue;
    // Some guard envelopes intentionally cover a list or grid. They are
    // not button bounds: only explicit debug rectangles may replace them.
    const point = move.tap ?? move.hold;
    const rects = move.visual_rect ? [move.visual_rect] : move.forbidden && move.area ? [move.area] : move.debug_rects ?? (move.debug_dynamic ? [] : move.area ? [move.area]
      : point ? [[point[0] - (move.forbidden ? tolerance : .025), point[1] - (move.forbidden ? tolerance : .012),
        point[0] + (move.forbidden ? tolerance : .025), point[1] + (move.forbidden ? tolerance : .012)]] : []);
    for (const [index, rect] of rects.entries()) {
      if (zones.some((zone) => zone.kind === move.semantic_kind && JSON.stringify(zone.rect) === JSON.stringify(rect))) continue;
      zones.push({ id: `${move.id}-${index}`, move: move.id,
        dynamic: Boolean(move.debug_dynamic || rects.length > 1),
        kind: move.semantic_kind === 'navigation' ? 'tap' : move.semantic_kind === 'draggable' ? 'draggable' : 'action',
        semantic_kind: move.semantic_kind, forbidden: Boolean(move.forbidden),
        conditional: Boolean(move.precondition), guard_rect: move.area, visual_source: move.visual_source, rect });
    }
  }
  if (dynamic?.screen === screen && Date.now() / 1000 - dynamic.at >= 0
      && Date.now() / 1000 - dynamic.at <= 2) zones.push(...dynamic.zones.map((zone) => ({ ...zone, dynamic: true })));
  if (scan) {
    // The battle remains behind these measured bottom panels. Other
    // overlays can cover the controls, so do not draw through them.
    const visible = new Set(['panel', 'equipment_weapon', 'equipment_accessories', 'soul_weapon', 'better_weapon_toast']);
    const controlsVisible = scan.screen === 'battle'
      && typeof scan.plain === 'boolean'
      && (scan.overlays ?? []).every((overlay) => visible.has(overlay));
    const existing = zones.findIndex((zone) => zone.id === 'preset_arrow');
    if (existing >= 0) zones.splice(existing, 1);
    const arrow = graph?.screens?.battle?.moves?.find((move) => move.id === 'preset_arrow');
    const toastCoversReducedArrow = scan.plain === false && (scan.overlays ?? []).includes('better_weapon_toast');
    if (controlsVisible && !toastCoversReducedArrow && arrow && !arrow.forbidden) {
      // Exact folded-arrow bounds, with a small border around the triangle:
      // fixtures/battle_arrow_full (480×1040), battle_arrow_minimized
      // (720×1560). The side control is fixed to the battle viewport.
      const rect = scan.plain
        ? [460 / 480, 450 / 1040, 476 / 480, 475 / 1040]
        : [691 / 720, 535 / 1560, 714 / 720, 571 / 1560];
      zones.push({ id: arrow.id, kind: 'tap', conditional: Boolean(arrow.precondition),
        rect, fixed: true });
    }
  }
  return zones.flatMap((zone) => {
    if (zone.fixed || zone.forbidden || !['tap', 'action', 'draggable'].includes(zone.kind) || !tracked?.has(zone.id)) return [zone];
    const rect = tracked.get(zone.id);
    return rect ? [{ ...zone, rect }] : [];
  }).sort((a, b) => Number(Boolean(a.forbidden || a.kind === 'forbidden'))
    - Number(Boolean(b.forbidden || b.kind === 'forbidden')));
}

export function recognisedScreen(scan, registry = null) {
  if (!scan || !scan.screen || ['unknown', 'other', 'menu'].includes(scan.screen) || Date.now() / 1000 - scan.at > 10) return null;
  const tree = registry?.tree ?? {};
  const overlays = [...new Set((scan.overlays ?? []).filter((item) => typeof item === 'string'
    && item !== 'panel' && item !== 'better_weapon_toast'))];
  const ancestry = new Map();
  for (const name of overlays) {
    const parents = new Set();
    let current = name;
    while (current) {
      if (parents.has(current)) return null;
      parents.add(current);
      // A visual overlay may be registered outside the navigation tree.
      current = current === name && !tree[name] && name !== scan.screen && overlays.includes(scan.screen)
        ? scan.screen : tree[current]?.parent;
    }
    ancestry.set(name, parents);
  }
  const deepest = overlays.filter((name) => !overlays.some((other) => other !== name && ancestry.get(other).has(name)));
  if (overlays.length && deepest.length !== 1) return null;
  if (!overlays.length && scan.overlays?.includes('panel')) return null;
  return deepest[0] ?? scan.screen;
}

// Detection evidence never authorises a navigation gesture.
export function landmarksFor(screen, registry) {
  return (registry?.tree?.[screen]?.landmarks ?? []).map((landmark) => ({
    ...landmark, kind: 'scannable', detection: true,
  }));
}

export function zoneRemovalProposal(target) {
  const kind = target.kind === 'action' ? 'action' : target.forbidden || target.kind === 'forbidden' ? 'forbidden'
    : RECTANGLE_ROLES.includes(target.kind) ? target.kind
    : target.detection || target.kind === 'scannable' ? 'detection'
      : target.kind === 'tap' ? 'navigation' : target.kind;
  let zoneId = target.zoneId ?? target.id;
  if (!target.user && !/^(manual|region|user):/.test(zoneId)) {
    if (target.dynamic) zoneId = `dynamic:${target.screen}:${target.id}:${target.rect.map((v) => v.toFixed(6)).join(':')}`;
    else if (kind === 'detection') zoneId = zoneId.startsWith('landmark:') ? zoneId : `landmark:${zoneId}`;
    else zoneId = `policy:${target.screen}:${target.move ?? target.id}`;
  }
  return { zoneId, nodeId: target.nodeId ?? `screen:${target.screen}`, screen: target.screen,
    operation: 'remove', kind, forbidden: Boolean(target.forbidden || target.kind === 'forbidden'), rect: [...target.rect], conditional: Boolean(target.conditional || target.dynamic) };
}

export function feedbackZones(screen, configured, annotations, scan = null) {
  if (!screen || ['unknown', 'other', 'menu'].includes(screen)) return configured;
  const identities = new Set([screen]);
  if (screen === 'quest_panel' && ['daily', 'repeat', 'achievement'].includes(scan?.quest_tab)) identities.add(`quest_${scan.quest_tab}`);
  const user = annotations.filter((zone) => identities.has(zone.screen) && zone.user === true
    && zone.rect?.length === 4 && zone.rect.every((value) => Number.isFinite(value) && value >= 0 && value <= 1)
    && zone.rect[0] < zone.rect[2] && zone.rect[1] < zone.rect[3]);
  const removals = user.filter((zone) => zone.proposal === 'remove' || zone.removedProposal);
  const matched = new Set();
  const canonical = (id) => typeof id === 'string' ? id
    .replace(/^edge:configured:[^:]+:/, '').replace(new RegExp(`^policy:${screen}:`), '').replace(/^policy:/, '') : null;
  const kind = (zone) => zone.kind === 'action' ? 'action' : zone.forbidden || zone.kind === 'forbidden' ? 'forbidden'
    : RECTANGLE_ROLES.includes(zone.kind) ? zone.kind
    : zone.detection || ['scannable', 'detection'].includes(zone.kind) ? 'detection'
    : zone.kind === 'tap' ? 'navigation' : zone.kind;
  const idMatches = (item, zone) => {
    const configuredIds = [zone.id, zone.move, ...(zone.aliases ?? [])].map(canonical).filter(Boolean);
    return [item.zoneId, item.id, ...(item.aliases ?? [])].map(canonical)
      .some((id) => id && configuredIds.includes(id));
  };
  const anchored = new Set(removals.filter((item) => configured.some((zone) => idMatches(item, zone))));
  return [...configured.map((zone) => {
    const pending = removals.find((item) => idMatches(item, zone) || !anchored.has(item)
      && !/^(manual|region):/.test(item.zoneId ?? item.id) && kind(item) === kind(zone)
      && Boolean(item.forbidden || item.kind === 'forbidden') === Boolean(zone.forbidden || zone.kind === 'forbidden')
      && item.rect.every((value, index) => Math.abs(value - zone.rect[index]) <= .003));
    if (!pending) return zone;
    matched.add(pending);
    return { ...zone, proposal: 'remove', user: true };
  }), ...user.filter((zone) => !matched.has(zone))].sort((a, b) => Number(Boolean(a.forbidden || a.kind === 'forbidden'))
    - Number(Boolean(b.forbidden || b.kind === 'forbidden')));
}

export const ANNOTATIONS = [
  { kind: 'navigation', label: 'Ajouter un bouton de navigation' },
  { kind: 'forbidden', label: 'Déclarer un bouton de navigation interdit' },
  { kind: 'progression_value', label: 'Marquer une valeur de progression' },
  { kind: 'resource_value', label: 'Marquer une valeur de ressource' },
  { kind: 'screen_identifier', label: 'Marquer un identifiant d’écran' },
  { kind: 'vertical', label: 'Marquer un slider vertical' },
  { kind: 'horizontal', label: 'Marquer un slider horizontal' },
  { kind: 'action', label: 'Marquer un bouton d’action' },
  { kind: 'action', forbidden: true, label: 'Déclarer un bouton d’action interdit' },
  { kind: 'draggable', label: 'Marquer un élément déplaçable' },
];

export function screenDisplayName(id, graph, registry, tr = (value) => value) {
  return tr(graph?.screens?.[id]?.name ?? registry?.tree?.[id]?.name ?? 'Écran non identifié');
}

export const SCREEN_GROUPS = [
  ['all', 'Tous'], ['combat', 'Combat'], ['character', 'Character'], ['equipment', 'Equipment'],
  ['companion', 'Companion'], ['adventure', 'Adventure'], ['shop', 'Shop'], ['other', 'Autres'],
];

export function screenGroup(id, registry) {
  const seen = new Set();
  let current = id;
  while (current && current !== 'battle' && !seen.has(current)) {
    seen.add(current);
    if (/^(equipment|soul_weapon|black_orb|weapon_detail|spirit)/.test(current)) return 'equipment';
    if (/^(character|promotion)/.test(current)) return 'character';
    if (/^(companion|beast)/.test(current)) return 'companion';
    if (/^(adventure|dungeon|mine|guild)/.test(current)) return 'adventure';
    if (/^shop/.test(current)) return 'shop';
    current = registry?.tree?.[current]?.parent;
  }
  return /^(battle|stage_select|skill|familiar|scroll)/.test(id) ? 'combat' : 'other';
}

export function screenChoices(graph, registry, group = 'all', tr = (value) => value) {
  const ids = new Set([...Object.keys(graph?.screens ?? {}), ...Object.keys(registry?.tree ?? {})]);
  return [...ids].filter((id) => group === 'all' || screenGroup(id, registry) === group)
    .map((id) => [id, screenDisplayName(id, graph, registry, tr)])
    .sort((a, b) => a[1].localeCompare(b[1]));
}

export function annotationPoint(event, bounds) {
  return { x: Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    y: Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)) };
}

// Keep panel geometry separate from capture rendering: dragging or folding
// never replaces an armed annotation surface or restarts its pointer gesture.
export function floatingDebugPanel(viewport, stop) {
  let position = null;
  let minimised = false;
  let current = null;
  let drag = null;
  let deferred = null;
  const clamp = () => {
    if (!current) return;
    const bounds = viewport.getBoundingClientRect();
    const size = current.panel.getBoundingClientRect();
    if (!position) position = { x: bounds.width * .02,
      y: current.compact ? bounds.height * .05 : bounds.height * .93 - size.height };
    position.x = Math.max(0, Math.min(position.x, Math.max(0, bounds.width - size.width)));
    position.y = Math.max(0, Math.min(position.y, Math.max(0, bounds.height - size.height)));
    current.panel.style.left = `${position.x}px`;
    current.panel.style.top = `${position.y}px`;
  };
  const paint = () => {
    if (!current) return;
    current.panel.style.width = minimised ? 'auto' : 'min(380px, 96%)';
    current.content.style.display = minimised ? 'none' : '';
    current.toggle.textContent = minimised ? '+' : '−';
    current.toggle.setAttribute('aria-label', current.tr(minimised ? 'Agrandir le menu de navigation' : 'Réduire le menu de navigation'));
    current.toggle.setAttribute('aria-expanded', String(!minimised));
    current.panel.setAttribute('data-debug-minimised', String(minimised));
    clamp();
  };
  return {
    clamp,
    get dragging() { return Boolean(drag); },
    afterDrag(fn) { deferred = fn; },
    attach(panel, content, compact, tr) {
      const header = document.createElement('div');
      header.setAttribute('data-debug-drag-handle', '');
      header.style.cssText = 'display:flex;align-items:center;gap:8px;pointer-events:auto;touch-action:none;cursor:move;user-select:none';
      const title = document.createElement('span');
      title.textContent = `⠿ ${tr('Navigation')}`;
      title.style.cssText = 'flex:1;font-weight:600';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.setAttribute('data-debug-toggle', '');
      toggle.style.cssText = 'pointer-events:auto;padding:1px 7px;border:1px solid #888;border-radius:3px;background:#292929;color:#fff;font:inherit;cursor:pointer;touch-action:none';
      toggle.onpointerdown = stop;
      toggle.onpointerup = stop;
      toggle.onclick = (event) => { stop(event); minimised = !minimised; paint(); };
      header.append(title); header.append(toggle);
      header.onpointerdown = (event) => {
        stop(event);
        if (drag || (event.button !== undefined && event.button !== 0)) return;
        clamp();
        drag = { pointer: event.pointerId, ...position };
        // Distinct client and panel coordinates are needed after clamping.
        drag.clientX = event.clientX; drag.clientY = event.clientY;
        header.setPointerCapture?.(event.pointerId);
      };
      header.onpointermove = (event) => {
        stop(event);
        if (!drag || drag.pointer !== event.pointerId) return;
        position = { x: drag.x + event.clientX - drag.clientX,
          y: drag.y + event.clientY - drag.clientY };
        clamp();
      };
      const end = (event) => {
        stop(event);
        if (!drag || drag.pointer !== event.pointerId) return;
        drag = null;
        if (header.hasPointerCapture?.(event.pointerId)) header.releasePointerCapture(event.pointerId);
        const done = deferred; deferred = null; done?.();
      };
      header.onpointerup = end;
      header.onpointercancel = end;
      header.onlostpointercapture = end;
      panel.setAttribute('data-debug-panel', '');
      panel.append(header); panel.append(content);
      current = { panel, content, compact, toggle, tr };
      paint();
    },
  };
}

export default function navigationDebug(api, { enabled = () => true } = {}) {
  const layer = document.createElement('div');
  layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:30';
  const zoneLayer = document.createElement('div');
  zoneLayer.style.cssText = 'position:absolute;inset:0;pointer-events:none';
  const tracker = visualTracker(api.video);
  let graph = null;
  let registry = null;
  let disposed = false;
  let captureState = 'idle';
  let captureId = null;
  let captureKind = 'navigation';
  let captureForbidden = false;
  let record = null;
  let refreshing = false;
  let hiddenCheck = 0;
  let rendered = '';
  let armedUntil = 0;
  let closePreview = null;
  let snapshotPending = false;
  let snapshotMessage = '';
  let expectedScreen = '';
  let correctionOpen = false;
  let correctionGroup = 'all';
  let dynamic = null;
  let dynamicAt = 0;
  let userAnnotations = [];
  let feedbackMode = false;
  let feedbackTarget = null;
  let feedbackMessage = '';
  let currentZones = [];
  let holdTimer = null;
  let oral = null, oralPending = false, oralRetryAt = 0, oralUnavailable = false;
  async function ensureOral() {
    if (oral || oralPending || Date.now() < oralRetryAt || !api.url) return;
    oralPending = true; oralUnavailable = false; oralRetryAt = Date.now() + 30000;
    try {
      // This independent, explicitly CORS-allowed module can be upgraded
      // without restarting the game gateway during the user's Free play.
      const url = new URL(api.url('/'));
      if (url.protocol === 'https:') url.pathname = '/navigation-review/page_oral_feedback.js';
      else { url.port = '7890'; url.pathname = '/page_oral_feedback.js'; }
      url.search = `?attempt=${Math.floor(Date.now() / 30000)}`; url.hash = '';
      const { default: oralFeedback, freezeOralContext, liveOralTransport } = await import(url.href);
      if (disposed || !tools()) return;
      oral = oralFeedback({ tr: api.tr, transport: liveOralTransport(api), capture: () => freezeOralContext({
        image: api.video?.(), layer: api.layer, source: 'live', nodeId: screen ? `screen:${screen}` : `live:${Date.now()}`,
        screen, displayName: screenDisplayName(screen, graph, registry, api.tr), regions: currentZones,
        enabled: identification() || navigation(),
        state: { scan, correctionGroup, feedbackMode, selectedZone: feedbackTarget, debugEnabled: active(),
          identification: identification(), navigation: navigation(), reporting: tools() },
      }) });
      rendered = ''; render();
    } catch { oralUnavailable = true; }
    finally { oralPending = false; if (!disposed) { rendered = ''; render(); } }
  }
  const identification = () => api.setting('screenIdentification') === 'on';
  const navigation = () => api.setting('navigationDebug') === 'on';
  const tools = () => api.setting('navigationFeedback') === 'on';
  const active = () => !disposed && enabled() && (identification() || navigation() || tools());
  const busy = () => ['arming', 'armed', 'saving', 'cancelling'].includes(captureState);
  const clear = () => { if (oral?.busy) oral.cancel(); closePreview?.(); closePreview = null; layer.replaceChildren(); layer.remove(); rendered = ''; };
  const stop = (event) => { event.preventDefault(); event.stopPropagation(); };
  const floating = floatingDebugPanel(api.layer, stop);
  async function cancelTools() {
    oral?.cancel(); closePreview?.(); closePreview = null;
    clearTimeout(holdTimer); feedbackMode = false; feedbackTarget = null; correctionOpen = false;
    if (captureState === 'armed') {
      const id = captureId; captureState = 'cancelling';
      try { await api.post('/trace/cancel', { id }); }
      finally { captureId = null; captureState = 'cancelled'; }
    }
  }
  const finishTouch = (tap, synthetic = false) => {
    if (!tools() || captureState !== 'armed') return;
    captureState = 'saving';
    if (synthetic || api.setting('traceTaps') === 'off') {
      api.post('/trace', tap).then((answer) => {
        if (!answer?.ok) { captureState = 'failed'; render(); }
      }).catch(() => { captureState = 'failed'; render(); });
    }
    render();
  };
  const stopTap = api.onTap?.((tap) => finishTouch(tap));
  let screen = null;
  let scan = null;

  function drawZone(zone, parent = layer) {
    const [left, top, right, bottom] = zone.rect.map((part) => Math.max(0, Math.min(1, part)));
    const box = document.createElement('div');
    const forbidden = zone.forbidden || zone.kind === 'forbidden';
    const detection = recognition(zone);
    const colour = forbidden ? COLOURS.forbidden : COLOURS[zone.kind];
    const slider = !forbidden && (zone.kind === 'vertical' || zone.kind === 'horizontal');
    const visual = zoneStyle(zone);
    box.style.cssText = `position:absolute;left:${left * 100}%;top:${top * 100}%;width:${(right - left) * 100}%;height:${(bottom - top) * 100}%;box-sizing:border-box;color:${colour};pointer-events:none`;
    box.style.cssText += `;background:${colour}33;border-radius:${visual.radius}px`;
    if (slider) addSliderChevrons(box, colour, zone.kind, zone.rect);
    box.style.cssText += `;opacity:${visual.opacity};border:${visual.dash === 'none' ? `${visual.width}px solid ${colour}` : '0'}`;
    if (visual.hatch) addZoneHatching(box, colour, visual.radius);
    if (visual.opacity < 1) box.style.cssText += ';background:transparent';
    if (visual.double) box.style.cssText += `;outline:1px solid ${colour};outline-offset:-4px`;
    if (visual.dash !== 'none') {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 100 100'); svg.setAttribute('preserveAspectRatio', 'none');
      svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none';
      const outline = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      for (const [key, value] of Object.entries({ x: .5, y: .5, width: 99, height: 99, rx: visual.radius, ry: visual.radius, fill: 'none',
        stroke: colour, 'stroke-width': visual.width, 'stroke-dasharray': visual.dash,
        'stroke-linecap': visual.linecap, 'vector-effect': 'non-scaling-stroke' })) outline.setAttribute(key, value);
      svg.append(outline); box.append(svg);
    }
    if (zone.kind === 'draggable' && zone.trajectory?.length >= 2
        && zone.trajectory.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y))) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('viewBox', '0 0 100 100'); svg.setAttribute('preserveAspectRatio', 'none');
      svg.setAttribute('data-zone-trajectory', zone.kind);
      svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none';
      const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
      const markerId = `zone-chevron-${++trajectorySerial}`;
      for (const [key, value] of Object.entries({ id: markerId, viewBox: '0 0 10 10', refX: 8, refY: 5,
        markerWidth: 6, markerHeight: 6, orient: 'auto' })) marker.setAttribute(key, value);
      const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      for (const [key, value] of Object.entries({ d: 'M1 1 L8 5 L1 9', fill: 'none', stroke: colour,
        'stroke-width': 1.5, 'stroke-dasharray': 'none' })) chevron.setAttribute(key, value);
      marker.append(chevron); svg.append(marker);
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
      const points = zone.trajectory.map((point) => `${(point.x - left) / (right - left) * 100},${(point.y - top) / (bottom - top) * 100}`).join(' ');
      for (const [key, value] of Object.entries({ points, fill: 'none', stroke: colour, 'stroke-width': 2,
        'stroke-dasharray': 'none', 'vector-effect': 'non-scaling-stroke', 'marker-end': `url(#${markerId})` })) line.setAttribute(key, value);
      svg.append(line); box.append(svg);
    }
    box.setAttribute('data-zone-source', zone.user ? 'user' : 'configured');
    box.setAttribute('data-zone-origin', zone.source ?? (zone.user ? 'user_feedback' : 'navigation_guard'));
    box.setAttribute('data-zone-forbidden', String(Boolean(forbidden)));
    box.setAttribute('data-zone-kind', zone.kind === 'action' ? 'action' : forbidden ? 'forbidden' : RECTANGLE_ROLES.includes(zone.kind) ? zone.kind
      : detection ? 'detection' : zone.kind === 'tap' ? 'navigation' : zone.kind);
    const roleLabel = ROLE_LABELS[zone.kind];
    const label = forbidden ? `${zone.id} · ${api.tr(zone.kind === 'action' || zone.semantic_kind === 'action' ? 'Action interdite' : 'Navigation interdite')}` : zone.id;
    box.title = roleLabel && !forbidden ? `${api.tr(roleLabel)} · ${zone.id}` : detection && !forbidden ? `${api.tr('Repère de détection')} · ${zone.id}` : zone.conditional ? `${label} · ${api.tr('condition à vérifier')}` : label;
    parent.append(box);
    return box;
  }

  function renderZones() {
    if (!active() || !graph || !registry) return;
    // An unidentified bottom panel still leaves the fixed battle arrow
    // visible. With no identity zonesFor emits no panel or Battle moves.
    const zones = zonesFor(screen, graph, registry, scan, null, dynamic);
    const tracked = tracker.update(screen, zones, registry?.tree?.[screen]?.scroll ?? []);
    zoneLayer.replaceChildren();
    const configured = [...landmarksFor(screen, registry), ...zonesFor(screen, graph, registry, scan, tracked, dynamic)]
      .map((zone) => ({ ...zone, source: zone.source ?? (zone.detection ? 'calibrated_reader' : 'navigation_guard') }));
    currentZones = visibleDebugZones(feedbackZones(screen, configured, graph.screens?.[screen] ? userAnnotations : [], scan), identification(), navigation());
    for (const zone of currentZones) drawZone(zone, zoneLayer);
  }

  function render() {
    if (!active() || !graph || !registry) { clear(); return; }
    if (tools()) ensureOral();
    floating.clamp();
    if (floating.dragging) { floating.afterDrag(render); return; }
    const signature = JSON.stringify([identification(), navigation(), tools(), screen, scan?.plain, scan?.overlays, captureState, captureId, captureKind, record, snapshotPending, snapshotMessage, correctionOpen, correctionGroup, feedbackMode, feedbackTarget?.id, feedbackMessage]);
    renderZones();
    if (signature === rendered && layer.isConnected) return;
    rendered = signature;
    if (!layer.isConnected) api.layer.append(layer);
    layer.replaceChildren();
    layer.append(zoneLayer);
    const name = document.createElement('div');
    const label = screen ? screenDisplayName(screen, graph, registry, api.tr) : api.tr('Écran non identifié');
    name.textContent = api.tr('Écran : {screen}', { screen: label });
    name.style.cssText = 'position:absolute;left:50%;top:1%;transform:translateX(-50%);max-width:90%;padding:3px 7px;border:1px solid #ffe100;border-radius:4px;background:#000c;color:#fff;font:600 12px sans-serif;text-align:center';
    if (identification()) layer.append(name);
    if (!tools()) return;

    if (feedbackMode && !busy()) {
      const surface = document.createElement('div');
      surface.setAttribute('data-zone-feedback-surface', '');
      surface.style.cssText = 'position:absolute;inset:0;pointer-events:auto;touch-action:none;user-select:none;z-index:1';
      surface.onclick = surface.ondblclick = surface.oncontextmenu = surface.onwheel = stop;
      let origin = null;
      const cancelHold = () => { clearTimeout(holdTimer); holdTimer = null; };
      surface.onpointerdown = (event) => {
        stop(event); cancelHold();
        origin = annotationPoint(event, surface.getBoundingClientRect());
        surface.setPointerCapture?.(event.pointerId);
        const target = [...currentZones].reverse().find((zone) => zone.rect[0] <= origin.x && origin.x <= zone.rect[2]
          && zone.rect[1] <= origin.y && origin.y <= zone.rect[3]);
        const identity = screen;
        if (target && identity) holdTimer = setTimeout(() => {
          if (!active() || !feedbackMode || screen !== identity) return;
          feedbackTarget = { ...target, screen: target.screen ?? identity, displayScreen: identity }; render();
        }, 500);
      };
      surface.onpointermove = (event) => {
        stop(event);
        const point = annotationPoint(event, surface.getBoundingClientRect());
        if (origin && Math.hypot(point.x - origin.x, point.y - origin.y) > .02) cancelHold();
      };
      surface.onpointerup = surface.onpointercancel = (event) => { stop(event); cancelHold(); origin = null; };
      if (feedbackTarget) {
        const remove = document.createElement('button');
        remove.type = 'button'; remove.textContent = api.tr('Supprimer · proposition uniquement');
        remove.setAttribute('data-zone-feedback-remove', feedbackTarget.id);
        remove.style.cssText = 'position:absolute;left:10%;top:15%;max-width:80%;padding:10px;pointer-events:auto;background:#171717;color:#fff;border:1px solid #ff5353';
        remove.onpointerdown = remove.onpointerup = stop;
        remove.onclick = async (event) => {
          stop(event);
          const target = feedbackTarget;
          if (!active() || !target || (target.displayScreen ?? target.screen) !== screen) return;
          const proposal = zoneRemovalProposal(target);
          try {
            const response = await api.post('/navigation/zone-feedback', proposal);
            if (!response?.ok) throw Error('feedback rejected');
            userAnnotations.push({ ...target, id: `pending:${target.id}`, zoneId: proposal.zoneId,
              user: true, source: 'user_feedback', proposal: 'remove', removedProposal: true });
            feedbackMessage = 'Proposition enregistrée pour le développeur · comportement inchangé';
            feedbackTarget = null;
          } catch { feedbackMessage = 'Échec de l’enregistrement'; }
          render();
        };
        surface.append(remove);
      }
      layer.append(surface);
    }

    // Annotation gestures are consumed here, before they reach Android.
    if (captureState === 'armed' && captureKind !== 'navigation') {
      const surface = document.createElement('div');
      surface.setAttribute('data-annotation-surface', '');
      surface.style.cssText = 'position:absolute;inset:0;pointer-events:auto;touch-action:none;cursor:crosshair';
      let start = null;
      let preview = null;
      surface.onpointerdown = (event) => {
        stop(event);
        start = annotationPoint(event, surface.getBoundingClientRect());
        surface.setPointerCapture?.(event.pointerId);
      };
      surface.onpointermove = (event) => {
        stop(event);
        if (!start || !['vertical', 'horizontal', ...RECTANGLE_ANNOTATIONS].includes(captureKind)) return;
        const end = annotationPoint(event, surface.getBoundingClientRect());
        preview?.remove();
        preview = drawZone({ id: captureKind, kind: captureKind, forbidden: captureForbidden, rect: [
          Math.min(start.x, end.x), Math.min(start.y, end.y), Math.max(start.x, end.x), Math.max(start.y, end.y)] }, surface);
      };
      surface.onpointerup = (event) => {
        stop(event);
        if (!start) return;
        const end = annotationPoint(event, surface.getBoundingClientRect());
        const slider = ['vertical', 'horizontal'].includes(captureKind);
        const area = RECTANGLE_ANNOTATIONS.includes(captureKind);
        if (area && (Math.abs(end.x - start.x) < 0.01 || Math.abs(end.y - start.y) < 0.01)) {
          start = null; preview?.remove(); return;
        }
        if (slider && Math.abs(end[captureKind === 'vertical' ? 'y' : 'x'] - start[captureKind === 'vertical' ? 'y' : 'x']) < 0.02) return;
        finishTouch({ ...start, kind: slider || area ? 'swipe' : 'tap', ...(slider || area ? { end } : {}) }, true);
        start = null;
      };
      surface.onpointercancel = (event) => { stop(event); start = null; preview?.remove(); };
      layer.append(surface);
    }

    const panel = document.createElement('div');
    panel.style.cssText = `position:absolute;max-width:96%;max-height:100%;box-sizing:border-box;overflow:auto;pointer-events:${busy() ? 'none' : 'auto'};z-index:2;padding:7px;border:1px solid #ffe100;border-radius:5px;background:#171717ed;color:#fff;font:12px sans-serif`;
    panel.setAttribute('data-capture-layout', busy() ? 'compact' : 'actions');
    panel.onpointerdown = (event) => event.stopPropagation();
    panel.onpointerup = (event) => event.stopPropagation();
    const content = document.createElement('div');
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px';
    for (const action of busy() ? [] : ANNOTATIONS) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = api.tr(action.label);
      button.disabled = busy() || snapshotPending || feedbackMode;
      button.style.cssText = 'flex:1 1 130px;padding:5px;border:1px solid #888;border-radius:3px;background:#292929;color:#fff;font:inherit;cursor:pointer';
      button.onclick = async (event) => {
        stop(event);
        if (busy() || snapshotPending) return;
        snapshotMessage = '';
        captureState = 'arming'; captureKind = action.kind; captureForbidden = action.forbidden === true || action.kind === 'forbidden'; captureId = null; record = null;
        render();
        try {
          const response = await api.post('/trace/arm', { kind: action.kind, forbidden: captureForbidden });
          const answer = response?.ok ? response.body : null;
          captureId = answer?.id ?? null;
          armedUntil = answer?.until ?? Date.now() / 1000 + (answer?.seconds ?? 30);
          captureState = answer?.armed ? 'armed' : 'failed';
          if (!tools()) await cancelTools();
        } catch { captureState = 'failed'; }
        render();
      };
      actions.append(button);
    }
    content.append(actions);
    if (!busy()) {
      const snapshots = document.createElement('div');
      snapshots.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;margin-top:6px';
      const snapshotButton = (label, kind, callback) => {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = api.tr(label);
        button.setAttribute('data-screen-evidence', kind);
        button.disabled = snapshotPending;
        button.style.cssText = 'flex:1;padding:5px;border:1px solid #888;border-radius:3px;background:#292929;color:#fff;font:inherit;cursor:pointer';
        button.onclick = async (event) => { stop(event); if (!snapshotPending) await callback(); };
        snapshots.append(button);
      };
      const captureScreen = async (correction = false) => {
        if (snapshotPending || (correction && !expectedScreen)) return;
        snapshotPending = true; snapshotMessage = 'Enregistrement de l’écran…'; render();
        try {
          const response = await api.post('/trace/capture', correction ? { expected_screen: expectedScreen } : {});
          const answer = response?.body?.record ?? response?.body;
          if (!response?.ok || !answer?.id) throw Error('capture failed');
          record = answer; captureId = answer.id;
          captureKind = correction ? 'screen_correction' : 'screen'; captureForbidden = false;
          captureState = 'saved';
          snapshotMessage = correction ? 'Erreur de détection enregistrée avec la capture' : 'Écran enregistré';
          correctionOpen = false;
        } catch { snapshotMessage = 'Échec de l’enregistrement'; }
        snapshotPending = false; render();
      };
      snapshotButton('Enregistrer cet écran', 'capture', () => captureScreen());
      snapshotButton(feedbackMode ? 'Terminer la correction des zones' : 'Corriger une zone', 'zone-feedback', () => {
        feedbackMode = !feedbackMode; feedbackTarget = null; feedbackMessage = '';
        clearTimeout(holdTimer); render();
      });
      snapshotButton(screen ? 'Mauvais écran détecté' : 'Identifier cet écran', 'correction', () => {
        correctionOpen = !correctionOpen; render();
      });
      content.append(snapshots);
      if (feedbackMode || feedbackMessage) {
        const note = document.createElement('div');
        note.setAttribute('data-zone-feedback-instructions', '');
        note.textContent = api.tr(feedbackMessage || 'Maintenez une zone 0,5 s pour proposer sa suppression. Aucun geste n’est envoyé au jeu.');
        content.append(note);
      }
      if (correctionOpen) {
        const tabs = document.createElement('div');
        tabs.setAttribute('role', 'tablist');
        tabs.setAttribute('aria-label', api.tr('Famille d’écrans'));
        tabs.style.cssText = 'display:flex;gap:4px;overflow-x:auto;max-width:100%;margin-top:6px;padding-bottom:4px';
        for (const [group, title] of SCREEN_GROUPS) {
          if (group !== 'all' && !screenChoices(graph, registry, group).length) continue;
          const tab = document.createElement('button');
          tab.type = 'button'; tab.textContent = api.tr(title);
          tab.setAttribute('role', 'tab'); tab.setAttribute('data-screen-group', group);
          tab.setAttribute('aria-selected', String(correctionGroup === group));
          tab.style.cssText = `flex:none;padding:4px 7px;border:1px solid ${correctionGroup === group ? '#ffe100' : '#666'};border-radius:4px;color:#fff;background:#292929`;
          tab.onclick = (event) => {
            stop(event); correctionGroup = group;
            if (expectedScreen !== 'unknown' && !screenChoices(graph, registry, group).some(([id]) => id === expectedScreen)) expectedScreen = '';
            render();
          };
          tabs.append(tab);
        }
        content.append(tabs);
        const correction = document.createElement('div');
        correction.style.cssText = 'display:flex;gap:4px;margin-top:6px';
        const select = document.createElement('select');
        select.setAttribute('data-expected-screen', '');
        select.setAttribute('aria-label', api.tr('Écran réellement affiché'));
        select.style.cssText = 'min-width:0;flex:1;background:#292929;color:#fff;font:inherit';
        for (const [value, title] of [['', api.tr('Écran réellement affiché')],
          ['unknown', api.tr('Écran non identifié')], ...screenChoices(graph, registry, correctionGroup, api.tr)]) {
          const option = document.createElement('option');
          option.value = value; option.textContent = title; select.append(option);
        }
        select.value = expectedScreen; select.disabled = snapshotPending;
        const submit = document.createElement('button');
        submit.type = 'button'; submit.textContent = api.tr('Enregistrer la correction');
        submit.setAttribute('data-screen-evidence', 'submit');
        submit.disabled = snapshotPending || !expectedScreen;
        select.onchange = () => { expectedScreen = select.value; submit.disabled = snapshotPending || !expectedScreen; };
        submit.onclick = async (event) => { stop(event); if (!submit.disabled) await captureScreen(true); };
        correction.append(select); correction.append(submit); content.append(correction);
      }
      if (snapshotMessage) {
        const feedback = document.createElement('div');
        feedback.setAttribute('role', 'status'); feedback.setAttribute('data-screen-evidence-status', '');
        feedback.textContent = api.tr(snapshotMessage); content.append(feedback);
      }
    }
    if (oral && (!busy() || oral.busy)) content.append(oral.element);
    else if (!busy() && (oralPending || oralUnavailable)) {
      const notice = document.createElement('div'); notice.setAttribute('role', 'status');
      notice.textContent = api.tr(oralPending ? 'Chargement du retour vocal…' : 'Retour vocal indisponible · nouvelle tentative automatique');
      content.append(notice);
    }
    const status = document.createElement('div');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.style.cssText = 'margin-top:6px;line-height:1.5';
    const slider = ['vertical', 'horizontal'].includes(captureKind);
    const message = ['screen', 'screen_correction'].includes(captureKind) && captureState === 'saved'
      ? (captureKind === 'screen_correction' ? 'Erreur de détection enregistrée avec la capture' : 'Écran enregistré')
      : ({ idle: 'Choisis un élément à déclarer', arming: 'Capture avant…',
      armed: RECTANGLE_ANNOTATIONS.includes(captureKind) ? 'Capture avant enregistrée · Trace un rectangle autour de l’élément'
        : slider ? 'Capture avant enregistrée · Trace le slider' : 'Capture avant enregistrée · Clique sur l’élément',
      saving: 'Capture avant enregistrée · Capture après…', saved: 'Captures avant et après enregistrées · Déclaration enregistrée',
      cancelling: 'Annulation…', cancelled: 'Capture annulée · Choisis une action',
      failed: 'Échec de l’enregistrement', expired: 'Capture expirée · Choisis une action' })[captureState];
    status.textContent = api.tr(message);
    if (captureState !== 'idle' && ANNOTATIONS.some((item) => item.kind === captureKind)) status.textContent = `${api.tr(ANNOTATIONS.find((item) => item.kind === captureKind && Boolean(item.forbidden || item.kind === 'forbidden') === captureForbidden)?.label ?? '')} · ${status.textContent}`;
    content.append(status);
    if (busy()) {
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.textContent = api.tr('Annuler');
      cancel.disabled = captureState === 'arming' || captureState === 'cancelling';
      cancel.style.cssText = 'pointer-events:auto;float:right;padding:3px 7px;margin-left:6px;border:1px solid #888;border-radius:3px;background:#292929;color:#fff;font:inherit;cursor:pointer';
      cancel.onclick = async (event) => {
        stop(event);
        if (cancel.disabled) return;
        const id = captureId;
        captureState = 'cancelling'; render();
        try {
          const answer = await api.post('/trace/cancel', { id });
          captureState = answer?.ok ? 'cancelled' : 'failed';
        } catch { captureState = 'failed'; }
        captureId = null; record = null; render();
      };
      content.append(cancel);
    }
    if (record && !busy()) {
      if (record.expected_screen) {
        const correction = document.createElement('div');
        correction.setAttribute('data-screen-correction', '');
        const detected = archivedScreen(record, 'before') ?? record.before_scan?.screen ?? record.before;
        correction.textContent = api.tr('Détecté : {detected} · Attendu : {expected}', {
          detected: detected && detected !== 'unknown'
            ? graph.screens?.[detected]?.name ?? detected : api.tr('Écran non identifié'),
          expected: graph.screens?.[record.expected_screen]?.name ?? record.expected_screen,
        });
        content.append(correction);
      }
      for (const [key, label] of [['before_url', 'Capture avant'], ['after_url', 'Capture après']]) {
        if (!record[key]) continue;
        const link = document.createElement('a');
        link.href = record[key]; link.target = '_blank'; link.rel = 'noopener';
        const side = key === 'before_url' ? 'before' : 'after';
        link.setAttribute('data-capture-open', side);
        link.onclick = (event) => {
          // Modified clicks retain the browser's access to the original PNG.
          if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
          stop(event); closePreview?.();
          const identity = archivedScreen(record, side);
          const historicalScan = record[`${side}_scan`];
          const zones = identity ? visibleDebugZones(feedbackZones(identity, [...landmarksFor(identity, registry), ...zonesFor(identity, graph, registry,
            { ...historicalScan, at: Date.now() / 1000 })], userAnnotations, historicalScan), identification(), navigation()) : [];
          closePreview = capturePreview({ layer: api.layer, record, side, zones, drawZone, tr: api.tr });
        };
        link.textContent = api.tr(label);
        link.style.cssText = 'color:#ffe100;margin-right:12px';
        content.append(link);
      }
      if (record.tap) {
        const coords = document.createElement('div');
        coords.textContent = `${record.id} · ${record.tap.x.toFixed(3)}, ${record.tap.y.toFixed(3)}${record.tap.end ? ` → ${record.tap.end.x.toFixed(3)}, ${record.tap.end.y.toFixed(3)}` : ''}`;
        content.append(coords);
      }
    }
    layer.append(panel);
    floating.attach(panel, content, busy(), api.tr);
  }

  const update = async () => {
    if (!active() || !graph || !registry) { clear(); return; }
    if (refreshing || (document.hidden && Date.now() - hiddenCheck < 2000)) return;
    hiddenCheck = Date.now();
    refreshing = true;
    try {
      const [state, archive, annotations] = await Promise.all([
        getScreen(api).catch(() => null), api.get('/trace/manual').catch(() => null),
        api.get('/navigation/annotations').catch(() => null),
      ]);
      if (!active()) { clear(); return; }
      scan = state?.scan;
      screen = recognisedScreen(scan, registry);
      if (annotations?.annotations) userAnnotations = annotations.annotations;
      if (feedbackTarget && (feedbackTarget.displayScreen ?? feedbackTarget.screen) !== screen) feedbackTarget = null;
      if (['character_enhance', 'soul_weapon', 'soul_weapon_engraving', 'soul_weapon_engraving_piece', 'soul_weapon_engraving_preview'].includes(screen)
          && Date.now() - dynamicAt >= 1000) {
        dynamicAt = Date.now();
        dynamic = (await api.get('/navigation-debug?dynamic=1').catch(() => null))?.dynamic ?? null;
      }
      const clicks = archive?.clicks ?? [];
      const found = captureId ? clicks.find((click) => click.id === captureId) : captureState === 'idle' ? clicks[0] : null;
      if (found && !['arming', 'cancelling'].includes(captureState)) {
        record = found; captureId = found.id; captureKind = found.kind ?? 'navigation'; captureForbidden = found.forbidden === true || found.kind === 'forbidden';
        captureState = found.capture_status === 'cancelled' ? 'cancelled' : found.capture_status === 'armed' ? (captureState === 'saving' ? 'saving' : 'armed') : found.capture_status === 'error' ? 'failed' : found.capture_status === 'complete' || found.after_url ? 'saved' : 'saving';
      } else if (captureState === 'armed' && Date.now() / 1000 > armedUntil) captureState = 'expired';
      render();
    } finally { refreshing = false; }
  };
  api.get('/navigation-debug').then((answer) => {
    graph = answer?.graph; registry = answer?.registry;
    return api.get('/trace').catch(() => null);
  }).then((trace) => {
    const pending = trace?.armed ?? trace?.pending;
    if (pending) {
      captureId = pending.id; captureKind = pending.kind ?? 'navigation'; captureForbidden = pending.forbidden === true || pending.kind === 'forbidden';
      armedUntil = pending.until ?? 0; captureState = trace.armed ? 'armed' : 'saving';
    }
    update();
  }).catch(() => clear());
  const timer = window.setInterval(update, 250);
  window.addEventListener?.('resize', floating.clamp);
  let animation = null;
  let lastFrame = 0;
  const animate = (at) => {
    if (disposed) return;
    if (at - lastFrame >= 100 && !document.hidden) {
      lastFrame = at;
      renderZones();
    }
    animation = window.requestAnimationFrame?.(animate);
  };
  animation = window.requestAnimationFrame?.(animate);

  return {
    debug: [{ type: 'choice', key: 'screenIdentification', label: 'Identification écran',
      choices: [{ value: 'off', label: 'Désactivé' }, { value: 'on', label: 'Activé' }] },
    { type: 'choice', key: 'navigationDebug', label: 'Zones de navigation',
      choices: [{ value: 'off', label: 'Désactivé' }, { value: 'on', label: 'Activé' }] },
    { type: 'choice', key: 'navigationFeedback', label: 'Outils signalement',
      choices: [{ value: 'off', label: 'Désactivé' }, { value: 'on', label: 'Activé' }] },
    { type: 'status', label: 'Légende navigation',
      value: () => api.tr('Jaune arrondi : navigation · orange à angles droits : action · rouge hachuré arrondi : navigation interdite · rouge hachuré à angles droits : action interdite · bleu : progression · turquoise : ressource · vert : identifiant d’écran · rose : déplaçable · violet : slider, chevrons dans le sens du déplacement · pointillés : vos ajouts · tirets transparents : vos suppressions · double trait fin : bouton conditionnel') }],
    onSetting: (key) => {
      if (!['navigationDebug', 'screenIdentification', 'navigationFeedback'].includes(key)) return;
      if (key === 'navigationFeedback' && !tools()) cancelTools().catch(() => {});
      rendered = ''; render(); update();
    },
    update,
    dispose: () => { disposed = true; oral?.dispose(); clearTimeout(holdTimer); closePreview?.(); window.removeEventListener?.('resize', floating.clamp); stopTap?.(); window.clearInterval(timer); window.cancelAnimationFrame?.(animation); tracker.reset(); clear(); },
  };
}
