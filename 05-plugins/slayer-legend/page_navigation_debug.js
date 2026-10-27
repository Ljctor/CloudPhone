// Optional, read-only map of navigation points on the live game image.
// Only the recognised screen's allowed moves are drawn. The navigation
// guard still makes the decision before any actual plugin gesture.
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

export function zonesFor(screen, graph, registry) {
  const moves = graph?.screens?.[screen]?.moves ?? [];
  const tolerance = graph?.tolerance ?? 0.03;
  const safe = moves.filter((move) => eligible(move, moves, tolerance));
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
  return zones;
}

export function recognisedScreen(scan) {
  if (!scan || scan.screen === 'unknown' || Date.now() / 1000 - scan.at > 10) return null;
  const overlays = (scan.overlays ?? []).filter((item) => item !== 'panel' && item !== 'better_weapon_toast');
  if (!overlays.length && scan.overlays?.includes('panel')) return null;
  return overlays.at(-1) ?? scan.screen;
}

export default function navigationDebug(api, { enabled = () => true } = {}) {
  const layer = document.createElement('div');
  layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;z-index:30';
  let graph = null;
  let registry = null;
  let last = '';
  let disposed = false;
  let captureState = 'idle';
  let captureId = null;
  const stopTap = api.onTap?.((tap) => {
    if (captureState !== 'armed') return;
    if (api.setting('traceTaps') === 'off') api.post('/trace', tap).catch(() => null);
    captureState = 'saving';
    last = '';
    update();
    window.setTimeout(async () => {
      const archive = await api.get('/trace/manual').catch(() => null);
      captureState = archive?.clicks?.some((click) => click.id === captureId) ? 'saved' : 'failed';
      last = '';
      update();
      if (captureState === 'saved') window.setTimeout(() => {
        captureState = 'idle'; last = ''; update();
      }, 2500);
    }, 3000);
  });
  const clear = () => { layer.replaceChildren(); layer.remove(); last = ''; };
  const active = () => !disposed && enabled() && api.setting('navigationDebug') === 'on';

  const paint = (zones, screen) => {
    if (!layer.isConnected) api.layer.append(layer);
    layer.replaceChildren();
    const name = document.createElement('div');
    const label = screen ? (graph.screens?.[screen]?.name ?? screen) : api.tr('Écran non identifié');
    name.textContent = api.tr('Écran : {screen}', { screen: label });
    name.style.cssText = 'position:absolute;left:50%;top:1%;transform:translateX(-50%);max-width:90%;padding:3px 7px;border:1px solid #ffe100;border-radius:4px;background:#000c;color:#fff;font:600 12px sans-serif;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
    layer.append(name);
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = api.tr(({ idle: 'Enregistrer un clic', arming: 'Capture avant…',
      armed: 'Clique dans le jeu', saving: 'Capture après…', saved: 'Clic enregistré',
      failed: 'Réessayer le clic' })[captureState]);
    button.disabled = captureState === 'arming' || captureState === 'saving' || captureState === 'saved';
    button.style.cssText = 'position:absolute;left:50%;bottom:7%;transform:translateX(-50%);pointer-events:auto;z-index:1;padding:7px 10px;border:2px solid #ffe100;border-radius:5px;background:#171717;color:#fff;font:600 12px sans-serif;white-space:nowrap;cursor:pointer';
    button.onpointerdown = (event) => event.stopPropagation();
    button.onpointerup = (event) => event.stopPropagation();
    button.onclick = async (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (captureState !== 'idle' && captureState !== 'failed') return;
      captureState = 'arming';
      button.textContent = api.tr('Capture avant…');
      button.disabled = true;
      try {
        const answer = await api.post('/trace/arm', {});
        captureId = answer?.id ?? null;
        captureState = answer?.armed ? 'armed' : 'failed';
      } catch { captureState = 'failed'; }
      last = '';
      update();
    };
    layer.append(button);
    for (const zone of zones) {
      const [left, top, right, bottom] = zone.rect.map((part) => Math.max(0, Math.min(1, part)));
      const box = document.createElement('div');
      const colour = COLOURS[zone.kind];
      box.style.cssText = `position:absolute;left:${left * 100}%;top:${top * 100}%;width:${(right - left) * 100}%;height:${(bottom - top) * 100}%;border:2px ${zone.conditional ? 'dashed' : 'solid'} ${colour};background:${colour}33;box-sizing:border-box;border-radius:3px`;
      box.title = zone.conditional ? `${zone.id} · ${api.tr('condition à vérifier')}` : zone.id;
      layer.append(box);
    }
  };

  const update = async () => {
    if (!active() || !graph || !registry) { clear(); return; }
    const state = await api.get('/game').catch(() => null);
    if (!active()) { clear(); return; }
    const screen = recognisedScreen(state?.scan);
    const key = `${screen}:${state?.scan?.at ?? ''}`;
    if (key === last) return;
    last = key;
    paint(screen ? zonesFor(screen, graph, registry) : [], screen);
  };
  api.get('/navigation-debug').then((answer) => {
    graph = answer?.graph;
    registry = answer?.registry;
    update();
  }).catch(() => clear());
  const timer = window.setInterval(update, 2000);

  return {
    debug: [{ type: 'choice', key: 'navigationDebug', label: 'Zones de navigation',
      choices: [{ value: 'off', label: 'Désactivé' }, { value: 'on', label: 'Activé' }] },
    { type: 'status', label: 'Légende navigation',
      value: () => api.tr('Jaune : clic · bleu : vertical · violet : horizontal · pointillés : condition à vérifier') }],
    onSetting: (key) => { if (key === 'navigationDebug') update(); },
    update,
    dispose: () => { disposed = true; stopTap?.(); window.clearInterval(timer); clear(); },
  };
}
