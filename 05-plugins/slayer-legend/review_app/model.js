export const COLOURS = { navigation: '#ffe100', tap: '#ffe100', action: '#ff9a23', forbidden: '#ff5353',
  detection: '#2dd4bf', scannable: '#2dd4bf', vertical: '#168bff', horizontal: '#bb50ff', draggable: '#ff65bd' };
export const inside = (point, rect) => Array.isArray(rect) && rect.length === 4
  && point.x >= rect[0] && point.y >= rect[1] && point.x <= rect[2] && point.y <= rect[3];
const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const valid = (point) => point && Number.isFinite(point.x) && Number.isFinite(point.y)
  && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1;

// Match recorded evidence only. A direction and start position are needed
// for a swipe; a neighbouring tap must never stand in for a missing drag.
export function matchGesture(edges, gesture, regions = []) {
  if (!valid(gesture.start) || gesture.end && !valid(gesture.end)) return { matches: [], forbidden: false };
  if (regions.some((region) => (region.forbidden || region.kind === 'forbidden')
      && (region.source === 'navigation_guard_envelope' || !region.user && region.source !== 'user_feedback')
      && inside(gesture.start, region.rect))) {
    return { matches: [], forbidden: true };
  }
  const isDrag = gesture.end && distance(gesture.start, gesture.end) >= .035;
  const matches = [];
  for (const edge of edges) {
    if (!valid(edge.start) || ['forbidden', 'action'].includes(edge.annotationKind)) continue;
    const edgeDrag = ['swipe', 'drag', 'draggable', 'vertical', 'horizontal'].includes(edge.kind);
    if (Boolean(isDrag) !== edgeDrag) continue;
    let score = distance(gesture.start, edge.start);
    if (isDrag) {
      if (!valid(edge.end) || score > .22) continue;
      const a = { x: gesture.end.x - gesture.start.x, y: gesture.end.y - gesture.start.y };
      const b = { x: edge.end.x - edge.start.x, y: edge.end.y - edge.start.y };
      const norm = Math.hypot(a.x, a.y) * Math.hypot(b.x, b.y);
      if (!norm) continue;
      const cosine = (a.x * b.x + a.y * b.y) / norm;
      if (cosine < .75) continue;
      score += (1 - cosine) * .12 + Math.min(distance(gesture.end, edge.end), .5) * .12;
    } else {
      if (score > .06) continue;
      if (edge.kind === 'long' && gesture.duration < 500) continue;
    }
    matches.push({ edge, score });
  }
  matches.sort((a, b) => a.score - b.score);
  const best = matches[0]?.score ?? 0;
  const destinations = new Set();
  return { forbidden: false, matches: matches.filter(({ edge, score }) => {
    if (score > best + .025 || destinations.has(edge.to)) return false;
    destinations.add(edge.to);
    return true;
  }).map(({ edge }) => edge) };
}

export function gestureLabel(edge) {
  if (edge.annotationKind === 'draggable' || edge.kind === 'drag') return 'Glisser-déposer';
  if (edge.kind === 'swipe' && edge.end) {
    const x = edge.end.x - edge.start.x, y = edge.end.y - edge.start.y;
    return Math.abs(y) >= Math.abs(x) ? `Slide ${y < 0 ? 'vers le haut' : 'vers le bas'}`
      : `Slide ${x < 0 ? 'vers la gauche' : 'vers la droite'}`;
  }
  return edge.kind === 'long' ? 'Appui long' : 'Clic';
}

export function screenLabel(node) {
  if (node.screen === 'battle') return node.scan?.plain === true || (node.battleViewport?.size === 'big' && node.battleViewport?.calibrated) ? 'Combat Interface' : 'Vue avec combat';
  const label = node.label && node.label !== node.screen ? node.label : node.screen;
  if (!label || ['other', 'unknown'].includes(label)) return 'Écran à identifier';
  return label.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export function battlefieldLabel(node) {
  const field = node.battlefield ?? node.battle_viewport ?? node.battleViewport;
  if (!field) return null;
  const size = typeof field === 'string' ? field : field.size;
  return ({ mini: 'Mini', compact: 'Compact', small: 'Petit', medium: 'Moyen', big: 'Grand', large: 'Grand', none: 'Absent', unknown: 'Indéterminé' })[size] ?? size;
}
