// Navigation map and explicit, user-initiated annotations on the live image.
// Only the recognised screen's allowed moves are drawn. The navigation
// guard still makes the decision before any actual plugin gesture.
import visualTracker from './page_navigation_tracking.js';
import { getScreen } from './page_screen_scan.js';
import capturePreview, { archivedScreen } from './page_navigation_preview.js';
const COLOURS = { tap: '#ffe100', vertical: '#168bff', horizontal: '#bb50ff' };

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

export function zonesFor(screen, graph, registry, scan = null, tracked = null) {
  const moves = graph?.screens?.[screen]?.moves ?? [];
  const tolerance = graph?.tolerance ?? 0.03;
  const safe = moves.filter((move) => eligible(move, moves, tolerance)
    && (!move.combat_return || (scan?.screen === 'battle' && scan.plain === false
      && recognisedScreen(scan) === screen)));
  const zones = safe.filter((move) => move.tap || move.hold || (move.area && move.kind !== 'swipe'))
    .map((move) => ({ id: move.id, kind: 'tap', conditional: Boolean(move.precondition), rect: move.area ?? [
      (move.tap ?? move.hold)[0] - 0.025, (move.tap ?? move.hold)[1] - 0.012,
      (move.tap ?? move.hold)[0] + 0.025, (move.tap ?? move.hold)[1] + 0.012,
    ] }));
  const scrolls = registry?.tree?.[screen]?.scroll ?? [];
  for (const move of safe.filter((item) => item.area && item.kind === 'swipe')) {
    const known = scrolls.find((item) => item.move === `${screen}/${move.id}` && item.measured);
    if (!known) continue;
    zones.push({ id: move.id, kind: known.direction === 'horizontal' ? 'horizontal' : 'vertical',
      conditional: Boolean(move.precondition),
      rect: known.rect });
  }
  for (const move of safe.filter((item) => item.swipe)) {
    const known = scrolls.find((item) => item.move === `${screen}/${move.id}` && item.measured);
    const [x1, y1, x2, y2] = move.swipe;
    const vertical = Math.abs(y2 - y1) >= Math.abs(x2 - x1);
    zones.push({ id: move.id, kind: vertical ? 'vertical' : 'horizontal',
      conditional: Boolean(move.precondition),
      rect: known?.rect ?? [Math.min(x1, x2) - 0.025, Math.min(y1, y2) - 0.015,
        Math.max(x1, x2) + 0.025, Math.max(y1, y2) + 0.015] });
  }
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
    if (zone.fixed || zone.kind !== 'tap' || !tracked?.has(zone.id)) return [zone];
    const rect = tracked.get(zone.id);
    return rect ? [{ ...zone, rect }] : [];
  });
}

export function recognisedScreen(scan) {
  if (!scan || scan.screen === 'unknown' || Date.now() / 1000 - scan.at > 10) return null;
  const overlays = (scan.overlays ?? []).filter((item) => item !== 'panel' && item !== 'better_weapon_toast');
  if (!overlays.length && scan.overlays?.includes('panel')) return null;
  return overlays.at(-1) ?? scan.screen;
}

// Detection evidence never authorises a navigation gesture.
export function landmarksFor(screen, registry) {
  return (registry?.tree?.[screen]?.landmarks ?? []).map((landmark) => ({
    ...landmark, kind: 'scannable', detection: true,
  }));
}

