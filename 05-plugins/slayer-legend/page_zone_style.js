// Shared visual semantics for live debug and the passive navigation review.
// These styles describe feedback; they never change gesture permissions.
export const ZONE_COLOURS = {
  tap: '#ffe100', navigation: '#ffe100', action: '#ff9a23', forbidden: '#ff5353',
  progression_value: '#409cff', resource_value: '#2dd4bf',
  detection: '#4ade80', scannable: '#4ade80', screen_identifier: '#4ade80',
  vertical: '#bb50ff', horizontal: '#bb50ff', draggable: '#ff65bd',
};
export function zoneStyle(zone) {
  const removal = zone.proposal === 'remove' || zone.removedProposal === true;
  const user = zone.user === true || zone.source === 'user_feedback';
  const conditionalButton = Boolean(zone.conditional)
    && ['tap', 'navigation', 'action'].includes(zone.kind ?? 'tap');
  return {
    hatch: !removal && Boolean(zone.forbidden) && (zone.kind === 'action' || zone.semantic_kind === 'action'),
    dash: removal ? '10 7' : user ? '1 5' : 'none',
    opacity: removal ? .28 : 1,
    linecap: user && !removal ? 'round' : 'butt',
    double: conditionalButton && !user && !removal,
    width: conditionalButton && !user && !removal ? 1 : 2,
  };
}

// SVG remains present in both the live overlay and frozen oral-feedback evidence.
let hatchSerial = 0;
export function addZoneHatching(box, colour) {
  const ns = 'http://www.w3.org/2000/svg';
  const element = (name, attributes) => {
    const node = document.createElementNS(ns, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    return node;
  };
  const id = `forbidden-action-hatch-${++hatchSerial}`;
  const svg = element('svg', { 'data-zone-hatch': 'action' });
  svg.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
  const defs = element('defs', {});
  const pattern = element('pattern', { id, patternUnits: 'userSpaceOnUse', width: 8, height: 8 });
  pattern.append(element('path', { d: 'M-2 2 L2 -2 M0 8 L8 0 M6 10 L10 6', stroke: colour, 'stroke-width': 2, opacity: .45 }));
  defs.append(pattern); svg.append(defs);
  svg.append(element('rect', { width: '100%', height: '100%', fill: `url(#${id})` }));
  box.append(svg);
}