export const ANNOTATIONS = [
  { kind: 'navigation', label: 'Ajouter un bouton de navigation' },
  { kind: 'forbidden', label: 'Déclarer un bouton de navigation interdit' },
  { kind: 'scannable', label: 'Marquer un élément scannable' },
  { kind: 'vertical', label: 'Marquer un slider vertical' },
  { kind: 'horizontal', label: 'Marquer un slider horizontal' },
];

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
  const active = () => !disposed && enabled() && api.setting('navigationDebug') === 'on';
  const busy = () => ['arming', 'armed', 'saving', 'cancelling'].includes(captureState);
  const clear = () => { closePreview?.(); closePreview = null; layer.replaceChildren(); layer.remove(); rendered = ''; };
  const stop = (event) => { event.preventDefault(); event.stopPropagation(); };
  const floating = floatingDebugPanel(api.layer, stop);
  const finishTouch = (tap, synthetic = false) => {
    if (captureState !== 'armed') return;
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
    const colour = zone.kind === 'forbidden' ? '#ff5353' : zone.kind === 'scannable' ? '#52e99a' : COLOURS[zone.kind];
    const slider = zone.kind === 'vertical' || zone.kind === 'horizontal';
    box.style.cssText = `position:absolute;left:${left * 100}%;top:${top * 100}%;width:${(right - left) * 100}%;height:${(bottom - top) * 100}%;box-sizing:border-box;color:${colour};pointer-events:none`;
    if (slider) {
      box.style.cssText += `;border:2px ${zone.conditional ? 'dashed' : 'solid'} ${colour};background:${colour}33;border-radius:3px`;
      box.style.cssText += `;display:flex;flex-direction:${zone.kind === 'vertical' ? 'column' : 'row'};align-items:center;justify-content:space-between;font:bold 22px sans-serif;text-shadow:0 1px 3px #000`;
      for (const glyph of zone.kind === 'vertical' ? ['⌃', '⌄'] : ['❮', '❯']) {
        const chevron = document.createElement('span');
        chevron.textContent = glyph;
        if (zone.conditional) chevron.style.opacity = '0.65';
        box.append(chevron);
      }
    } else {
      box.style.cssText += `;border:2px ${zone.conditional ? 'dashed' : 'solid'} ${colour};background:${colour}33;border-radius:3px`;
    }
    box.setAttribute('data-zone-kind', zone.detection ? 'detection' : 'navigation');
    box.title = zone.detection ? `${api.tr('Repère de détection')} · ${zone.id}` : zone.conditional ? `${zone.id} · ${api.tr('condition à vérifier')}` : zone.id;
    parent.append(box);
    return box;
  }

  function renderZones() {
    if (!active() || !graph || !registry) return;
    // An unidentified bottom panel still leaves the fixed battle arrow
    // visible. With no identity zonesFor emits no panel or Battle moves.
    const zones = zonesFor(screen, graph, registry, scan);
    const tracked = tracker.update(screen, zones, registry?.tree?.[screen]?.scroll ?? []);
    zoneLayer.replaceChildren();
    for (const zone of landmarksFor(screen, registry)) drawZone(zone, zoneLayer);
    for (const zone of zonesFor(screen, graph, registry, scan, tracked)) drawZone(zone, zoneLayer);
  }

  function render() {
    if (!active() || !graph || !registry) { clear(); return; }
    floating.clamp();
    if (floating.dragging) { floating.afterDrag(render); return; }
    const signature = JSON.stringify([screen, scan?.plain, scan?.overlays, captureState, captureId, captureKind, record, snapshotPending, snapshotMessage, correctionOpen]);
    renderZones();
    if (signature === rendered && layer.isConnected) return;
    rendered = signature;
    if (!layer.isConnected) api.layer.append(layer);
    layer.replaceChildren();
    layer.append(zoneLayer);
    const name = document.createElement('div');
    const label = screen ? (graph.screens?.[screen]?.name ?? screen) : api.tr('Écran non identifié');
    name.textContent = api.tr('Écran : {screen}', { screen: label });
    name.style.cssText = 'position:absolute;left:50%;top:1%;transform:translateX(-50%);max-width:90%;padding:3px 7px;border:1px solid #ffe100;border-radius:4px;background:#000c;color:#fff;font:600 12px sans-serif;text-align:center';
    layer.append(name);

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
        if (!start || !['vertical', 'horizontal', 'scannable'].includes(captureKind)) return;
        const end = annotationPoint(event, surface.getBoundingClientRect());
        preview?.remove();
        preview = drawZone({ id: captureKind, kind: captureKind, rect: [
          Math.min(start.x, end.x), Math.min(start.y, end.y), Math.max(start.x, end.x), Math.max(start.y, end.y)] }, surface);
      };
      surface.onpointerup = (event) => {
        stop(event);
        if (!start) return;
        const end = annotationPoint(event, surface.getBoundingClientRect());
        const slider = ['vertical', 'horizontal'].includes(captureKind);
        const area = captureKind === 'scannable';
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
      button.disabled = busy() || snapshotPending;
      button.style.cssText = 'flex:1 1 130px;padding:5px;border:1px solid #888;border-radius:3px;background:#292929;color:#fff;font:inherit;cursor:pointer';
      button.onclick = async (event) => {
        stop(event);
        if (busy() || snapshotPending) return;
        snapshotMessage = '';
        captureState = 'arming'; captureKind = action.kind; captureId = null; record = null;
        render();
        try {
          const response = await api.post('/trace/arm', { kind: action.kind });
          const answer = response?.ok ? response.body : null;
          captureId = answer?.id ?? null;
          armedUntil = answer?.until ?? Date.now() / 1000 + (answer?.seconds ?? 30);
          captureState = answer?.armed ? 'armed' : 'failed';
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
          captureKind = correction ? 'screen_correction' : 'screen';
          captureState = 'saved';
          snapshotMessage = correction ? 'Erreur de détection enregistrée avec la capture' : 'Écran enregistré';
          correctionOpen = false;
        } catch { snapshotMessage = 'Échec de l’enregistrement'; }
        snapshotPending = false; render();
      };
      snapshotButton('Enregistrer cet écran', 'capture', () => captureScreen());
      snapshotButton('Mauvais écran détecté', 'correction', () => {
        correctionOpen = !correctionOpen; render();
      });
      content.append(snapshots);
      if (correctionOpen) {
        const correction = document.createElement('div');
        correction.style.cssText = 'display:flex;gap:4px;margin-top:6px';
        const select = document.createElement('select');
        select.setAttribute('data-expected-screen', '');
        select.setAttribute('aria-label', api.tr('Écran réellement affiché'));
        select.style.cssText = 'min-width:0;flex:1;background:#292929;color:#fff;font:inherit';
        const choices = { unknown: { name: api.tr('Écran non identifié') }, ...registry.tree, ...graph.screens };
        for (const [value, title] of [['', api.tr('Écran réellement affiché')],
          ...Object.entries(choices).sort((a, b) => (a[1].name ?? a[0]).localeCompare(b[1].name ?? b[0]))
            .map(([id, node]) => [id, node.name ?? id])]) {
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
    const status = document.createElement('div');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    status.style.cssText = 'margin-top:6px;line-height:1.5';
    const slider = ['vertical', 'horizontal'].includes(captureKind);
    const message = ['screen', 'screen_correction'].includes(captureKind) && captureState === 'saved'
      ? (captureKind === 'screen_correction' ? 'Erreur de détection enregistrée avec la capture' : 'Écran enregistré')
      : ({ idle: 'Choisis un élément à déclarer', arming: 'Capture avant…',
      armed: captureKind === 'scannable' ? 'Capture avant enregistrée · Trace un rectangle autour de l’élément'
        : slider ? 'Capture avant enregistrée · Trace le slider' : 'Capture avant enregistrée · Clique sur l’élément',
      saving: 'Capture avant enregistrée · Capture après…', saved: 'Captures avant et après enregistrées · Déclaration enregistrée',
      cancelling: 'Annulation…', cancelled: 'Capture annulée · Choisis une action',
      failed: 'Échec de l’enregistrement', expired: 'Capture expirée · Choisis une action' })[captureState];
    status.textContent = api.tr(message);
    if (captureState !== 'idle' && ANNOTATIONS.some((item) => item.kind === captureKind)) status.textContent = `${api.tr(ANNOTATIONS.find((item) => item.kind === captureKind)?.label ?? '')} · ${status.textContent}`;
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
          detected: graph.screens?.[detected]?.name ?? detected ?? api.tr('Écran non identifié'),
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
          const zones = identity ? [...landmarksFor(identity, registry), ...zonesFor(identity, graph, registry,
            { ...historicalScan, at: Date.now() / 1000 })] : [];
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
      const [state, archive] = await Promise.all([
        getScreen(api).catch(() => null), api.get('/trace/manual').catch(() => null),
      ]);
      if (!active()) { clear(); return; }
      scan = state?.scan;
      screen = recognisedScreen(scan);
      const clicks = archive?.clicks ?? [];
      const found = captureId ? clicks.find((click) => click.id === captureId) : captureState === 'idle' ? clicks[0] : null;
      if (found && !['arming', 'cancelling'].includes(captureState)) {
        record = found; captureId = found.id; captureKind = found.kind ?? 'navigation';
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
      captureId = pending.id; captureKind = pending.kind ?? 'navigation';
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
    debug: [{ type: 'choice', key: 'navigationDebug', label: 'Zones de navigation',
      choices: [{ value: 'off', label: 'Désactivé' }, { value: 'on', label: 'Activé' }] },
    { type: 'status', label: 'Légende navigation',
      value: () => api.tr('Vert : repère de détection · jaune : clic · chevrons bleus : vertical · chevrons violets : horizontal · pointillés : condition à vérifier') }],
    onSetting: (key) => { if (key === 'navigationDebug') update(); },
    update,
    dispose: () => { disposed = true; closePreview?.(); window.removeEventListener?.('resize', floating.clamp); stopTap?.(); window.clearInterval(timer); window.cancelAnimationFrame?.(animation); tracker.reset(); clear(); },
  };
}
